# Insight Selection Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development for disjoint units; root integrates and verifies. User has authorized execution and opted out of further approval questions.

**Goal:** Replace app research with source-diverse problem discovery, explicit selection and immediately usable outputs, compared with actual ChatGPT.
**Architecture:** Bounded staged provider, source-grounded topic metadata, public/owner history and feedback, existing shared workers and private brochure snapshots.
**Tech Stack:** Python/SQLite/Responses and vanilla JS; no new dependencies.
**Spec:** docs/superpowers/specs/2026-11-03-insight-selection-design.md

## Global constraints

- Existing key and gpt-6.1-sol, no secret output; six provider requests /24 web actions maximum, no automatic retries.
- New pipeline in both direct research and briefing; keep auth/CSRF/ownership,2sharedcollections/24h and existing private work limits.
- History/feedback strictly public-field allowlists; distinguish inferred need from observed source facts;0–3 publishable candidates.
- Actual ChatGPT browser baseline, exact shared brief and preserved raw outputs; no claim of user acceptance or universal superiority.

## Review focus

- No copied agency posts counted as independent demand; no unread snippets promoted to source evidence.
- Reworded old problem must not count as new; update requires sourced change.
- A complete-looking asset must not invent clinic policy, procedure, cost or product capability.
- Feedback from one account/private research must not leak to other users/public research context.
- Empty selection/partial evidence must preserve existing feed and surface an honest outcome.

## Tasks

- [x] Provider worker: brochure/insights.py, insight_schema.py, provider.py, tests/test_insights.py. Tests first for multi-lane provenance, explicit rank/rejection, repeated history, empty selection, finished-asset rules and maxcalls. Verify targeted; root runs full suite.
- [x] Persistence worker: brochure/insight_store.py, briefing.py, workflows.py, tests/test_insight_store.py/test_briefing.py/test_workflows.py. Read exact interfaces in spec. Test feedback isolation/allowlisting, source selection snapshot, zero-result retention and new provider routing/history before implementation.
- [x] UI worker: web/app.js/style.css, tests/test_ui.cjs. Tests first for evidence/ready asset without compose, disclosure/copy/feedback persistence, zero result and legacy fallback; preserve current recovery/polling.
- [x] Root: server.py/tests/test_http.py dependency injection and auth+CSRF feedback route; test rejects private/foreign feedback then implement.
- [x] Root: freeze baseline brief, run actual ChatGPT and one new live collection, preserve output, independent source check and blinded artifact review, meaningful browser/export checks.
- [x] Review/fix: independent code review, fullPython/UI checks, documentation/checkpoint/evaluation report and final usable artifacts. No git operation in read-only/unusable checkout.

## Integration adjustments

- Direct research also supports `briefing` as the “전체 분야에서 찾기” option.
  It remains an owner-private research job using the existing account limit.
  This permits broad on-demand research without changing the shared feed limit.
- The old server's scheduled09:00 collection consumed the second public slot and
  failed its old audit. The live new comparison therefore uses private broad
  research; the shared cap is unchanged and no collection record is removed.
- Independent review reproduced primary-URL/date identity collisions between
  different problems and updates. Add conceptual problem and update identity,
  retaining legacy IDs, predecessor topics and their separate feedback.
- Actual IAB clipboard calls reported success without changing the clipboard.
  Full readonly text and manual selection now provide a verified native-copy
  path; automatic-copy wording does not claim confirmed success.

## Completion evidence

`docs/experiments/insight-selection-2026-11-03/report.md` records the frozen first
outputs, source audits, blinded comparison and scope limits. ChatGPT was better
on practical relevance/readability in this run; no favorable retry or clinician
acceptance claim. `verification.json` records 161 Python checks, final UI/syntax
checks, exact manual copy/paste, persisted feedback and real compose/revise/review/
export/reopening. Separate reviewed R2 PDF/DOCX passed all-page visual inspection.
Final independent review found no further actionable UI/report issues.
