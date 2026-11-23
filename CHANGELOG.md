# Changelog

## 2026-11-23
- README: an "In 30 seconds" overview with one picture, and charts for the result, the startup prompt and the month on each model (**overview.svg**, **result.svg**, **startup_prompt.svg**, **month_by_model.svg**). No numbers changed.
- README: the notes under the result table fold into "How to read these numbers".

## 2026-11-20
- STUDY.md cites Anthropic's docs where a finding rests on a published rule (prices, prompt caching, subagent model, the cap setting), with a Sources list at the end.
- STUDY.md section 9 states what 3 runs per arm could detect: a difference of about 25% (computed). Also fixed a stale `test_simulate.py` name there.
- README and STUDY.md say the simulator models only the cap, not `/clear` or clearing old tool results.
- STUDY.md section 1: checked against ccusage 20.0.51. Same tokens to within 0.01% and the same US$5,150.83 for Oct 19 to Nov 18.
- Added **sample/**, made-up usage data, and a `--data` flag on `analyze_usage.py` and `simulate.py` to read it. A test runs both reports on it.
- Added a GitHub Actions check (`.github/workflows/test.yml`): the tests run on Ubuntu and Windows with Python 3.9 on every pull request and push to `main`.
- Renamed `test_simulate.py` to `test_scripts.py`: it now checks every script, not just the simulator.
- Version 1.0: tagged and released on GitHub.
- Added `CITATION.cff` and two README badges (tests, licence).
- Re-rendered **how_it_works.png** and **how_it_works.pdf** with the new test file name.
- Fixed `simulate.py --since`: a fresh session is now sized from each session's true first call, not from the first call inside the date range. The whole-month figures did not change.
- The scripts no longer crash on logs with a model that `prices.py` does not list, on an empty log folder, or on a missing `usage.csv`. They say what happened instead.
- `extract_usage.py` counts a tool call once when a resumed session logs it again. `audit_startup.py` has `--help` and skips half-written log lines.
- `experiment.py` saves the `claude` version with each run. Tests added for the extractor, the date-range fix and unpriced models.
- Added a controlled test of the 200k cap: a 35-prompt task (`LONG_PROMPTS`, 32 checks) and arms E and F in `experiment.py`. STUDY.md section 9 has the 6 runs: 22% fewer prompt tokens with the cap, no saving in dollars, same quality.
- README: a seventh finding and a result row from that test. The 35% is now stated as an estimate for long sessions.
- `experiment.py` reports the CLI's own cost in its medians and counts compactions.
- Added `experiment.py` and `experiment_task.py`: a controlled test of a project file, a code map and a mid-task handoff on the same scripted task. STUDY.md section 8 has the 12 runs: no measurable saving from the file or the map, and the handoff cost more.
- README: a sixth finding from that test.
- `analyze_usage.py --split` now also prints cost and calls per typed prompt, per model.
- `simulate.py --without-top N` leaves out the N costliest sessions.
- The repo map's result strip now shows the 26% figure without the longest session and all three models.
- The README result table now shows all three models and the month without its largest session (26% saved, not 35%).

## 2026-11-19
- The repo map (**how_it_works.png**, **how_it_works.pdf**) now shows the headline result: the month with and without a 200k context cap.
- Added the usage extractor, the baseline report and the what-if simulator.
- Costs are in US$ at API list prices (prices read from Anthropic's pricing page on 2026-11-19).
- Added `test_simulate.py` with hand-made calls and known answers.
- Added `python analyze_usage.py --split YYYY-MM-DD`: cost per call before and from a date, per model, plus what real compactions cost.
- README: measured before and after for the 200k auto-compact setting, and a check of the simulator against 67 real compactions.
- Added `python audit_startup.py`: sizes each part of a session's first prompt (tool definitions, system prompt, skills list, connectors, instruction files). README has the result for one session, and two measured trims: skills moved into their project, and a deny rule that removes an unused tool (needs an app restart).
- Added the `/delegate` skill: one job, one subagent, cheapest model that fits. README has one measured run on Haiku 5.5.
- Added **GUIDE.md**: which model and effort for which job, with list prices and my month of calls priced on each model. `python analyze_usage.py` now ends with that comparison.
- Added `python simulate.py --sensitivity`: the saving of a cap for a range of the two assumed checkpoint values. README has the table for the 200k cap.
- README rewritten as the front page of the study (question, five findings, what to do, how to run it). The detailed sections moved unchanged into **STUDY.md**.
- Added an MIT licence.
- Added **spend_by_prompt_size.svg**, the chart on the front page.
- Dropped the planned cap warning: Claude Code's `autoCompactWindow` setting already does it.
- Added **how_it_works.pdf**: a one-page map of how the scripts fit together, made from **how_it_works.html**.
- README: the map is now on the front page as **how_it_works.png**.
- README: a result table at the top, the month with and without the 200k cap, in dollars and percent.
