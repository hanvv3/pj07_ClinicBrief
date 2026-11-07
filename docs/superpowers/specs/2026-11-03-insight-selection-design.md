# Clinic problem discovery and useful output

User explicitly authorized implementing the proposed source-diverse discovery and comparing actual output with ordinary ChatGPT. No more interview/design approval questions. Existing key/model remain unchanged. This supersedes the narrow topic selection in direct research and the briefing, not account/data/export protections.

## Outcome

Find public evidence of concrete clinic-owner/staff tasks, infer useful topic hypotheses, verify answers separately, rank usefulness and novelty, and deliver complete usable text. A source announcement alone is not a reason to publish. Show actual observation, who benefits, selection reason, sources, and a copyable finished asset. Distinguish observed facts from inferred demand; do not claim prevalence or savings from a few examples. Sources must include publicly accessible clinic voices/notices and complementary independent technical/institutional sources when available. Do not fabricate diversity to fill quotas. Naver blog body availability is not guaranteed and no new Naver credentials are available.

## Approaches and chosen implementation

More keywords in the old prompt would leave selection unmeasured. A large unrestricted browsing agent would obscure cost and admission rules. Implement a bounded, staged discovery process on the existing Responses transport with explicit candidate decisions and history. Actual ChatGPT browser output is the comparison baseline; an API simulation must never be labeled actual ChatGPT.

## Provider contract

Add `OpenAIProvider.discover_insights(category, *, history=None, progress=None)` for the existing categories communication/operations/ai-literacy/briefing. All application research paths call it. Keep the old discover method for compatibility/diagnostics; no UI research path uses it.

Implement the orchestration in brochure/insights.py and schemas in brochure/insight_schema.py. Use existing _request transport, trusted KST dates, source URL validation and body-access ∩ native-citation evidence rules. No automatic retries. Maximum six Responses requests: two separate source-discovery lanes (clinic tasks/questions and tools/changes), a structured candidate selection, focused answer research, final structured topics/assets, and audit. Each browsing lane has at most eight web actions: maximum24 web actions total. Scout source cap16 combined; answer/final topic source cap5 each. Max6 initial candidates; final0–3. If insufficient evidence/usefulness survives, zero is a valid successful result; preserve old saved feed.

Candidate evaluation must explicitly score task specificity, usable output, novelty against history, and evidence (0–3 each). Server computes totals and enforces minimums; no self-reported overall pass. Reject blank worksheets, generic 'check/learn' takeaways, repeated problems with no sourced substantive change, and unsupported rules/features/benefits. Comparison of paraphrases against history is required in selection/audit; normalized problem_key additionally blocks exact conceptual repeats. Favor a small genuinely usable set over filling3. Publish only after factual and asset-scope audit. Medical/financial education remains permitted; patient-specific care and personalized trading are out of scope.

Return `{topics, usage, selection_report}`. Each topic retains the existing base fields (including coverage_area/why_now for ALL new topics), sources/claims, plus:

```
selection: {
 audience: 'director'|'staff'|'both', problem: string<=400,
 problem_key: string<=80, reason:string<=600,
 novelty:'new'|'update', previous_topic_id:string|null, change:string<=400,
 signals:[{source_id:string, observation:string<=500}],
 scores:{specificity:int, usability:int, novelty:int, evidence:int}, total:int
}
ready_to_use: {title:string<=120, format:'prompt'|'message'|'checklist'|'comparison'|'brief',
 body:string<=3000, adaptation_note:string<=500}
selection_report: {sources_read:int, candidates_considered:int,
 rejected:[{title:string<=150, reason:string<=400}], selected_count:int}
```

Use exact server-bound source IDs. Signals reference body-read+cited sources and describe observed content, not invented quotations. Each final topic needs at least one signal; role/source independence must be reasoned honestly. Source0 remains the core story basis so existing source-date labels stay truthful. Ready text must be complete and actionable under stated assumptions; if local policy details are necessary, provide a usable neutral version or narrowly named adaptation, never invent recipient policy. The audit rejects empty placeholders as a finished asset. No baseline source URLs or manually authored scenarios are injected into production discovery.

History contract: `{recent_topics:[{id,title,problem,problem_key,coverage_area,summary,change}], feedback:[{problem_key,verdict,count}]}`. Summary/change are bounded public text (400 characters each); legacy records use empty defaults. Compare proposed updates against prior summary/change, not just the prior title. Reject an identical already-covered change locally. Limit recent_topics30 and feedback30 and the serialized history to24KiB, retaining newest whole records. Accept only these allowlisted public fields; never company_text, saved brochure/notes, identities, freeform feedback or secrets. Treat historical text as untrusted. Shared briefing sees shared public history/aggregate feedback only; direct research sees own public research history and own feedback, plus shared public topics if useful. Do not share private user research across users.

## Persistence/integration

New `brochure/insight_store.py`: `InsightStore(path)` with `set_feedback(owner, topic_id, problem_key, verdict, shared=False)`, `feedback_for(owner, topic_ids)` mapping id→verdict, `history_feedback(owner=None, shared=False)` returns above bounded aggregates, and helper `build_history(topics, feedback)` for strict allowlisting. Verdicts useful/not_useful/seen. Upsert one current vote per owner/topic. No external calls. Shared aggregate includes only votes on shared feed topics, never own research votes.

`BriefingService(..., insights=None)` preserves injected dependency compatibility. refresh calls discover_insights with bounded shared history. Retain selection/ready_to_use through a reusable validation/projector in insight_store.py; legacy saved topics remain readable without the added fields. Job result retains count/usage plus allowlisted selection_report. Zero results update success state without deleting prior items. Existing global2/24h, same scheduler/worker limits and no paid GET remain.

Insight feed identity distinguishes normalized conceptual problem keys on the same core source. Updates include predecessor and normalized change/source basis so the previous item and its votes remain separate. Identical recollection remains stable, and legacy fingerprints are unchanged.

`Workflows(..., briefing=None, insights=None)` calls discover_insights for direct research with owner history. Saving topics retains new metadata; compose takes existing selected snapshot. Provider._public_topic must carry public selection/ready asset so a later brochure doesn't lose the actual solution. Preserve empty-source/data protections and exact replay before lookup/readiness.

Direct research includes `briefing` as a broad “전체 분야에서 찾기” option under the existing private account quota; it does not submit a shared feed collection.

Root HTTP routes: GET briefing/research add top-level `feedback` map for current viewer (not inside shared stored items). POST `/api/topic-feedback` strict body `{topic_id,source:'briefing'|'research',verdict}` auth+CSRF, verify visible topic before store; returns `{topic_id,verdict}`. No private/freeform input. Instantiate one shared InsightStore in server and inject controller/workflows.

## UI

Feed and direct-research cards use new metadata when available: who/which task, why selected, source observations, and finished asset. A visible '바로 쓸 자료 보기' opens complete copyable body with copy button; no paid composition is needed to get value. Keep optional brochure composition. Show useful/not_useful/seen feedback and current choice; reload restores own feedback. Avoid raw scores as proof of usefulness. Empty successful selection explains that no sufficiently useful new topic survived and old items remain. Legacy topics gracefully retain source/usage details. Broader direct-category labels and description must match actual new behavior.

## Verification and baseline

Freeze one Korean brief shared by actual ChatGPT and new pipeline before collecting outputs. Ask3 useful topics across clinic practice/AI/operations with public sources and complete usable outputs; prohibit invented recipient policy. Use actual ChatGPT Chat browser mode, record exposed model/mode, exact prompt, full visible answer/citations, timing and limitations. Do not claim matched hidden search budgets/models. No product/customer/company secrets in either run.

Run one new actual collection within application limits and independently verify its source claims. Compare shuffled outputs without method labels using specificity, usefulness to intended audience, completion of asset, novelty, evidence/accuracy, and adaptation burden. Scores are editorial judgments, not real clinician acceptance; document weak cases and if ChatGPT performs better. Then verify at least one selected ready asset against source and app copy/view path and real brochure composition/export if needed to prove solution survives. Save original outputs; never secretly rewrite failed generated output. Further paid runs require a concrete observed defect and bounded diagnosis.

Runtime bundled Python; local app only. No usable writable Git checkout, no commit/PR/deployment. User feedback validation in real clinics and illustrated template integration remain separate.
