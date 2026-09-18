#!/usr/bin/env bash
name=$1; out=$(dirname "$0")/gen-$name.json
unset_list=$(env | grep -oE '^(CLAUDECODE|CLAUDE_CODE_[A-Z_]+)=' | tr -d = | sed 's/^/-u /' | tr '\n' ' ')
env $unset_list CLAUDE_FORCE_OAUTH=1 CLAUDE_CODE_OAUTH_TOKEN="$(cat ~/.claude/setup-token.txt)" CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 timeout 1500 claude -p --model claude-opus-5 --output-format json --max-turns 1 < $name.txt > "$out" 2> "$out.err"; echo "$name rc=$?"
