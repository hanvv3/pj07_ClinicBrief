---
name: skill-improvement-lab
description: Improve an existing skill or agent workflow from real failures and compare versions with a fixed rubric, blind judgments, and user feedback. Use for skill evaluation or behavior-quality iteration, not ordinary edits or every task.
---
# Skill Improvement Lab

Codex adaptation of Anthropic's skill-creator. Preserve intent, explain why, remove ineffective instructions, and learn from outputs without fitting the workflow to a few examples. The built-in `skill-creator` remains available for creating ordinary skills.

## Work from the actual problem

Use the conversation and existing artifacts before asking for more input. A clear request authorizes ordinary reversible improvements; this skill adds no interview or approval gate. Inspect where the failure arose (selection, inputs, writing, schema, review, or presentation) before adding another rule. Match the effort to the task; a small wording edit need not launch an evaluation campaign.

When evaluating a change, keep the baseline, input evidence, target audience, and intended outcome fixed. Use the project's agreed rubric; if none exists, write a small provisional rubric before seeing results and identify it as provisional. Separate correctness from reading quality. An accurate but awkward text and a fluent but misleading text fail for different reasons.

## Compare without revealing the answer

For a meaningful comparison, give a fresh judge only the task, frozen rubric, source excerpts, and anonymized outputs. Omit author/model names, improvement claims, and this development conversation. In Codex, a subagent with `fork_turns="none"` can provide a context-separated review; a separate API request is also possible within the authorized budget. If neither is available, label an inline review as contextual rather than blind.

Use [agents/comparator.md](agents/comparator.md) as the judge's task. Repeat with A/B swapped in another fresh context when acceptance depends on the result. Map verdicts back to original outputs before comparing them. An order-dependent result is unstable, not an improvement win. Tie, neither acceptable, and insufficient evidence are legitimate outcomes. Compare with real human preferences when available; an absent reply is not a positive label.

Keep source-supported factual checks separate from the prose-quality comparison. Do not infer unsupported facts from fluency or accept a link as proof. Preserve important qualifiers; do not reward shortness or caution volume by itself. Record concise cited reasons, not private chain-of-thought.

## Iterate proportionally

Change the smallest mechanism supported by the failure. A good example plus its purpose may be more useful than extra MUST/NEVER rules. Keep final confirmation cases separate from cases used to tune the instructions. Do not silently retry until a favorable result appears or invent token/time measurements. A model's preference is evidence about that judge, not proof of clinician acceptance.

Save artifacts in a task-owned workspace such as `.local-data/evals/` when this project uses it. [references/artifacts.md](references/artifacts.md) gives the lightweight layout and a portable HTML review command. Human feedback and automated judgments are distinct records. A real user review can be added later; don't manufacture one to finish a run.

Only relevant new lessons belong in the project's existing learning notes. Merge or retire old guidance rather than continually adding rules. Installation itself does not change the application's runtime prompts or prove quality improvement.

For upstream provenance, compatibility limitations, and removed tools, see [references/origin.md](references/origin.md).
