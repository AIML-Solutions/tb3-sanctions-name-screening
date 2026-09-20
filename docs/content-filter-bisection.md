# Why version 4 exists: bisecting the API content filter

Every Claude Code trial on versions 3 and 3.1 ended with `API Error: 400 Output blocked by content
filtering policy` (four reproductions). The earlier conclusion in this repository, that the filter reacts
to the engine code, was wrong. This note records the experiment that found the actual trigger. All runs
used headless Claude Code (`claude -p`, `claude-opus-5`) on a Max subscription; raw summaries and the
scripts are in `results/v4-b73c94d/content-filter-bisection/`.

## Method

1. **Verbatim echo tests.** Ask the model to reproduce a file exactly. The whole reference engine (45 KB,
   20.8k output tokens), the generator's name pools, the first 40 KB of the watchlist, the nickname list
   and the Arabic letter map all echoed without a block. The engine code and the data are not the trigger.
2. **Session resume.** The two headless experiments from Sep 14 left their session files behind. Resuming
   the blocked session reproduces the block on the very next turn, before any tool runs, which gives a
   cheap, repeatable reproduction at the exact context that failed (about 180k tokens).
3. **Mutated resumes.** Copies of that session with a fresh id and untouched (signed) thinking blocks, each
   with one change to the prompts, assistant text and tool results, resumed under the same conditions.
   Because the filter turned out to be probabilistic, each variant was repeated.

## Results

| variant (same 180k-token context) | blocked / runs |
|---|---|
| untouched session | 4 / 5 |
| all Arabic, Cyrillic and Chinese characters replaced by `?` | 1 / 1 |
| context truncated to its first half | 1 / 1 |
| tool-result contents removed (prompts and assistant text kept) | 0 / 1 |
| redact *sanctions, watchlist, screening, designated, decoy, customer* | 0 / 3 |
| redact only `SDN-` uids and *passport* | 1 / 3 |
| redact only the militant-style nicknames (*Abu Layth, The Engineer, Al-Hakim, ...*) | 1 / 3 |
| redact all three groups | 0 / 5 |

Reading: the trigger is the compliance vocabulary that the agent's own data-inspection commands print
back into the context, compounded by OFAC-style program codes (`SDGT`, `SDNTK`, `CYBER`) on every list entry
and by nicknames associated with real militants. Script characters, code, and context length are not it.
The filter is stochastic (about 80% per turn on the original context), which is why a 50-turn trial never
survived and why the fix has to remove the vocabulary rather than reduce it.

## The fix (version 4, `experiments/archive-record-linkage`)

The same task with the same names, rules, generator logic, verifier and floors, framed as linking newly
digitised records to an archive register: `register.json` / `records.csv` / `link.py`, `record_id`,
`AR-` uids, `document` identifiers instead of passports, a `collections` field (port ledgers, passenger
manifests, ...) instead of program codes, neutral nicknames and entity stems, and one surname swapped
(Nasrallah to Saadallah, keeping the Allah-compound rule). Sanctions vocabulary appears nowhere the agent
can read. The reference solution clears every bar on the regenerated data (A 0.996 / 1.000, B 0.998 / 0.998).
The substance, and the author's domain, is still sanctions screening; the README says so.


## Correction and root cause (Sep 18, controlled high-context probes)

The "it's the compliance vocabulary" conclusion above was wrong. Direct experiments settle it. Each probe
builds a ~130k-token context (a large register dump) and asks the model, in one turn, to write the
name-matching engine; the only thing varied is which entries fill the register. Four runs per variant,
Claude Code `claude-opus-5` on the Max subscription. Verdicts in `probes/probe-verdicts.tsv`.

| register content (high context) | blocked |
|---|---|
| Arabic / Persian individuals | 0 / 4 |
| Cyrillic / Russian individuals | 0 / 4 |
| Entities and vessels (companies, ships, IMO/registration) | 0 / 4 |
| Western individuals | 0 / 4 |
| **Chinese individuals (pinyin / Wade-Giles / Cantonese names)** | **4 / 4** |

**Root cause: the filter fires on generating code that matches/identifies Chinese personal names at scale.**
It is not the sanctions framing, not Arabic or Muslim names, not the domain vocabulary (the agent wrote none),
and not script characters (Arabic and Cyrillic script both pass). Sixteen of sixteen non-Chinese runs
completed; four of four Chinese-individual runs were blocked. The most plausible reading is that a large
database of Chinese individuals plus identity-matching code pattern-matches to mass-surveillance concerns in
the provider's output classifier.

**Consequence for this task.** The real agentic runs blocked ~100% because the register contains Chinese
individuals, and Chinese romanization (pinyin, Wade-Giles, Cantonese, Hokkien/Teochew) is one of the task's
central difficulty axes. Removing Chinese individuals is the only change the evidence predicts would let
Claude Code complete; it costs one hard variation axis but the Arabic/Persian/Cyrillic transliteration,
name-order, nasab, alias, entity and vessel machinery remains, which is hard on its own (earlier versions
were Arabic-heavy and agents still failed). This is the basis for a possible v5.

## Resolution (v6): keep the difficulty, lose the trigger

The root cause and the difficulty were the same thing seen from two sides. The filter blocks generating code
that matches Chinese **individuals** at scale; the difficulty that defeated the agents on the held-out batch
was Chinese romanization's **arbitrary, lookup-based** surname mappings (Zhang / Cheung / Chang / Teo), which
cannot be derived by rule the way Arabic or Cyrillic transliteration can. Removing Chinese individuals lifted
the filter but also made the task solvable: a control run of Claude Code on the Chinese-free task completed
in 151 minutes and scored reward 1.0 (`results/v5-9a05110/`).

The fix separates the two. A further probe showed Chinese **entities and vessels** do not trip the filter
(4/4 completed at high context), because the sensitive signal is identifying *people*, not companies. So v6:

- removes Chinese individuals (the trigger), and
- reintroduces the arbitrary-lookup difficulty through Chinese-named **companies**: the watchlist lists them
  in pinyin, the sample and batch A show them in pinyin, and batch B holds out their Wade-Giles, Cantonese and
  Hokkien stem spellings (so a listed "Zhu Freight" must be matched to a batch-B customer's "Chu Freight" that
  the agent never saw). The reference solution canonicalizes entity stems by pinyin reading-set intersection.

This keeps the task in the author's sanctions-screening domain, hard for the same reason it was always hard,
and lets Claude Code run to completion. The v6 confirmatory Claude trial completed with no filter block and
scored reward 0 — a genuine model failure (batch B recall 0.916, entity-suffix recall 0.610), archived under
`results/v6-e668f1a/`. The full v6 trial matrix (three Claude, three Codex, both cheat runs) is recorded there.
