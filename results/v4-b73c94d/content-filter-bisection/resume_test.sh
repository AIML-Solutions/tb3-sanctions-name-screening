#!/usr/bin/env bash
# usage: resume_test.sh <label> <cwd> <session-id> [prompt]
label=$1; cwd=$2; sid=$3; prompt=${4:-"Continue with the next step."}
out=/tmp/claude-1000/-home-dennis/df25b411-c284-408b-9aa9-ba0b160c27d1/scratchpad/filter-bisect/resume-$label.json
unset_list=$(env | grep -oE '^(CLAUDECODE|CLAUDE_CODE_[A-Z_]+)=' | tr -d = | sed 's/^/-u /' | tr '\n' ' ')
cd "$cwd" && env $unset_list CLAUDE_FORCE_OAUTH=1 CLAUDE_CODE_OAUTH_TOKEN="$(cat ~/.claude/setup-token.txt)" CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 timeout 1500 claude -p --resume "$sid" --fork-session --model claude-opus-5 --output-format json --max-turns 1 "$prompt" > "$out" 2> "$out.err"
python3 - "$out" "$label" <<'PY'
import json,sys
p,label=sys.argv[1:]
try: ev=json.load(open(p))
except Exception: print(label, "unparsable:", open(p).read()[:300], open(p+".err").read()[:300]); sys.exit()
res=[e for e in ev if e.get("type")=="result"]; r=res[0] if res else {}
txt=str(r.get("result",""))
asst=[e for e in ev if e.get("type")=="assistant"]
kinds=[[(c.get("type"),c.get("name") or "") for c in (e.get("message") or {}).get("content") or []] for e in asst]
u=r.get("usage") or {}
print(f"{label}: is_error={r.get('is_error')} subtype={r.get('subtype')} blocked={'content filtering' in json.dumps(ev)} in={u.get('input_tokens')} cache_read={u.get('cache_read_input_tokens')} cache_create={u.get('cache_creation_input_tokens')} out={u.get('output_tokens')} assistant_msgs={kinds[:4]} head={txt[:100]!r}")
PY
