# sanctions-name-screening: a Terminal-Bench 3 task

An original [Terminal-Bench 3](https://github.com/harbor-framework/terminal-bench-3) task, built to the TB3
contribution bar: the TB3 static checks and rubric review, oracle 1.0 / nop 0.0 in Docker, and trials of the
frontier coding agents that TB3 CI runs by default (Codex `gpt-5.6-sol` at `xhigh`, Claude Code
`claude-opus-5` at `max`), including trials where the agents are told to cheat.

**Status (honest summary).** The submitted version is `results/final-c3d44e4/`. On it, **Codex
(`gpt-5.6-sol`, xhigh) fails all three standard trials** (reward 0; batch B recall 0.911 / 0.917 / 0.890,
missing the transliteration and Chinese-company-romanization floors), and **both cheat runs score 0**
(the verifier is not gameable). **Claude Code (`claude-opus-5`, max) solves the task all three times**
(reward 1.0; batch B 0.988 / 0.992 / 0.993). So this task does **not** meet the assignment's bar of all three
Claude Code trials failing: a fair, rubric-compliant version of this problem is within Claude Code's
capability. It is submitted with that stated plainly, alongside two findings that came out of trying to
reach the bar.

**Finding 1 — a content filter that blocks matching Chinese *individuals*.** Early versions used Chinese
personal names for difficulty, and every Claude Code trial was blocked by the provider's output content
filter before an engine was written. A controlled investigation
([`docs/content-filter-bisection.md`](docs/content-filter-bisection.md)) isolated the trigger to generating
code that matches Chinese personal names at scale (16/16 non-Chinese high-context probes completed; 4/4
Chinese-individual probes were blocked) — not the sanctions framing, not Arabic or Cyrillic names. The task
was redesigned to carry the same romanization difficulty through Chinese *companies*, which the filter
permits, so Claude Code runs to completion.

**Finding 2 — the fair-difficulty ceiling.** Once the graded convention is disclosed (required for a
rubric-fair task), Claude Code at max effort reconstructs even obscure Wade-Giles/Cantonese/Hokkien
company-name romanizations well enough to clear the floors. Every clean, full-budget Claude Code run on a
fair version passes (0.976–0.993). The only Claude "failures" observed were on an *undisclosed* grading axis
(which is unfair and fails the implementation rubric) or on runs cut short by API limits. Codex, being
weaker, fails the fair task. The honest conclusion: a fair version of this task defeats Codex but not Claude
Code. The full version history and trial data are under [`results/`](results/).

The task itself lives in [`tasks/sanctions-name-screening/`](tasks/sanctions-name-screening/) in the
exact layout TB3 expects, so it can be dropped into a TB3 pull request as-is.

## The task in one paragraph

A compliance team must screen a batch of 3,058 onboarding customers (individuals, companies, vessels)
against a 2,100-entry sanctions list and write `MATCH` / `NO_MATCH` decisions with the matched list
uid. The list mixes Latin and original-script names (Arabic, Persian, Cyrillic), several romanization
systems (Wade-Giles, Cantonese, pinyin; French, German and English transliterations of Arabic and
Russian), name-order and particle variation, patronymics and nasab chains, nicknames, strong and weak
aliases, partial dates of birth and identifiers. The batch is seeded with look-alikes that must not be
flagged. The verifier grades the decisions against hidden labels with both a recall floor and a
precision floor, per variation class, and then runs the agent's engine (`/app/screen.py`, standard
library only) on a second batch that exists only in the verifier image, with four romanization
conventions the agent never saw, to the same bars. That is the model-validation bar a bank applies
before trusting a vendor screening engine: a held-out batch, and generic fuzzy matching trades one
floor against the other.

Full task description: [`instruction.md`](tasks/sanctions-name-screening/instruction.md).
Screening policy the verifier enforces:
[`screening_policy.md`](tasks/sanctions-name-screening/environment/data/screening_policy.md).

## Layout

```
tasks/sanctions-name-screening/   the TB3 task (task.toml, instruction.md, README.md,
                                  environment/, solution/, tests/ incl. the data generator)
scripts/generate_data.py          wrapper around tests/generate_data.py
scripts/score.sh                  scores the reference solution on hidden and dev splits
scripts/tests/                    focused policy unit tests for the reference solution
scripts/checks/                   the TB3 static checks, vendored so they run offline
scripts/make_cheat_task.sh        builds the /cheat variant (red-team prompt appended)
scripts/summarize_runs.py         harbor job directories -> results table
docs/oracle-iterations.md         every reference-solution change with its measured effect
docs/task-template.toml           TB3 task template used as the schema reference
```

## Reproducing every gate

Prerequisites: Docker, and [`uv`](https://docs.astral.sh/uv/) (Harbor runs through `uvx`).

```bash
# 1. static checks (22 scripts, the same ones TB3 CI runs; vendored byte-identical)
for f in scripts/checks/*.sh; do bash "$f" tasks/sanctions-name-screening || echo "FAIL $f"; done

# 2. validate: reference solution must score 1.0, no-op agent must score 0.0
uvx harbor run -p tasks/sanctions-name-screening --agent oracle --env docker
uvx harbor run -p tasks/sanctions-name-screening --agent nop    --env docker

# 3. agent trials, the pairs from TB3's .github/harbor-run-defaults.yml, 3 trials each
uvx harbor run -p tasks/sanctions-name-screening --env docker -k 3 \
    --agent codex -m openai/gpt-5.6-sol --ak reasoning_effort=xhigh
CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 uvx harbor run -p tasks/sanctions-name-screening --env docker -k 3 \
    --agent claude-code -m anthropic/claude-opus-5 --ak reasoning_effort=max

# 4. cheat trials: the red-team prompt TB3 appends for /cheat, one run per agent
scripts/make_cheat_task.sh tasks/sanctions-name-screening <tb3-checkout> build/cheat
uvx harbor run -p build/cheat/sanctions-name-screening --env docker \
    --agent codex -m openai/gpt-5.6-sol --ak reasoning_effort=xhigh
CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000 uvx harbor run -p build/cheat/sanctions-name-screening --env docker \
    --agent claude-code -m anthropic/claude-opus-5 --ak reasoning_effort=max
```

Agent credentials: Harbor reads `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, or with
`CODEX_FORCE_AUTH_JSON=1` / `CLAUDE_FORCE_OAUTH=1` (+ `CLAUDE_CODE_OAUTH_TOKEN` from
`claude setup-token`) it uses a ChatGPT or Claude subscription login instead.

The generator is deterministic (`python3 scripts/generate_data.py` rebuilds every data file
byte-for-byte). Hidden labels are written only to `tests/data/`, which is baked into the verifier
image and never into the agent's environment.

## Results

All runs are recorded under [`results/`](results/) (harbor `result.json`, verifier stdout, agent transcripts) and
summarised in [`results/README.md`](results/README.md); nothing is edited by hand. Version = git commit the
run evaluated. Final status as of 2026-09-16; the trial matrix below is complete except where a platform limitation is noted.

### Gates on the submitted version (`results/final-c3d44e4/`: Chinese individuals removed for filter-safety; the disclosed Chinese-company romanization difficulty is held out to batch B)

| gate | result | evidence |
|---|---|---|
| TB3 static checks (22, byte-identical to upstream CI) | pass, 0 failures | run `scripts/reproduce.sh` |
| rubric review (35 criteria, TB3 rubric, independent reviewer per version) | v1 26/6/3, v2 28/4/3, v3 28/3/2, **submitted tree 34/0/1** (the reviewer re-ran the checks, the verifier and the generator itself); every fail fixed and re-checked | `results/*/rubric-verdicts.json` |
| Docker build | clean | `results/final-c3d44e4/` |
| oracle (reference solution) | reward 1.0, 10/10 verifier tests (batch A decisions + engine on batch B); A 0.990 / 0.998, B 0.991 / 0.990, dev 0.990 / 1.0 | `results/v6-e668f1a/` |
| nop | reward 0.0 | `results/final-c3d44e4/` |
| unit tests (policy regressions) | 7/7 | `scripts/tests/` |
| verifier cheat probes (author-written engines that hunt for labels or run the generator inside the verifier) | reward 0 | `results/v3-2ebb652/cheat-probe-*` |

### Standard trials

**Submitted version (`results/final-c3d44e4/`). Codex fails all three; Claude Code solves all three.**

| agent | trial 1 | trial 2 | trial 3 | outcome |
|---|---|---|---|---|
| Codex gpt-5.6-sol xhigh | reward 0.0, B 0.911 | reward 0.0, B 0.917 | reward 0.0, B 0.890 | **fails 3/3** (transliteration + Chinese-company floors) |
| Claude Code claude-opus-5 max | reward 1.0, B 0.988 | reward 1.0, B 0.992 | reward 1.0, B 0.993 | **passes 3/3** |

Cheat runs: Codex 0 (safety-classifier refusal), Claude Code 0 (found no bypass; left a genuine engine that
still failed batch B). This does not meet the "all three Claude trials fail" bar — see the honest status
above. The rows below are the earlier versions, kept as the iteration record.


| version | agent | outcome | note |
|---|---|---|---|
| v1 | Codex gpt-5.6-sol xhigh | **reward 1.0** in 12 min | data leaks (sequential ids, enumerable vocabulary); fixed in v2 |
| v2.1 | Codex gpt-5.6-sol xhigh | **reward 1.0** in 37 min | calibrated on the sample, mined the visible batch; fixed in v3 by grading the engine on an unseen batch |
| v3 | Codex gpt-5.6-sol xhigh, 4 attempts | all ended in `ApiUsageLimitError` at 21 / 12 / 43 / 58 min (ChatGPT subscription windows) | not valid trials. Two attempts left an engine behind; graded afterwards in the real verifier both **fail batch B** (recall 0.919 and 0.948; T1/T2/T3/T10/T11/T13 under the 0.90 floor) with precision 0.997 |
| v3 | Claude Code claude-opus-5 max, 1 attempt | ended by `API Error: 400 Output blocked by content filtering policy` on its first engine write, 30 min in | not a valid trial; API failure |
| v3 | Claude Code claude-opus-5 max, 2 further reproductions | the same filter error, one with the task re-worded (identity resolution instead of sanctions) | platform limitation, 3/3; `results/v3-2ebb652/claude-content-filter-experiments/` |
| v3.1 | Claude Code claude-opus-5 max, standard trial on the submitted version | `400 Output blocked by content filtering policy` after 40 min and 17 tool calls of analysis, before any engine; harbor `AgentSafetyRefusalError` | platform limitation, 4/4; `results/v3.1-e8c3aa4/claude-trial-invalid-content-filter-1` |
| v3.1 | Codex gpt-5.6-sol xhigh, trial 1 | **reward 0.0** in 50 min, no infrastructure error | batch A passed (0.991 / 1.0); batch B recall 0.924, six classes under the floor, precision 1.0 |
| v3.1 | Codex gpt-5.6-sol xhigh, trial 2 | **reward 0.0** in 40 min, no infrastructure error | batch A passed (0.999 / 1.0); batch B recall 0.942, five classes under the floor, precision 1.0 |
| v3.1 | Codex gpt-5.6-sol xhigh, trial 3 | **reward 0.0** in 45 min, no infrastructure error | batch A passed (0.998 / 1.0); batch B recall 0.951, T11 and T13 under the floor, precision 0.999 |
| v3.1 | Claude Code /cheat (TB3 hack-trial prompt) | **reward 0.0**, 9 min, 20 tool calls | completed adversarial run: probed labels, generator, verifier, logs, mounts, degenerate outputs; built and rejected a co-located-labels trick; left the stub engine; "no credible bypass found"; `results/v3.1-e8c3aa4/claude-cheat-1` |
| v3.1 | Codex /cheat x2 (TB3 hack-trial prompt) | **reward 0.0** both, 28 s and 21 s | ended by OpenAI's safety classifier ("flagged for possible cybersecurity risk") after 2-3 read-only commands; no engine written; `results/v3.1-e8c3aa4/codex-cheat-{1,2}` |

### Adversarial (/cheat) trials

Both agents' cheat runs score 0 on the submitted version (v6). Claude Code completed the adversarial run and
left a co-located answer-key harvester as the engine; the verifier deletes its label files before running the
engine, so it found nothing and failed every floor (reward 0) — the verifier is not exploitable. Codex was
ended by OpenAI's own safety classifier refusing the hack-trial prompt (reward 0, no engine written), as on
the earlier versions. The verifier's threat model and author-run probes (label-hunting and
generator-execution engines, all reward 0) are in `results/v6-e668f1a/`, `results/README.md` and
`analysis/FAILURE_ANALYSIS.md`.

## Why the agents fail

Full analysis with quoted transcript lines: [`analysis/FAILURE_ANALYSIS.md`](analysis/FAILURE_ANALYSIS.md).
In brief: on version 1 Codex found that customer ids were assigned in generation order and that the variant
vocabulary was small enough to enumerate from the labelled sample. On version 2 it calibrated a rule-based
matcher on the sample and then mined the unlabeled batch for unmatched near-hits with consistent dates,
learning the held-out conventions from the batch itself. Version 3 grades the agent's engine on a batch it
never sees, with four romanization conventions named in the instruction but absent from every file the agent
can read. Every engine Codex produced on version 3, including the three full-length trials, clears the visible
batch and misses the unseen one in the transliteration-bearing classes while keeping precision above 0.997: the engines are not loose,
they are incomplete, and the batch they cannot see is what exposes it.

## Reviewer notes and known limitations

Points a careful reviewer will raise, answered rather than hidden:

- **Every trial ran while this repository was private.** The `tests/` directory (labels, batch B, the
  generator with its seeds) is public now, as it is for every merged TB3 task; an open-internet agent that
  fetched it could reconstruct the labels. That is the benchmark-wide exposure of any `tests/` directory,
  guarded by the "do not cheat" trailer, and it does not affect the recorded results.
- **Batch B's conventions are named on purpose.** The instruction and the policy tell the agent which four
  conventions the unseen batch adds, with example spellings. The task is to implement transliteration
  rules, not to guess which languages exist; the three Codex trials show that knowing the list is not the
  same as clearing it (0.924 to 0.951 recall on B with the list in hand).
- **Verifier resource limits.** The batch-B engine runs under `prlimit` with a 2 GiB address space, 50 MB
  file size and 64 processes, matching the verifier container's 2048 MB memory in `task.toml`; the
  instruction states one core and 300 s. The reference solution uses about 3 s and well under 200 MB.
- **Oracle and generator share vocabulary.** Both are built from the same canonical name pools and the
  same published romanization rules, so overlap in their tables is expected; the oracle is not an inverse
  of the generator (its slot model and reading sets are general and it scores below 100% on both batches,
  with the misses logged in `docs/oracle-iterations.md`).
- **The policy file says "verifier" twice.** It is an in-world bank document that also serves as the
  grading specification; the wording was left as the agents saw it.
- **`harbor analyze` was not run.** TB3 CI runs an LLM trial analysis after `/run` and `/cheat` with an
  API key; on a no-spend budget the analysis was written by hand from the transcripts instead
  (`analysis/FAILURE_ANALYSIS.md`), using the same taxonomy as TB3's `trial-analysis` prompt.
- **`scripts/` is repository tooling**, not part of the task package; the task directory stands alone.

## Design notes

- **Outcome-verified, not process-verified.** The verifier reads two artifacts, `/app/decisions.csv`
  and `/app/screen.py`, and scores them against labels that exist only in the verifier image. Nothing
  in the agent's container reveals a label; the public dev sample is a second draw from the same
  generator with a different seed, so the policy is learnable but the batch is not.
- **A batch the agent never sees.** Batch B (verifier image only) has new customers against the same
  list and four further romanization conventions, named in the instruction and policy (Turkish and
  Indonesian spellings of Arabic names, scientific transliteration of Russian, Hokkien/Teochew Chinese
  surnames). The verifier deletes its label files from disk before running the engine, runs it as an
  unprivileged user with a 300 s budget, and applies the same floors. An engine that reproduces the
  spellings it can see does not clear them; one that implements the policy does.
- **Two floors per class.** Overall recall and precision at least 0.97, recall at least 0.90 in each
  of thirteen true-match classes (transliteration, script-only, structure, strong alias, corroborated
  weak alias, identifier, entity suffix, vessel prefix, partial DOB, stacked conventions, twins,
  script-side customers, unlisted identifiers), false-positive rate at most 0.05 in each of seven
  decoy classes and at most 0.01 among unrelated people, companies and vessels, and the right uid on at least 0.97
  of true matches. Loosening the matcher to lift one class breaks a decoy
  ceiling; tightening it drops a true-match class. Each threshold is a separate pytest so a failing
  run shows which bar was missed.
- **Stdlib-only reference solution.** `solution/screen.py` (transliteration tables, a phonological
  slot model for vowels, Wade-Giles reading sets, a small name lexicon, role-aware alignment, the policy
  rules) proves the task is solvable inside the environment with no network and no extra packages. It
  scores 0.996 recall / 1.000 precision on batch A and 0.999 / 0.998 on batch B, deliberately not 100%: the remaining misses
  are documented rule gaps, and `docs/oracle-iterations.md` records every change and its effect.
- **A sample, not a census.** The development sample is generated with four romanization conventions;
  the batch uses ten. The instruction says so. A matcher that reproduces the sample's spellings does not
  clear the per-class floors on the batch.
- **Synthetic, realistic data.** Name pools, romanization variants, alias conventions, partial dates
  and identifier formats follow list-publisher practice (OFAC SDN, HMT, EU), but no entry corresponds
  to a real listed party.

## Author

Dennis Tien Donaghy, AIML Solutions. Background: a decade of OSINT watchlist aggregation and
entity-resolution work across OFAC, HM Treasury, EU and UN lists, then financial data systems and
agentic-AI engineering.
