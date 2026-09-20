#!/usr/bin/env python3
"""Score the reference solution on batch B (verifier-only). Run from the repo root."""
import csv, subprocess, sys
from collections import defaultdict
from pathlib import Path
task = Path(__file__).resolve().parents[1] / "tasks" / __import__("os").environ.get("TASK", "sanctions-name-screening")
out = "/tmp/score-b.csv"
subprocess.run([sys.executable, str(task / "solution" / "screen.py"), "--watchlist", str(task / "environment/data/watchlist.json"),
                "--customers", str(task / "tests/data/customers_b.csv"), "--out", out], check=True, capture_output=True)
lab = {r["customer_id"]: r for r in csv.DictReader(open(task / "tests/data/labels_b.csv"))}
dec = {r["customer_id"]: r for r in csv.DictReader(open(out))}
tp = fp = fn = ok = 0; per = defaultdict(lambda: [0, 0, 0])
for cid, l in lab.items():
    d = dec[cid]; k = l["class"]; per[k][0] += 1
    if l["expected_decision"] == "MATCH":
        if d["decision"] == "MATCH": tp += 1; ok += d["matched_uid"] == l["expected_uid"]; per[k][1] += 1
        else: fn += 1
    elif d["decision"] == "MATCH": fp += 1; per[k][2] += 1
bad = []
for k, (n, h, f) in sorted(per.items()):
    if k.startswith("T") and h / n < 0.9: bad.append(f"{k}={h/n:.3f}")
    if not k.startswith("T") and f / n > (0.01 if k.startswith("R") else 0.05): bad.append(f"{k} fpr={f/n:.3f}")
print(f"BATCH-B recall={tp/(tp+fn):.4f} precision={tp/(tp+fp):.4f} uid={ok/max(tp,1):.4f} (fn={fn} fp={fp}) | below bar: {', '.join(bad) or 'none'}")
