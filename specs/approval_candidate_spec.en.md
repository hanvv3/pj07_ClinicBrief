# Clinic Brochure SaaS — Product and Development Baseline

Revision: 2.0 | 2026-11-02 | Companion: `approval_candidate_spec.ko.md`

## 1. Purpose and document authority

Help a CSO sales representative choose a useful topic, leave a self-contained Korean brochure with a clinic director or reception/nursing staff, and explain it accurately using private companion material. Contact with the director is the intended benefit, not a guaranteed outcome.

Use this English file as the compact implementation reference; the Korean companion must carry the same revision, IDs, and meaning. Read one language during development. Explicit user decisions override both; reconcile material translation conflicts before implementing the affected behavior.

`C`, `REQ`, and `NS` preserve the original constraints, requirements, and exclusions. `Q` identifies additions proposed by this review; `D` identifies changeable working defaults. These additions are proposed implementation baselines, not claims of previous user agreement. This is a directional specification, not a complete technical design.

## 2. Retained product contract

| ID | Requirement |
| --- | --- |
| C-001 | Deliver a web application. |
| C-002 | Deliver it as a cloud SaaS product. |
| REQ-001 | Discover and create engaging topics that support CSO representatives' contact with clinic directors. Clinic-practice AI prompt setup and AI news are examples, not mandatory categories. |
| REQ-002 | Focus the initial release on useful, non-advertising topics. |
| REQ-003 | Use external web research to find current information, show source-backed candidates, and let the representative select a candidate before brochure generation. |
| REQ-004 | Generate a director-facing brochure suitable for direct delivery or delivery through nursing/reception staff. |
| REQ-005 | Generate separate representative material for visit conversations and deeper study, with citations to researched sources. |
| REQ-006 | Support AI-led composition as the primary mode and company-provided material as an alternative source. |
| REQ-007 | Provide each brochure as PDF and a genuinely editable document. |
| REQ-008 | Let the representative review and use the material without a separate organizational approval step. |
| REQ-009 | Recommend broadly useful topics across specialties; do not segment by clinic type or director demographics. |
| NS-001 | Exclude personal-résumé pitches. |
| NS-002 | Exclude product-promotion material from the initial release, including promotion introduced through company inputs. |
| NS-003 | Exclude clinic-contact/sales-outcome analytics and data-based personalization or segmentation from the initial release. |

Future possibilities are not implementation commitments. Operational cost/error measurements are distinct from the sales analytics excluded by NS-003.

## 3. Core user journey

1. Discover candidates with a title, practical value for directors, and research basis. A headline alone is insufficient.
2. Select one candidate; optionally supply supported company material and sender/contact details. Company inputs do not bypass selection or evidence checks.
3. Generate the brochure and its separate representative explanation from the selected topic and evidence.
4. Preview both; correct content or request revision. Allow review without introducing a second approver.
5. Export the reviewed brochure, save the work, and reopen it later. Changes must not silently leave stale companion material or downloads attached to the revised content.

AI-led composition does not mean inventing facts. Company material does not become verified merely because it was uploaded.

## 4. Content and evidence quality

- **[Q-001] Practical value:** Each candidate explains why a director would care and offers a concrete takeaway. Translate news into a relevant implication; explain what a suggested prompt/example does and its limits. Avoid generic headlines, exaggerated benefits, and promised access or results.
- **[Q-002] Two audiences:** The brochure must work without a spoken introduction: clear topic and benefit, concise explanation, actionable example/takeaway, and relevant limitations. Use supplied sender details only; never invent contact information, credentials, or service offers. Companion material provides a brief opening for staff/director conversations, plain-language explanation, likely questions and answers, and what the representative cannot confidently claim. Internal talking notes must never enter director-facing exports.
- **[Q-003] Claim support:** Connect important factual claims to inspectable supporting sources, not an unrelated bibliography. Preserve title, publisher, direct URL, available publication/update date, research date, and enough context to understand the claim-source relationship. Prefer primary sources; distinguish sourced facts, suggestions, and uncertainty. Do not fabricate citations or treat a search snippet as verified article content. If a central claim lacks support, revise the topic or explain why it cannot proceed as a supported brochure.
- **[Q-004] Honest currentness:** Check whether time-sensitive claims remain applicable. Research time, source publication time, and current validity are different. The newest returned result alone never proves currentness. Undated sources may support stable background facts without proving recent change. Disclose unresolved conflicts or age limitations; do not present stale/unverified content as current. Search failure must be visible; reusing older evidence requires clear labeling and representative choice. Search passes, ranking, refresh periods, and status-field names remain implementation choices.
- **[Q-005] Content boundaries:** Company inputs follow the same evidence and non-promotion rules. Identify their origin and conflicts with external evidence; retain useful neutral portions where possible. Treat webpages and uploaded content as evidence, never as instructions that override product rules. Separate AI examples from claims of clinical suitability or measured outcomes; do not generate patient-specific diagnosis or treatment instructions. Patient records are outside the initial input scope.

## 5. Inputs, saved work, and document outputs

- **[Q-006] Narrow input support:** State supported company-input types and size limits; report unreadable, unsupported, or excessive input clearly. Choose a small input surface for the first release. Arbitrary formats, OCR, connected drives, and a company knowledge base are not implied. Do not send private company content into public search queries.
- **[Q-007] Consistent saved revision:** Save the selected topic, evidence references, actual generated content, representative material, and their export association. Reopening work must not regenerate it silently. PDF and editable exports must represent the same content revision; companion material must agree. Content changes require renewed checks and review before being marked ready. External edits to downloaded documents are outside the application's verified revision.
- **[Q-008] Usable exports and recovery:** Verify Korean fonts, readable layout, intact links/citations, and no clipped or missing content. Editable output must contain editable text, not page images; identical pagination across formats is unnecessary. Generation is complete only when both audience materials exist; export is complete only when both brochure formats succeed. Keep valid partial results, identify failures, and retry the failed step without unnecessarily rerunning research or generation. Representative-material PDF/DOCX exports are not required by REQ-007.

## 6. Minimum SaaS operating baseline

- **[Q-009] Private ownership:** Require authentication and server-side ownership checks for saved inputs, drafts, notes, and downloads. One account must not retrieve another account's material. Files are private by default. Establish this before any deployed flow accepts real private material; organization roles and approval workflows are unnecessary for the pilot.
- **[Q-010] Bounded, recoverable work:** Preserve completed work across reloads and provider failures; show progress and actionable errors. Prevent duplicate billable work from repeated submissions. Configure limits for research, generation, input size, concurrency, duration, and retries; record enough cost/error information to operate the pilot. Do not retry indefinitely or report partial work as complete.
- **[Q-011] Data lifecycle:** Users can retrieve and delete their saved work and associated artifacts. Define and communicate retention, backup-deletion behavior, and external AI processing before the pilot; disclose any delayed deletion. Send only necessary content to configured providers and keep private content/credentials out of routine logs.

## 7. Development direction and phase gates

Start with a small application whose research, composition, saved content, and rendering responsibilities are separated in code. A simple application backend is the default; independent services, an agent framework, vector/graph databases, and distributed workflows need demonstrated value. Handle long operations with visible progress and recovery; choose the mechanism in the active phase plan.

| Phase | Build and exit condition |
| --- | --- |
| 1. Prove the deliverable | Use a small, researched example path from topic selection to Korean brochure, private notes, and real PDF/editable files. A human can explain the practical value and verify the evidence; inspect actual rendered files. Internal prototypes use non-sensitive inputs. |
| 2. Complete the workflow | Connect actual discovery, selection, both composition modes, correction/review, authenticated ownership, saved work, and revision-consistent exports. A representative can complete and reopen both input paths; another account cannot access them. Implement failures alongside each feature. |
| 3. Run a controlled SaaS pilot | Verify provider outages, reloads, duplicate requests, partial exports, usage limits, and deletion behavior. Choose numeric budgets and document the deployment/recovery procedure. All retained requirements and adopted quality rules work together before calling the initial release complete. |

Later expansion requires a separate scoped decision. Do not build future features or their infrastructure merely because they appear in a roadmap.

## 8. Acceptance outcomes

Use a few representative end-to-end cases and targeted failure checks, not repeated assertions for every document section:

- A useful, supported topic can be chosen; an irrelevant headline or unsupported central claim does not pass as a ready brochure.
- The Korean handout stands alone, while private notes let the representative explain a useful example and a relevant limitation. No internal notes leak into either brochure export.
- Both AI-led and supported company-input paths satisfy the same scope and evidence rules, including conflicting or promotional input.
- Correction/review, reopening, and PDF/editable export preserve the same substantive content and evidence references.
- Stale/undated evidence and unavailable research produce truthful limitations, not a false currentness label or invented citations.
- Partial generation/export failure preserves valid work, identifies the missing result, and permits bounded recovery.
- Access isolation, private downloads, deletion, and usage controls work; all original exclusions remain intact.

Examples guide evaluation; they do not require a particular prompt, model response, fixture, or internal schema. Actual contact-rate improvement can be explored later; it is not a required analytics feature or launch guarantee.

## 9. Working defaults and decisions left open

| ID | Changeable starting choice |
| --- | --- |
| D-001 | Korean interface and generated materials; DOCX for the editable brochure. |
| D-002 | One readable template, initially a short A4 handout; compact source/date attribution on the brochure and full evidence in private notes. Optional supplied sender/contact block. Exact length is a content-validation decision. |
| D-003 | A small correction/regeneration flow; representative notes viewable and copyable in the app. No full document editor or DOCX reimport requirement. |
| D-004 | Individual-account pilot. Team administration, billing automation, CRM, automated outreach, tracking links, and physician databases require separate scope decisions. |

Choose providers, stack, persistence design, rendering tools, supported company inputs, and measurable quality/usage thresholds in the phase that needs them. Record consequential choices and reasons there. This baseline intentionally does not fix API schemas, database tables, candidate counts, freshness windows, or pixel-level layouts.

## 10. Instructions for development across context resets

- Keep this baseline stable. Preserve requirement IDs; change both languages together. Use short decision records for accepted changes, not unexplained new assumptions.
- Detail only the current phase in a phase plan; archive completed detail. Break work into small, demonstrable outcomes with relevant verification.
- Maintain a short checkpoint containing the current phase, completed and verified work with evidence, consequential decisions and reasons, relevant paths, unresolved blockers, and the next action.
- On restart/compaction, read the English baseline, current phase plan, and latest checkpoint before relevant code. Do not reconstruct requirements from a compressed chat summary or reload both full translations routinely.
- Inspect the existing repository and environment before choosing tools. Check only affected acceptance outcomes; record actual results and remaining limits. Preserve the user's choices and ask only when an unresolved decision materially changes scope, cost, or the intended outcome.

Revision note: aligned the two supplied versions; retained original IDs; replaced the Korean-only currentness algorithm; consolidated repeated checks; removed undefined decision references; added proposed content, revision, SaaS, and recovery principles. No product implementation is included.
