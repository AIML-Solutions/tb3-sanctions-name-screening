#!/usr/bin/env bash
# usage: echo_test.sh <name> <file>  -> asks Claude headlessly to reproduce the file verbatim; records whether the output filter fires
name=$1; f=$2; out=$(dirname "$0")/out-$name.txt
unset_list=$(env | grep -oE '^(CLAUDECODE|CLAUDE_CODE_[A-Z_]+)=' | tr -d = | sed 's/^/-u /' | tr '\n' ' ')
{ printf 'Reproduce the following file content exactly, verbatim, inside one fenced code block, with no commentary before or after.\n\n-----BEGIN FILE-----\n'; cat "$f"; printf '\n-----END FILE-----\n'; } > prompt-$name.txt
env $unset_list CLAUDE_FORCE_OAUTH=1 CLAUDE_CODE_OAUTH_TOKEN="$(cat ~/.claude/setup-token.txt)" timeout 900 claude -p --model claude-opus-5 --output-format json --max-turns 1 < prompt-$name.txt > "$out" 2> "$out.err"
rc=$?
python3 - "$out" "$name" "$rc" <<'PY'
import json,sys
p,name,rc=sys.argv[1:]
try:
    j=json.load(open(p)); r=str(j.get("result",""))
    blocked="content filtering" in r
    print(f"{name}: rc={rc} is_error={j.get('is_error')} blocked={blocked} out_tokens={(j.get('usage') or {}).get('output_tokens')} head={r[:80]!r}")
except Exception as e:
    print(f"{name}: rc={rc} unparsable: {open(p).read()[:200]!r} err={open(p+'.err').read()[:200]!r}")
PY
