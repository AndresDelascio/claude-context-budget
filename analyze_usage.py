"""Baseline + spike report from usage.csv (made by extract_usage.py).

Unit: US$ "API-equivalent cost" = MEASURED token counts x list prices (prices.py).
COMPUTED, and not a bill: on a subscription plan you pay a flat fee instead.

Run:  python analyze_usage.py
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

from prices import cost_parts

DATA = Path(__file__).parent / "data"
PARTS = ("in", "out", "write", "read")


def load():
    rows = list(csv.DictReader((DATA / "usage.csv").open(encoding="utf-8")))
    for r in rows:
        for k in ("in", "out", "cache_write_5m", "cache_write_1h", "cache_read", "subagent", "fast"):
            r[k] = int(r[k])
        r["p_in"], r["p_out"], r["p_write"], r["p_read"] = cost_parts(
            r["model"], r["in"], r["cache_write_5m"], r["cache_write_1h"], r["cache_read"], r["out"], r["fast"])
        r["w"] = r["p_in"] + r["p_out"] + r["p_write"] + r["p_read"]
        r["ctx"] = r["in"] + r["cache_write_5m"] + r["cache_write_1h"] + r["cache_read"]  # prompt size, tokens
        r["proj"] = r["project"].split("scratch-")[-1] if "scratch-workspaces" in r["project"] else r["project"]
    return rows


def group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[key(r)].append(r)
    return g


def usd(x):
    return f"${x:10,.2f}"


def mix(rs):
    """Share of cost by component, e.g. 'in 0% out 12% write 30% read 58%'."""
    tot = sum(r["w"] for r in rs) or 1
    return " ".join(f"{p} {100 * sum(r['p_' + p] for r in rs) / tot:.0f}%" for p in PARTS)


def table(title, g, n=15, extra=lambda rs: ""):
    print(f"\n== {title} ==")
    for k, rs in sorted(g.items(), key=lambda kv: -sum(r["w"] for r in kv[1]))[:n]:
        print(f"{usd(sum(r['w'] for r in rs))} {len(rs):6d} calls  {k}  {extra(rs)}")


def main():
    rows = load()
    prompts = json.loads((DATA / "prompts.json").read_text(encoding="utf-8"))
    total = sum(r["w"] for r in rows)
    print(f"TOTAL {usd(total)} API-equivalent, {len(rows)} calls | {mix(rows)}")

    print("\n== per day ==")
    for day, rs in sorted(group(rows, lambda r: r["ts"][:10]).items()):
        w = sum(r["w"] for r in rs)
        sub = sum(r["w"] for r in rs if r["subagent"])
        print(f"{day} {usd(w)} sub {100 * sub / w:3.0f}%  {'#' * int(w / total * 200)}")

    table("per model, main vs subagent", group(rows, lambda r: (r["model"], "SUB" if r["subagent"] else "main")), extra=mix)
    table("per project", group(rows, lambda r: r["proj"]))
    table("top hours (UTC)", group(rows, lambda r: r["ts"][:13]), 12,
          lambda rs: f"sub {100 * sum(r['w'] for r in rs if r['subagent']) / sum(r['w'] for r in rs):.0f}% | {mix(rs)} | "
                     + ",".join(sorted({r['proj'][:28] for r in rs})))

    print("\n== top sessions ==")
    for s, rs in sorted(group(rows, lambda r: r["session"]).items(), key=lambda kv: -sum(r["w"] for r in kv[1]))[:12]:
        w = sum(r["w"] for r in rs)
        main_rs = [r for r in rs if not r["subagent"]]
        sub_rs = [r for r in rs if r["subagent"]]
        agents = group(sub_rs, lambda r: r["agent_file"])
        models = {m: round(100 * sum(r["w"] for r in x) / w) for m, x in group(rs, lambda r: (r["model"][7:], "S" if r["subagent"] else "m")).items()}
        print(f"\n{usd(w)} ({100 * w / total:.0f}% of all) {s[:8]} {rs[0]['proj'][:40]}  {rs[0]['ts'][:16]} -> {rs[-1]['ts'][:16]}")
        print(f"   calls main {len(main_rs)} / sub {len(sub_rs)} in {len(agents)} agents | {mix(rs)}")
        print(f"   models {models}")
        if main_rs:
            ctx = sorted(r["ctx"] for r in main_rs)
            print(f"   main prompt size (tokens): median {ctx[len(ctx) // 2] / 1e3:.0f}k  max {ctx[-1] / 1e3:.0f}k")
        print(f"   first prompt: {prompts.get(s, '?')[:160]!r}")

    # Cache rebuilds: a call that re-writes a big prompt instead of reading it (idle gap, compaction, model switch)
    big = [r for r in rows if r["cache_write_5m"] + r["cache_write_1h"] > 100_000]
    print(f"\n== cache rebuilds >100k tokens: {len(big)} calls, {usd(sum(r['p_write'] for r in big))} = "
          f"{100 * sum(r['p_write'] for r in big) / total:.0f}% of all ==")

    # How much of main-thread spend happens at each prompt size
    print("\n== main-thread spend by prompt size ==")
    main_rows = [r for r in rows if not r["subagent"]]
    mt = sum(r["w"] for r in main_rows)
    for lo, hi in ((0, 50), (50, 100), (100, 200), (200, 400), (400, 10_000)):
        rs = [r for r in main_rows if lo * 1000 <= r["ctx"] < hi * 1000]
        print(f"{lo:4d}-{hi:<5d}k {100 * sum(r['w'] for r in rs) / mt:3.0f}%  {len(rs)} calls")

    table("tools called (by spend of the calling turn)", group([r for r in rows if r["tools"]], lambda r: r["tools"].split("|")[0]), 12)


if __name__ == "__main__":
    main()
