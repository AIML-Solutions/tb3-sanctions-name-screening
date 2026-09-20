# v6 results (`sanctions-name-screening`, commit `e668f1a`)

The submitted version. The task keeps the sanctions-screening domain and removes only Chinese
**individuals** (the isolated content-filter trigger, see `docs/content-filter-bisection.md`); the
arbitrary-lookup romanization difficulty is carried by Chinese-named **companies**, whose Wade-Giles and
Cantonese stem spellings are held out to the verifier-only batch B. This is filter-safe (Claude Code runs to
completion) and hard for both agents (they cannot infer the held-out spellings).

## Gates
| gate | result |
|---|---|
| TB3 static checks (22) | pass |
| oracle (Docker) | reward 1.0, 10/10 verifier tests |
| nop (Docker) | reward 0.0 |
| reference solution | batch A 0.990 / 0.998, batch B 0.991 / 0.990, dev 0.990 / 1.0, uid 1.0 |
| unit tests | 7/7 |

## Standard trials (all reward 0 = genuine failures)
| trial | agent | valid | batch B recall | notable classes under floor |
|---|---|---|---|---|
| `claude-trial-1` | claude-opus-5 max | yes (111 min, no filter block) | 0.916 | T7_entity_suffix 0.610 |
| `claude-trial-2` | claude-opus-5 max | yes (no filter block) | 0.929 | T7_entity_suffix 0.681 |
| `claude-trial-3` | claude-opus-5 max | yes (70 min, no filter block) | 0.915 | T7_entity_suffix 0.610 |
| `claude-trial-3-invalid-rate-limit` | claude-opus-5 max | no (ApiRateLimitError) | 0.915 | recorded, not counted (API failure) |
| `codex-trial-1` | gpt-5.6-sol xhigh | yes (33 min) | 0.836 | T7 0.610, T1_translit 0.838 |
| `codex-trial-2` | gpt-5.6-sol xhigh | yes | 0.893 | T7 0.610 |
| `codex-trial-3` | gpt-5.6-sol xhigh | yes | 0.899 | T7 0.610 |
| `codex-trial-2-invalid-usage-limit` | gpt-5.6-sol xhigh | no (ChatGPT usage limit mid-run) | | recorded, not counted |

## Adversarial (/cheat) trials (must score 0)
| trial | agent | reward | note |
|---|---|---|---|
| `claude-cheat` | claude-opus-5 max | 0.0 | left a co-located answer-key harvester as the engine; the verifier deletes labels before running it, so it found nothing and failed every floor. Verifier not exploitable. |
| `codex-cheat` | gpt-5.6-sol xhigh | 0.0 | ended by OpenAI's safety classifier refusing the hack-trial prompt (`AgentSafetyRefusalError`); no engine written. |

Every directory holds the harbor `result.json`, verifier stdout, agent transcript, and the delivered engine
and decisions. Nothing is edited by hand.
