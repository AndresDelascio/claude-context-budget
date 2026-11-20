# Changelog

## 2026-11-20
- `analyze_usage.py --split` now also prints cost and calls per typed prompt, per model.
- `simulate.py --without-top N` leaves out the N costliest sessions.
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
