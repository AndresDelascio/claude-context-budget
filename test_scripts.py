"""Checks for every script in this repo on hand-made inputs with known answers. Run:  python test_scripts.py"""
import contextlib
import csv
import io
import json
import tempfile
from math import isclose
from pathlib import Path

import extract_usage
from analyze_usage import compactions, load, per_call, per_prompt, price, reprice
from audit_startup import first_request
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


def test_per_call():
    # Two Opus main calls with 100k and 300k of cached history, plus a subagent call that must be left out.
    rows = [price(call(100_000, write=0)), price(call(300_000, write=0)), price(call(30_000, model=FABLE, subagent=1))]
    opus = per_call(rows)
    assert list(opus) == [OPUS] and opus[OPUS]["calls"] == 2
    assert isclose(opus[OPUS]["read"], 0.04)        # mean of 100k and 300k tokens at $0.20 per million
    assert isclose(opus[OPUS]["out"], 0.01)         # 500 output tokens at $20 per million
    assert isclose(opus[OPUS]["usd"], 0.04 + 0.01 + 10 * 4e-6)  # plus 10 fresh input tokens at $4 per million
    assert opus[OPUS]["prompt"] == 200_010          # median prompt, tokens


def test_reprice():
    # One call: 100k cached tokens read, 10 fresh input tokens, 500 output tokens.
    usd = reprice([call(100_000, write=0)], (OPUS, "claude-sonnet-5-5", "claude-haiku-5-5"))
    assert isclose(usd[OPUS], 0.02 + 0.01 + 10 * 4e-6)
    assert isclose(usd["claude-sonnet-5-5"], 0.01 + 0.005 + 10 * 2e-6)  # half of Opus on every price
    assert isclose(usd["claude-haiku-5-5"], 5 * (0.001 + 0.00025 + 10 * 1e-7))  # prompt over 100k tokens: 5x


def test_compactions():
    # Prompt goes 100k -> 150k -> 60k: only the last step is a drop below 70%. ts gives the call order.
    rows = [dict(price(call(n)), ts=f"2026-01-01T00:0{i}") for i, n in enumerate((100_000, 150_000, 60_000))]
    assert [(a["cache_read"], b["cache_read"]) for a, b in compactions(rows)] == [(150_000, 60_000)]


def test_per_prompt():
    # Session s1: prompt at minute 1, then a main call and a subagent call; prompt at minute 5, then one main call.
    # A call at minute 0 has no prompt before it and is left out. Session s2 has a call but no typed prompt.
    def at(minute, **kw):
        return dict(price(call(100_000, write=0, **kw)), ts=f"2026-01-01T00:0{minute}")
    rows = [at(0), at(2), at(3, model=FABLE, subagent=1), at(6), at(2, session="s2")]
    turns = [{"ts": "2026-01-01T00:01", "session": "s1"}, {"ts": "2026-01-01T00:05", "session": "s1"}]
    first, second = sorted(per_prompt(rows, turns), key=lambda p: p["ts"])
    assert (first["calls"], second["calls"]) == (2, 1)
    assert first["model"] == second["model"] == OPUS            # the subagent's model does not name the prompt
    assert isclose(first["usd"], rows[1]["w"] + rows[2]["w"]) and isclose(second["usd"], rows[3]["w"])


def test_first_request():
    # A made-up session log: tool definitions and system prompt, one skills list, one message, then the first reply.
    tools = [{"name": "Read"}, {"name": "mcp__maps__find"}, {"name": "mcp__maps__route"}]
    log = [
        {"type": "api-request-shape", "shape": {"system": [{"text": "s" * 100}], "tools": tools}},
        {"type": "attachment", "attachment": {"type": "skill_listing", "content": "- cad-a: x\n- cad-b: y\n- kit:z"}},
        {"type": "api-request-blob", "message": {"content": [{"type": "text", "text": "m" * 50}]}},
        {"type": "assistant", "message": {"model": "m", "usage": {"input_tokens": 5, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 75}}},
    ]
    parts, tokens, _ = first_request(json.dumps(d) for d in log)
    size = {}
    for group, member, chars in parts:
        size[group, member] = size.get((group, member), 0) + chars
    assert tokens == 100                                                   # 5 + 20 + 75
    assert size["system prompt", ""] == 100
    assert size["skills list", "cad-*"] == 16 and size["skills list", "kit:*"] == 5   # two cad skills share a row
    assert size["tool definitions", "server maps"] == sum(len(json.dumps(t)) for t in tools[1:])
    assert size["first message and other context", ""] == 50 - 21          # message text minus the skills list inside it
    assert first_request(json.dumps(d) for d in log[1:]) is None           # no request record: nothing to size


def test_experiment_summarize():
    # Two API calls, each: 10 fresh input tokens, 100k cached tokens read, 500 output tokens, on Sonnet 5.5.
    from experiment import summarize
    c = {"input_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100_000, "output_tokens": 500}
    s = summarize([c, c], turns=[{}, {"is_error": True}])
    assert isclose(s["usd"], 2 * (0.01 + 0.005 + 10 * 2e-6))  # same prices as test_reprice
    assert (s["calls"], s["prompt_tokens"], s["max_prompt"], s["output_tokens"], s["errors"]) == (2, 200_020, 100_010, 1_000, 1)


def test_date_range_uses_true_session_starts():
    # A date range that begins mid-session: its first call is a 252k prompt, not a fresh start.
    tail = MAIN[100:]
    cost, n = simulate(tail, cap=150_000)  # sized from the range itself: "fresh" looks bigger than the cap
    assert n == 0 and isclose(cost, sum(call_cost(r) for r in tail))
    cost, n = simulate(tail, cap=150_000, starts=MAIN[:1])  # sized from the session's real first call (52k)
    assert n > 0 and cost < sum(call_cost(r) for r in tail)


def test_load_leaves_out_unpriced_models():
    with tempfile.TemporaryDirectory() as tmp:
        cols = "ts,project,session,subagent,agent_file,model,in,out,cache_write_5m,cache_write_1h,cache_read,tools,fast"
        Path(tmp, "usage.csv").write_text(
            f"{cols}\nt1,p,s,0,,{OPUS},10,500,0,0,0,,0\nt2,p,s,0,,some-old-model,10,500,0,0,0,,0\n", encoding="utf-8")
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            rows = load(Path(tmp))
        assert [r["model"] for r in rows] == [OPUS] and "some-old-model" in said.getvalue()
        try:
            load(Path(tmp, "missing"))
            raise AssertionError("a missing usage.csv should stop with a message")
        except SystemExit as e:
            assert "extract_usage.py" in str(e)


def test_extract():
    def line(**d):
        return json.dumps(d, separators=(",", ":")) + "\n"  # Claude Code writes compact JSON

    def reply(mid, out, block, w=300, w1h=200):
        usage = {"input_tokens": 5, "output_tokens": out, "cache_read_input_tokens": 1_000,
                 "cache_creation_input_tokens": w, "cache_creation": {"ephemeral_1h_input_tokens": w1h}}
        return line(type="assistant", timestamp="2026-01-01T00:00:0" + mid[-1],
                    message={"id": mid, "model": OPUS, "usage": usage, "content": [block]})

    tool = {"type": "tool_use", "id": "t1", "name": "Read"}
    with tempfile.TemporaryDirectory() as tmp:
        logs, out = Path(tmp, "logs"), Path(tmp, "out")
        (logs / "proj" / "s2" / "subagents").mkdir(parents=True)
        # One API call logged as two blocks (the second has the final output count) after one typed prompt.
        (logs / "proj" / "s1.jsonl").write_text(
            line(type="user", timestamp="2026-01-01T00:00:00", message={"content": "fix the bug"})
            + reply("m1", 10, {"type": "text", "text": "ok"}) + reply("m1", 50, tool) + "not json\n", encoding="utf-8")
        (logs / "proj" / "s2.jsonl").write_text(reply("m1", 50, tool), encoding="utf-8")  # resumed: same call again
        (logs / "proj" / "s2" / "subagents" / "agent-a.jsonl").write_text(reply("m2", 7, {**tool, "id": "t2", "name": "Bash"}, w=0, w1h=0), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            extract_usage.main(logs, out)
        m1, m2 = csv.DictReader((out / "usage.csv").open(encoding="utf-8"))
        assert (m1["in"], m1["out"], m1["cache_write_1h"], m1["cache_write_5m"], m1["cache_read"]) == ("5", "50", "200", "100", "1000")
        assert m1["tools"] == "Read" and m1["subagent"] == "0"         # counted once, though logged three times
        assert (m2["session"], m2["subagent"], m2["tools"]) == ("s2", "1", "Bash")
        assert [t["text"] for t in json.loads((out / "turns.json").read_text(encoding="utf-8"))] == ["fix the bug"]
        try:
            extract_usage.main(Path(tmp, "empty"), out)
            raise AssertionError("no logs should stop with a message")
        except SystemExit as e:
            assert "No API calls" in str(e)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
