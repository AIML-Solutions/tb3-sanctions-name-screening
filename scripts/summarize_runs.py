#!/usr/bin/env python3
"""Summarize harbor job directories into a markdown table for the README.

    python3 scripts/summarize_runs.py <harbor-output-dir> [job-name ...]

Each job directory holds config.json (agents + tasks) and one directory per
trial with result.json (reward, tokens, timings) and verifier/ctrf.json.
"""

import json
import sys
from datetime import datetime
from pathlib import Path


def _dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def trial_rows(job_dir: Path):
    job_cfg = json.loads((job_dir / "config.json").read_text()) if (job_dir / "config.json").exists() else {}
    agents = job_cfg.get("agents") or [{}]
    agent = agents[0]
    for trial in sorted(p for p in job_dir.iterdir() if p.is_dir()):
        result_file = trial / "result.json"
        if not result_file.exists():
            continue
        try:
            result = json.loads(result_file.read_text())
        except json.JSONDecodeError:
            result = {"exception_info": {"exception_type": "unreadable result.json"}}
        verifier = result.get("verifier_result") or {}
        reward = (verifier.get("rewards") or {}).get("reward")
        ctrf = trial / "verifier" / "ctrf.json"
        tests = ""
        if ctrf.exists():
            summary = json.loads(ctrf.read_text()).get("results", {}).get("summary", {})
            tests = f"{summary.get('passed', 0)}/{summary.get('tests', 0)}"
        ar = result.get("agent_result") or {}
        exe = result.get("agent_execution") or {}
        start, end = _dt(exe.get("started_at")), _dt(exe.get("finished_at"))
        minutes = f"{(end - start).total_seconds() / 60:.0f}" if start and end else ""
        exc = result.get("exception_info") or {}
        yield {
            "trial": trial.name.split("__")[-1],
            "agent": agent.get("name", "?"),
            "model": agent.get("model_name") or "",
            "reward": reward,
            "tests": tests,
            "minutes": minutes,
            "tokens": f"{(ar.get('n_input_tokens') or 0) / 1e6:.1f}M in / {(ar.get('n_output_tokens') or 0) / 1e3:.0f}k out"
            if ar.get("n_input_tokens") else "",
            "exception": exc.get("exception_type", "") if exc else "",
        }


def main():
    out = Path(sys.argv[1])
    jobs = sys.argv[2:] or sorted(p.name for p in out.iterdir() if p.is_dir())
    print("| job | trial | agent | model | reward | tests passed | agent minutes | tokens | exception |")
    print("|---|---|---|---|---|---|---|---|---|")
    for job in jobs:
        for r in trial_rows(out / job):
            print(f"| {job} | {r['trial']} | {r['agent']} | {r['model']} | {r['reward']} | {r['tests']} | "
                  f"{r['minutes']} | {r['tokens']} | {r['exception']} |")


if __name__ == "__main__":
    main()
