# sanctions-name-screening: a Terminal-Bench 3 task

An original [Terminal-Bench 3](https://github.com/laude-institute/terminal-bench-3) task, built to the TB3
contribution bar: it passes the TB3 static checks and rubric review, the reference solution scores
1.0 and the no-op agent 0.0 in Docker, and the frontier coding agents that TB3 CI runs by default
(Codex `gpt-5.6-sol` at `xhigh`, Claude Code `claude-opus-5` at `max`) fail it, including when they
are told to cheat.

The task itself lives in [`tasks/sanctions-name-screening/`](tasks/sanctions-name-screening/) in the
exact layout TB3 expects, so it can be dropped into a TB3 pull request as-is.

## The task in one paragraph

A compliance team must screen a batch of 5,827 onboarding customers (individuals, companies, vessels)
against a 1,800-entry sanctions list and write `MATCH` / `NO_MATCH` decisions with the matched list
uid. The list mixes Latin and original-script names (Arabic, Persian, Cyrillic), several romanization
systems (Wade-Giles, Cantonese, pinyin; French, German and English transliterations of Arabic and
Russian), name-order and particle variation, patronymics and nasab chains, nicknames, strong and weak
aliases, partial dates of birth and identifiers. The batch is seeded with look-alikes that must not be
flagged. The verifier grades the decisions against hidden labels with both a recall floor and a
precision floor, per variation class. That is the model-validation bar a bank applies before trusting
a vendor screening engine, and generic fuzzy matching trades one floor against the other.

Full task description: [`instruction.md`](tasks/sanctions-name-screening/instruction.md).
Screening policy the verifier enforces:
[`screening_policy.md`](tasks/sanctions-name-screening/environment/data/screening_policy.md).

## Layout

```
tasks/sanctions-name-screening/   the TB3 task (task.toml, instruction.md, README.md,
                                  environment/, solution/, tests/)
scripts/generate_data.py          deterministic generator for the watchlist, the hidden
                                  customer batch + labels, and the public dev sample
scripts/checks/                   the TB3 static checks, vendored so they run offline
scripts/make_cheat_task.sh        builds the /cheat variant (red-team prompt appended)
docs/                             TB3 task template used as the schema reference
```

## Reproducing every gate

Prerequisites: Docker, and [`uv`](https://docs.astral.sh/uv/) (Harbor runs through `uvx`).

```bash
# 1. static checks (24 scripts, same ones TB3 CI runs)
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

RESULTS_PLACEHOLDER

## Why the agents fail

FAILURE_ANALYSIS_PLACEHOLDER

## Design notes

- **Outcome-verified, not process-verified.** The verifier reads one artifact, `/app/decisions.csv`,
  and scores it against labels that exist only in the verifier image. Nothing in the agent's
  container reveals a label; the public dev sample is a second draw from the same generator with a
  different seed, so the policy is learnable but the batch is not.
- **Two floors per class.** Overall recall and precision at least 0.97, recall at least 0.90 in each
  of nine true-match classes (transliteration, script-only, structure, strong alias, corroborated
  weak alias, identifier, entity suffix, vessel prefix, partial DOB), false-positive rate at most
  0.05 in each of five decoy classes and at most 0.01 among 4,200 unrelated customers, and the right
  uid on at least 0.97 of true matches. Loosening the matcher to lift one class breaks a decoy
  ceiling; tightening it drops a true-match class. Each threshold is a separate pytest so a failing
  run shows which bar was missed.
- **Stdlib-only reference solution.** `solution/screen.py` (transliteration tables, a small name
  lexicon, role-aware token alignment, the policy rules) proves the task is solvable inside the
  environment with no network and no extra packages; pandas, rapidfuzz and unidecode are installed
  for the agent's convenience, not required.
- **Synthetic, realistic data.** Name pools, romanization variants, alias conventions, partial dates
  and identifier formats follow list-publisher practice (OFAC SDN, HMT, EU), but no entry corresponds
  to a real listed party.

## Author

Dennis Tien Donaghy, AIML Solutions. Background: a decade of OSINT watchlist aggregation and
entity-resolution work across OFAC, HM Treasury, EU and UN lists, then financial data systems and
agentic-AI engineering.
