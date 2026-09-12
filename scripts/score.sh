#!/usr/bin/env bash
# Score the reference solution on the hidden batch and the dev split, plus the unit tests.
# Usage: scripts/score.sh [label]   (run from the repo root; prints one summary line per split)
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
task=$root/tasks/sanctions-name-screening
py=${PYTHON:-python3}
pytest=${PYTEST:-"$HOME/triage-mesh/.venv/bin/python -m pytest"}
label=${1:-}
units=$($pytest -q -p no:cacheprovider "$root/scripts/tests" 2>&1 | tail -1)
cd "$task"
$py solution/screen.py --watchlist environment/data/watchlist.json --customers environment/data/customers.csv --out /tmp/score-hidden.csv >/dev/null
out=$(DECISIONS_PATH=/tmp/score-hidden.csv $pytest -q -p no:cacheprovider tests/test_decisions.py -rA 2>&1 || true)
rec=$(echo "$out" | grep -oE "^recall=[0-9.]+" | head -1); prec=$(echo "$out" | grep -oE "^precision=[0-9.]+" | head -1)
uid=$(echo "$out" | grep -oE "^uid_accuracy=[0-9.]+" | head -1)
below=$(echo "$out" | grep -oE "below 0.9: .*" | head -1 | cut -c12-); exceeded=$(echo "$out" | grep -oE "exceeded: .*" | head -1 | cut -c11-)
passed=$(echo "$out" | grep -oE "[0-9]+ passed|[0-9]+ failed" | tr '\n' ' ')
echo "HIDDEN [$label] $rec $prec $uid | class-recall-below: ${below:-none} | fpr-exceeded: ${exceeded:-none} | $passed| units: $units"
$py solution/screen.py --watchlist environment/data/watchlist.json --customers environment/data/dev/customers_dev.csv --out /tmp/score-dev.csv >/dev/null
$py - <<'EOF'
import csv
lab = {r["customer_id"]: r for r in csv.DictReader(open("environment/data/dev/labels_dev.csv"))}
dec = {r["customer_id"]: r for r in csv.DictReader(open("/tmp/score-dev.csv"))}
tp = fp = fn = ok = 0
for cid, l in lab.items():
    d = dec[cid]
    if l["expected_decision"] == "MATCH":
        if d["decision"] == "MATCH":
            tp += 1; ok += d["matched_uid"] == l["expected_uid"]
        else:
            fn += 1
    elif d["decision"] == "MATCH":
        fp += 1
print(f"DEV    recall={tp/(tp+fn):.4f} precision={tp/(tp+fp):.4f} uid={ok/max(tp,1):.4f} (fn={fn} fp={fp})")
EOF
