"""What-if simulator: re-price your real Claude Code usage under cheaper habits.

Every API call re-sends the whole conversation, so a long session pays for its
history again on every step. This script replays the calls in data/usage.csv and
asks: what would the same work have cost if
  1. long conversations had been checkpointed into a fresh session at a size cap,
  2. subagents had run on a cheaper model,
  3. every session had started with less fixed overhead?

Token counts are MEASURED (from your logs). Dollars are COMPUTED at list prices
(prices.py). The policy results also depend on the ASSUMED values below.

Run:  python simulate.py            (after python extract_usage.py)
      python simulate.py --since 2026-11-12 --cap 200 --trim-startup 30
      python simulate.py --sensitivity --cap 200   (how much the two assumed values matter)
      python simulate.py --data sample             (made-up data, to try it without logs)
"""
import argparse
from statistics import median

from pathlib import Path

from analyze_usage import DATA, load
from prices import PRICES, cost_parts

# --- ASSUMED values (not measured). Change them here. ---
SUMMARY_OUT_TOKENS = 4_000  # tokens Claude writes for the hand-off summary at a checkpoint
CARRY_TOKENS = 20_000       # summary + files re-read at the start of the fresh session
SUBAGENT_MODEL = "claude-sonnet-5-5"  # the cheaper model subagents are re-priced on
# --- reporting ---
SWEEP_SUMMARY = (1_000, 4_000, 16_000)         # --sensitivity tries these summary sizes (tokens)...
SWEEP_CARRY = (5_000, 20_000, 50_000, 100_000)  # ...against these carried-over sizes (tokens)
SCORE_CTX_TOKENS = 200_000  # score = share of spend on calls with a prompt larger than this


def call_cost(r, model=None, prompt=None):
    """US$ of call r, optionally on another model and/or with its prompt resized to `prompt` tokens."""
    n_in, w5m, w1h, read = r["in"], r["cache_write_5m"], r["cache_write_1h"], r["cache_read"]
    if prompt is not None and prompt != r["ctx"]:
        new = n_in + w5m + w1h  # content that was not in the cache yet
        if new <= prompt:
            read = prompt - new  # new content stays the same; only the re-read history shrinks
        else:  # a full cache rebuild bigger than the simulated prompt: scale it down
            k = prompt / new
            n_in, w5m, w1h, read = n_in * k, w5m * k, w1h * k, 0
    return sum(cost_parts(model or r["model"], n_in, w5m, w1h, read, r["out"], r["fast"] and not model))


def session_starts(rows):
    """The first main-conversation call of each session in `rows`."""
    first = {}
    for r in rows:
        if not r["subagent"]:
            first.setdefault(r["session"], r)
    return list(first.values())


def simulate(rows, cap=None, sub_model=None, trim=0, starts=None):
    """Cost of the same calls under a policy. Returns (US$, number of checkpoints).

    starts:    the calls that size a fresh session (default: the first call of each session in `rows`).
               Pass the true session starts when `rows` is a date range: a session that began before
               the range would otherwise count a mid-session prompt as a fresh start.

    rows:      calls in time order (from analyze_usage.load)
    cap:       a main conversation is checkpointed into a fresh session when its prompt passes `cap` tokens
    sub_model: subagent calls on a pricier model are re-priced on this one (ASSUMES the same token counts)
    trim:      every prompt is `trim` tokens smaller (leaner startup: fewer tools, skills, instructions)
    """
    first = session_starts(rows) if starts is None else starts
    # A fresh session starts at the typical MEASURED startup prompt plus what the checkpoint carries over.
    # Only part of that prompt is written to the cache again; the rest (system prompt, tools) is still
    # cached from earlier sessions, so `fresh_write` is the MEASURED non-cached part of a first call.
    fresh = fresh_write = CARRY_TOKENS
    if first:
        fresh += max(median(r["ctx"] for r in first) - trim, 0)
        fresh_write = min(fresh, fresh_write + median(r["ctx"] - r["cache_read"] for r in first))

    total, checkpoints = 0.0, 0
    threads = {}  # (session, model) -> (real prompt size, simulated prompt size) at its previous call
    for r in rows:
        ctx = max(r["ctx"] - trim, 0)
        if r["subagent"]:
            cheaper = sub_model and PRICES[sub_model][0] < PRICES[r["model"]][0]  # never re-price upward
            total += call_cost(r, sub_model if cheaper else None, ctx)
            continue
        sim = ctx
        if cap:
            key = (r["session"], r["model"])  # caches are per model, so each model is its own thread
            real_prev, sim_prev = threads.get(key, (0, 0))
            # Real prompt grew: the simulated one grows by the same amount.
            # Real prompt shrank (a real /compact or /clear): follow it down, never above the real size.
            sim = sim_prev + ctx - real_prev if ctx >= real_prev else min(sim_prev, ctx)
            if sim > cap and fresh < cap:
                # A checkpoint is not free: one call reads the old context and writes a summary, then
                # the fresh session writes the non-cached part of its starting prompt to the cache.
                # ponytail: those written tokens are also charged as a read below, so savings are
                # slightly understated; model the first fresh call exactly if that ever matters.
                total += sum(cost_parts(r["model"], 0, 0, fresh_write, sim_prev, SUMMARY_OUT_TOKENS, r["fast"]))
                checkpoints += 1
                sim = fresh
            threads[key] = (ctx, sim)
        total += call_cost(r, None, sim)
    return total, checkpoints


def sensitivity(rows, cap, starts=None):
    """Print the saving of one cap for each pair of the two ASSUMED checkpoint values."""
    global SUMMARY_OUT_TOKENS, CARRY_TOKENS
    keep = SUMMARY_OUT_TOKENS, CARRY_TOKENS
    base, _ = simulate(rows)
    print(f"Saved by a new session past {cap // 1000}k tokens (checkpoints in brackets), by ASSUMED value:")
    print(f"{'summary / carried over':>24s}" + "".join(f"{c:>16,d}" for c in SWEEP_CARRY))
    for SUMMARY_OUT_TOKENS in SWEEP_SUMMARY:
        cells = []
        for CARRY_TOKENS in SWEEP_CARRY:
            cost, n = simulate(rows, cap=cap, starts=starts)
            cells.append(f"{100 * (1 - cost / base):.1f}% ({n})")
        print(f"{SUMMARY_OUT_TOKENS:>24,d}" + "".join(f"{c:>16s}" for c in cells))
    SUMMARY_OUT_TOKENS, CARRY_TOKENS = keep


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cap", type=int, nargs="+", default=[300, 200, 150], metavar="K",
                    help="context caps to try, in thousands of tokens (default: 300 200 150)")
    ap.add_argument("--trim-startup", type=int, default=0, metavar="K",
                    help="also try prompts this many thousand tokens smaller (leaner startup)")
    ap.add_argument("--since", default="", metavar="YYYY-MM-DD", help="only calls on or after this UTC date")
    ap.add_argument("--until", default="9999-12-31", metavar="YYYY-MM-DD", help="only calls before this UTC date")
    ap.add_argument("--without-top", type=int, default=0, metavar="N",
                    help="leave out the N costliest sessions, to see how much the result depends on them")
    ap.add_argument("--sensitivity", action="store_true",
                    help="only print how the saving of each --cap moves with the two assumed checkpoint values")
    ap.add_argument("--data", type=Path, default=DATA, metavar="DIR", help="folder with usage.csv (default: data)")
    args = ap.parse_args()

    every = load(args.data)
    rows = [r for r in every if args.since <= r["ts"] < args.until]  # ISO timestamps compare as text
    if not rows:
        raise SystemExit("no calls in that date range")
    # True session starts that fall in the range; a range with none falls back to all of them.
    starts = [r for r in session_starts(every) if args.since <= r["ts"] < args.until] or session_starts(every)
    if args.without_top:
        spend = {}
        for r in rows:
            spend[r["session"]] = spend.get(r["session"], 0) + r["w"]
        top = set(sorted(spend, key=spend.get, reverse=True)[:args.without_top])
        print(f"Left out the {len(top)} costliest session(s): ${sum(spend[s] for s in top):,.2f}, "
              f"{100 * sum(spend[s] for s in top) / sum(spend.values()):.0f}% of the period (COMPUTED)")
        rows = [r for r in rows if r["session"] not in top]
        starts = [r for r in starts if r["session"] not in top] or starts
    if args.sensitivity:
        for c in args.cap:
            sensitivity(rows, c * 1000, starts)
        return
    sub = SUBAGENT_MODEL.removeprefix("claude-")
    trim = args.trim_startup * 1000
    policies = [("as logged", {})]
    policies += [(f"new session past {c}k context", {"cap": c * 1000}) for c in args.cap]
    policies += [(f"subagents on {sub}", {"sub_model": SUBAGENT_MODEL})]
    if trim:
        policies += [(f"startup {args.trim_startup}k tokens smaller", {"trim": trim})]
    policies += [(f"{c}k cap + {sub} subagents" + (" + smaller startup" if trim else ""),
                  {"cap": c * 1000, "sub_model": SUBAGENT_MODEL, "trim": trim}) for c in args.cap]

    base, _ = simulate(rows)  # same running total as the policy rows, so "as logged" shows exactly 0.0%
    print(f"{len(rows)} API calls, {rows[0]['ts'][:10]} .. {rows[-1]['ts'][:10]} (UTC)")
    print("Cost = US$ at API list prices, COMPUTED from MEASURED tokens. Not a subscription bill.\n")
    print(f"{'policy':50s} {'cost':>11s} {'saved':>6s}  checkpoints")
    for label, kw in policies:
        cost, n = simulate(rows, starts=starts, **kw)
        print(f"{label:50s} ${cost:10,.2f} {100 * (1 - cost / base):5.1f}%  {n or ''}")
    big = sum(r["w"] for r in rows if not r["subagent"] and r["ctx"] > SCORE_CTX_TOKENS)
    print(f"\nScore: {100 * big / base:.0f}% of spend was on main-conversation calls with a prompt over "
          f"{SCORE_CTX_TOKENS // 1000}k tokens (lower is better)")
    print(f"ASSUMED: checkpoint summary {SUMMARY_OUT_TOKENS} output tokens, fresh session carries "
          f"{CARRY_TOKENS} tokens, subagents use the same tokens on {sub}.")


if __name__ == "__main__":
    main()
