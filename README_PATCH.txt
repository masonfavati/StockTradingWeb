StockTradingWeb Milestone 3D.3 — optional macOS forward-research scheduling

Files added or updated:
  backend/app/analysis/forward_evaluation.py  (updated timing rules)
  backend/app/analysis/forward_journal.py     (updated timing rules)
  backend/app/analysis/forward_schedule.py
  backend/app/analysis/forward_schedule_cli.py
  backend/tests/test_forward_schedule.py
  docs/MILESTONE_3D3_SCHEDULED_RESEARCH.md

Updates two existing modules; no migration, no credentials or automatic installation.
Important: both capture and outcome evaluation now recognize strictly-before-09:00 NY
entry-date records. The regular exchange opens at 09:30; not a guaranteed fill.
See docs/MILESTONE_3D3_SCHEDULED_RESEARCH.md for activation and safety notes.
