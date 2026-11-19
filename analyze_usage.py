"""Baseline + spike report from usage.csv (made by extract_usage.py).

Unit: US$ "API-equivalent cost" = MEASURED token counts x list prices (prices.py).
COMPUTED, and not a bill: on a subscription plan you pay a flat fee instead.

Run:  python analyze_usage.py
      python analyze_usage.py --split 2026-11-16   (cost per call before and from that date)
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from prices import cost_parts

DATA = Path(__file__).parent / "data"
PARTS = ("in", "out", "write", "read")
MIN_CALLS = 100  # --split skips a model with fewer calls than this in either period: too few to compare
DROP = 0.7  # a prompt below 70% of the previous call's prompt counts as a compaction (context was summarized)


def price(r):
    """Add to one call: US$ per part (p_*), total US$ (w) and prompt size in tokens (ctx)."""
    r["p_in"], r["p_out"], r["p_write"], r["p_read"] = cost_parts(
        r["model"], r["in"], r["cache_write_5m"], r["cache_write_1h"], r["cache_read"], r["out"], r["fast"])
    r["w"] = r["p_in"] + r["p_out"] + r["p_write"] + r["p_read"]
    r["ctx"] = r["in"] + r["cache_write_5m"] + r["cache_write_1h"] + r["cache_read"]
    return r


def load():
    rows = list(csv.DictReader((DATA / "usage.csv").open(encoding="utf-8")))
    for r in rows:
        for k in ("in", "out", "cache_write_5m", "cache_write_1h", "cache_read", "subagent", "fast"):
            r[k] = int(r[k])
        price(r)
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


def per_call(rows):
    """Main-conversation averages per model: US$ per call (usd, read, write, out) and median prompt in tokens."""
    out = {}
    for model, rs in group([r for r in rows if not r["subagent"]], lambda r: r["model"]).items():
        n = len(rs)
        out[model] = {"calls": n, "usd": sum(r["w"] for r in rs) / n, "prompt": median(r["ctx"] for r in rs),
                      **{p: sum(r["p_" + p] for r in rs) / n for p in ("read", "write", "out")}}
    return out


def compactions(rows):
    """(call before, call after) for each main-conversation call whose prompt fell below DROP x the previous one."""
    pairs = []
    for rs in group([r for r in rows if not r["subagent"]], lambda r: (r["session"], r["model"])).values():
        rs = sorted(rs, key=lambda r: r["ts"])
        pairs += [(a, b) for a, b in zip(rs, rs[1:]) if b["ctx"] < DROP * a["ctx"]]
    return pairs


def before_after(rows, split):
    """Print main-conversation cost per call before and from `split` (a UTC date), per model.

    Per call and per model, because the amount of work and the model mix differ between the two
    periods. One model has the same prices in both, so a lower number means cheaper calls.
    """
    before = per_call([r for r in rows if r["ts"] < split])  # ISO timestamps compare as text
    after = per_call([r for r in rows if r["ts"] >= split])
    print(f"Main-conversation calls before / from {split} (UTC). US$ per call at list prices, COMPUTED from MEASURED tokens.")
    print("Not a controlled test: the work in the two periods is not the same.\n")
    print(f"{'model':11s} {'period':7s} {'calls':>7s} {'$/call':>7s} {'read':>6s} {'write':>6s} {'out':>6s} {'median prompt':>14s}")
    for model in sorted(before.keys() & after.keys()):
        b, a = before[model], after[model]
        if min(b["calls"], a["calls"]) < MIN_CALLS:
            continue
        for period, s in (("before", b), ("after", a)):
            print(f"{model.removeprefix('claude-'):11s} {period:7s} {s['calls']:7,d} {s['usd']:7.3f} "
                  f"{s['read']:6.3f} {s['write']:6.3f} {s['out']:6.3f} {s['prompt']:14,.0f}")
        print(f"{'':11s} change  {'':7s} {100 * (a['usd'] / b['usd'] - 1):+6.0f}%\n")

    # What a real compaction costs, to check the simulator's checkpoint assumptions against the logs
    late = [r for r in rows if r["ts"] >= split and not r["subagent"]]
    pairs = compactions(late)
    if pairs:
        first = [b for _, b in pairs]  # first call after each compaction
        print(f"Compactions from {split}: {len(pairs)} in {len(late):,d} main calls (MEASURED)")
        print(f"  prompt before, median tokens       {median(a['ctx'] for a, _ in pairs):9,.0f}")
        print(f"  prompt after, median tokens        {median(b['ctx'] for b in first):9,.0f}")
        print(f"  cache re-written, median tokens    {median(b['cache_write_5m'] + b['cache_write_1h'] for b in first):9,.0f}")
        print(f"  first call after, share of spend   {100 * sum(b['w'] for b in first) / sum(r['w'] for r in late):8.0f}%  (COMPUTED)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", metavar="YYYY-MM-DD", help="only print cost per call before and from this UTC date")
    args = ap.parse_args()
    rows = load()
    if args.split:
        return before_after(rows, args.split)
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
