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
| `v2-73478fb/rubric-verdicts.json` | TB3 rubric review of v2 (28 pass / 4 fail / 3 n/a); its leakage check found the surface-shape tells fixed in v2.1 | |
| `v2.1-413c554/oracle` | reference solution, Docker | 1.0 |
| `v2.1-413c554/nop` | no-op agent, Docker | 0.0 |
| `v2.1-413c554/codex-trial-1-invalid-usage-limit` | Codex gpt-5.6-sol xhigh; **not a valid trial**: the ChatGPT account's usage cap was hit after 21 min / 4.9M input tokens / 34 commands (`ApiUsageLimitError`), reward 0.0 by default. Kept because the transcript shows the agent's approach on v2.1 up to that point. Trials 2-3 were stopped before starting. | n/a |
| `v2.1-413c554/codex-trial-1` | Codex gpt-5.6-sol xhigh, valid trial: **reward 1.0** in 37 min, 108 commands, 24.1M input / 87k output tokens. Verifier: recall 0.9939, precision 0.9992, uid 1.0. Trials 2-3 stopped: the task must change again. | 1.0 |
| `v3-94d7e63/oracle` | reference solution, Docker; 10/10 verifier tests (batch A decisions + engine run on batch B as an unprivileged user) | 1.0 |
| `v3-94d7e63/nop` | no-op agent, Docker | 0.0 |
| `v3-94d7e63/cheat-probe-label-hunting-engine` | author-written probe, not an agent trial: an engine that walks /tests, /app, /tmp, /root, /home, /logs, /etc, /var for any `*label*.csv` and otherwise answers NO_MATCH, run through the real verifier as the oracle. Agent side: it sees only the public `dev/labels_dev.csv`. Verifier side: nothing (labels deleted before it runs; it runs as `nobody`), batch B recall 0.0. | 0.0 |
| `v3-2ebb652/oracle` | reference solution, Docker, hardened verifier; 10/10 | 1.0 |
| `v3-2ebb652/nop` | no-op agent, Docker, hardened verifier | 0.0 |
| `v3-2ebb652/codex-trial-invalid-usage-limit-2` | Codex gpt-5.6-sol xhigh on v3; **not a valid trial**: ChatGPT usage cap hit after 12 min (`ApiUsageLimitError`). Rerun scheduled for the next window. | n/a |
| `v3-2ebb652/codex-trial-invalid-usage-limit-3` | Codex gpt-5.6-sol xhigh on v3, launched on a freshly reset 5-hour window; **not a valid trial**: usage cap hit after 43 min, 79 commands, 22.9M input tokens (`ApiUsageLimitError`). Its `/app/screen.py` at cut-off survived as an artifact (`codex-engine-at-cutoff.py`); run through the real verifier afterwards it **passes batch A (recall 0.9753, precision 0.9969) and fails batch B (recall 0.9193; T1 0.861, T2 0.870, T3 0.879, T10 0.806, T11 0.884, T13 0.840)** while keeping precision 0.997 on B. Informative, not evidence: the agent had 43 of 240 minutes. | n/a |
