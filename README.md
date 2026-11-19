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

## What fills a new session

`audit_startup.py` reads the first request of a session from the logs and sizes each part of it. This is one of my sessions in the Claude desktop app on Nov 19, before I typed a word of real work:

| Part | Characters | Share | Tokens (estimated) |
|---|---|---|---|
| Tool definitions (53 tools) | 137,130 | 54% | 48,600 |
| System prompt | 36,544 | 14% | 13,000 |
| Skills list (97 skills) | 29,705 | 12% | 10,500 |
| First message and other context | 12,655 | 5% | 4,500 |
| Names of tools loaded on demand (268) | 11,309 | 4% | 4,000 |
| MCP server instructions | 10,198 | 4% | 3,600 |
| Hook output | 5,228 | 2% | 1,900 |
| Instruction files (`CLAUDE.md`) | 4,915 | 2% | 1,700 |
| Subagent types list | 4,502 | 2% | 1,600 |
| **Total** | 252,186 | 100% | **89,428 (measured)** |

Characters are measured. The total of 89,428 tokens is measured. Tokens per part are estimated: the measured total is shared out by characters.

What stands out:

- **Tool definitions are over half.** One built-in tool for publishing pages is 37,384 characters, about 13,000 tokens. The 19 tools of the built-in browser are another 22,433 characters.
- **My own instructions are small.** `CLAUDE.md` is 2% of the startup prompt. Trimming it would save almost nothing.
- **40 skills I installed for one project load in every project.** They sit in my personal skills folder and take 14,023 characters, about 5,000 tokens, in every session.
- **Connectors cost tokens even when unused.** One data connector I rarely use adds 67 tool names and its instructions: 6,712 characters, about 2,400 tokens.

Run it on your own most recent session:

```
python audit_startup.py
```

### First trim, measured

Skills in `~/.claude/skills/` load in all projects. Skills in `.claude/skills/` inside a project load only there ([skills docs](https://code.claude.com/docs/en/skills.md)). I moved the 40 one-project skills into that project and audited a new session in this folder:

| | Before | After |
|---|---|---|
| Skills in the list | 97 | 57 |
| Skills listed by name only, no description | 28 | 0 |
| Skills list, characters | 29,705 | 25,520 |

All three rows are measured.

- **The saving is smaller than I expected.** The 40 skills took 14,023 characters, but the list shrank by only 4,185, about 1,500 tokens (estimated).
- **The reason is a size budget.** Claude Code caps the skills list. With 97 skills mine was at the cap, so 28 skills were cut down to a bare name. With 40 gone, the freed room went back to those 28 descriptions.
- **The real gain is quality, not size.** Claude can now read what every installed skill is for. Before, it could not for 28 of them.

The first prompt of the test session was 85,156 tokens against 89,428 (both measured). Most of that drop is my shorter first message, not the trim, so I do not count it as a saving.

### Second trim, measured: a deny rule removes a tool, after a restart

A deny rule with a bare tool name removes that tool from the prompt ([permissions docs](https://code.claude.com/docs/en/permissions.md)). I put this in `.claude/settings.local.json` inside one project, so it applies only there:

```json
{
  "permissions": {
    "deny": ["Artifact"]
  }
}
```

`Artifact` is the 37,384-character publishing tool from the table above. For the test I also denied a second, smaller tool as a control.

| Request | Tools sent | Tool definitions, characters |
|---|---|---|
| New session, app not restarted | both tools still there | unchanged |
| Same project, after restarting the app | both tools gone, nothing else changed | 145,037 → 102,875 |

Both rows are measured from the logged requests.

- **A brand-new settings file needed an app restart.** A new session alone did not pick it up in the desktop app. Once the file was loaded, a later edit to it took effect in the running session: when I removed the control rule, that tool came back without a restart.
- **Denying the one tool removes 37,384 characters**, about 13,000 tokens (estimated) from every request in that project.
- **The cost:** Claude cannot publish pages from that project while the rule is on. Only deny tools you do not use there.

The second row comes from a session I resumed after the restart, not a brand-new one. The tool list is what was sent, so the character numbers hold, but I have not yet measured the token total of a new session with the rule on.

### Not tried yet

- An MCP server added at local scope loads only in that project ([MCP docs](https://code.claude.com/docs/en/mcp.md)).
- The skills docs describe a setting for the size budget of the skills list.

Limits of the audit:

- It is one session. My first prompts range from 73k to 95k tokens (measured, 83 sessions in November).
- Sharing tokens out by characters assumes every part has the same characters per token. Tool definitions are JSON and prose is not, so the per-part numbers can be off.
- All my sessions run in the desktop app. A terminal session loads fewer tools and will look different.
- It needs a recent Claude Code version. Older logs do not record the request.

## Delegate a job to a cheaper model

A subagent started from a chat on the top model runs on the top model too, unless told otherwise. `/delegate` is a small skill that hands one job to one subagent on the cheapest model that fits, so the main chat never has to switch models.

```
/delegate list every assumed constant in simulate.py
/delegate sonnet add a test for the --since option
```

What the skill tells Claude to do:

1. Pick the model. A word in front (`haiku`, `sonnet`, `opus`) forces it. Otherwise:

   | Job | Model |
   |---|---|
   | Find, list, count, look up, read and summarize, run a command and report | Haiku |
   | A well-specified edit, writing tests or docs | Sonnet |
   | Hard debugging, design, costly if wrong | Opus |

2. Write a brief of under 200 words: goal, files, what is already known, what done looks like, and a reply of at most 15 lines.
3. Start one subagent on that model and tell it not to start agents of its own.
4. Check the reply against the files before reporting, and say which model ran.

Install it for all your projects by copying one folder (PowerShell):

```powershell
Copy-Item -Recurse .claude\skills\delegate $HOME\.claude\skills\
```

### One measured run

I ran the steps of the skill once on the first example above, from a chat on Fable 5.2:

| | Value | Kind |
|---|---|---|
| Model the subagent ran on | Haiku 5.5 | measured |
| API calls | 4 | measured |
| Tokens | 56,695 cache write, 156,079 cache read, 2,168 output | measured |
| Agents started by the subagent | 0 | measured |
| Cost on Haiku 5.5 | US$0.01 | computed |
| Same tokens on Sonnet 5.5 | US$0.18 | computed, assumes the same token counts |
| Same tokens on Fable 5.2 | US$0.68 | computed, assumes the same token counts |

All four constants it reported were at the lines it gave. I checked them against the file.

Two things this run shows:

- **A subagent has its own startup cost.** Its first prompt was 47,954 tokens (measured) before it read anything. Delegating a tiny job does not pay. Delegating bulk reading does.
- **The model choice matters most per job, not per month.** This job was about 70 times cheaper on Haiku than on Fable. Subagents were still only 7.2% of my spend.

### The typed command, in a new session

I then typed `/delegate` in a new session on Fable 5.2 and asked it to run the tests. From that session's log, all measured:

- The subagent ran on Sonnet 5.5, in 3 API calls, and started no agents of its own.
- The brief was 191 words.
- The main chat re-ran the test command itself before reporting, and ended with `Ran on: sonnet.`

The subagent cost US$0.15 (computed), against US$0.60 for the same tokens on Fable 5.2. Its first prompt was 48,643 tokens.

That run also showed a flaw. "Run the tests" should have gone to Haiku, but the table said "tests" under Sonnet. I changed the rows to "run a command and report" (Haiku) and "writing tests" (Sonnet). The changed table is not re-tested.

Limits: two runs, both small jobs. For a job this small, delegating costs more than doing it in the main chat, because of the subagent's startup. I did not compare answer quality between models.

## Which model, which effort

**GUIDE.md** is a one-page guide: which model fits which job, what the choice costs, and where to set it.

The same month of my calls at each model's list price (computed; assumes the token counts would not change with the model):

| Calls | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 | Fable 5.2 |
|---|---|---|---|---|
| All 39,275 calls | US$974 | US$2,509 | US$5,019 | US$7,131 |
| The 3,713 subagent calls | US$57 | US$176 | US$352 | US$545 |

Haiku 5.5 is 1/20 the price of Sonnet 5.5 per token, but only 0.4x here. A Haiku prompt above 100,000 tokens pays 5 times the price, and 96% of my calls were above that (measured). `python analyze_usage.py` prints both rows at the end of its report.

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
5. Optional: see what fills a new session. This reads the logs directly, so it works without step 2:
   ```
   python audit_startup.py
   ```

Useful options:

```
python simulate.py --cap 250 200            # try other caps, in thousands of tokens
python simulate.py --trim-startup 30        # also try a 30k smaller startup prompt
python simulate.py --since 2026-11-12       # only the last week
python analyze_usage.py --split 2026-11-16  # cost per call before and from a date
python audit_startup.py path/to/session.jsonl  # audit one chosen session
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

It runs the price function, the simulator, the before and after helpers and the startup audit on hand-made inputs with known answers, and prints `ok`.

## Files

- **extract_usage.py** reads the Claude Code logs and writes one row per API call to **data/usage.csv**.
- **prices.py** holds the price table and the function that turns tokens into dollars.
- **analyze_usage.py** prints the baseline report (ending with the same calls priced on each model) and, with `--split`, the before and after comparison.
- **simulate.py** runs the what-if comparison.
- **audit_startup.py** sizes each part of a session's first prompt.
- **.claude/skills/delegate/SKILL.md** is the `/delegate` skill.
- **GUIDE.md** is the guide for picking a model and an effort level.
- **test_simulate.py** checks **prices.py**, **analyze_usage.py**, **simulate.py** and **audit_startup.py**.

## Next

Not built yet:

- More startup trims (connectors, the skills list budget, other unused tools), each measured like the first two.
- More measured `/delegate` runs, on bulk reading jobs where it should pay.
- A longer before and after comparison once these are in daily use. The one above covers four days.

I planned a warning for sessions that pass the cap. I dropped it: the built-in setting above already does the job.

## About

Built by Andres Delascio, mechanical engineering grad. Human-led engineering with AI-assisted implementation (Claude Code). Every number above comes from running these scripts on my own logs.
