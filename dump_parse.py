"""Dump how Python reads samples.txt, for test_parity.js to compare against."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import signals as sigmod

with open(os.path.join(HERE, "settings.example.json"), encoding="utf-8") as f:
    cfg = json.load(f)
with open(os.path.join(HERE, "samples.txt"), encoding="utf-8") as f:
    lines = [l.rstrip("\n") for l in f if l.strip() and not l.startswith("#")]

print(json.dumps([sigmod.parse(l, cfg=cfg).dict() for l in lines]))
