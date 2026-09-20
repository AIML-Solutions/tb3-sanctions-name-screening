#!/usr/bin/env bash
# Reproduce every non-agent gate from a fresh clone: data determinism, static checks,
# local scoring of the reference solution, unit tests, and (with Docker) oracle + nop.
#
#   scripts/reproduce.sh            # checks + local scoring
#   scripts/reproduce.sh --docker   # also harbor oracle/nop in Docker (needs uv + Docker)
set -eu
root=$(cd "$(dirname "$0")/.." && pwd)
task=tasks/${TASK:-sanctions-name-screening}
cd "$root"

echo "== 1. data determinism (generator rebuilds every data file byte for byte)"
tmp=$(mktemp -d); cp -r "$task/environment/data" "$tmp/data"; cp "$task/tests/data/labels.csv" "$tmp/labels.csv"
PYTHONDONTWRITEBYTECODE=1 python3 "$task/tests/generate_data.py" >/dev/null
diff -rq "$tmp/data" "$task/environment/data" && cmp "$tmp/labels.csv" "$task/tests/data/labels.csv" && echo "   identical"
rm -rf "$tmp"

echo "== 2. TB3 static checks"
fails=0
for f in scripts/checks/*.sh; do bash "$f" "$task" >/dev/null 2>&1 || { fails=$((fails+1)); echo "   FAIL $f"; }; done
echo "   failures: $fails"; [ "$fails" -eq 0 ]

echo "== 3. reference solution on hidden batch and dev sample; policy unit tests"
if [ -z "${PYTEST:-}" ]; then python3 -c "import pytest" 2>/dev/null && PYTEST="python3 -m pytest" || PYTEST="uvx pytest"; fi
PYTHONDONTWRITEBYTECODE=1 PYTEST="$PYTEST" scripts/score.sh reproduce

if [ "${1:-}" = "--docker" ]; then
  echo "== 4. harbor oracle (expect 1.0) and nop (expect 0.0) in Docker"
  out=$(mktemp -d)
  uvx harbor run -p "$task" --agent oracle --env docker -o "$out" 2>&1 | grep -E "Mean:" || true
  uvx harbor run -p "$task" --agent nop --env docker -o "$out" 2>&1 | grep -E "Mean:" || true
  python3 scripts/summarize_runs.py "$out"
fi
find "$task" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
echo "== done"
