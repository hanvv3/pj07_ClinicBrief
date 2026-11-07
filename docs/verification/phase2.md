# Phase 2 verification — 2026-11-03

Status: Phase 2 local technical verification complete. Scope: synthetic, non-sensitive inputs. This is not a public SaaS release or acceptance by a real sales representative.

## Automated verification

- Bundled Python: `python3 -m unittest discover -s tests` — **92 tests passed**, 9.689 seconds.
- `node tests/test_ui.cjs` and `node --check web/app.js` — passed.
- Tests cover HTTP auth/CSRF and cross-account access, research/compose/revise ownership, request identity, quotas, concurrent deletion/admission, restart interruption, source trace and dates, public/private content boundaries, and real DOCX/PDF conversion with bounded partial failure recovery.
- Provider tests inject responses and never make billable API calls. They prove validation/control behavior, not semantic accuracy of live models.

## Actual provider and browser evidence

The existing user-configured key was used; no new key was created or exposed. Initial tests used `gpt-5-mini`; after the user requested a capability investigation, frozen comparisons led to the current `gpt-6.1-sol` default. Public research was separated from private composition. Test servers used isolated `.local-data/phase2-qa` and `.local-data/phase2-research-final` directories. See the separate model comparison report for controls, results and limitations.

- Live research: a successful three-call run saved an AHRQ Tool 5 candidate after matching source-body access and native citation records, strict extraction, and an independent candidate audit. That run reported 52,624 tokens. Earlier rejected runs remained visible failures; no fixture fallback or automatic paid retry occurred.
- Original-source comparison found that the candidate mislabeled a review date as an update date and overextended appointment guidance to payment methods/immediate application. The audit had passed despite those issues. The deterministic date fix was applied to the one earlier synthetic QA topic as a documented metadata migration, with before/after and raw responses retained. No candidate title, summary, claim, or recommendation was rewritten in storage. Its peripheral content limitations remain visible in the QA candidate.
- AI-led path: one real composition and one revision, four provider calls and 20,402 tokens. Both documents changed; review reset and old URLs returned 409. Reviewed R2 files were downloaded and exact saved reopening verified. `output/live-smoke/ai-r2.pdf`, `.docx`, and `ai/verification.json` contain the evidence. Both PDF pages were visually checked; Korean text is searchable, fonts embedded, links intact, DOCX text editable, and private notes absent.
- Earlier company path: R1 was rejected during agent source comparison for payment claims and internal field names; R2 retained a wrong “repeat in my words” opening in private notes. One correction failed the audit; saved R3 then copied private openings into the brochure despite passing audit. These rejected revisions were not exported. Sol corrected the body as R4, and its files/reopening passed technical checks, but an inherited Mini topic notice remained overbroad. R4 is retained as diagnostic evidence, not the final recommended sample.

The date migration record is `.local-data/phase2-research-final/diagnostic/date-normalization-migration.json`. Normal application logging does not retain provider response bodies; diagnostic captures were enabled only in a temporary synthetic-only QA wrapper. All reviewer statements here refer to agent/tool-based comparison, not a human acceptance claim.

## Company final artifact check

The final sample starts from fresh Sol research, avoiding the earlier contaminated source snapshot. Research job `d914d57be2904a70b39130bb6d2edcdf` produced the CDC-based topic `research-d89a76a69caa4399be9c9946778ec73a`. The browser selected it, submitted a synthetic company editing brief, reviewed both audiences, exported and reopened draft `aaf36b77c7144dd5879f1b54730e3d30`, revision 1. No corrections, metadata migrations or out-of-band content edits were needed for this path.

- One research job (3 provider requests) and one composition job (2 requests): 48,751 total tokens. This is the successful fresh path, not the total cost of earlier diagnostics.
- Agent/source comparison passed factual attribution, editorial scope, audience separation, sender accuracy and the inherited evidence notice. Displayed date 2025-07-21 remains unclassified; publication/update dates are unknown, checked date 2026-11-03.
- `output/live-smoke/company-sol-r1.pdf` and `.docx` downloaded via authenticated HTTP from the same links rendered by the browser. This confirms returned file bytes, not a native browser-download completion event.
- PDF: both pages visually inspected, no clipped/overlapping content; searchable Korean, embedded Noto fonts and valid source hyperlinks. DOCX: editable OOXML text. Private openings/explanation, internal terms and the input-only marker are absent from both exports.
- Both API and browser reopening retain the exact saved revision and download association. The first composition snapshot matches exported content. Manifest: `output/live-smoke/company-sol/verification.json`; screenshot: `docs/verification/phase2-desktop.png`.

## Consequential fixes and limits

- Revised source acquisition uses completed `open_page` or `find_in_page` on a loaded page plus a native citation of the same URL; search snippets alone cannot qualify. Normal discovery has three requests, at most four with the bounded extra source read, and at most eight web actions.
- Source IDs/URLs are paired by the server. Research/check dates use the Asia/Seoul clock. Explicitly mislabeled review dates are cleared from the update field without inventing replacements.
- Dedicated revision requests can narrow scope and remove content within evidence/safety boundaries. Neutral company examples can shape editorial suggestions. Known implementation terms/private quality-note references in public prose are rejected before save.
- Job replay precedes mutable version checks; prepared/generated request namespaces do not collide. Deletion and new job admission are serialized. UI result reopening retrieves current stored content and cannot resurrect deleted job snapshots.
- Authentication and local limits are implemented, but production account controls, TLS/hosting, backups/recovery, provider outage drills, numeric spending budgets, broader content evaluation, and practical representative feedback remain Phase 3 work.
- A passing model audit is not a factual guarantee. The observed false passes and required revisions must be included in the pilot quality evaluation; this run does not establish an unassisted content-success rate.
