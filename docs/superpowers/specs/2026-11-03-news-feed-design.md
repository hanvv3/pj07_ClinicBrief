# Periodic public news and practical topics

The user requests an agent that keeps finding worthwhile news and medical/practical information from the web, not a manually maintained scenario catalog. Prior instructions explicitly opt out of repeated interviews and approval questions; implement sensible defaults directly. A later example asks for a ready-to-copy ChatGPT medical-assistant setup rather than only teaching prompt-writing concepts. This adds an editorial requirement without replacing the recurring discovery task.

## Approach and scope

Reuse Python, SQLite, the existing durable JobRunner and gpt-6.1-sol web-search/evidence pipeline. Add a shared, authenticated public feed with scheduled collection, a manual refresh and selection into existing private brochure composition. This is an application feature, not a Codex chat reminder. Public inputs only; no patient/company/private account material reaches its search. The 16 hypothetical scenarios are neither required inputs nor disguised live results.

An RSS-only collector would be cheap but too dependent on a fixed publisher list and usually lacks full claim context. Independent searches per account would duplicate calls and public content. The chosen default is one common public collection, with source inspection and private composition only after a user selects a topic. These are implementation decisions, not claims that the user specified a particular schedule.

Collect once daily at 09:00 Asia/Seoul while the local server runs. Add a manual collection button. Both share a global maximum of two new collection jobs per rolling 24 hours, including failed/interrupted jobs; normally each makes three provider requests, four at most. No automatic retry of a failed collection or replay of missed days. The main server starts the scheduler; make_server alone does not start timers in tests. Operator can disable scheduling with --no-auto-briefing. Missing key means no paid requests. No email, chat messages, push notifications or cloud deployment.

## Discovery and editing

Add discover('briefing'), retaining normal 1–3 candidates, strict source access/citation requirements, exact source IDs and separate audit. Build the public query from the server's current Korean date and an inclusive 14-day lookback. Medical research and practice AI are primary; rotate attention among operations/equipment, economics/investing and hobbies/life. Do not infer interests from age or specialty. Prefer primary sources; media can reveal leads but cannot justify facts attributed to unread linked papers.

Briefing topics add coverage_area (medical, ai, operations, economy, life) and why_now (max400 characters). First source must be the primary basis of the story, not a newer irrelevant background page. Its date drives freshness, never research time. Date ambiguity remains explicit. Dated sources in the 14-day window appear as recent; older and undated materials have separate labels. No claim that the date or model audit guarantees continuing validity.

Medical research summaries are permitted; patient-specific diagnosis/treatment instructions are not. Financial articles distinguish publication/report dates, holdings and commentary; no invented real-time positions, guaranteed returns or personal allocations. Korean copy explains a concrete problem and usable result without exaggerated benefit claims. Ready-to-copy presets, finished examples and evidence briefs are preferred over abstract writing lessons. A how-to/set-up item must not be called breaking news merely because it was collected today.

## Persistence and API

BriefingService(path, provider, jobs, enabled=True, clock=None) owns a separate public-feed SQLite database. Use the existing job pool under reserved owner __briefing__, kind briefing. APIs require login; POST additionally requires CSRF. Shared-job progress is not in users' private /api/jobs.

- GET /api/briefing returns {items:Topic[],status:{auto_enabled,schedule_hour:9,timezone:'Asia/Seoul',next_run_at,last_success_at,last_attempt,daily_limit:2,remaining_runs,configured}}.
- POST /api/briefing/refresh {request_id} returns {job:publicJob}, HTTP202. Reject unknown request fields, so arbitrary private text cannot enter research.
- Topic IDs are feed- plus32hex, with collected_at and freshness:{kind:'recent'|'older'|'undated',date:ISO|null,label:Korean}. Freshness recomputes on reads; month-only/future/ambiguous dates cannot be recent.
- POST /api/compose accepts source:'briefing' and a saved feed ID. Resolve from server feed store at admission, deep-copy into the existing owner-only draft. Users may share the public source item but never each other's generated documents or inputs.

Canonicalize primary URL and date for deterministic deduplication; strip fragments/tracking parameters but retain meaningful query parameters. A new dated source update may form a new item. Keep at most90 items and30 days of collected public material. Collection failure preserves the last good feed. Public job results contain counts/usage only. A saved private draft retains its own evidence snapshot when a feed item expires.

## UI

Default to 새 소식, with 직접 조사 and 준비된 예제 available. Show schedule, last successful collection, current progress/error, remaining collection allowance, source dates, source links, reader relevance and a practical takeaway. Manual collection is explicit, disabled while running/no key/quota exhausted. Poll active collection every2s and otherwise the visible feed every60s with GET only. Page entry/reload never starts paid work. Selecting an item reuses both-material composition/review/export.

## Verification

Tests cover idempotence and global quota, timer boundary/restart/failure behavior, URL deduplication, source freshness vs collection time, last-good-feed retention, authenticated CSRF routes, shared public vs private draft ownership, provider evidence controls, UI refresh/polling and source selection. Complete a real-key collection and independently compare returned claims/dates with source pages. Verify browser display and selecting a feed item; preserve existing regression suite. Capture a screenshot of actual results. Existing illustrated brochure preview is not silently claimed to be the production renderer.
