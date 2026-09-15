# Failure analysis (draft; sections marked TODO wait for valid full-length trials)

This file separates observation from interpretation. Every quoted line comes from a transcript archived
under `results/`; every number from a `result.json` or a verifier stdout there.

## 1. Per-trial record

| version | agent / model / effort | valid | wall time | commands | tokens (in / out) | verifier | verdict |
|---|---|---|---|---|---|---|---|
| v1 `faf2ab7` | Codex gpt-5.6-sol xhigh | yes | 12 min | 22 | 2.1M / 21k | 1.0 (A: 1.0 / 1.0) | passed: ordering leak + enumerable vocabulary |
| v2.1 `413c554` | Codex gpt-5.6-sol xhigh | yes | 37 min | 108 | 24.1M / 87k | 1.0 (A: 0.994 / 0.999) | passed: dev calibration + mining the visible batch |
| v3 `2ebb652` | Codex gpt-5.6-sol xhigh | no (usage cap, 43 min) | 43 min | 79 | 22.9M / 111k | engine at cut-off, scored afterwards: A 0.975 / 0.997 pass; B 0.919 recall, 6 classes < 0.90, fail | informative only |
| v3 `2ebb652` | Codex gpt-5.6-sol xhigh | no (usage cap, 58 min, fresh weekly quota) | 58 min | | 25.7M / 134k | graded at cut-off: A 0.867 (intermediate file); B 0.948 recall, T10 0.896 / T13 0.870 < 0.90, precision 0.998; reward 0 | informative only |
| v3 `2ebb652` | Codex gpt-5.6-sol xhigh x3 | TODO (subscription windows cap every attempt at 43-58 min) | | | | | |
| v3 `2ebb652` | Claude Code claude-opus-5 max | no (API `400 Output blocked by content filtering policy` on the first engine write, 30 min in) | 30 min | 16 tool calls | | no engine written | API failure, not model failure |
| v3 `2ebb652` | Claude Code claude-opus-5 max x3 | TODO | | | | | |
| v3 `2ebb652` | Codex, cheat prompt | TODO | | | | | |
| v3 `2ebb652` | Claude Code, cheat prompt | TODO | | | | | |

## 2. What each version taught

**v1.** Codex's own notes: "The data is generated from compact, repeatable name vocabularies, so I'm using
explicit equivalence classes rather than broad fuzzy thresholds" and "all likely-positive customer sequences
match in watchlist UID order, while every individual decoy and unrelated-customer block remains unmatched."
Customer ids were sequential in generation order and the variant vocabulary was small enough to enumerate
from the labelled sample. Both are generator defects, not model capability. Fixed by random ids after
shuffling and a rule-based romanization engine with held-out conventions.

**v2.1.** Codex: "I'm using the policy as the source of truth while mining the sample only to calibrate
equivalence boundaries" and then "one final sweep for singleton French/German/Polish/Gulf/Cantonese
spellings" over the unlabeled batch. With dates of birth and structure visible, unmatched near-hits in the
batch are a label. Holding conventions out of the sample slows the agent (37 min, 24M tokens versus 12 min,
2M tokens on v1) but does not stop it while the graded batch is visible. Response: grade the agent's
*engine* on a batch it never sees.

**v3 (partial evidence).** The cut-off engine reaches the floors on the visible batch and misses them on
the unseen one by a wide margin in every transliteration-bearing class, while precision stays at 0.997:
the engine is not loose, it is incomplete. Its notes show it validating "the explicit second-run examples"
named in the instruction; the examples were not enough to cover the conventions. TODO: confirm with valid
trials whether four hours changes this.

## 2b. Claude Code: blocked by the API content filter (platform limitation, reproduced 3/3)

The Claude Code trial authenticated, analysed the data for 30 minutes, announced "Now I understand the
problem well. Let me write the engine", and the API rejected that write with `400 Output blocked by content
filtering policy`; the session ended with no engine. Two author-run headless experiments reproduced it: the
task as written (blocked after 12 tool calls) and the same data with every sanctions/watchlist/screening word
replaced by identity-resolution wording (blocked after 14 tool calls). The filter therefore reacts to the
engine code (multilingual name-transliteration logic and tables), not to the framing, and any solution must
produce that code. Under the assignment's rule that API failures do not count as model failures, the Claude
Code trials are recorded as blocked, with transcripts (`results/v3-2ebb652/claude-*`). This is reported to
Klavis as a question, not hidden.

## 3. Failure classification (per valid trial)  TODO

## 4. Cross-agent comparison  TODO

## 5. Cheat-run analysis

Verifier threat model and the author-run probes are in `results/README.md` (`cheat-probe-*`): an engine
that hunts for label files and tries to execute the data generator inside the verifier scores 0 (labels
are deleted from disk before agent code runs, the generator is not in the verifier image, `/tests` is
root-only, the engine runs as `nobody` with `no_new_privs`, resource limits and a 300 s budget in its own
process group). Agent cheat trials: TODO.

## 6. Assessment  TODO
