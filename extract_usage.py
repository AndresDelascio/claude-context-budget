"""Extract one row per API call from Claude Code's local transcripts.

Reads ~/.claude/projects/**/*.jsonl (read-only) and writes three files into data/:
usage.csv (one row per API call), prompts.json (first prompt of each session) and
turns.json (every typed prompt, cut to 200 characters). data/ is git-ignored because
it holds your own prompt text. All token counts are MEASURED (copied from the `usage`
field the API returned).

Run:  python extract_usage.py
"""
import csv
import json
from pathlib import Path

LOG_ROOT = Path.home() / ".claude" / "projects"
OUT_DIR = Path(__file__).parent / "data"


def main(log_root=LOG_ROOT, out_dir=OUT_DIR):
    calls = {}    # message id -> row; one API call is logged once per content block, so dedupe
    seen_tools = set()  # tool call ids; a resumed session copies old messages into a new file
    prompts = {}  # session id -> first thing the user typed
    turns = []    # every prompt the user typed
    for path in log_root.rglob("*.jsonl"):
        rel = path.relative_to(log_root)
        project = rel.parts[0]
        is_subagent_file = "subagents" in rel.parts
        # main file is <session>.jsonl; subagent files live in <session>/subagents/
        session = rel.parts[1] if is_subagent_file else path.stem
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"usage"' in line and '"assistant"' in line:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    m = d.get("message") or {}
                    u = m.get("usage")
                    if not u or not m.get("id") or m.get("model") == "<synthetic>":
                        continue
                    cc = u.get("cache_creation") or {}
                    tools = []
                    for b in m.get("content", []):
                        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") not in seen_tools:
                            seen_tools.add(b.get("id"))
                            tools.append(b["name"])
                    row = calls.setdefault(m["id"], {
                        "ts": d.get("timestamp", ""), "project": project, "session": session,
                        "subagent": int(is_subagent_file or bool(d.get("isSidechain"))),
                        "agent_file": path.stem if is_subagent_file else "",
                        "model": m.get("model", ""), "in": 0, "out": 0,
                        "cache_write_5m": 0, "cache_write_1h": 0, "cache_read": 0, "tools": "",
                        "fast": int(u.get("speed") == "fast"),  # fast mode is billed at 2x
                    })
                    w = u.get("cache_creation_input_tokens") or 0
                    w1h = cc.get("ephemeral_1h_input_tokens") or 0
                    row["in"] = max(row["in"], u.get("input_tokens") or 0)
                    row["out"] = max(row["out"], u.get("output_tokens") or 0)  # last block has the final count
                    row["cache_write_1h"] = max(row["cache_write_1h"], w1h)
                    row["cache_write_5m"] = max(row["cache_write_5m"], w - w1h)
                    row["cache_read"] = max(row["cache_read"], u.get("cache_read_input_tokens") or 0)
                    if tools:
                        row["tools"] = "|".join(filter(None, [row["tools"], *tools]))
                elif (not is_subagent_file and '"tool_result"' not in line
                      and line.startswith('{') and '"type":"user"' in line and len(line) < 200_000):
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    c = (d.get("message") or {}).get("content")
                    if isinstance(c, list):
                        c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                    if (isinstance(c, str) and c.strip() and not c.lstrip().startswith("<")
                            and not d.get("isMeta") and not d.get("isSidechain")):
                        prompts.setdefault(session, c.strip()[:300])
                        # every typed prompt, so spend can be grouped per user turn
                        turns.append({"ts": d.get("timestamp", ""), "session": session,
                                      "chars": len(c), "text": c.strip()[:200]})

    rows = sorted(calls.values(), key=lambda r: r["ts"])
    if not rows:
        raise SystemExit(f"No API calls found under {log_root}. Use Claude Code first, then run this again.")
    out_dir.mkdir(exist_ok=True)
    with (out_dir / "usage.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out_dir / "prompts.json").write_text(json.dumps(prompts, indent=1), encoding="utf-8")
    (out_dir / "turns.json").write_text(json.dumps(sorted(turns, key=lambda t: t["ts"]), indent=1), encoding="utf-8")
    print(f"{len(rows)} API calls, {len(turns)} typed prompts, {len(prompts)} sessions, {rows[0]['ts'][:10]} .. {rows[-1]['ts'][:10]}")


if __name__ == "__main__":
    main()
