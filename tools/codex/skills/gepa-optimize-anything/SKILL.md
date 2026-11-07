---
name: gepa-optimize-anything
description: Improve prompts or other text artifacts with GEPA using an existing evaluator and bounded experiments. Use for requested automated optimization or comparison of candidate instructions, after a useful evaluation target is available; ordinary edits do not need an optimization run.
---
# GEPA for Codex

Use GEPA when repeated, measured experiments are likely to improve an artifact. A clear manual edit or a missing evaluation criterion may be the better next step. This skill installs the tool; it does not automatically start paid model calls or change the application.

## Available environment

The separate interpreter is `~/.codex/tools/gepa/.venv/bin/python`. It contains the pinned GEPA source recorded in [provenance](references/provenance.md), plus the small dependency set needed for the in-process backend. It does not share the application's virtual environment.

Run the local wiring check with that interpreter and `scripts/smoke_test.py`. This uses a deterministic mock proposer and no credentials, and checks integration only, not writing quality. Read [the API reference](references/api.md) for real experiments; use `OptimizeAnythingConfig` and verify the installed signature if upgrading.

## A useful experiment

Start from the user's purpose and the project's existing evaluation criteria. Record the seed artifact, representative examples and why a result is good or bad. For generalization, keep development examples, selection examples and a final test set distinct. A judge's preference is a measurement to calibrate against readers, not a substitute for them.

Use `engine="gepa"`, the in-process backend. Give it a feedback-rich evaluator: factual errors and missing information are useful feedback; a bare numerical score usually is not enough. For editorial work, preserve the intended meaning and necessary conditions while comparing reader value and naturalness. Avoid tuning to a single example, fixed word counts or a growing blacklist.

Choose the reflection model explicitly from configured, available models. Reuse authorized credentials through environment variables, never embed them in prompts, files or reports. Codex subscription access is not a GEPA API credential. Do not silently choose an Anthropic model or install Claude CLI to satisfy an upstream example.

Use a finite evaluation-call limit, modest concurrency and a process timeout appropriate to the authorized task. Account for evaluator/generator costs as well as the proposer: GEPA's proposer cost option does not cap every external call inside the evaluator. Existing authorization and budgets carry forward; installation alone is not authorization for an optimization campaign. Do not automatically increase the budget when a small run is inconclusive.

Store execution outputs in a local ignored directory such as `.local-data/evals/`. Keep credentials and private data out of feedback sent to the proposer. Preserve baseline and candidate outputs, actual usage and failures. Apply a winning candidate only after evaluating it on the held-out examples and understanding relevant regressions; do not overwrite production prompts merely because the optimizer returned a best candidate.

## Optional detail

- [Writing evaluators](references/writing_evaluators.md): feedback and data separation.
- [API](references/api.md): installed upstream API shape. Examples using other engines or providers are alternatives, not setup requirements.
- [Gotchas](references/gotchas.md): optimization failure modes.
- [Tracking](references/tracking.md): optional integrations; local records are sufficient by default.

The upstream autoresearch/meta_harness backends require Claude subprocesses and are outside this Codex setup. The original upstream guide is retained as reference only, not an instruction to install extra services or run its sample budgets.
