# Checkpoint 2026-11-03

## Current phase and user direction

Phase 1 deliverable validation implemented. User explicitly selected “1단계 산출물 검증부터 진행” on 2026-11-03. The SaaS initial release is not complete. English baseline revision 2.0 remains unchanged; the original specification directory was not edited.

Design: `docs/superpowers/specs/2026-11-03-phase1-design.md`.
Plan: `docs/superpowers/plans/2026-11-03-phase1.md`.

## Working result

- Local Korean app at `http://127.0.0.1:8765`, started with `bash scripts/run.sh`; static browser UI with Python loopback backend, SQLite snapshots, separate rendering module.
- Three manually researched background topics: plain-language notices, appointment teach-back, AI notice fact checking. CDC, AHRQ, NIST source bodies inspected; claims and applicable context stored in `brochure/data/topics.json`.
- Selected template content produces both a standalone Korean handout and separate representative notes. No private notes enter the DOCX/PDF renderer's allowlisted model.
- Sender changes create revisions, invalidate review/downloads; review/export check the current revision. Idempotent creation, reopen, deletion, partial export retries and missing-artifact recovery implemented.
- No live search, AI provider, company uploads, authentication, deployment, clinical advice, segmentation, promotion or sales analytics.

## Verification evidence

Final command: bundled Python `-m unittest discover -s tests -v` → **23 tests passed** in 4.344 seconds. HTTP tests ran with approved loopback socket access; default sandbox cannot bind sockets.

`node --check web/app.js` and `node tests/test_ui.cjs` passed. The retained UI harness covers both-audience review, literal sender text, unsaved changes, revision invalidation, partial export retry, missing-file recovery control and download restoration after reverting edits. It is a DOM state harness, not a full browser substitute.

`python scripts/verify_samples.py --render-pages` produced all three PDF/DOCX pairs under `output/samples/`. All samples are two A4 pages. All six rendered pages visually inspected; Korean glyphs readable, no clipping/overlap, example and limitations kept together, active source links. `pdffonts` confirmed embedded subsets and Unicode mappings. Structural checks verify editable OOXML text, matching source links and no private sentinel text. Manifest: `output/samples/verification.json`.

Browser QA: selected first topic, created both materials, saved a clearly fictional sender, observed revision 2, viewed both tabs, reviewed, exported both formats, restarted server/reloaded, reopened unchanged saved work. Desktop screenshot: `docs/verification/phase1-desktop.jpg`. Mobile workspace checked at 390 × 844: DOM content width equals viewport content width (375), no horizontal overflow. Restored default viewport. Browser console had no errors/warnings.

Browser tool download-event wait timed out and reset the tool session. Do not claim the browser download completion event was verified. The same displayed download URLs were separately fetched over HTTP: PDF 200, application/pdf, 128719 bytes, two pages with searchable Korean; DOCX 200, correct MIME, 38703 bytes, editable `w:t` text. Final sample files were also validated directly.

Independent review completed with no remaining significant findings. Fixed during review:

- DEL/C1 controls rejected at input instead of failing during export (observed regression RED→GREEN).
- PDF timeout kills and reaps the Linux process group, including converter children (real child-sentinel regression RED→GREEN).
- File recovery action remains available even when persisted metadata says ready.
- Reverted unsaved sender edits restore current download links.

## Consequential implementation defaults

- Phase 1 uses curated, openly labeled templates and original research rather than pretending to make live provider calls. No provider account, API key or billable requests were needed.
- Python standard library HTTP is appropriate only for loopback validation. Replace it with production hosting/auth in Phase 2 before real private data is accepted.
- DOCX is the canonical render input; LibreOffice produces its PDF. Two pages preserve legibility. No full document editor in this phase.
- Current input surface: sender name 40 characters/contact 100 characters, body limit 8 KiB. Rendering serialized; PDF timeout 45 seconds; manual bounded retries.
- Data persists until deletion; app has no backup/external AI processing. Filesystem backups, downloaded copies and secure SQLite erasure remain outside prototype deletion guarantees and are disclosed in README.
- `.git` is an inaccessible empty read-only mount and `git status` reports no repository. No branch or commit was created.

## Remaining work and next action

Phase 1 user evaluation of practical usefulness and handout tone remains a human acceptance step. The implementation and artifact checks above are complete.

Next: plan Phase 2 actual source discovery and grounded AI composition, select providers and numeric budgets, then connect review/correction and supported neutral company inputs. Establish authentication, account ownership and private artifact access before accepting private company material or deploying. Keep research, factual support and freshness checks honest; draft revisions must preserve current export behavior. Phase 3 covers operational failures, limits, deletion/backups and deployment/recovery validation.
