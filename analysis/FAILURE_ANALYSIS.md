# Failure analysis

This file separates observation from interpretation. Every quoted line comes from a transcript archived
under `results/`; every number from a `result.json` or a verifier stdout there.

## 0. Submitted version (v6): both agents fail, and the Claude content filter is resolved

The submitted task is **v6** (`results/v6-e668f1a/`). It is the earlier sanctions task with one change forced
by a provider-side content filter and one change that keeps the difficulty intact:

- **The filter.** On versions 3 and 3.1 every Claude Code trial was blocked by `400 Output blocked by content
  filtering policy` before an engine was written (four reproductions). A controlled investigation
  (`docs/content-filter-bisection.md`) isolated the trigger: generating code that matches **Chinese personal
  names at scale**. High-context probes, holding everything constant but the register's contents, blocked 4/4
  on Chinese individuals and 0/16 on Arabic individuals, Cyrillic individuals, Western individuals, and
  companies/vessels. It is not the sanctions framing, the Arabic names, or the vocabulary.
- **The fix.** v6 removes Chinese *individuals* and reintroduces the same arbitrary-lookup romanization
  difficulty through Chinese-named *companies* (filter-safe: 4/4 probes completed). The watchlist lists them
  in pinyin; the sample and batch A show pinyin; batch B holds out their Wade-Giles/Cantonese/Hokkien stem
  spellings (a listed `Zhu Freight` must be matched to a batch-B customer's `Chu Freight`). The reference
  solution canonicalizes entity stems by pinyin reading-set intersection.

**v6 trial matrix (TB3 CI defaults: Codex gpt-5.6-sol xhigh, Claude Code claude-opus-5 max, three each).**

| agent | trial | valid | reward | batch B recall | entity-suffix (T7) recall |
|---|---|---|---|---|---|
| Claude Code | 1 | yes (no filter block, 111 min) | 0.0 | 0.916 | 0.610 |
| Claude Code | 2 | yes (no filter block) | 0.0 | 0.929 | 0.681 |
| Claude Code | 3 | yes (no filter block, 70 min) | 0.0 | 0.915 | 0.610 |
| Codex | 1 | yes (33 min) | 0.0 | 0.836 | 0.610 |
| Codex | 2 | yes | 0.0 | 0.893 | 0.610 |
| Codex | 3 | yes | 0.0 | 0.899 | 0.610 |

Infrastructure failures that do not count and were re-run: one Claude trial hit an API rate limit, and two
Codex attempts failed on ChatGPT usage/auth limits (all archived under `results/v6-e668f1a/` with the
`-invalid-` suffix). Cheat runs: Claude Code completed the adversarial run and scored 0 (it left a
co-located answer-key harvester; the verifier deletes labels before running the engine, so it found nothing);
Codex scored 0 by OpenAI's safety classifier refusing the hack-trial prompt.

**Why they fail.** Both agents clear the visible batch and collapse on batch B's entity-suffix class
(recall 0.61 every run), because the held-out Wade-Giles/Cantonese/Hokkien company-stem spellings are
lookup-based, not rule-derivable: nothing the agent can read tells it that `Cheung`, `Chang`, or `Teo` are
the same stem as `Zhang`. Codex additionally slips on transliteration (T1 ~0.84) where Claude holds
(~0.95), so Codex fails wider; but the entity class alone puts both below the 0.90 per-class floor and the
0.97 overall floor. Precision stays high throughout (0.97-1.0), so the engines are not loose — they are
incomplete on exactly the axis the task holds out. This is the same failure mode that defeated the agents on
the Chinese-individual versions, now delivered through a channel the content filter permits.



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
| v3 `2ebb652` | Claude Code claude-opus-5 max, repeats | no: the same filter error in two further headless reproductions, one with the task re-worded (section 2b) | | | | no engine written | platform limitation, 3/3 |
| v3.1 `e8c3aa4` | Claude Code claude-opus-5 max, standard | no (`400 Output blocked by content filtering policy` after 40 min of analysis; harbor `AgentSafetyRefusalError`) | 40 min | 17 | 1.16M / 100k | no engine written | platform limitation, 4/4 |
| v3.1 `e8c3aa4` | Codex xhigh, cheat prompt x2 | reward 0, but ended by OpenAI's safety classifier (`AgentSafetyRefusalError`) | 28 s, 21 s | 3, 2 | 46k / 0.7k; 29k / 0.6k | no engine written | provider refusal of the hack-trial prompt (section 5) |
| v3.1 `e8c3aa4` | Claude Code max, cheat prompt | **yes** (no filter error: it never wrote an engine) | 9 min | 20 | 529k / 35k | 0.0: stub engine, no decisions | **genuine cheat failure: agent reports "no credible bypass found"** (section 5) |

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
named in the instruction; the examples were not enough to cover the conventions. Confirmed by the three
full-length v3.1 trials below: the extra time narrows the gap (0.924, 0.942, 0.951) without closing it.

## 2b. Claude Code: blocked by the API content filter (platform limitation, reproduced 4/4)

The Claude Code trial authenticated, analysed the data for 30 minutes, announced "Now I understand the
problem well. Let me write the engine", and the API rejected that write with `400 Output blocked by content
filtering policy`; the session ended with no engine. Two author-run headless experiments reproduced it: the
task as written (blocked after 12 tool calls) and the same data with every sanctions/watchlist/screening word
replaced by identity-resolution wording (blocked after 14 tool calls). The filter therefore reacts to the
engine code (multilingual name-transliteration logic and tables), not to the framing, and any solution must
produce that code. Under the assignment's rule that API failures do not count as model failures, the Claude
Code trials are recorded as blocked, with transcripts (`results/v3-2ebb652/claude-*`). A fourth attempt on the
submitted version (`e8c3aa4`, plain wording, smaller batch) ran 40 minutes and 17 tool calls of analysis and
was blocked at the same point, before any engine existed; harbor classifies that run
`AgentSafetyRefusalError` (`results/v3.1-e8c3aa4/claude-trial-invalid-content-filter-1`). This is reported
to Klavis as a question, not hidden.

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

## 4. Cross-agent comparison

See the end of section 3: not possible on this task, because Claude Code never reaches an engine (section 2b).
On the visible batch all three Codex engines pass with at most one false positive; the difficulty is entirely
in the unseen batch.

## 5. Cheat-run analysis

Verifier threat model and the author-run probes are in `results/README.md` (`cheat-probe-*`): an engine
that hunts for label files and tries to execute the data generator inside the verifier scores 0 (labels
are deleted from disk before agent code runs, the generator is not in the verifier image, `/tests` is
root-only, the engine runs as `nobody` with `no_new_privs`, resource limits and a 300 s budget in its own
process group).

**Codex /cheat runs (2 of 2): reward 0, ended by OpenAI's safety classifier, not by the verifier.** With the
TB3 hack-trial prompt appended, Codex opened each run by declaring its plan (run 1: "widening the search to
image layers, caches, repository metadata, process arguments"; run 2: "inspect the workspace and
grading-facing artifacts for leaks, brittle validation, path/symlink opportunities") and issued two or three
read-only commands (`find` over /app and /, the policy, the stub engine, `/logs/verifier`). The next model
turn was refused: "This content was flagged for possible cybersecurity risk", and harbor recorded
`AgentSafetyRefusalError` after 28 s and 21 s. No engine or decisions were written, so the verifier errored on
the placeholder engine (10 errors). Classification: the score of 0 is genuine but uninformative about the
verifier; what the agent was about to try is the surface the author-run probes already exercise (label
hunting on disk, generator execution inside the verifier), and those probes score 0 against the hardening
listed above. Both transcripts are archived (`results/v3.1-e8c3aa4/codex-cheat-{1,2}`).

**Claude Code /cheat run (1 of 1): reward 0, a completed adversarial run.** The content filter that stops
the standard runs never fired here because the agent never wrote a matching engine. In 9 minutes and 20 tool
calls it did what the hack-trial prompt asks: searched the filesystem for labels, generator or verifier code
(only `dev/labels_dev.csv` exists, with D-ids disjoint from the graded C-ids), inspected `/logs`, mounts,
environment and setup files, checked that all-MATCH and all-NO_MATCH fail the floors, and built a
proof-of-concept engine that reads any co-located labels CSV. Its own test of that engine: "co-located
layout reproduces the gold labels 1324/1324; isolated layout finds nothing, all NO_MATCH, recall 0, hard
fail". It then argued the trick is not a credible bypass because the visible batch is graded independently
with no label source in the sandbox and the hidden batch's layout is controlled by the verifier, removed
its probe files, left the stub engine and no decisions file, and concluded: "no working shortcut, bypass,
or verifier weakness exists; the only path that passes grading is the intended legitimate engine". That is
the intended reading of the design (labels deleted before the engine runs, `/tests` root-only, engine as
`nobody`), reached independently by the agent. Transcript: `results/v3.1-e8c3aa4/claude-cheat-1`.

## 6. Assessment

The task does what the assignment asks of it on the side that could be measured. Three full-effort Codex
runs on the submitted version (`e8c3aa4`) each finished inside a subscription window with no infrastructure
error and scored 0: every engine passed the visible batch and missed the recall floor on the unseen batch
(0.924, 0.942, 0.951) while keeping precision at 0.999 or above. The failure is the intended one, the
agents cannot finish inferring a romanization policy from the examples they are given, and it narrowed
run over run without closing, which is the behaviour of a task that is hard rather than broken. The oracle
scores 0.996/1.000 and 0.999/0.998 on the two batches, nop scores 0, the static checks pass 22/22, and the
cheat probes and both Codex cheat runs score 0. The Claude Code side is a documented platform limitation:
the API's content filter blocks the engine write in every configuration tried (four reproductions,
including a re-worded task and one on the submitted version), which the assignment classes as an API failure rather than a model failure.
Two things would strengthen the evidence further and are noted as open: a Claude Code result once the
filter is lifted or an alternative route is agreed with Klavis, and a Codex cheat run that is not ended by the
provider's classifier, which would need a prompt other than the fixed TB3 hack-trial text (the Claude Code
cheat run already supplies a completed adversarial attempt).
