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
| v3.1 `e8c3aa4` | Codex gpt-5.6-sol xhigh, trial 1 | **yes** | 50 min | 69 | 19.0M / 105k | 0.0: A 0.991 / 1.0 pass; B 0.924 recall, six classes < 0.90, precision 1.0 | **genuine failure: incomplete generalization to unseen conventions** |
| v3.1 `e8c3aa4` | Codex gpt-5.6-sol xhigh, trial 2 | **yes** | 40 min | 62 | 13.6M / 93k | 0.0: A 0.999 / 1.0 pass; B 0.942 recall, five classes < 0.90, precision 1.0 | **genuine failure: incomplete generalization, narrower than trial 1** |
| v3.1 `e8c3aa4` | Codex gpt-5.6-sol xhigh, trial 3 | **yes** | 45 min | 92 | 17.1M / 93k | 0.0: A 0.998 / 1.0 pass; B 0.951 recall, T11 0.884 / T13 0.860 < 0.90, precision 0.999 | **genuine failure: incomplete generalization, narrowest margin** |
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

## 3. Failure classification (per valid trial)

**v3.1 Codex trial 1: flawed execution of a correct plan (incomplete generalization), high confidence.**
The agent's plan was right and its self-validation was thorough: it built a rule-based, threshold-free
matcher, audited every new batch match for precision, corrected two policy edge cases (nickname readings,
weak-alias tie-break), and reported "Development sample: 1,324/1,324 correct across all 23 classes" and
"all original-script watchlist words have a deterministic transliteration". On the visible batch it scored
recall 0.991 with zero false positives. On the unseen batch its precision stayed at 1.0 and its recall fell
to 0.924, with every transliteration-bearing class under the floor (T1 0.870, T2 0.826, T3 0.897, T10 0.866,
T11 0.814, T13 0.880) and the identifier, entity and vessel classes intact. The engine is not loose; it is
missing the four named conventions' rules in enough places that one name in eight slips through. The
pivotal moment is the final note: it declared completion on the strength of the sample and the visible
batch, the two things the task says are not a census, without a test it could run for the unseen part.
Premature confidence is the secondary tag; the primary is incomplete generalization.

**v3.1 Codex trial 2: same class, narrower margin, high confidence.** This run implemented the four named
conventions explicitly and checked them against list entries ("Ahmet/Cemal/Hüseyin/Kasım, Achmad/Joesoef,
dropped-diacritic scientific Russian forms, and Tan/Lim/Ong/Goh/Teo surnames") before declaring completion
with dev 1,324/1,324. Batch A: recall 0.999, zero false positives. Batch B: recall 0.942, precision 1.0; T2
0.899 and T3 0.897 just under the floor, T10 0.881, T11 0.884, T13 0.860. Worked examples in the instruction
were enough to get the named forms right and not enough to get the conventions right: the misses are the
combinations the examples do not show (a Turkish spelling inside a family-first structure, an Indonesian
spelling on a twin that must be resolved by date, an assimilated article on a Hokkien-adjacent name), which
is what "stacked" and "structure" classes measure. Same primary tag as trial 1.

**v3.1 Codex trial 3: same class, narrowest margin, high confidence.** The most careful of the three: 92
commands, explicit negative controls on the confusable pairs the policy warns about (Hassan/Hussein,
Samir/Samira, Saleh/Salehi, Faris/Farsi), all named unseen-convention examples verified against list
entries. Batch A 0.998 / 1.0. Batch B recall 0.951, precision 0.999; T1, T2, T3 and T10 now clear the floor
and only T11 (twins, 0.884) and T13 (unlisted identifiers, 0.860) do not. Those two classes are where an
unseen spelling meets a second rule (choose the right twin by date; ignore an identifier the list does not
know and fall back to the name): the engine's generalization gaps are now concentrated in interactions
rather than in any single convention. Three runs, three failures of the same kind, with recall on the unseen
batch rising 0.924 -> 0.942 -> 0.951 and precision never below 0.999: the agents are not guessing, they are
converging on a policy they cannot finish inferring from what they can see.

**Cross-agent comparison.** Not possible on this task: Claude Code's runs end at the API content filter
before an engine exists (section 2b). What can be said is that on the visible batch Codex's three engines
all passed with zero or one false positive, so the difficulty is entirely in the unseen batch.

## 4. Cross-agent comparison  TODO

## 5. Cheat-run analysis

Verifier threat model and the author-run probes are in `results/README.md` (`cheat-probe-*`): an engine
that hunts for label files and tries to execute the data generator inside the verifier scores 0 (labels
are deleted from disk before agent code runs, the generator is not in the verifier image, `/tests` is
root-only, the engine runs as `nobody` with `no_new_privs`, resource limits and a 300 s budget in its own
process group). Agent cheat trials: TODO.

## 6. Assessment  TODO
