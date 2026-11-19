# claude-context-budget

A small Python tool that reads your own Claude Code logs, shows where your tokens went, and estimates what the same work would have cost with cheaper habits.

## The problem

Claude re-sends the whole conversation on every step. A session that has grown to 400k tokens pays for those 400k tokens again on each tool call. Cost follows how long the session is, not how much work you asked for.

Most advice says "pick a cheaper model". On my own logs, the length of the session mattered far more than the model.

## What it found on my usage

One month of my Claude Code logs: Oct 19 to Nov 19, 2026, 39,275 API calls, 90 sessions.

| Result | Value | Kind |
|---|---|---|
| Cost at API list prices | US$5,179 | computed from measured tokens |
| Spend on calls with a prompt over 200k tokens | 76% | computed |
| Sessions that ever passed 200k tokens | 24 of 90 (measured), holding 95% of spend | computed |
| Largest single session | 50% of spend; median prompt 463k tokens (measured) | computed |
| Spend by token type | cache reads 56%, cache writes 28%, output 15%, fresh input under 1% | computed |
| Subagents | 7.2% of spend | computed |
| Prompt size of a brand-new session | 85k tokens (median) | measured |

I am on a subscription, so US$5,179 is not what I paid. It is what the same tokens cost at list prices, which makes sessions and models comparable.

### What-if results

`simulate.py` replays the same calls under different habits:

| Habit | Cost | Saved |
|---|---|---|
| As logged | $5,179 | |
| Start a new session past 300k tokens | $3,543 | 31.6% |
| Start a new session past 200k tokens | $3,356 | 35.2% |
| Start a new session past 150k tokens | $3,595 | 30.6% |
| Run subagents on Sonnet 5.5 | $4,976 | 3.9% |
| 200k cap + Sonnet subagents | $3,154 | 39.1% |
| 200k cap + Sonnet subagents + 30k less startup overhead | $2,921 | 43.6% |

These are estimates, not measurements. They depend on the assumptions listed under [How the simulator works](#how-the-simulator-works). The 30k startup saving in the last row is assumed, not yet shown to be achievable.

Three results worth noting:

1. **A checkpoint is not free.** A new session has to write its starting prompt to the cache again. That is why a 150k cap saves less than a 200k cap: it forces 1,211 restarts instead of 504.
2. **Cheap tokens still add up.** A cache read costs 5% of a normal input token on Opus 5.5, yet cache reads are 56% of the total, because every call re-reads the whole history.
3. **Subagent model choice was a small lever for me.** Subagents were 7.2% of my spend. Someone who delegates more will see a bigger number.

## Measured before and after

Claude Code already has the cap built in, as one setting. This line in `~/.claude/settings.json` makes it summarize the conversation before the prompt reaches 200k tokens:

```json
"autoCompactWindow": 200000
```

The same thing can be set inside a session with `/autocompact 200k`. Both are described in the [Claude Code docs](https://code.claude.com/docs/en/model-config.md#set-the-auto-compact-window).

My settings file has this line. From Nov 17 on, no prompt in my logs is above 170k tokens. On Nov 16, 19 of 1,396 calls still were, the largest at 251k. Before that, the median Opus 5.5 prompt was 370k. The table compares the main-conversation calls before Nov 16 with the calls from Nov 16 to Nov 19:

| Model | Period | Calls | US$ per call | of which cache reads | Median prompt |
|---|---|---|---|---|---|
| Opus 5.5 | before | 31,018 | 0.137 | 0.084 | 370k |
| Opus 5.5 | from Nov 16 | 1,891 | 0.075 | 0.026 | 136k |
| Fable 5.2 | before | 1,260 | 0.167 | 0.051 | 199k |
| Fable 5.2 | from Nov 16 | 874 | 0.155 | 0.026 | 135k |
| Sonnet 5.5 | before | 163 | 0.036 | 0.011 | 111k |
| Sonnet 5.5 | from Nov 16 | 156 | 0.041 | 0.012 | 126k |

Token counts and call counts are measured. Dollars are computed at list prices.

- **Opus 5.5: 45% cheaper per call.** This is where my long sessions were. Almost all of the drop is cache reads.
- **Fable 5.2: 7% cheaper per call.** Cache reads halved, but cache writes went up, so the net gain is small.
- **Sonnet 5.5: 14% more per call.** These sessions were never near the cap, so the cap had nothing to cut.

The comparison is per call and per model because the two periods hold different amounts of work and a different mix of models. Reproduce it with:

```
python analyze_usage.py --split 2026-11-16
```

Limits of this comparison:

- It is not a controlled test. The work before and after is not the same work, and the second period is only four days.
- I did not record the day I changed the setting. Nov 16 is the first day in the logs where almost no spend sits above 200k. That the setting caused the drop is my inference from the prompt sizes.

### Checking the simulator against real compactions

The same command lists the real compactions in the second period, which lets me check the simulator's assumptions:

| | Simulator | Logs from Nov 16 (67 compactions) |
|---|---|---|
| Prompt after a checkpoint | 104,801 tokens (85k measured start + 20k assumed) | 106,375 tokens, median, measured |
| Cache re-written after a checkpoint | 56,051 tokens (36k measured + 20k assumed) | 49,009 tokens, median, measured |

The assumed values are close to what happened, and the cache re-write is slightly on the costly side. Compaction started at a median prompt of 165,921 tokens. The first call after each compaction adds up to 13% of main-conversation spend in that period (computed), so a checkpoint is a real cost, not a rounding error.

After the cap, a typical prompt is about 136k tokens, and about 85k of that is there before I type anything. That startup prompt is now the largest part left to cut.

## Run it on your own logs

You need Python 3.9 or newer. No packages to install.

1. Download this folder and open a terminal in it.
2. Extract your usage. This only reads your logs in `~/.claude/projects`:
   ```
   python extract_usage.py
   ```
3. Run the simulator:
   ```
   python simulate.py
   ```
4. Optional: print the detailed report (per day, per model, per session):
   ```
   python analyze_usage.py
   ```

Useful options:

```
python simulate.py --cap 250 200            # try other caps, in thousands of tokens
python simulate.py --trim-startup 30        # also try a 30k smaller startup prompt
python simulate.py --since 2026-11-12       # only the last week
python analyze_usage.py --split 2026-11-16  # cost per call before and from a date
```

**Privacy:** everything stays on your machine. The extract step writes three files into **data/**, which is git-ignored because it holds the first 200 to 300 characters of your prompts.

## How the simulator works

For each main conversation it tracks a simulated prompt size. The simulated prompt grows by the same amount as the real one. When it passes the cap, the simulator charges a checkpoint and continues from a fresh session. Each call is then re-priced with the smaller prompt: new content costs the same, only the re-read history shrinks.

| Input | Kind | Value |
|---|---|---|
| Token counts per call | measured | from the `usage` field in the logs |
| Prices | published | **prices.py**, read from Anthropic's pricing page on 2026-11-19 |
| Size of a fresh session | measured | median first prompt of your sessions (85k for me) |
| Cache re-write of a fresh session | measured | median non-cached part of a first prompt (36k for me) |
| Summary written at a checkpoint | assumed | 4,000 output tokens |
| Context carried into the fresh session | assumed | 20,000 tokens (summary plus files read again) |
| Subagents on a cheaper model | assumed | same token counts as on the original model |

Limits:

- It assumes the work after a checkpoint takes the same calls and the same output as before. It does not model quality.
- Dollar figures use list prices. They are not a subscription bill.
- The assumed values sit at the top of **simulate.py**. Change them and re-run to see how much the result moves.

## Check the code

```
python test_simulate.py
```

It runs the price function, the simulator and the before and after helpers on hand-made calls with known answers, and prints `ok`.

## Files

- **extract_usage.py** reads the Claude Code logs and writes one row per API call to **data/usage.csv**.
- **prices.py** holds the price table and the function that turns tokens into dollars.
- **analyze_usage.py** prints the baseline report and, with `--split`, the before and after comparison.
- **simulate.py** runs the what-if comparison.
- **test_simulate.py** checks the three files above.

## Next

Not built yet:

- An audit of the startup prompt: what makes up the 85k tokens a new session begins with, and what can be removed.
- A `/delegate` command that hands one focused job to a subagent on a chosen model with a short brief, so the main chat never has to switch models.
- A short guide for picking the model and effort for a task.
- A longer before and after comparison once these are in daily use. The one above covers four days.

I planned a warning for sessions that pass the cap. I dropped it: the built-in setting above already does the job.

## About

Built by Andres Delascio, mechanical engineering grad. Human-led engineering with AI-assisted implementation (Claude Code). Every number above comes from running these scripts on my own logs.
