# Content-filter experiments (author-run, headless Claude Code, claude-opus-5, Max subscription)

Purpose: after the Claude Code trial died on `API Error: 400 Output blocked by content filtering policy`
at its first attempt to write the engine, determine whether the task's wording (sanctions screening) or
the engine code itself trips the filter.

| variant | wording | outcome |
|---|---|---|
| `orig` | the task as written | 12 tool calls, ~30 min of analysis, then blocked at the engine write. No `screen.py`. |
| `reskin` | same data, same policy rules and verifier; every occurrence of sanctions / watchlist / screening replaced by identity resolution / registry / duplicate-account wording | 14 tool calls, ~44 min, then blocked at the engine write. No `screen.py`. |

Conclusion: the filter reacts to the engine (multilingual name-transliteration code and tables), not to the
framing. Any solution to this task has to produce that code, so Claude Code trials on the current API cannot
complete regardless of wording. Three reproductions (one harbor trial, two experiments). The transcripts here
are the full `--output-format json` streams with the OAuth token redacted.
