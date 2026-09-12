# Recorded runs

Each directory holds the harbor `result.json` (reward, timings, token counts) and the verifier's
stdout for one run, plus the agent transcript for agent trials. Directory names carry the task
version (git commit) the run evaluated. Nothing here is edited by hand.

| directory | run | reward |
|---|---|---|
| `v1-faf2ab7/oracle` | reference solution, Docker | 1.0 |
| `v1-faf2ab7/nop` | no-op agent, Docker | 0.0 |
| `v1-faf2ab7/codex-trial-1` | Codex gpt-5.6-sol xhigh, trial 1 of 3 (trials 2-3 stopped after this pass) | 1.0 |
| `v1-faf2ab7/rubric-verdicts.json` | TB3 rubric review of v1 (26 pass / 6 fail / 3 n/a) | |
| `v2-73478fb/oracle` | reference solution, Docker | 1.0 |
| `v2-73478fb/nop` | no-op agent, Docker | 0.0 |
