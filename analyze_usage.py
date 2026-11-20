"""Baseline + spike report from usage.csv (made by extract_usage.py).

Unit: US$ "API-equivalent cost" = MEASURED token counts x list prices (prices.py).
COMPUTED, and not a bill: on a subscription plan you pay a flat fee instead.

Run:  python analyze_usage.py
      python analyze_usage.py --split 2026-11-16   (cost per call before and from that date)
"""
import argparse
import bisect
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from prices import PRICES, cost_parts

DATA = Path(__file__).parent / "data"
PARTS = ("in", "out", "write", "read")
MIN_CALLS = 100  # --split skips a model with fewer calls than this in either period: too few to compare
MIN_PROMPTS = 20  # same for the per-prompt table, in typed prompts
CURRENT = ("claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")  # models compared by reprice()
SCRATCH_MARK = "scratch-workspaces"  # a project folder with this in its name is shown by its last part only (long temp paths)
DROP = 0.7  # a prompt below 70% of the previous call's prompt counts as a compaction (context was summarized)


def price(r):
    """Add to one call: US$ per part (p_*), total US$ (w) and prompt size in tokens (ctx)."""
    r["p_in"], r["p_out"], r["p_write"], r["p_read"] = cost_parts(
        r["model"], r["in"], r["cache_write_5m"], r["cache_write_1h"], r["cache_read"], r["out"], r["fast"])
    r["w"] = r["p_in"] + r["p_out"] + r["p_write"] + r["p_read"]
    r["ctx"] = r["in"] + r["cache_write_5m"] + r["cache_write_1h"] + r["cache_read"]
    return r


def load(data=DATA):
    """Read usage.csv and price every call. Calls on a model that prices.py does not list are left out."""
    if not (data / "usage.csv").exists():
        raise SystemExit(f"{data / 'usage.csv'} not found. Run python extract_usage.py first.")
    rows = list(csv.DictReader((data / "usage.csv").open(encoding="utf-8")))
    priced = [r for r in rows if r["model"] in PRICES]
    if len(priced) < len(rows):  # say so instead of failing or guessing a price
        print(f"Left out {len(rows) - len(priced)} of {len(rows)} calls on models not in prices.py: "
              + ", ".join(sorted({r["model"] for r in rows} - set(PRICES))) + "\n")
    for r in priced:
        for k in ("in", "out", "cache_write_5m", "cache_write_1h", "cache_read", "subagent", "fast"):
            r[k] = int(r[k])
        price(r)
        if SCRATCH_MARK in r["project"]:
            r["project"] = r["project"].split("scratch-")[-1]
    return priced


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


def per_prompt(rows, turns):
    """One record per typed prompt: its UTC time, the model that answered, US$ and API calls it set off.

    A call (main conversation or subagent) belongs to the last prompt typed before it in the same
    session, so this is the cost of getting one request done, not of one step. `turns` is turns.json.
    Calls made before a session's first typed prompt are left out.
    """
    typed = {s: sorted(t["ts"] for t in ts) for s, ts in group(turns, lambda t: t["session"]).items()}
    out = {}
    for r in sorted(rows, key=lambda r: r["ts"]):
        i = bisect.bisect_right(typed.get(r["session"], []), r["ts"]) - 1  # last prompt at or before this call
        if i < 0:
            continue
        p = out.setdefault((r["session"], i), {"ts": typed[r["session"]][i], "model": None, "usd": 0.0, "calls": 0})
        p["usd"] += r["w"]
        p["calls"] += 1
        if p["model"] is None and not r["subagent"]:
            p["model"] = r["model"]  # the first main-conversation call is the one that answered
    return [p for p in out.values() if p["model"]]


def compactions(rows):
    """(call before, call after) for each main-conversation call whose prompt fell below DROP x the previous one."""
    pairs = []
    for rs in group([r for r in rows if not r["subagent"]], lambda r: (r["session"], r["model"])).values():
        rs = sorted(rs, key=lambda r: r["ts"])
        pairs += [(a, b) for a, b in zip(rs, rs[1:]) if b["ctx"] < DROP * a["ctx"]]
    return pairs


def reprice(rows, models=CURRENT):
    """US$ for the same calls at each model's list price, standard speed.
    ASSUMES the token counts would not change with the model; in practice they do."""
    return {m: sum(sum(cost_parts(m, r["in"], r["cache_write_5m"], r["cache_write_1h"], r["cache_read"], r["out"]))
                   for r in rows) for m in models}


def before_after(rows, split, turns=()):
    """Print main-conversation cost per call, then cost per typed prompt, before and from `split` (a UTC date), per model.

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

    # Per typed prompt: a cheaper call is no saving if the same request now takes more calls.
    prompts = group(per_prompt(rows, turns), lambda p: p["model"])
    print("Per typed prompt (main and subagent calls it set off). US$ COMPUTED, counts MEASURED.\n")
    print(f"{'model':11s} {'period':7s} {'prompts':>7s} {'median $':>9s} {'mean $':>8s} {'calls/prompt':>13s}")
    for model, ps in sorted(prompts.items()):
        b, a = [p for p in ps if p["ts"] < split], [p for p in ps if p["ts"] >= split]
        if min(len(b), len(a)) < MIN_PROMPTS:
            continue
        stats = [(median(p["usd"] for p in x), sum(p["usd"] for p in x) / len(x), sum(p["calls"] for p in x) / len(x))
                 for x in (b, a)]
        for period, x, (med, mean, calls) in zip(("before", "after"), (b, a), stats):
            print(f"{model.removeprefix('claude-'):11s} {period:7s} {len(x):7,d} {med:9.2f} {mean:8.2f} {calls:13.1f}")
        print(f"{'':11s} change  {'':7s} " + " ".join(
            f"{100 * (after / before - 1):+{w}.0f}%" for w, before, after in zip((8, 7, 12), *stats)) + "\n")

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
        return before_after(rows, args.split, json.loads((DATA / "turns.json").read_text(encoding="utf-8")))
    prompts = json.loads((DATA / "prompts.json").read_text(encoding="utf-8"))
    total = sum(r["w"] for r in rows)
    print(f"TOTAL {usd(total)} API-equivalent, {len(rows)} calls | {mix(rows)}")

    print("\n== per day ==")
    for day, rs in sorted(group(rows, lambda r: r["ts"][:10]).items()):
        w = sum(r["w"] for r in rs)
        sub = sum(r["w"] for r in rs if r["subagent"])
        print(f"{day} {usd(w)} sub {100 * sub / w:3.0f}%  {'#' * int(w / total * 200)}")

    table("per model, main vs subagent", group(rows, lambda r: (r["model"], "SUB" if r["subagent"] else "main")), extra=mix)
    table("per project", group(rows, lambda r: r["project"]))
    table("top hours (UTC)", group(rows, lambda r: r["ts"][:13]), 12,
          lambda rs: f"sub {100 * sum(r['w'] for r in rs if r['subagent']) / sum(r['w'] for r in rs):.0f}% | {mix(rs)} | "
                     + ",".join(sorted({r["project"][:28] for r in rs})))

    print("\n== top sessions ==")
    for s, rs in sorted(group(rows, lambda r: r["session"]).items(), key=lambda kv: -sum(r["w"] for r in kv[1]))[:12]:
        w = sum(r["w"] for r in rs)
        main_rs = [r for r in rs if not r["subagent"]]
        sub_rs = [r for r in rs if r["subagent"]]
        agents = group(sub_rs, lambda r: r["agent_file"])
        models = {m: round(100 * sum(r["w"] for r in x) / w) for m, x in group(rs, lambda r: (r["model"][7:], "S" if r["subagent"] else "m")).items()}
        print(f"\n{usd(w)} ({100 * w / total:.0f}% of all) {s[:8]} {rs[0]['project'][:40]}  {rs[0]['ts'][:16]} -> {rs[-1]['ts'][:16]}")
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

    # The model choice in dollars: identical calls, four price lists
    print("\n== the same calls at each model's prices (assumes equal token counts) ==")
    for title, rs in (("all calls", rows), ("subagent calls only", [r for r in rows if r["subagent"]])):
        costs = reprice(rs)
        low = costs["claude-sonnet-5-5"]
        print(f"{title}: " + "  ".join(f"{m[7:]} {usd(c).strip()} ({c / low:.1f}x Sonnet)" for m, c in costs.items()))


if __name__ == "__main__":
    main()
