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

## The fix (version 4, `tasks/archive-record-linkage`)

The same task with the same names, rules, generator logic, verifier and floors, framed as linking newly
digitised records to an archive register: `register.json` / `records.csv` / `link.py`, `record_id`,
`AR-` uids, `document` identifiers instead of passports, a `collections` field (port ledgers, passenger
manifests, ...) instead of program codes, neutral nicknames and entity stems, and one surname swapped
(Nasrallah to Saadallah, keeping the Allah-compound rule). Sanctions vocabulary appears nowhere the agent
can read. The reference solution clears every bar on the regenerated data (A 0.996 / 1.000, B 0.998 / 0.998).
The substance, and the author's domain, is still sanctions screening; the README says so.
