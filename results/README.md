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
| `v3-2ebb652/claude-trial-invalid-content-filter-1` | Claude Code claude-opus-5 max on v3; **not a valid trial**: after 30 min of analysis (16 tool calls) the agent's first attempt to write the engine was rejected by the API with `400 Output blocked by content filtering policy`; the session ended with no `/app/screen.py`, and harbor raised on the missing artifact. API failure, not a model failure. | n/a |
| `v3-2ebb652/codex-trial-invalid-usage-limit-4` | Codex gpt-5.6-sol xhigh on v3, fresh 5-hour window and a freshly reset weekly cap; **not a valid trial**: usage cap hit after 58 min, 25.7M input tokens. Both artifacts existed at cut-off and the verifier graded them: reward 0; batch B recall 0.9483 (T10 0.896, T13 0.870 under the floor), precision 0.998; batch A 0.867 (an intermediate decisions file). Second cut-off engine to fail batch B. | n/a (graded 0.0) |
| `v3.1-33430e6/oracle` | reference solution, Docker, v3.1 (batch A 3,058 rows); 10/10 | 1.0 |
| `v3.1-33430e6/nop` | no-op agent, Docker, v3.1 | 0.0 |
| `v3-2ebb652/claude-content-filter-experiments` | author-run headless Claude Code experiments: original wording and a benign re-wording both end in `400 Output blocked by content filtering policy` at the engine write (3/3 reproductions incl. the trial). See its README. | n/a |
| `v3.1-e8c3aa4/codex-trial-1` | **Codex gpt-5.6-sol xhigh, valid trial 1 of 3: reward 0.0.** 50 min, 69 commands, 19.0M input / 105k output tokens, no exception. Batch A: recall 0.9907, precision 1.0, uid 1.0 (pass). Batch B: recall 0.9241, precision 1.0; T1 0.870, T2 0.826, T3 0.897, T10 0.866, T11 0.814, T13 0.880 under the 0.90 floor (fail). The agent's own final note claims 1,324/1,324 on the dev sample. | 0.0 |
| `v3.1-e8c3aa4/codex-trial-2` | **Codex gpt-5.6-sol xhigh, valid trial 2 of 3: reward 0.0.** 40 min, 62 commands, 13.6M input / 93k output tokens, no exception. Batch A: recall 0.9990, precision 1.0 (pass). Batch B: recall 0.9419, precision 1.0; T2 0.899, T3 0.897, T10 0.881, T11 0.884, T13 0.860 under the 0.90 floor (fail). The agent implemented the four named conventions from their examples ("Ahmet/Cemal/Hüseyin/Kasım, Achmad/Joesoef, ... Tan/Lim/Ong/Goh/Teo") and reported dev 1,324/1,324. | 0.0 |
