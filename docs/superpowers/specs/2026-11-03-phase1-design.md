# Phase 1 deliverable design

User direction on 2026-11-03: start with Phase 1 deliverable validation. Product reference: `specs/approval_candidate_spec.en.md`, revision 2.0. Original specifications remain unchanged. Q/D items are treated as working implementation choices, not retroactive user agreements.

## Outcome

A Korean local web application lets a representative inspect researched examples, select one, assemble a director-facing handout and separate private notes, review them, and download actual editable DOCX and Korean PDF files. This proves the deliverable; it is not the SaaS release.

## Approaches and decision

- Full cloud SaaS now would couple evidence quality and rendering validation to identity, paid providers and deployment. Defer to phases 2 and 3.
- A document-only spike would prove typography but omit selection and audience separation.
- Selected implementation default: a local Python web application, static browser UI, SQLite saved snapshots, python-docx authoring and LibreOffice PDF conversion. It covers the user-selected Phase 1 with a small dependency surface. No git repository is accessible in this workspace; keep changes as local files.

## Scope and boundaries

- Use 2–3 manually researched, explicitly labeled examples. No fake live search or AI generation indicators. Date of research does not imply a new development.
- Compose from reviewed example templates; API/provider integration and arbitrary company uploads belong to Phase 2. No paid API calls in this phase.
- Support supplied sender name/contact only. No invented credentials. Input lengths 40/100 characters; reject unsafe control characters.
- Save complete content, evidence, notes and export state in SQLite. Reopen without regeneration; allow deletion. Sender changes increment revision and invalidate review and exports.
- Review requires the current revision and a single representative. No organizational approval.
- DOCX and PDF use the same director-facing content; private notes never enter rendering. DOCX is real editable text. PDF conversion embeds available Korean fonts.
- Preserve a successful DOCX if PDF conversion fails and offer retry of the missing step. Bound rendering time and serialize exports.
- Local loopback only, non-sensitive example data only. No authentication or cloud deployment in Phase 1; not suitable for company/patient records. These limitations must be visible in the UI and README.

## Components

`brochure/catalog.py` reads researched fixtures and validates claim/source links. `brochure/service.py` owns revision rules and snapshots. `brochure/storage.py` persists SQLite records. `brochure/rendering.py` authors DOCX and converts PDF. `brochure/server.py` provides same-origin HTTP endpoints and serves `web/`. No separate services, frontend framework, agent framework or vector database.

## Data and HTTP contract

All JSON is UTF-8. Errors are `{ "error": "Korean actionable message" }`.

Topic: `id, category, title, summary, director_value, takeaway, reading_minutes, research_date, evidence_status, evidence_notice, sources, claims, brochure, notes`.

Source: `id, title, publisher, url, published_at` (nullable), `checked_at, context`.

Brochure: `title, intro, sections: [{heading, body, source_ids}], example: {heading, body}, limitations: [string], sender: {name, contact}`. The example is clearly labeled a suggested administrative example.

Notes: `opening_staff, opening_director, explanation, qa: [{question, answer}], cannot_claim: [string], claim_map: [{claim, source_ids}]`.

Draft: `id, topic_id, revision, created_at, updated_at, status` (`draft`, `reviewed`, `exported`), `brochure, notes, sources, research_date, evidence_notice, exports: {docx: {status, url, error}, pdf: {status, url, error}}`. Export status is `pending`, `ready`, or `failed`; absent URLs/errors are null. URLs include revision. Only both ready means exported.

- `GET /api/topics` → `{topics: Topic[]}`.
- `GET /api/drafts` → `{drafts: Draft[]}`; `GET /api/drafts/{id}` → Draft.
- `POST /api/drafts` with `{topic_id, sender_name, sender_contact, request_id}` → Draft. Matching request_id is idempotent; conflicting body is 409.
- `PATCH /api/drafts/{id}` with `{revision, sender_name, sender_contact}` → Draft.
- `POST /api/drafts/{id}/review` with `{revision}` → Draft.
- `POST /api/drafts/{id}/exports` with `{revision}` → Draft; format failures are preserved in `exports`.
- `GET /api/drafts/{id}/download/{docx|pdf}?revision=N` → private local file for current reviewed revision only.
- `DELETE /api/drafts/{id}` → `{deleted: true}`; remove associated artifacts.

Renderer interfaces: `render_docx(draft: dict, output_path: Path) -> Path` and `render_pdf(docx_path: Path, output_path: Path, timeout: int = 45) -> Path`. The renderer consumes brochure/sources/research_date/evidence_notice only.

## Acceptance

Inspect source content; verify useful Korean handout and notes; render every sample and inspect pages; ensure source links survive, Korean glyphs render, no notes leak, and DOCX contains editable paragraphs. Test reopen, stale revisions, idempotence, partial-export retry, deletion, oversized inputs and loopback origin restrictions. Record remaining Phase 2/3 work in the checkpoint.
