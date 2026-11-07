# Content and brochure feedback — 2026-11-03

This records user feedback and investigation. The user subsequently opted out of further questions and asked for autonomous scenario creation; proceed with reasonable editorial choices. The previous technical workflow and model comparison results remain valid, but do not establish editorial quality or practical appeal.

## Confirmed user requirements

- Write natural Korean. Explain unfamiliar ideas in ordinary sentences, use examples when useful, and avoid both compressed jargon and excessive length.
- Produce a designed brochure with relevant, natural imagery, rather than a text dump on A4.
- Choose attractive topics for clinic owners: useful medical/practice AI setup, clinic marketing, recurring equipment problems and costs, and more informed independent non-covered pricing decisions are examples, not a closed category list.
- Learn from actual problems and experience rather than relying only on web discovery. The user has tacit field knowledge, not stored visit notes.
- Catchy titles may take inspiration from news headline techniques, but must not depend on misleading promises.
- Later clarification adds hobbies, economics, stocks, near-future portfolio questions and famous investors' thinking. Do not restrict interesting topics to clinic operations. Age examples suggest situations to consider, not observed demographic facts or individual profiling.
- The user explicitly rejected repeated interview questions. Generate hypothetical scenarios ourselves, labeled as such. The known printer event ended with a technician solving it; its technical cause and cost are unknown.

## Initial findings before the news-feed iteration

- `brochure/provider.py:24` fixes three narrow searches: CDC/AHRQ communication and workflow checks, plus NIST/WHO AI literacy and cautions. The original product already permits engaging AI setup and broader non-promotional practical topics.
- The UI and workflow accept category IDs but no practical question to guide discovery (`web/app.js:431`, `brochure/workflows.py:31`). Candidate ordering does not evaluate reader interest or diversify practical problems.
- Composition instructions steer suggestions toward checks/questions and repeat limitations. The schema permits substantial text; JSON limits alone do not explain the unnatural writing (`brochure/provider.py:589`, `brochure/provider_schema.py:29`).
- `brochure/rendering.py:95` starts a blank Word document; `render_docx` writes a linear stack of paragraphs, an early evidence notice, sections, an example, limitations and references. There is no visual content model or reusable designed layout with image placement.
- Stronger model capability remains helpful, but cannot by itself change this restricted discovery contract or renderer.

## Earlier directions and remaining document work

One route broadens searches and improves editing/templates using public information. Another could add optional field-experience interviews, but the user has now rejected further questions and chosen autonomous scenario creation for this iteration. Create plausible situations, select interesting and usable angles, then research the factual answer. AI-led discovery remains the primary mode; an interview is not a prerequisite.

Ask about a recent event, what the person did, and what remained difficult. Keep the remembered account separate from interpretation and from an AI-generated hypothesis. Do not invent missing costs, frequency, causes, quotations or resolutions. A recollection can identify a useful topic without proving that most clinic owners share it or that a proposed solution works. Before any public search, remove identities and private details; the public query should describe the general problem.

Potential future topic sources include consenting clinic staff/owners explaining an actual task, field representatives recalling a visit, and voluntarily supplied service/repair histories. These are optional collection methods, not data already accessed. No external interviews, contacts, recordings, messages or private-system imports have been performed. Do not ask the user to supply these now.

Use public research to check the proposed answer: manufacturer support for a particular printer/model; official product documentation for an AI feature; HIRA for the scope and interpretation of published non-covered prices. Independent pricing material needs comparable service contents and the clinic's own cost assumptions; public prices alone do not establish an optimal price. A brochure about marketing methods is distinct from generating a clinic advertisement.

Two likely brochure shapes are a short illustrated guide someone can follow and a comparison sheet that helps a decision. Use real, verified screenshots for actual settings; photographs or illustrations for context; diagrams/tables for relationships and comparisons. Preserve editable text in DOCX and render PDF from the same saved revision. Keep important limitations visible while consolidating repeated research-process caveats.

The completed editorial deliverable is `output/editorial-preview/catalog.md` and `scenarios.json`: sixteen hypothetical scenarios across five interest areas. `printer-service-brief.docx`, `.pdf` and `.png` provide one illustrated, editable printer brochure preview. The one-page output was visually inspected; editable Korean, matching PDF/DOCX text, embedded image and source links passed verification. This lets the user see actual writing and design without more interview questions. The printer's actual symptoms remain unknown; no invented episode is presented as a real case. The live application's automatic behavior is unchanged.

## Research references

- GOV.UK interview guidance recommends concrete stories and actual examples rather than general descriptions of how work should happen: https://www.gov.uk/service-manual/user-research/using-in-depth-interviews
- GOV.UK contextual research describes observing actual tasks, barriers and workarounds, with participant consent: https://www.gov.uk/service-manual/user-research/contextual-research-and-observation
- HIRA publishes institution-level non-covered prices and explains that staffing, facilities, equipment, procedure difficulty and included services/materials affect comparison: https://www.hira.or.kr/npay/index.do?WT.gnb=%EB%B9%84%EA%B8%89%EC%97%AC%EC%A7%84%EB%A3%8C%EB%B9%84%EC%A0%95%EB%B3%B4%23app%2Frb%2FnpayDamtInfoList&pgmid=HIRAA030009000000
- The 2026 AMA survey describes US physicians' actual reported AI uses, including medical research summaries. It can suggest questions to explore, but is not evidence of Korean clinic owners' priorities: https://www.ama-assn.org/practice-management/digital-health/more-80-physicians-use-ai-professionally-ama-survey

No product code, dependencies or provider configuration changed during investigation. Preview work subsequently uses one built-in image generation call, a standalone DOCX/PDF builder and the scenario collection. The existing application's automatic discovery and generation behavior is unchanged.

## Implemented follow-up

The user subsequently asked for periodic web discovery beyond the sixteen scenarios. The application now has a shared daily public-news feed, wider medical/AI/operations/economy/life discovery and source-based freshness labels. One real collection and the browser handoff passed; see `docs/verification/news-feed-2026-11-03.md`. New setup-oriented content should deliver complete usable text, not just concepts: a fourth prepared example now provides a ChatGPT medical-assistant setup and three ready requests. These are authored examples grounded in official product documentation, not fabricated news. The illustrated output template remains a prototype; applying it to production rendering is still pending.

## User review after trying the live feed

The user still feels no practical value or novelty from direct research. Results feel hand-curated/static despite real web calls. They ask whether an agent can infer topics from other clinics' Naver blogs and diverse sources, and whether ordinary ChatGPT is currently a better choice. This is a product-value objection, not a request for more prepared examples. Do not treat the previous 115 passing technical tests as editorial acceptance.

Read-only audit confirms: direct research still uses three fixed CDC/AHRQ/NIST/WHO-oriented queries; only the shared briefing expands the interests. Discovery has six search/open tool actions and at most five sources (plus a narrowly bounded source-read fallback), then extraction/audit without new research. It receives no prior topic history, user relevance feedback or clinic-work hypotheses. URL/date deduplication is not semantic novelty. There is no explicit usefulness ranking, independent-publisher problem clustering or discovery/verification source separation. The saved WHO research-methodology story supplies a blank worksheet and is weak evidence of immediate clinic-owner/staff value.

Proposed direction, not implemented: gather bounded Korean public problem signals, group related questions while deduplicating syndicated/promotional copies, form concrete audience/task hypotheses, verify the answer against appropriate primary sources, compare candidates for usefulness/novelty/finished-output value, and remember actual user feedback. Source recurrence is an observed signal, not proof of prevalence or demand. Benchmark real candidates against ordinary ChatGPT on the same brief before claiming a service advantage. The current service's proven advantages are workflow/storage/export; superior topic insight is unproven.

Feasibility check: Naver officially offers blog search metadata (title, link, description, author-blog fields, post date), not full article bodies: https://developers.naver.com/docs/serviceapi/search/blog/blog.md . No Naver credentials or connector were configured. Naver blog access was blocked in this investigation, so no claims are based on unread blog text. Accessible clinic-provided notices on https://ddocdoc.com/hospital/6861ea75fb5ba20a2a9d066a and https://ddocdoc.com/hospital/5ed4ab03c9cecac803996054 describe arrival timing after mobile check-in and differing cancellation rules. These suggest an editorial hypothesis about arrival/closing-time communication, not an industry-wide trend or a proven way to reduce delays. Patient reviews were not used as topic evidence. Official ChatGPT search/multi-source research documentation: https://learn.chatgpt.com/docs/web-search .
