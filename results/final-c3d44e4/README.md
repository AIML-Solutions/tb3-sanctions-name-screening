# Final results (`sanctions-name-screening`, commit `c3d44e4`)

The submitted version. An original Terminal-Bench 3 task: screen a customer batch against a sanctions
watchlist, and the verifier grades the agent's decisions on the visible batch and re-runs the agent's engine
on a hidden batch that uses romanization conventions named in the policy but absent from everything the agent
can read (Turkish/Indonesian/scientific/Polish spellings, and Chinese company names under Wade-Giles,
Cantonese and Hokkien romanization).

## Gates
| gate | result |
|---|---|
| TB3 static checks (22) | pass |
| implementation-rubric review | pass (fairness fix: the Chinese-company romanization axis is disclosed in the instruction and policy) |
| oracle (Docker) | reward 1.0, 10/10 verifier tests |
| nop (Docker) | reward 0.0 |
| reference solution | batch A ~0.991 / 0.998, batch B ~0.989 / 0.997, dev ~0.990 / 1.0, uid 1.0 |
| unit tests | 7/7 |

## Standard trials (TB3 CI defaults: Codex gpt-5.6-sol xhigh, Claude Code claude-opus-5 max, 3 each)

| trial | agent | valid | reward | batch B recall | classes under floor |
|---|---|---|---|---|---|
| `codex-trial-1` | codex xhigh | yes | 0.0 | 0.911 | T1_translit 0.899, T7_entity 0.891 |
| `codex-trial-2` | codex xhigh | yes | 0.0 | 0.917 | T1_translit 0.899 |
| `codex-trial-3` | codex xhigh | yes | 0.0 | 0.890 | T1_translit 0.868 |
| `claude-trial-1-PASSED` | claude-opus-5 max | yes | **1.0** | 0.988 | none (passed) |
| `claude-trial-2-PASSED` | claude-opus-5 max | yes | **1.0** | 0.992 | none (passed) |
| `claude-trial-3-PASSED` | claude-opus-5 max | yes | **1.0** | 0.993 | none (passed) |

**Codex fails all three; Claude Code solves the task all three.** This is the honest result. See
`analysis/FAILURE_ANALYSIS.md` and `docs/content-filter-bisection.md` for the two findings behind it: the
content filter that blocks Chinese-individual matching (resolved by moving the difficulty to Chinese
companies), and the finding that Claude Code at max effort is at or above the fair-difficulty ceiling for
this task, so a rubric-compliant version does not reliably defeat it, while it defeats Codex.

## Adversarial (/cheat) trials (must score 0)
| trial | agent | reward | note |
|---|---|---|---|
| `codex-cheat` | codex xhigh | 0.0 | ended by OpenAI's safety classifier refusing the hack-trial prompt; no engine written |
| `claude-cheat` | claude-opus-5 max | 0.0 | completed the adversarial run, found no bypass, and left a genuine engine that then failed batch B recall (9/10 tests pass, overall-recall[B] fails). The verifier is not gameable. |

Every directory holds the harbor `result.json`, verifier stdout, agent transcript, and the delivered engine
and decisions. Nothing is edited by hand.
