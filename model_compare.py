"""Head-to-head shadow model check on manually labeled replay disagreements.

Uses the existing Anthropic key. Never reads or writes trading settings, and
never calls the order endpoint. Results stay in ignored local-reader-measure/.
"""
import csv
import json
import os
import statistics
import subprocess

import ai_reader
import context_reader
import reader_measure

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = reader_measure.OUT
LABELS = os.path.join(OUT, "pilot-v1-disagreements.csv")
RESULT = os.path.join(OUT, "model-compare-pilot.json")
EXPECTED = {
    "parser_correct_ai_miss": "CLOSE",
    "parser_false_alert": "NONE",
    "ai_false_alert": "NONE",
    "ai_wrong_expiry_year": "OPEN",
    "historical_caller_exit": "NONE",
    "ai_partial_contract": "CLOSE",
    "parser_missed_caller_trim": "TRIM",
    "parser_missed_entry": "OPEN",
    "same_contract_date_format": "OPEN",
}


def run(models):
    rows = {r["id"]: r for r in reader_measure.jsonl(reader_measure.PREPARED)}
    with open(LABELS, encoding="utf-8", newline="") as f:
        labels = [r for r in csv.DictReader(f)
                  if r.get("manual_label") in EXPECTED]
    with open(os.path.join(HERE, "settings.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    allowed = cfg.get("allowed_symbols", []) or []
    results = []
    for model in models:
        model_cfg = json.loads(json.dumps(cfg))
        model_cfg.setdefault("execution", {}).setdefault("ai_reader", {})["shadow_model"] = model
        for item in labels:
            current = rows[item["id"]]
            raw, ms = context_reader.read(current, current["prior"],
                                          allowed, model_cfg)
            grade = context_reader.assess(current, current["prior"], raw, allowed)
            results.append({"model": model, "id": item["id"],
                            "expected": EXPECTED[item["manual_label"]],
                            "label": item["manual_label"], "raw": raw,
                            "grade": grade, "model_ms": ms,
                            "channelId": current["channelId"]})
            print(model, len([r for r in results if r["model"] == model]),
                  "/", len(labels), flush=True)
    payload = [{"text": ai_reader.canonical(r["grade"].get("read")),
                "channelId": r["channelId"]} for r in results]
    proc = subprocess.run(["node", os.path.join(HERE, "reader_parse.js")],
                          input=json.dumps(payload).encode("utf-8"),
                          capture_output=True, timeout=120, check=True)
    for result, parsed in zip(results, json.loads(proc.stdout)):
        result["parsed"] = parsed
        result["action_correct"] = ((parsed.get("action") or "NONE")
                                    == result["expected"])
    summary = {}
    for model in models:
        subset = [r for r in results if r["model"] == model]
        lat = sorted(r["model_ms"] for r in subset)
        summary[model] = {
            "labeled_cases": len(subset),
            "correct_actions": sum(r["action_correct"] for r in subset),
            "false_entry_actions": sum(r["expected"] == "NONE" and
                                       (r["parsed"].get("action") == "OPEN")
                                       for r in subset),
            "flagged_field_risks": sum(bool(r["grade"]["safety_flags"])
                                       for r in subset),
            "p50_model_ms": statistics.median(lat) if lat else None,
            "p95_model_ms": lat[int(len(lat) * .95)] if lat else None,
        }
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "rows": results}, f,
                  ensure_ascii=False, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run(["claude-haiku-4-5-20251001", "claude-sonnet-5"])
