# Research result navigation — 2026-11-03

## Reproduced problem

The user's current completed research job was
`8f9c297451fa48d68752c32b76471066`: 4 reported sources read, 3 candidates
considered, **0 selected**. It was shown as 완료 with a generic 결과 열기 button.
Clicking that button was reproduced in the existing authenticated local browser:
the same broad topic screen and its 3 previously saved topics remained visible.
The job had no selected new topic to show.

`applyCompletedJob(research, true)` only fetched `/api/research` and set the same
topics/research page. There was no run-scoped destination or focus/scroll change.
The button handler also cleared its notice. A separate UI-harness reproduction
confirmed identical visible text before/after, one GET and no paid POST.

Before screenshot: [research-result-before-2026-11-03.jpg](research-result-before-2026-11-03.jpg).
The selected job and earlier 2-topic job's immutable result payload hashes were
recorded in [research-result-data-before-2026-11-03.json](research-result-data-before-2026-11-03.json).

## Implemented correction

- Open a distinct result screen for the chosen research run, with outcome,
  completion time, selection report and only that run's still-saved topic IDs.
- Distinguish zero selection from topics that were subsequently deleted.
- Use count-aware actions and a clear no-selection status. Keep detailed
  rejection reasons on the result screen, not in a long duplicate job card.
- Provide an exit to the full research collection, and move focus/scroll to the
  result heading after the final render.
- Preserve existing draft workflows, account boundaries, topic feedback and data.

## Verification

- Test-first regression reproduced the original behavior: opening a completed
  run from the research collection failed because no result heading appeared.
  New cases cover run isolation, zero selection, missing/deleted topics, current
  saved content, compose source identity, focus, completion/refresh/reload, session
  clearing and deletion.
- Root reran `node tests/test_ui.cjs` and `node --check web/app.js` after the final
  changes: both passed. This change only affects vanilla UI/CSS and its tests;
  backend/provider code was not changed.
- Actual browser: the zero-selection job opens a distinct result page with all
  three rejection reasons and no old topic cards. The heading is focused and the
  document is at scrollTop0. Its final live announcement states that no topic was
  selected instead of retaining a loading message.
- Actual browser: opening the earlier 2-topic run from 내 작업 displays exactly
  its account/AMIE cards and excludes the unrelated older AHRQ topic. Returning
  to the full collection restores all3saved topics and existing feedback states.
- Independent review reproduced two further navigation issues: a late background
  response could interrupt a newly opened/edited draft; declining the back
  navigation prompt could clear selected-result state. Both were fixed with
  regression cases and re-reviewed; no actionable finding remains in this scope.
- The two recorded job-result hashes and update timestamps remain identical.
  No research, composition or other paid AI request was issued for this fix.
- Final browser was reloaded with the latest code and left on the user's actual
  zero-selection result page. Proof: [0-topic result](research-result-empty-2026-11-03.jpg)
  and [2-topic result](research-result-positive-2026-11-03.jpg).
