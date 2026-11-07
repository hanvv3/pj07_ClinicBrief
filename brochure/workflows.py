"""Orchestrate paid work separately from authenticated storage and rendering."""
import copy
import uuid

from .service import AppError, sender_values
from .insight_store import build_history, project_insight_fields, public_selection_report


def text_input(value, limit, label):
    if not isinstance(value, str) or len(value) > limit:
        raise AppError(f'{label}는 {limit}자 이내로 입력해 주세요.')
    if any((ord(c) < 32 and c not in '\n\t\r') or 0x7f <= ord(c) <= 0x9f
           or 0xd800 <= ord(c) <= 0xdfff or ord(c) in (0xfffe,0xffff) for c in value):
        raise AppError(f'{label}에 사용할 수 없는 문자가 있습니다.')
    return value.strip()


def _research_topic(topic):
    if not isinstance(topic, dict):
        raise AppError('조사 결과의 주제 형식이 올바르지 않습니다.')
    public = {}
    for key in ('title', 'category', 'summary', 'director_value', 'takeaway', 'research_date',
                'evidence_status', 'evidence_notice', 'coverage_area', 'why_now'):
        if key in topic:
            public[key] = text_input(topic[key], 4000, '공개 주제')
    minutes = topic.get('reading_minutes')
    if type(minutes) is not int or not 1 <= minutes <= 10:
        raise AppError('조사 결과의 읽기 시간이 올바르지 않습니다.')
    public['reading_minutes'] = minutes
    sources, claims = topic.get('sources'), topic.get('claims')
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 5
            or not isinstance(claims, list) or not 1 <= len(claims) <= 8):
        raise AppError('조사 결과에 확인 가능한 근거가 필요합니다.')
    public['sources'] = []
    for source in sources:
        if not isinstance(source, dict):
            raise AppError('조사 결과의 출처 형식이 올바르지 않습니다.')
        clean = {key: text_input(source.get(key), 4000, '공개 출처')
                 for key in ('id', 'title', 'publisher', 'url', 'context')}
        for key in ('published_at', 'updated_at', 'checked_at', 'verification'):
            if key in source:
                clean[key] = text_input(source[key], 100, '출처 정보') if source[key] is not None else None
        public['sources'].append(clean)
    identifiers = {source['id'] for source in public['sources']}
    public['claims'] = []
    for claim in claims:
        refs = claim.get('source_ids') if isinstance(claim, dict) else None
        if (not isinstance(refs, list) or not 1 <= len(refs) <= 5
                or any(not isinstance(ref, str) or ref not in identifiers for ref in refs)):
            raise AppError('조사 결과의 주장과 출처 연결이 올바르지 않습니다.')
        public['claims'].append({'id': text_input(claim.get('id'), 80, '주장 식별자'),
            'text': text_input(claim.get('text'), 2000, '주장'), 'source_ids': list(refs)})
    try:
        public.update(project_insight_fields(topic))
    except ValueError:
        raise AppError('조사 결과의 주제 선택 정보가 올바르지 않습니다.') from None
    return public


def _usage(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ('requests', 'input_tokens', 'output_tokens', 'total_tokens')
            if type(value.get(key)) is int and 0 <= value[key] < 100_000_000}


class Workflows:
    def __init__(self, service, provider, jobs, briefing=None, insights=None):
        self.service, self.provider, self.jobs = service, provider, jobs
        self.briefing = briefing
        self.insights = insights

    def ready(self):
        if not self.provider.configured:
            raise AppError('OpenAI API 키가 설정되지 않았습니다. 서버의 .env.local 설정 후 다시 시도해 주세요.', 503)

    def research_topics(self, owner):
        return self.service.store.topics(owner)

    def research(self, owner, body):
        category = body.get('category')
        if category not in ('briefing', 'communication', 'operations', 'ai-literacy'):
            raise AppError('목록에서 조사 주제를 선택해 주세요.')
        history = None

        def prepare():
            nonlocal history
            self.ready()
            feedback = self.insights.history_feedback(owner=owner) if self.insights is not None else []
            shared = self.briefing.snapshot()['items'] if self.briefing is not None else []
            history = build_history(self.research_topics(owner) + shared, feedback)

        # Public research history and explicit votes only; never drafts or company input.
        def work(progress):
            result = self.provider.discover_insights(category, history=history, progress=progress)
            if (not isinstance(result, dict) or not isinstance(result.get('topics'), list)
                    or not 0 <= len(result['topics']) <= 3):
                raise AppError('조사 결과의 주제 수가 허용 범위를 벗어났습니다.')
            try:
                report = public_selection_report(result.get('selection_report'))
                if report and report['selected_count'] != len(result['topics']):
                    raise ValueError()
            except ValueError:
                raise AppError('조사 결과의 선택 보고서가 올바르지 않습니다.') from None
            topics = [_research_topic(topic) for topic in result['topics']]
            for topic in topics:
                topic['id'] = 'research-' + uuid.uuid4().hex
            if topics:
                self.service.store.save_topics(owner, topics)
            return {'topics': topics, 'usage': _usage(result.get('usage')), 'selection_report': report}
        return self.jobs.submit(owner, 'research', body.get('request_id'), {'category':category},
                                work, before_submit=prepare)

    def selected(self, owner, body):
        if body.get('source') == 'example':
            topic = next((t for t in self.service.topics if t['id'] == body.get('topic_id')), None)
        elif body.get('source') == 'research':
            topic = self.service.store.topic(owner, body.get('topic_id'))
        elif body.get('source') == 'briefing' and self.briefing is not None:
            topic = self.briefing.get_topic(body.get('topic_id'))
        else:
            topic = None
        if topic is None:
            raise AppError('선택한 주제를 찾을 수 없습니다. 목록에서 다시 선택해 주세요.', 404)
        return copy.deepcopy(topic)

    def compose(self, owner, body):
        if body.get('input_confirmed') is not True:
            raise AppError('외부 AI 처리와 입력 범위를 먼저 확인해 주세요.')
        source, topic_id = body.get('source'), body.get('topic_id')
        if source not in ('example', 'research', 'briefing') or not isinstance(topic_id, str):
            raise AppError('선택한 주제를 찾을 수 없습니다. 목록에서 다시 선택해 주세요.', 404)
        mode = body.get('mode')
        company = text_input(body.get('company_text',''), 6000, '회사 자료')
        if mode not in ('ai','company') or (mode == 'company' and not company) or (mode == 'ai' and company):
            raise AppError('작성 방식과 회사 자료 입력을 확인해 주세요.')
        sender = sender_values(body)
        payload = dict(topic_id=topic_id, source=source, mode=mode, company_text=company,sender=sender)
        topic = None

        def prepare():
            nonlocal topic
            self.ready()
            topic = self.selected(owner, body)

        def work(progress):
            result = self.provider.compose(topic, company_text=company, progress=progress)
            progress('검증한 자료를 저장하고 있습니다.')
            # ':' cannot occur in request IDs accepted by the prepared-draft route.
            draft = self.service.save_composition(owner,topic,result,sender,company,'compose:'+body['request_id'])
            return {'draft':draft,'usage':result.get('usage',{})}
        return self.jobs.submit(owner, 'compose', body.get('request_id'), payload, work, before_submit=prepare)

    def revise(self, owner, identifier, body):
        if body.get('input_confirmed') is not True:
            raise AppError('외부 AI 처리와 입력 범위를 먼저 확인해 주세요.')
        instructions = text_input(body.get('instructions'),1000,'수정 요청')
        if not instructions:
            raise AppError('수정할 내용을 입력해 주세요.')
        draft = previous = None
        payload = {'draft_id':identifier,'revision':body.get('revision'),'instructions':instructions}

        def prepare():
            nonlocal draft, previous
            self.ready()
            with self.service.lock:
                draft = self.service.get(identifier,owner)
                self.service.check_revision(draft,body.get('revision'))
                previous = {'brochure':copy.deepcopy(draft['brochure']),'notes':copy.deepcopy(draft['notes'])}
                previous['brochure']['sender'] = {'name':'','contact':''}

        def work(progress):
            # Check again before billable work, then atomically before replacing the snapshot.
            self.service.check_revision(self.service.get(identifier,owner),body['revision'])
            result = self.provider.compose(draft['selected_topic'],company_text=draft.get('company_text',''),
                       instructions=instructions,previous=previous,progress=progress)
            revised = self.service.replace_composition(owner,identifier,body['revision'],result)
            return {'draft':revised,'usage':result.get('usage',{})}
        return self.jobs.submit(owner,'revise',body.get('request_id'),payload,work,before_submit=prepare)

    def delete_draft(self, owner, identifier):
        def remove():
            self.service.delete(identifier,owner)
            for job in self.jobs.list(owner):
                result = job.get('result') or {}
                if result.get('draft',{}).get('id') == identifier:
                    self.jobs.delete(owner,job['id'])
        return self.jobs.run_if_idle(owner, remove)

    def delete_research(self, owner):
        def remove():
            self.service.store.delete_topics(owner)
            for job in self.jobs.list(owner):
                if job['kind'] == 'research':
                    self.jobs.delete(owner,job['id'])
        return self.jobs.run_if_idle(owner, remove)
