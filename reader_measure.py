"""Replay production parser and contextual AI over retained live room posts.

Read-only: writes local measurement files, never calls the order endpoint.
Run `python reader_measure.py --prepare`, then `--ai-all`, then `--report`.
The AI pass resumes from its JSONL output after interruption.
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import re
import subprocess
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

import context_reader

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "local-reader-measure")
PREPARED = os.path.join(OUT, "corpus.jsonl")
AI_OUT = os.path.join(OUT, "ai-context.jsonl")
QUEUE = os.path.join(OUT, "disagreements.csv")
SUMMARY = os.path.join(OUT, "summary.json")
LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(.+?)#(\d+)\]\s+([\s\S]*)$")
HEADER = re.compile(
    r"^(?:.*?)?(?:\[\s*)?\d{1,2}:\d{2}\s*[AP]M(?:\s*\])?\s+"
    r"[A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}\s+at\s+"
    r"\d{1,2}:\d{2}\s*[AP]M\s+", re.I)


def jsonl(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def corpus():
    """Match parser_gate.js's retained, non-history corpus and dedup key."""
    seen = set()
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, "DS Logs",
                                              "signal-room-chat*.txt"))):
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                m = LINE.match(line.rstrip("\n"))
                if not m or m[4].startswith("<history> "):
                    continue
                text = m[4]
                colon = text.find(": ")
                author = text[:colon].strip() if 0 <= colon < 60 else "?"
                if 0 <= colon < 60:
                    text = text[colon + 2:]
                text = HEADER.sub("", text)
                # JS slice(0, 120) counts UTF-16 code units, including emoji.
                # Python's [:120] counts code points and admitted one duplicate.
                key = (m[1], m[3], text.encode("utf-16-le")[:240])
                if key in seen:
                    continue
                seen.add(key)
                dt = datetime.strptime(m[1], "%Y-%m-%d %H:%M:%S")
                posted = int(dt.replace(tzinfo=ZoneInfo("America/New_York"))
                             .timestamp() * 1000)
                identity = (m[1] + "|" + m[3] + "|").encode("utf-8") + key[2]
                rows.append({"id": hashlib.sha256(identity)
                             .hexdigest()[:20], "at": m[1], "postedAt": posted,
                             "room": m[2].strip(), "channelId": m[3],
                             "author": author, "text": text})
    rows.sort(key=lambda r: (r["postedAt"], r["channelId"], r["id"]))
    return rows


def prepare():
    os.makedirs(OUT, exist_ok=True)
    rows = corpus()
    recent = defaultdict(lambda: deque(maxlen=context_reader.MAX_CONTEXT))
    for r in rows:
        prior = [dict(p) for p in recent[r["channelId"]]
                 if 0 <= r["postedAt"] - p["postedAt"] <= context_reader.CONTEXT_MS]
        r["prior"] = prior[-context_reader.MAX_CONTEXT:]
        recent[r["channelId"]].append({k: r[k] for k in
                                       ("id", "author", "postedAt", "text")})
    for start in range(0, len(rows), 500):
        batch = rows[start:start + 500]
        proc = subprocess.run(["node", os.path.join(HERE, "reader_parse.js")],
                              input=json.dumps([{"text": r["text"],
                                                 "channelId": r["channelId"]}
                                                for r in batch]).encode("utf-8"),
                              capture_output=True, timeout=120, check=True)
        signals = json.loads(proc.stdout)
        for r, sig in zip(batch, signals):
            r["parser"] = sig
    with open(PREPARED, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    actions = sum(bool((r["parser"] or {}).get("action")) for r in rows)
    print(json.dumps({"prepared": len(rows), "rooms": len(recent),
                      "parser_actions": actions, "file": PREPARED}))


def _one(r, cfg, allowed):
    for attempt in range(3):
        raw, ms = context_reader.read(r, r["prior"], allowed, cfg)
        if raw.get("_error") not in ("HTTP_429", "HTTP_500", "HTTP_503"):
            break
        time.sleep(2 ** (attempt + 1))
    grade = context_reader.assess(r, r["prior"], raw, allowed)
    return {"id": r["id"], "ai_raw": raw, "ai": grade,
            "model_ms": ms, "finishedAt": datetime.now().isoformat()}


def ai_all(limit=None, workers=2):
    if not os.path.exists(PREPARED):
        prepare()
    with open(os.path.join(HERE, "settings.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    if not context_reader.ai_reader.available(cfg):
        raise RuntimeError("AI key unavailable; no replay calls made")
    allowed = cfg.get("allowed_symbols", []) or []
    done = {r["id"] for r in jsonl(AI_OUT)}
    todo = [r for r in jsonl(PREPARED) if r["id"] not in done]
    if limit is not None:
        todo = todo[:limit]
    print(json.dumps({"total": sum(1 for _ in jsonl(PREPARED)),
                      "already_done": len(done), "this_run": len(todo),
                      "workers": workers}), flush=True)
    if not todo:
        return
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_one, r, cfg, allowed) for r in todo]
        with open(AI_OUT, "a", encoding="utf-8") as f:
            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()
                if i % 50 == 0 or i == len(todo):
                    print(json.dumps({"completed_this_run": i,
                                      "remaining": len(todo) - i}), flush=True)


def report():
    base = {r["id"]: r for r in jsonl(PREPARED)}
    ai = {r["id"]: r for r in jsonl(AI_OUT)}
    counts = defaultdict(int)
    latencies = []
    review = []
    for key, r in base.items():
        p = r.get("parser") or {}
        a = ai.get(key)
        if not a:
            counts["not_run"] += 1
            continue
        if (a.get("ai_raw") or {}).get("_error"):
            counts["ai_error"] += 1
            continue
        latencies.append(a.get("model_ms") or 0)
        ag = a.get("ai") or {}
        ar = ag.get("read") or {}
        pa, aa = p.get("action") or "NONE", ar.get("action") or "NONE"
        if pa == "NONE" and aa != "NONE":
            category = "potential_missed_alert"
        elif pa != "NONE" and aa == "NONE":
            category = "potential_false_alert"
        elif pa != "NONE" and aa != "NONE" and (
                str(p.get("symbol") or "").upper(), str(p.get("strike") or ""),
                str(p.get("side") or "").upper(), str(p.get("expiry") or "")) != (
                str(ar.get("ticker") or "").upper(), str(ar.get("strike") or ""),
                str(ar.get("side") or "").upper(), str(ar.get("expiry") or "")):
            category = "potential_wrong_contract"
        elif pa != aa:
            category = "potential_wrong_action"
        else:
            category = "agreement"
        counts[category] += 1
        if category != "agreement":
            review.append({"id": key, "category": category, "manual_label": "",
                           "room": r["room"], "at": r["at"],
                           "author": r["author"], "text": r["text"],
                           "context": json.dumps(r["prior"], ensure_ascii=False),
                           "parser": json.dumps(p, ensure_ascii=False),
                           "ai": json.dumps(ar, ensure_ascii=False)})
    os.makedirs(OUT, exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "category", "manual_label",
                                               "room", "at", "author", "text",
                                               "context", "parser", "ai"])
        writer.writeheader()
        writer.writerows(review)
    latencies.sort()
    summary = {"corpus": len(base), "ai_processed": len(ai),
               "counts": dict(counts), "review_rows": len(review),
               "model_latency_ms_p50": latencies[len(latencies)//2] if latencies else None,
               "model_latency_ms_p95": latencies[int(len(latencies)*.95)] if latencies else None,
               "note": "Disagreements are candidates, not labeled errors or trades."}
    with open(SUMMARY, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prepare", action="store_true")
    ap.add_argument("--ai-all", action="store_true")
    ap.add_argument("--ai-limit", type=int)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    if args.prepare or not (args.ai_all or args.ai_limit is not None or args.report):
        prepare()
    if args.ai_all or args.ai_limit is not None:
        ai_all(args.ai_limit, max(1, min(4, args.workers)))
    if args.report:
        report()
