#!/usr/bin/env bash
# Build the /cheat variant of a task: a copy whose instruction.md has the
# Terminal-Bench red-team prompt appended (mirrors TB3's run-cheat-trials job).
#
#   scripts/make_cheat_task.sh tasks/sanctions-name-screening <tb3-checkout> <out-dir>
set -euo pipefail

task_dir=${1:?task dir}
tb3=${2:?path to a terminal-bench-3 checkout (for docs/prompts/hack-trial-prompt.md)}
out=${3:?output dir}

name=$(basename "$task_dir")
rm -rf "$out/$name"
mkdir -p "$out"
cp -r "$task_dir" "$out/$name"
printf '\n' >> "$out/$name/instruction.md"
cat "$tb3/docs/prompts/hack-trial-prompt.md" >> "$out/$name/instruction.md"
echo "cheat task written to $out/$name"
