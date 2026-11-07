# Source and Codex adaptation

Upstream: https://github.com/anthropics/skills/tree/2c5958ecac7cee2b583967a2c4981d0f4a75c579/skills/skill-creator

Source revision resolved during installation: `2c5958ecac7cee2b583967a2c4981d0f4a75c579` (2026-11-08). Original downloaded directory was fetched from main immediately before revision resolution; the parent installer records the installation revision and validation.
License: Apache-2.0, copyright 2026 Anthropic, PBC; retained in [LICENSE.txt](../LICENSE.txt).

Modified for Codex on 2026-11-08:
- Renamed to `skill-improvement-lab` to leave Codex's system `skill-creator` untouched.
- Replaced the entrypoint and comparator with a task-scoped workflow, frozen rubric, source-supported checks, and honest tie/neither/insufficient-evidence outcomes. No compulsory interview, all-task evaluation, or fixed run count.
- Removed Claude-only `scripts/run_eval.py`, `improve_description.py`, and `run_loop.py`: these launch `claude -p`, write `.claude/commands`, or parse Claude Skill/Read stream events.
- Removed unused packaging, trigger-review, grader/analyzer, and schema material to avoid incompatible routes.
- Retained the portable HTML viewer/template; removed automatic termination of a process on its requested port and escaped inline JSON so output text cannot close its script element.
- Omitted the upstream benchmark aggregator: its default metadata assumes three runs and can substitute output characters for token usage. No numerical benchmark is claimed by this adaptation.

This skill provides reusable instructions and an offline review helper. It does not include an automatic provider API harness, human preference labels, or a completed editorial evaluation. Use Codex's available isolated agents or an independently implemented API evaluator for actual model judgments.
