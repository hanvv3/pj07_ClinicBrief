# Research Result Navigation Implementation Plan

**Goal:** Make opening a completed research job visibly open that run's outcome,
including an honest zero-selection outcome, without rerunning research.
**Architecture:** Add a job-scoped results page in the existing vanilla UI. Use
job result topic IDs intersected with current owner-saved topics; no new backend
endpoint or source data mutation. Existing topic controls remain available.
**Tech stack:** Vanilla JS/CSS and the existing Node UI regression harness.

## Evidence and design choice

The user's current completed job `8f9c297451fa48d68752c32b76471066` considered
three candidates and selected zero. Clicking 결과 열기 was reproduced: it
refetched the full saved-topic list and rendered the same page, with no focus or
scroll movement. A separate read-only test also found identical visible text.
The generic success badge implied that a new result existed.

A scroll-only fix would still mix this run with earlier topics and cannot explain
zero selection. Choose a dedicated result page with a clear title, completion
time, selected count, report and only this run's currently saved topics. This is
an implementation decision under the user's authorization to fix the UX, not a
new user-approved design gate. Existing no-interview preference applies.

## Constraints and review focus

- Preserve stored topics, reports, feedback and drafts. Do not issue paid calls.
- Use counts from the selected job, not the entire saved collection.
- Label zero selection clearly and link to its reasons; distinguish deleted
  formerly selected topics from a genuinely empty research result.
- Keep deletion/owner/session boundaries and source selection intact.
- Move focus and scroll after final render for explicit opens and completion.
- Preserve unrelated draft editing and existing discard checks.
- Avoid refactoring the server, provider, collection quotas or clipboard code.

## Tasks

- [x] Add failing regressions in `tests/test_ui.cjs` for same-page open, run
  isolation, zero selection, deleted topics, focus, session clearing and existing
  completion/reload pathways. Confirm failure before implementing.
- [x] Modify `web/app.js` and scoped `web/style.css`: add the result page,
  descriptive count-aware actions and no-selection badge, reusable topic cards,
  explicit result navigation and an exit to all saved research. Apply focus only
  after rendering the destination.
- [x] Run `node tests/test_ui.cjs` and `node --check web/app.js`, then independent
  review. Resolve actionable findings.
- [x] Reload the existing local tab; verify this real zero-selection job and a
  previous positive run, exact scoping, navigation, and unchanged saved data.
  Save proof and update checkpoint. No Git operation in this checkout.
