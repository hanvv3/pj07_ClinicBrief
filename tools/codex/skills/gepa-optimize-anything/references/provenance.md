# Source and adaptation

Source: https://github.com/gepa-ai/gepa
Commit: cb7674c8b231270134b8e5ea8b9db1a62ed8d081
Upstream skill: .claude/skills/gepa-optimize-anything/
License: MIT (see ../LICENSE.txt).
Adapted for Codex on 2026-11-08. The short entrypoint uses the in-process GEPA backend, an isolated interpreter, explicit budgets and no implicit paid calls. Original API/evaluator references are retained. The companion script is a local offline integration check, not a quality benchmark. No Claude CLI, external tracking service or full-extra dependency installation is required for this setup.
