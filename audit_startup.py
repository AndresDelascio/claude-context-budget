"""Startup audit: what fills the prompt of a new session before you type anything.

Reads the first request of a Claude Code session from the logs and sizes each part of it.
Characters per part and the token total of the first prompt are MEASURED.
Tokens per part are ESTIMATED: the measured total is shared out in proportion to characters.

Run:  python audit_startup.py                 (your most recent session)
      python audit_startup.py path/to/session.jsonl
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

LOGS = Path.home() / ".claude" / "projects"
TOP = 6  # rows printed per group; the rest are summed into one "more" row
MCP = re.compile(r"mcp__(.+?)__")  # tools from an MCP server are named mcp__<server>__<tool>


def source(name, builtin=None):
    """Tool name -> 'server <name>' for an MCP tool, else `builtin` (default: the tool's own name)."""
    m = MCP.match(name)
    return f"server {m.group(1)}" if m else builtin or name


def skill_group(name):
    """'plugin:skill' -> 'plugin:*', 'roblox-ui' -> 'roblox-*', so a family of skills is one row."""
    return name.split(":")[0] + ":*" if ":" in name else name.split("-")[0] + "-*"


def first_request(lines):
    """Size the first request of one session.

    Returns (parts, tokens, about) or None if the log does not record the request.
    parts: list of (group, member, characters), MEASURED. tokens: size of the first prompt, MEASURED.
    """
    parts, shape, blob_chars = [], None, 0
    for line in lines:
        d = json.loads(line)
        kind = d.get("type")
        if kind == "api-request-shape" and shape is None:
            shape = d["shape"]  # system prompt and tool definitions, as sent
        elif kind == "api-request-blob":  # the messages sent with the first request
            c = d["message"]["content"]
            blob_chars += len(c) if isinstance(c, str) else sum(len(b.get("text", "")) for b in c)
        elif kind == "attachment":  # pieces the app adds to those messages, logged one by one
            a = d["attachment"]
            if a.get("type") == "skill_listing":
                for s in a["content"].removeprefix("- ").split("\n- "):
                    parts.append(("skills list", skill_group(s.split(": ")[0]), len(s)))
            elif a.get("type") == "deferred_tools_delta":
                parts += [("names of tools loaded on demand", source(n, "built-in"), len(n)) for n in a["addedNames"]]
            elif a.get("type") == "mcp_instructions_delta":
                parts += [("MCP server instructions", "server " + n, len(b)) for n, b in zip(a["addedNames"], a["addedBlocks"])]
            elif a.get("type") == "agent_listing_delta":
                parts.append(("subagent types list", "", sum(len(x) for x in a["addedLines"])))
            elif a.get("type") == "hook_success" and a.get("content"):
                parts.append(("hook output", a["hookName"], len(a["content"])))
            elif a.get("type") == "instructions":
                parts += [("instruction files", Path(f["path"].replace("\\", "/")).name, len(f["content"])) for f in a["files"]]
        elif kind == "assistant" and not d.get("isSidechain"):
            if shape is None:
                return None
            u = d["message"].get("usage") or {}
            tokens = u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0)
            rest = blob_chars - sum(n for _, _, n in parts)  # your first message, environment notes, wrappers
            parts.append(("first message and other context", "", max(rest, 0)))
            parts += [("system prompt", "", len(b["text"])) for b in shape["system"]]
            parts += [("tool definitions", source(t["name"]), len(json.dumps(t))) for t in shape["tools"]]
            return parts, tokens, f"{d.get('entrypoint')} {d.get('version')}, {d['message'].get('model')}"
    return None


def report(parts, tokens):
    total = sum(n for _, _, n in parts)
    groups = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # group -> member -> [characters, items]
    for g, m, n in parts:
        groups[g][m][0] += n
        groups[g][m][1] += 1
    print(f"{'part':46s} {'chars':>9s} {'share':>6s} {'est. tokens':>12s}")
    for g, members in sorted(groups.items(), key=lambda kv: -sum(v[0] for v in kv[1].values())):
        n = sum(v[0] for v in members.values())
        print(f"{g:46s} {n:9,d} {100 * n / total:5.0f}% {n * tokens / total:12,.0f}")
        rows = sorted(members.items(), key=lambda kv: -kv[1][0])
        if len(rows) > 1:
            for m, (chars, items) in rows[:TOP]:
                label = m[:34] + (f" ({items})" if items > 1 else "")
                print(f"    {label:42s} {chars:9,d} {'':6s} {chars * tokens / total:12,.0f}")
            if len(rows) > TOP:
                more = sum(v[0] for _, v in rows[TOP:])
                print(f"    {f'{len(rows) - TOP} more':42s} {more:9,d} {'':6s} {more * tokens / total:12,.0f}")
    print(f"{'total':46s} {total:9,d} {'100%':>6s} {tokens:12,d}  (token total MEASURED)")


def main():
    files = [Path(sys.argv[1])] if len(sys.argv) > 1 else sorted(LOGS.glob("*/*.jsonl"), key=lambda p: -p.stat().st_mtime)
    for f in files:
        with f.open(encoding="utf-8") as fh:
            found = first_request(fh)
        if found:
            parts, tokens, about = found
            print(f"Session {f.stem[:8]} ({about}). First prompt: {tokens:,d} tokens, MEASURED.")
            print("Characters are MEASURED. Tokens per part are ESTIMATED from the share of characters.\n")
            return report(parts, tokens)
    print("No session found whose log records the first request (needs a recent Claude Code version).")


if __name__ == "__main__":
    main()
