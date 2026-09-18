#!/usr/bin/env bash
# Score the reference solution on the hidden batch and the dev split, plus the unit tests.
# Usage: scripts/score.sh [label]   (run from the repo root; prints one summary line per split)
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
task=$root/tasks/${TASK:-archive-record-linkage}
py=${PYTHON:-python3}
pytest=${PYTEST:-"$HOME/triage-mesh/.venv/bin/python -m pytest"}
label=${1:-}
units=$($pytest -q -p no:cacheprovider "$root/scripts/tests" 2>&1 | tail -1)
cd "$task"
$py solution/link.py --register environment/data/register.json --records environment/data/records.csv --out /tmp/score-hidden.csv >/dev/null
# the verifier deletes label files at import: run it from a scratch copy of tests/
scratch=$(mktemp -d); cp -r tests "$scratch/tests"
out=$(cd "$scratch/tests" && DECISIONS_PATH=/tmp/score-hidden.csv ENGINE_PATH="$task/solution/link.py" PYTHONDONTWRITEBYTECODE=1 $pytest -q -p no:cacheprovider test_decisions.py -rA 2>&1 || true)
rm -rf "$scratch"
rec=$(echo "$out" | grep -oE "^\[[AB]\] recall=[0-9.]+" | tr '\n' ' '); prec=$(echo "$out" | grep -oE "^\[[AB]\] precision=[0-9.]+" | tr '\n' ' ')
uid=$(echo "$out" | grep -oE "^\[[AB]\] uid_accuracy=[0-9.]+" | tr '\n' ' ')
below=$(echo "$out" | grep -oE "^E .*below 0.9: .*" | head -1 | sed "s/.*below 0.9: //"); exceeded=$(echo "$out" | grep -oE "^E .*exceeded: .*" | head -1 | sed "s/.*exceeded: //")
passed=$(echo "$out" | grep -oE "[0-9]+ passed|[0-9]+ failed" | tr '\n' ' ')
echo "HIDDEN [$label] $rec $prec $uid | class-recall-below: ${below:-none} | fpr-exceeded: ${exceeded:-none} | $passed| units: $units"
$py solution/link.py --register environment/data/register.json --records environment/data/dev/records_dev.csv --out /tmp/score-dev.csv >/dev/null
$py - <<'EOF'
import csv
lab = {r["record_id"]: r for r in csv.DictReader(open("environment/data/dev/labels_dev.csv"))}
dec = {r["record_id"]: r for r in csv.DictReader(open("/tmp/score-dev.csv"))}
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
