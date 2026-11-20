"""Controlled experiment: does a project file, a code map or a mid-task handoff change token usage?

The same scripted task (experiment_task.py) is run headlessly with `claude -p` in four set-ups ("arms"):
  A  nothing added
  B  a CLAUDE.md project file
  C  the same file plus a graphify code map
  D  the same file plus a handoff note and a fresh session halfway through
Everything else is held equal: same repo at a pinned tag, same model, same prompts, same tool
permissions, and the user's own CLAUDE.md, skills, plugins and MCP servers are kept out.

Token counts are MEASURED (logged by Claude Code for each API call). Dollars are COMPUTED at list
prices (prices.py). Each run really calls the model, so it uses your subscription or API credit.

Run:  python experiment.py --pilot          one run per arm
      python experiment.py --runs 3         three runs per arm
      python experiment.py --report DIR     print the table for a finished results folder again
Needs: the `claude` CLI logged in, git, and `graphify` on PATH for arm C.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

from experiment_task import LONG_PROMPTS, PROMPTS, REPO_TAG, REPO_URL
from prices import cost_parts

HERE = Path(__file__).parent
# --- configuration ---
MODEL = "claude-sonnet-5-5"   # pinned for every arm
ARMS = "ABCD"
LONG_ARMS = "EF"              # the 35-prompt task: E without a context cap, F with one
CAP_TOKENS = 200_000          # arm F: Claude Code summarises the conversation before it reaches this size
HANDOFF_AFTER = len(PROMPTS) // 2  # arm D: write the handoff after this many prompts, then start fresh
TURN_TIMEOUT_S = 1200         # give up on one prompt after 20 minutes
PYTEST = "pytest==8.3.4"      # click 8.1.7 turns warnings into errors, and newer pytest warns
TOOLS = "Bash,Read,Edit,Write,Glob,Grep"
WORK = Path(tempfile.gettempdir()) / "ccb-experiment"  # outside this repo, so no parent CLAUDE.md is picked up
OUT = HERE / "data" / "experiment"                     # git-ignored: it holds model output

PROJECT_FILE_PROMPT = (
    "Write a CLAUDE.md for this repository, at most 60 lines. Include only what a new contributor cannot "
    "see at a glance: how to run the tests, the conventions for code, tests and the changelog, where new "
    "public names must be exported, and any gotchas. Do not list the files one by one. Change nothing else.")
MAP_NOTE = (
    "\n## Code map\n"
    "A code graph of this repo is in graphify-out/. Read graphify-out/GRAPH_REPORT.md first. For "
    "\"where is\" and \"what calls\" questions run `graphify query \"<question>\"` or "
    "`graphify explain \"<symbol>\"`, and open source files only for the exact symbols you need.\n")
HANDOFF_PROMPT = (
    "Write HANDOFF.md for someone continuing this work in a new session with no memory of this one: what "
    "is done, which files changed, the conventions you followed, and how to run the tests. At most 40 lines.")
HANDOFF_PREFIX = "Read HANDOFF.md first; it describes the work done so far in this repo. Then: "


def run(cmd, cwd, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", **kw)


def child_env(venv):
    """Environment for the model's session: no CLAUDE* variables from a parent session, tests runnable as-is."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    env["PATH"] = str(venv_bin(venv)) + os.pathsep + env["PATH"]  # `python -m pytest` finds the pinned pytest
    env["PYTHONPATH"] = "src"                                     # ...and imports the workspace's own click
    return env


def venv_bin(venv):
    return venv / ("Scripts" if os.name == "nt" else "bin")


def ask(prompt, cwd, env, session=None, cap=None):
    """Send one prompt to a headless Claude Code session in `cwd`. Returns the CLI's result record."""
    home_md = Path.home() / ".claude"
    settings = {"claudeMdExcludes": [f"{home_md.as_posix()}/**"]}  # keep the user's own CLAUDE.md out
    if cap:
        settings["autoCompactWindow"] = cap  # Claude Code summarises the conversation when it nears this many tokens
    cmd = [shutil.which("claude"), "-p", "--model", MODEL, "--output-format", "json",
           "--setting-sources", "project", "--settings", json.dumps(settings),
           "--permission-mode", "acceptEdits", "--allowedTools", TOOLS, "--disallowedTools", "Agent,Task"]
    if session:
        cmd += ["--resume", session]
    try:
        p = run(cmd, cwd, env=env, input=prompt, timeout=TURN_TIMEOUT_S)  # prompt on stdin: no quoting problems
        return json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        return {"is_error": True, "result": f"no answer in {TURN_TIMEOUT_S} s", }
    except json.JSONDecodeError:
        return {"is_error": True, "result": (p.stdout + p.stderr)[-2000:]}


def setup():
    """Clone the pinned repo and make a venv with pytest, once. Returns (base repo, venv)."""
    base, venv = WORK / "base", WORK / "venv"
    WORK.mkdir(parents=True, exist_ok=True)
    if not base.exists():
        subprocess.run(["git", "clone", "-q", "--depth", "1", "--branch", REPO_TAG, REPO_URL, str(base)], check=True)
    if not venv.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        subprocess.run([str(venv_bin(venv) / "python"), "-m", "pip", "install", "-q", PYTEST], check=True)
    return base, venv


def score(ws, venv, long=False):
    """Quality of a finished workspace: the repo's own tests, and the task's checks."""
    env = child_env(venv)
    py = str(venv_bin(venv) / "python")
    tail = run([py, "-m", "pytest", "-q", "tests"], ws, env=env).stdout.strip().splitlines()[-1:]
    counts = dict((word, int(n)) for n, word in re.findall(r"(\d+) (passed|failed|error)", " ".join(tail)))
    done = run([py, str(HERE / "experiment_task.py")] + ["--long"] * long, ws, env=env).stdout.strip()
    return {"tests_passed": counts.get("passed", 0), "tests_failed": counts.get("failed", 0) + counts.get("error", 0),
            "checks": done}


def session_calls(session):
    """Read one session's transcript. Returns (token usage of every API call, tool calls that used the map, compactions).

    The CLI's JSON answer only itemises the last call of a prompt, so the transcript is the source.
    """
    calls, map_uses, compactions = {}, 0, 0  # message id -> usage; a message is logged once per content block, the last copy is complete
    for path in (Path.home() / ".claude" / "projects").glob(f"*/{session}.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            compactions += d.get("subtype") == "compact_boundary"  # the record Claude Code writes when it summarises
            if d.get("type") == "assistant" and "usage" in d.get("message", {}):
                calls[d["message"]["id"]] = d["message"]["usage"]
                # a `graphify ...` command or a read of graphify-out/ both have "graphify" in the tool input
                map_uses += sum(c["type"] == "tool_use" and "graphify" in json.dumps(c["input"]) for c in d["message"]["content"])
    return list(calls.values()), map_uses, compactions


def summarize(calls, turns=()):
    """Totals for one run. calls: usage of each API call (session_calls); turns: the CLI's answer to each prompt."""
    usd = 0.0
    for c in calls:
        cc = c.get("cache_creation") or {}
        usd += sum(cost_parts(MODEL, c["input_tokens"], cc.get("ephemeral_5m_input_tokens", 0),
                              cc.get("ephemeral_1h_input_tokens", 0), c["cache_read_input_tokens"], c["output_tokens"]))
    prompt = [c["input_tokens"] + c["cache_creation_input_tokens"] + c["cache_read_input_tokens"] for c in calls]
    return {"usd": usd, "calls": len(calls), "prompt_tokens": sum(prompt), "output_tokens": sum(c["output_tokens"] for c in calls),
            "max_prompt": max(prompt, default=0),  # largest context reached, tokens
            "errors": sum(bool(t.get("is_error")) for t in turns),
            "denied": sum(len(t.get("permission_denials") or []) for t in turns)}


def measure(turns):
    """Summary of the sessions behind `turns`, plus the CLI's own cost figure as a cross-check."""
    last = {t["session_id"]: t for t in turns if t.get("session_id")}  # total_cost_usd adds up across --resume
    read = [session_calls(s) for s in last]
    calls = [c for r in read for c in r[0]]
    return {**summarize(calls, turns), "cli_usd": sum(t.get("total_cost_usd", 0) for t in last.values()),
            "map_uses": sum(r[1] for r in read), "compactions": sum(r[2] for r in read), "calls_raw": calls}


def one_run(arm, n, base, venv, project_file, out):
    """Run the whole task once in one arm. Writes <out>/<arm><n>.json and returns its summary."""
    ws = WORK / "runs" / f"{out.name}-{arm}{n}"
    shutil.copytree(base, ws)
    if arm in "BCD":
        (ws / "CLAUDE.md").write_text(project_file + (MAP_NOTE if arm == "C" else ""), encoding="utf-8")
    if arm == "C":
        subprocess.run([shutil.which("graphify"), "update", "."], cwd=ws, capture_output=True, check=True)  # no model tokens
    env, turns, session = child_env(venv), [], None
    long, cap = arm in LONG_ARMS, CAP_TOKENS if arm == "F" else None
    for i, prompt in enumerate(LONG_PROMPTS if long else PROMPTS):
        if arm == "D" and i == HANDOFF_AFTER:
            turns.append(ask(HANDOFF_PROMPT, ws, env, session))
            session, prompt = None, HANDOFF_PREFIX + prompt
        t = ask(prompt, ws, env, session, cap)
        turns.append(t)
        session = t.get("session_id", session)
        if t.get("is_error"):
            break  # a failed turn would make the rest of the run meaningless
    result = {"arm": arm, "run": n, **measure(turns), **score(ws, venv, long), "turns": turns}
    (out / f"{arm}{n}.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result


def report(results, setup_usd=None):
    print(f"\n{'arm':4s}{'run':>4s}{'US$':>8s}{'CLI US$':>9s}{'calls':>7s}{'prompt tok':>12s}{'output tok':>11s}{'max prompt':>11s}"
          f"{'tests ok/bad':>14s}{'checks':>8s}{'errors':>7s}{'map uses':>9s}{'compactions':>12s}")
    for r in sorted(results, key=lambda r: (r["arm"], r["run"])):
        print(f"{r['arm']:4s}{r['run']:4d}{r['usd']:8.2f}{r['cli_usd']:9.2f}{r['calls']:7d}{r['prompt_tokens']:12,d}{r['output_tokens']:11,d}"
              f"{r['max_prompt']:11,d}{r['tests_passed']:>10d}/{r['tests_failed']:<3d}{r['checks']:>8s}{r['errors']:7d}{r.get('map_uses', '-'):>9}{r.get('compactions', '-'):>12}")
    if len(results) > len({r["arm"] for r in results}):
        print("\nmedian CLI US$ per arm (lowest .. highest run):")
        for arm in sorted({r["arm"] for r in results}):
            usd = sorted(r["cli_usd"] for r in results if r["arm"] == arm)
            print(f"  {arm}  {median(usd):6.2f}  ({usd[0]:.2f} .. {usd[-1]:.2f})")
    if setup_usd is not None:
        print(f"\nWriting the project file took one extra session: US${setup_usd:.2f} (COMPUTED), not included above.")
    print("Tokens MEASURED per API call (session transcripts); US$ COMPUTED at list prices; CLI US$ is the CLI's own "
          "figure; it also counts the summarising calls of a compaction, which the transcripts do not log. Tests: the repo's own suite. Checks: experiment_task.py. "
          "Map uses: tool calls that ran graphify or read its output.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pilot", action="store_true", help="one run per arm")
    ap.add_argument("--runs", type=int, default=1, metavar="N", help="runs per arm (default 1)")
    ap.add_argument("--arms", default=ARMS, help=f"which arms to run (default {ARMS}; {LONG_ARMS} is the context-cap test)")
    ap.add_argument("--report", metavar="DIR", help="only print the table for a finished results folder")
    args = ap.parse_args()
    if args.report:
        return report([json.loads(p.read_text(encoding="utf-8")) for p in Path(args.report).glob("[A-F]*.json")])

    base, venv = setup()
    out = OUT / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    # The project file is written once, by the model, on a throwaway copy, and reused by arms B, C and D.
    scratch = WORK / "runs" / f"{out.name}-setup"
    shutil.copytree(base, scratch)
    made, project_file = None, ""
    if set(args.arms) & set("BCD"):  # arms A, E and F use no project file
        made = ask(PROJECT_FILE_PROMPT, scratch, child_env(venv))
        project_file = (scratch / "CLAUDE.md").read_text(encoding="utf-8")
        (out / "CLAUDE.md").write_text(project_file, encoding="utf-8")
        (out / "setup.json").write_text(json.dumps(made, indent=1), encoding="utf-8")

    # Arms run side by side (same tokens, less waiting); runs of one arm are spread across the rounds.
    results = []
    for n in range(1, (1 if args.pilot else args.runs) + 1):
        with ThreadPoolExecutor(len(args.arms)) as pool:
            results += pool.map(lambda arm: one_run(arm, n, base, venv, project_file, out), args.arms)
    report(results, measure([made])["usd"] if made else None)
    print(f"Raw records: {out}")


if __name__ == "__main__":
    main()
