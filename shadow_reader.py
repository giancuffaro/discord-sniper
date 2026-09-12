"""Bounded, read-only live AI observer for typed Discord/Whop posts.

HTTP handlers enqueue quickly; one daemon worker calls the model and writes a
local JSONL tape. No result is returned to the extension's order path.
"""
import json
import os
import queue
import threading
import time
from collections import deque
from datetime import datetime

import ai_reader
import context_reader

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "local-reader-measure")
_lock = threading.Lock()
_recent = {}
_seen = {}
_jobs = queue.Queue(maxsize=256)
_worker_started = False


def _write(row):
    os.makedirs(OUT, exist_ok=True)
    day = datetime.now().strftime("%Y-%m-%d")
    with _lock:
        with open(os.path.join(OUT, "live-%s.jsonl" % day), "a",
                  encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _worker():
    while True:
        current, prior, parser, cfg = _jobs.get()
        try:
            allowed = cfg.get("allowed_symbols", []) or []
            raw, latency = context_reader.read(current, prior, allowed, cfg)
            grade = context_reader.assess(current, prior, raw, allowed)
            _write({"kind": "read", "current": current, "prior": prior,
                    "parser": parser, "ai_raw": raw, "ai": grade,
                    "model_ms": latency, "finishedAt": int(time.time() * 1000),
                    "queue_wait_ms": int(time.time() * 1000)
                    - current["enqueuedAt"] - latency,
                    "queue_remaining": _jobs.qsize()})
        except Exception as exc:
            _write({"kind": "error", "current": current,
                    "error": str(exc)[:160]})
        finally:
            _jobs.task_done()


def enqueue(body, cfg):
    """Remember a line and queue one fresh read; never block on the model."""
    global _worker_started
    if not isinstance(body, dict):
        return {"ok": False, "why": "bad_body"}
    room = str(body.get("channelId") or "")[:160]
    text = str(body.get("text") or "").strip()[:2000]
    if not room or not text:
        return {"ok": False, "why": "no_room_or_text"}
    now = int(time.time() * 1000)
    try:
        posted = int(body.get("postedAt") or now)
    except (TypeError, ValueError):
        posted = now
    if posted < now - context_reader.CONTEXT_MS or posted > now + 60000:
        return {"ok": True, "status": "old_or_future"}
    current = {"id": str(body.get("id") or "")[:160], "channelId": room,
               "author": str(body.get("author") or "?")[:100],
               "postedAt": posted, "text": text,
               "reply": bool(body.get("reply")),
               "history": bool(body.get("history")),
               "platform": str(body.get("platform") or "discord")[:20]}
    try:
        current["observerCpuMs"] = max(0.0, min(10000.0,
            float(body.get("observerCpuMs") or 0)))
    except (TypeError, ValueError):
        current["observerCpuMs"] = 0.0
    current["enqueuedAt"] = now
    key = (room, current["id"] or (current["author"], posted, text))
    with _lock:
        signature = (text, current["history"])
        if key in _seen and _seen[key] == signature:
            return {"ok": True, "status": "duplicate"}
        _seen[key] = signature
        if len(_seen) > 6000:
            _seen.clear()
            _seen[key] = signature
        ring = _recent.setdefault(room, deque(maxlen=context_reader.MAX_CONTEXT + 1))
        prior = [dict(p) for p in ring if p["postedAt"] <= posted
                 and posted - p["postedAt"] <= context_reader.CONTEXT_MS]
        if current["id"]:
            prior = [p for p in prior if p["id"] != current["id"]]
        prior = prior[-context_reader.MAX_CONTEXT:]
        if current["id"]:
            for prior_row in list(ring):
                if prior_row["id"] == current["id"]:
                    ring.remove(prior_row)
        ring.append(current)
        if len(_recent) > 200:
            oldest = next(iter(_recent))
            if oldest != room:
                del _recent[oldest]
    if current["history"]:
        return {"ok": True, "status": "context_only"}
    if not ai_reader.available(cfg):
        return {"ok": True, "status": "ai_off"}
    parser = body.get("parser") if isinstance(body.get("parser"), dict) else {}
    try:
        _jobs.put_nowait((current, prior, parser, cfg))
    except queue.Full:
        _write({"kind": "dropped", "current": current,
                "why": "shadow_queue_full", "queue_remaining": _jobs.qsize()})
        return {"ok": True, "status": "queue_full"}
    with _lock:
        if not _worker_started:
            threading.Thread(target=_worker, name="ai-shadow-reader",
                             daemon=True).start()
            _worker_started = True
    return {"ok": True, "status": "queued", "queue_remaining": _jobs.qsize()}
