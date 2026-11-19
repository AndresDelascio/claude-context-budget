# Changelog

## 2026-11-19

- Added the usage extractor, the baseline report and the what-if simulator.
- Costs are in US$ at API list prices (prices read from Anthropic's pricing page on 2026-11-19).
- Added `test_simulate.py` with hand-made calls and known answers.
- Added `python analyze_usage.py --split YYYY-MM-DD`: cost per call before and from a date, per model, plus what real compactions cost.
- README: measured before and after for the 200k auto-compact setting, and a check of the simulator against 67 real compactions.
- Added `python audit_startup.py`: sizes each part of a session's first prompt (tool definitions, system prompt, skills list, connectors, instruction files). README has the result for one session, and two measured trims: skills moved into their project, and a deny rule that removes an unused tool (needs an app restart).
- Dropped the planned cap warning: Claude Code's `autoCompactWindow` setting already does it.
