"""Checks for prices.py and simulate.py on hand-made calls. Run:  python test_simulate.py"""
from math import isclose

from prices import cost_parts
from simulate import CARRY_TOKENS, call_cost, simulate

OPUS, FABLE, SONNET, HAIKU = "claude-opus-5-5", "claude-fable-5-2", "claude-sonnet-5-5", "claude-haiku-5-5"


def call(read, session="s1", model=OPUS, subagent=0, write=2_000):
    r = {"session": session, "model": model, "subagent": subagent, "fast": 0, "in": 10, "out": 500,
         "cache_write_5m": 0, "cache_write_1h": write, "cache_read": read}
    r["ctx"] = r["in"] + write + read  # prompt size, tokens
    return r


# One main conversation whose prompt grows 52k -> 400k by 2k per call (175 calls; the real logs
# grow by about 1-2k per call), plus five Fable subagent calls.
MAIN = [call(read) for read in range(50_000, 400_000, 2_000)]
SUBS = [call(30_000, model=FABLE, subagent=1) for _ in range(5)]
ROWS = MAIN + SUBS
BASE = sum(call_cost(r) for r in ROWS)


def test_prices():
    # Opus 5.5: 1M cache-read tokens = $0.20, 1M output tokens = $20
    parts = cost_parts(OPUS, 0, 0, 0, 1_000_000, 1_000_000)
    assert all(isclose(got, want) for got, want in zip(parts, (0, 20, 0, 0.20)))  # floats: compare with isclose
    # Haiku 5.5: a 200k prompt is over the 100k line, so input costs $0.50/M instead of $0.10/M
    assert isclose(cost_parts(HAIKU, 200_000, 0, 0, 0, 0)[0], 0.10)
    assert isclose(cost_parts(HAIKU, 50_000, 0, 0, 0, 0)[0], 0.005)
    # fast mode doubles the price
    assert isclose(cost_parts(OPUS, 0, 0, 0, 0, 1_000_000, fast=1)[1], 40)


def test_no_policy_is_baseline():
    # isclose, not ==: Python's sum() rounds differently from a running total (differs at 1e-15)
    for cost, n in (simulate(ROWS), simulate(ROWS, cap=1_000_000)):  # a cap nobody reaches changes nothing
        assert isclose(cost, BASE) and n == 0


def test_cap():
    # Fresh session = 52,010 (first prompt) + CARRY = 72,010. The prompt passes 150k at call 49, then
    # every 39 calls (72,010 + 39 x 2k) -> calls 49, 88, 127, 166 of 174 -> 4 checkpoints.
    assert CARRY_TOKENS == 20_000, "the call numbers above assume a 20k carry"
    cost, n = simulate(ROWS, cap=150_000)
    assert n == 4 and cost < BASE


def test_checkpoints_have_a_price():
    # Same climb in 10k jumps: only 8 calls between checkpoints, too few to pay back the cache
    # re-write of each fresh session, so here the cap costs MORE than doing nothing.
    rows = [call(read) for read in range(50_000, 400_000, 10_000)]
    cost, n = simulate(rows, cap=150_000)
    assert n == 4 and cost > sum(call_cost(r) for r in rows)


def test_real_compaction_is_followed():
    # grows to 310k, really compacts to 62k, grows to 110k: only the first climb needs checkpoints
    rows = [call(r) for r in range(50_000, 310_000, 2_000)] + [call(r) for r in range(60_000, 110_000, 2_000)]
    _, n = simulate(rows, cap=150_000)
    assert n == 3  # calls 49, 88, 127 of the 129-call first climb; none after the real compaction


def test_subagent_reprice():
    saved_per_call = call_cost(SUBS[0]) - call_cost(SUBS[0], SONNET)
    assert saved_per_call > 0
    assert isclose(simulate(ROWS, sub_model=SONNET)[0], BASE - 5 * saved_per_call)
    haiku_subs = [call(30_000, model=HAIKU, subagent=1)]
    assert isclose(simulate(haiku_subs, sub_model=SONNET)[0], call_cost(haiku_subs[0]))  # never re-priced upward


def test_trim():
    assert simulate(ROWS, trim=10_000)[0] < BASE


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
