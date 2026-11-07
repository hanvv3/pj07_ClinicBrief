# Editorial quality implementation plan

**Goal:** Let clinic news read like useful news while preserving material facts; evaluate actual outputs before claiming better quality.

**Architecture:** Keep existing topic storage and brief/practical asset formats. Load shared editorial guidance in actual selection/composition/review requests. Allow omitted brochure examples and empty limitations where unnecessary. Compare frozen pre-change and changed production composition paths using fixed source packets and separate, anonymized judge requests.

**Spec:** AGENTS.md, docs/learning-notes.md and the user's approved evaluation discussion. The user explicitly prefers autonomous implementation without repeated interviews or approval rituals. Existing key reuse is authorized. No deployment, commit, external messages or unbounded optimization.

## Work

- [x] Preserve pre-change brochure source in .local-data/evals/editorial-2026-11-08/baseline and hash its files.
- [x] Freeze reader-quality rubric before generating comparison outputs: evals/editorial/rubric.md.
- [x] Build 12 evidence packets (news and practical) with provenance and no desired output answers: evals/editorial/cases.json.
- [x] Update brochure/insights.py, provider.py and shared editorial guidance: news can qualify on informational value; practical assets retain finished substance; separate reader prose from verification records.
- [x] Permit absent example content and empty limitations in provider_schema.py/validators; retain old saved drafts. Add regression tests for empty and half-empty examples.
- [x] Update rendering.py and web/app.js so omitted content leaves no empty headings/cards; verify DOCX and UI behavior.
- [x] Implement scripts/evaluate_editorial.py and test fixed inputs, anonymous order mapping, failure denominators, budget and resume behavior.
- [x] Run bounded real comparison with existing model/key. Preserve originals, audit rejections, usage and failed attempts. Keep independent factual and reader judgments separate; repeat reader judgment with swapped order. Do not silently regenerate favorable results.
- [x] Run appropriate full regression checks, review changes, verify local interface and at least one real output/export as warranted.
- [x] Report actual comparison results and remaining uncertainty; update brief learning record only with supported findings.

## Review focus

- A brief without an action/checklist is still useful; a practical asset without substance is not.
- Removing warnings cannot turn uncertain association into a causal claim or lose a material population/account limit.
- Empty examples render cleanly; half-empty examples fail validation; old drafts continue to work.
- A rejected or unassessable output cannot disappear from evaluation counts; swapped preference is mapped to identity.
- Baseline/current evidence, task and model match; judge sees neither development history nor version labels.

## Initial live limit

The 12-case pilot permits at most 84 API requests: 24 compositions × generation/audit, plus one factual and two order-swapped reader judgments per case. No automatic retry. Use bounded concurrency. If it cannot complete within the cap, report the incomplete/failed cases rather than raising the limit silently. A later correction needs a concrete observed defect and a separately identified run; earlier outputs remain intact.

## Observed correction during the pilot

The AMIE evidence packet ambiguously described the 90% denominator. Original-paper comparison found 100 completed AI conversations but 98 analyzed visits, with 88/98 top-seven and 73/98 top-three inclusion. Both the output and the evidence-only judge inherited the ambiguity. Preserve the original 12-case run and inputs; create cases-v2.json correcting that packet only, then run this one case in a separate directory with at most 7 additional requests. Report the original automatic verdict and this source-packet defect together; do not silently substitute a favorable rerun into the original score.
