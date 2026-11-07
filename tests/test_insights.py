"""Offline Responses fixtures exercise the real bounded insight orchestrator."""
import copy
import io
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from pathlib import Path
from unittest.mock import patch

from brochure.provider import OpenAIProvider, ProviderError, _public_topic
from tests.test_provider import response

CLINIC = 'https://clinic.example.org/notices/printing'
TOOLS = 'https://maker.example.org/help/print-status'
ANSWER = 'https://maker.example.org/help/print-queue'
STAGES = ('insight_clinic_scout', 'insight_tools_scout', 'insight_selection',
          'insight_answer_research', 'insight_topics', 'insight_edit', 'insight_audit')


def request_stage(request):
    payload = json.loads(request.data)
    name = payload['text']['format'].get('name')
    if name:
        return name
    instructions = payload['instructions']
    if 'Independently scout public clinic/hospital' in instructions:
        return 'insight_clinic_scout'
    if 'Independently scout complementary' in instructions:
        return 'insight_tools_scout'
    return 'insight_answer_research'


class InsightHTTPFixtures:
    """Route offline responses by stage, never by racing worker arrival order."""

    def __init__(self, *outputs):
        self.outputs = dict(zip(STAGES, outputs))
        self.requests = []
        self.lock = threading.Lock()

    def __call__(self, request, timeout):
        with self.lock:
            self.requests.append((request, timeout))
            result = self.outputs.pop(request_stage(request))
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(json.dumps(result, ensure_ascii=False).encode())


def narrative(url, text, *, opened=True, cited=True):
    raw = response({}, opened=False, cited=False, search=False)
    raw['output'] = []
    if opened:
        raw['output'].append({'type': 'web_search_call', 'status': 'completed',
                              'action': {'type': 'open_page', 'url': url}})
    raw['output'].append({'type': 'message', 'status': 'completed', 'role': 'assistant',
                          'content': [{'type': 'output_text', 'text': text,
                          'annotations': ([{'type': 'url_citation', 'url': url,
                                            'start_index': 0, 'end_index': len(text)}] if cited else [])}]})
    return raw


def scouts():
    return (narrative(CLINIC, '의원 공개 안내는 출력 대기 중인 문서의 상태 확인을 직원 업무로 설명합니다. 발행일 2026-11-01.'),
            narrative(TOOLS, '제조사 도움말은 출력 대기열에서 문서 상태를 볼 수 있다고 설명합니다. 게시일은 미상입니다.'))


def candidate(identifier='P1'):
    return {'id': identifier, 'title': '출력이 멈췄을 때 기사에게 보낼 상태 메모',
            'coverage_area': 'operations', 'why_now': '최근 의원 안내에서 확인한 출력 상태 전달 업무를 다룹니다.',
            'selection': {'audience': 'staff', 'problem': '출력이 멈추면 기사에게 관찰한 상태를 어떻게 전달할까',
                          'problem_key': 'print-status-message', 'reason': '공개 안내의 실제 업무를 바탕으로 보낼 문장을 제공합니다.',
                          'novelty': 'new', 'previous_topic_id': None, 'change': '',
                          'signals': [{'source_id': 'S1', 'observation': '의원 공개 안내는 출력 상태 확인을 직원 업무로 설명합니다.'}],
                          'scores': {'specificity': 3, 'usability': 3, 'novelty': 3, 'evidence': 2}},
            'answer_question': '기능이나 정책을 지어내지 않고 출력 상태 확인 요청을 완성할 수 있는가?',
            'asset_format': 'message', 'change_source_ids': []}


def selected(*items):
    return response({'candidates': list(items)})


def source(identifier, url, context):
    return {'id': identifier, 'title': '출력 상태 안내', 'publisher': '공개 도움말 제공자', 'url': url,
            'published_at': None, 'updated_at': None, 'context': context}


def final_topic(identifier='P1'):
    return {'id': identifier, 'title': '출력이 멈췄을 때 기사에게 보낼 상태 메모',
            'summary': '공개 안내는 출력 상태 확인 업무를 설명하고, 제조사는 대기열에서 상태를 볼 수 있다고 안내합니다.',
            'director_value': '직원이 기사에게 확인을 요청할 때 사용할 중립적인 연락 문장입니다.',
            'takeaway': '기사에게 바로 보낼 수 있는 출력 상태 확인 요청문을 제공합니다.',
            'reading_minutes': 2, 'evidence_notice': '개별 의원의 장비와 계약 조건은 확인하지 않았습니다.',
            'coverage_area': 'operations', 'why_now': '참고 자료: 공개된 출력 상태 안내를 바탕으로 한 업무 문장입니다.',
            'sources': [source('S1', CLINIC, '의원 공개 안내에서 출력 상태 확인을 직원 업무로 설명합니다. 해당 업무의 관찰 근거입니다.'),
                        source('A1', ANSWER, '제조사 도움말은 출력 대기열에서 문서 상태를 확인할 수 있다고 설명합니다. 정확한 화면은 제품별로 다를 수 있습니다.')],
            'claims': [{'id': 'C1', 'text': '공개 안내는 출력 상태 확인을 직원 업무로 설명합니다.', 'source_ids': ['S1']},
                       {'id': 'C2', 'text': '제조사 도움말은 출력 대기열에서 문서 상태를 볼 수 있다고 안내합니다.', 'source_ids': ['A1']}],
            'ready_to_use': {'title': '기사에게 보내는 출력 상태 확인 요청', 'format': 'message',
                             'body': '안녕하세요. 출력이 진행되지 않아 상태 확인을 요청드립니다. 현재 화면의 오류 문구와 출력 대기열 상태를 먼저 확인하겠습니다. 원격으로 확인 가능한지, 방문이 필요한지 안내해 주세요. 비용이 발생하는 작업은 금액과 범위를 먼저 알려 주시면 확인 후 진행하겠습니다.',
                             'adaptation_note': '관찰한 오류 문구가 있으면 별도 메시지로 덧붙이세요. 계약 조건이나 방문 가능 여부는 단정하지 않았습니다.'}}


def audit(*ids, passed=True, reason=''):
    return response({'decisions': [{'id': identifier, 'factual_support': passed, 'asset_complete': passed,
                                   'novelty_supported': passed, 'scope_safe': passed,
                                   'provenance_correct': passed, 'reason': reason} for identifier in ids]})


def edited_topic(topic):
    item = {key: copy.deepcopy(topic[key]) for key in
            ('id', 'title', 'summary', 'director_value', 'takeaway', 'why_now')}
    item['ready_to_use'] = {key: topic['ready_to_use'][key] for key in ('title', 'body')}
    return item


class InsightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-provider-credential-00000'}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.provider = OpenAIProvider(Path(self.tmp.name))
        clock = patch('brochure.provider._today', return_value='2026-11-03')
        clock.start()
        self.addCleanup(clock.stop)

    def transport(self, *outputs):
        fixture = InsightHTTPFixtures(*outputs)
        patched = patch('brochure.provider.urlopen', fixture)
        patched.start()
        self.addCleanup(patched.stop)
        return fixture

    def full(self, *, candidates=None, topics=None, edited=None, audited=None):
        topics = topics if topics is not None else [final_topic()]
        return self.transport(*scouts(), selected(*(candidates if candidates is not None else [candidate()])),
                              narrative(ANSWER, '공식 제품 도움말은 출력 대기열에서 문서 상태를 볼 수 있다고 설명합니다. 날짜 미상.'),
                              response({'topics': topics}),
                              edited if edited is not None else response({'topics': [edited_topic(t) for t in topics]}),
                              audited if audited is not None else audit('P1'))

    @staticmethod
    def payloads(transport):
        ordered = sorted(transport.requests, key=lambda item: STAGES.index(request_stage(item[0])))
        return [json.loads(request.data) for request, _ in ordered]

    def test_scouts_overlap_join_before_selection_and_keep_lane_source_ids(self):
        clinic_url = 'https://z-clinic.example.org/notice'
        tools_url = 'https://a-maker.example.org/help'
        trace_context = ContextVar('insight_test_trace', default=None)
        for first in STAGES[:2]:
            with self.subTest(first=first):
                barrier = threading.Barrier(2, timeout=2)
                first_finished = threading.Event()
                completed, contexts = [], []
                lock = threading.Lock()
                fixture = InsightHTTPFixtures(narrative(clinic_url, '의원 원문 보고서'),
                                             narrative(tools_url, '제조사 원문 보고서'), selected())

                def request(request, timeout):
                    name = request_stage(request)
                    if name in STAGES[:2]:
                        contexts.append(trace_context.get())
                        try:
                            barrier.wait()
                        except threading.BrokenBarrierError:
                            self.fail('The second independent scout never ran concurrently.')
                        if name != first:
                            self.assertTrue(first_finished.wait(2))
                        with lock:
                            completed.append(name)
                        if name == first:
                            first_finished.set()
                    else:
                        self.assertEqual(set(completed), set(STAGES[:2]))
                    return fixture(request, timeout)

                token = trace_context.set('public-run-context')
                try:
                    with patch('brochure.provider.urlopen', request):
                        result = self.provider.discover_insights('operations')
                finally:
                    trace_context.reset(token)
                self.assertEqual(result['topics'], [])
                self.assertEqual(result['usage']['requests'], 3)
                self.assertEqual(completed[0], first)
                self.assertEqual(contexts, ['public-run-context', 'public-run-context'])
                selection = json.loads(self.payloads(fixture)[2]['input'][0]['content'])
                self.assertEqual(selection['verified_sources'], {'S1': clinic_url, 'S2': tools_url})
                self.assertEqual([report['lane'] for report in selection['scout_reports']], list(STAGES[:2]))
                self.assertEqual([report['report'] for report in selection['scout_reports']],
                                 ['의원 원문 보고서', '제조사 원문 보고서'])

    def test_concurrent_runs_on_same_provider_do_not_mix_reports_or_contexts(self):
        barrier = threading.Barrier(4, timeout=3)
        trace_context = ContextVar('concurrent_insight_test_trace', default=None)
        selected_inputs = {}
        lock = threading.Lock()

        def request(request, timeout):
            name = request_stage(request)
            data = json.loads(json.loads(request.data)['input'][0]['content'])
            category = data['category']
            self.assertEqual(trace_context.get(), category)
            if name in STAGES[:2]:
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    self.fail('Independent runs must both execute both scouts concurrently.')
                raw = narrative(f'https://public.example.org/{category}/{name}', category + ' 공개 보고서')
            else:
                self.assertEqual(name, 'insight_selection')
                with lock:
                    selected_inputs[category] = data
                raw = selected()
            return io.BytesIO(json.dumps(raw, ensure_ascii=False).encode())

        def run(category):
            token = trace_context.set(category)
            try:
                return self.provider.discover_insights(category)
            finally:
                trace_context.reset(token)

        with patch('brochure.provider.urlopen', request), ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, category) for category in ('operations', 'communication')]
            results = [future.result() for future in futures]
        for category, data in selected_inputs.items():
            self.assertEqual([report['report'] for report in data['scout_reports']],
                             [category + ' 공개 보고서'] * 2)
            self.assertTrue(all('/' + category + '/' in url for url in data['verified_sources'].values()))
        self.assertEqual(len(selected_inputs), 2)
        self.assertEqual([result['usage']['requests'] for result in results], [3, 3])

    def test_graph_states_serialize_without_credentials_or_raw_reasoning(self):
        from brochure.insights import _build_graph

        fixture = self.full()
        for raw in fixture.outputs.values():
            raw['private_transport_metadata'] = 'PRIVATE_TRANSPORT_MARKER'
            raw['output'].insert(0, {'type': 'reasoning', 'summary': ['PRIVATE_REASONING_MARKER']})
        initial = {
            'public_input': {'category': 'operations', 'validation_context': {'research_date': '2026-11-03'}},
            'history': {'recent_topics': [], 'feedback': []},
            'responses': [], 'reports': [], 'verified': {}, 'rejected': {},
            'considered': 0, 'chosen': [], 'answer_ids': [], 'published': [],
        }
        messages = []
        graph = _build_graph(self.provider, messages.append)
        for state in graph.stream(initial, config={'max_concurrency': 2}, stream_mode='values'):
            serialized = json.dumps(state, ensure_ascii=False)
            self.assertNotIn('PRIVATE_TRANSPORT_MARKER', serialized)
            self.assertNotIn('PRIVATE_REASONING_MARKER', serialized)
            self.assertNotIn('sk-test-provider-credential', serialized)
        self.assertEqual(len(state['result']['topics']), 1)
        self.assertEqual(state['result']['usage']['requests'], 7)
        self.assertTrue(messages)

    def test_seven_bounded_stages_publish_complete_asset_with_exact_provenance(self):
        transport = self.full()
        result = self.provider.discover_insights('briefing')
        self.assertEqual(len(result['topics']), 1)
        topic = result['topics'][0]
        self.assertEqual(topic['selection']['total'], 11)
        self.assertEqual(topic['selection']['signals'][0]['source_id'], 'S1')
        self.assertEqual(topic['ready_to_use']['body'], final_topic()['ready_to_use']['body'])
        self.assertEqual(topic['sources'][1]['url'], ANSWER)
        self.assertEqual(topic['sources'][1]['verification'], 'body_access_and_cited')
        self.assertEqual(result['selection_report'], {'sources_read': 3, 'candidates_considered': 1,
                                                     'rejected': [], 'selected_count': 1})
        self.assertEqual(result['usage']['requests'], 7)
        self.assertEqual(result['usage']['total_tokens'], 420)
        requests = self.payloads(transport)
        self.assertEqual([p.get('max_tool_calls', 0) for p in requests], [8, 8, 0, 8, 0, 0, 0])
        self.assertTrue(all(p['store'] is False for p in requests))
        inputs = [json.loads(p['input'][0]['content']) for p in requests]
        self.assertNotIn('scout_reports', inputs[1])
        self.assertEqual(inputs[0]['validation_context']['research_date'], '2026-11-03')
        self.assertEqual(inputs[0]['validation_context']['news_window']['start'], '2026-10-21')
        self.assertEqual(inputs[4]['verified_sources']['A1'], ANSWER)
        self.assertEqual(inputs[6]['history'], {'recent_topics': [], 'feedback': []})
        self.assertEqual(_public_topic(topic)['ready_to_use'], topic['ready_to_use'])
        self.assertEqual(_public_topic(topic)['selection'], topic['selection'])

    def test_low_score_candidate_is_rejected_locally_before_answer_research(self):
        bad = candidate()
        bad['selection']['scores']['usability'] = 1
        transport = self.transport(*scouts(), selected(bad))
        result = self.provider.discover_insights('operations')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['usage']['requests'], 3)
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(result['selection_report']['candidates_considered'], 1)
        self.assertIn('완성', result['selection_report']['rejected'][0]['reason'])

    def test_news_brief_can_be_complete_without_a_task_or_adaptation(self):
        story = candidate()
        story.update(title='출력 대기열에서 문서 상태를 볼 수 있습니다', asset_format='brief')
        story['selection']['problem'] = '출력 대기열은 직원에게 어떤 정보를 보여줄까'
        story['selection']['reason'] = '장비를 관리하는 직원이 출력 대기열에서 볼 수 있는 정보를 이해할 수 있습니다.'
        topic = final_topic()
        topic['title'] = story['title']
        topic['ready_to_use'] = {
            'title': story['title'], 'format': 'brief', 'adaptation_note': '',
            'body': '제조사 도움말에 따르면 출력 대기열에서 문서의 상태를 볼 수 있습니다. '
                    '정확한 화면은 제품에 따라 다를 수 있습니다. 의원의 공개 안내에서도 '
                    '직원이 출력 상태를 확인하는 업무를 소개하고 있습니다.'}
        transport = self.full(candidates=[story], topics=[topic])
        result = self.provider.discover_insights('briefing')
        self.assertEqual(result['topics'][0]['ready_to_use'], topic['ready_to_use'])
        self.assertEqual(result['topics'][0]['claims'], topic['claims'])
        self.assertEqual(len(transport.requests), 7)

    def test_editorial_guidance_is_loaded_for_topic_writing_and_audit(self):
        prompts = Path(self.tmp.name) / 'prompts'
        prompts.mkdir()
        (prompts / 'editorial.md').write_text('SHARED_EDITORIAL_POLICY', encoding='utf-8')
        (prompts / 'editorial-examples.md').write_text('FICTIONAL_STYLE_EXAMPLES', encoding='utf-8')
        transport = self.full()
        with patch('brochure.editorial.PROMPT_DIR', prompts):
            self.provider.discover_insights('briefing')
        requests = self.payloads(transport)
        self.assertIn('SHARED_EDITORIAL_POLICY', requests[4]['instructions'])
        self.assertIn('FICTIONAL_STYLE_EXAMPLES', requests[4]['instructions'])
        self.assertIn('SHARED_EDITORIAL_POLICY', requests[5]['instructions'])
        self.assertIn('FICTIONAL_STYLE_EXAMPLES', requests[5]['instructions'])
        self.assertIn('SHARED_EDITORIAL_POLICY', requests[6]['instructions'])

    def test_edit_replaces_public_copy_and_keeps_evidence_and_selection_intact(self):
        topic = final_topic()
        topic['summary'] = '출력 상태 확인 요청 전달의 필요성이 확인된 상황입니다.'
        revised = edited_topic(topic)
        revised['title'] = '프린터가 멈췄다면, 기사에게 이 문장을 보내세요'
        revised['summary'] = '기사에게 출력 상태를 확인해 달라고 요청할 때 쓸 연락 문장입니다.'
        revised['ready_to_use']['body'] = (
            '안녕하세요. 프린터에서 문서가 나오지 않아 연락드립니다. 오류 문구와 출력 대기열을 확인한 뒤 '
            '현재 상태를 알려드리겠습니다. 원격 확인이 가능한지 안내해 주세요. 방문이나 수리 비용이 '
            '든다면 작업 전에 금액과 범위를 알려 주세요.')
        transport = self.full(topics=[topic], edited=response({'topics': [revised]}))
        result = self.provider.discover_insights('operations')
        published = result['topics'][0]
        self.assertEqual(published['title'], revised['title'])
        self.assertEqual(published['summary'], revised['summary'])
        self.assertEqual(published['ready_to_use']['body'], revised['ready_to_use']['body'])
        self.assertEqual(published['claims'], topic['claims'])
        for actual, original in zip(published['sources'], topic['sources']):
            self.assertEqual({key: actual[key] for key in original}, original)
        self.assertEqual(published['selection'], {**candidate()['selection'], 'total': 11})
        for key in ('format', 'adaptation_note'):
            self.assertEqual(published['ready_to_use'][key], topic['ready_to_use'][key])
        self.assertEqual(published['evidence_status'], 'needs_review')
        inputs = [json.loads(p['input'][0]['content']) for p in self.payloads(transport)]
        edit_input = inputs[5]
        self.assertEqual(set(edit_input), {'topics'})
        item = edit_input['topics'][0]
        self.assertEqual(set(item), {'id', 'audience', 'purpose', 'facts', 'draft'})
        self.assertEqual(item['facts']['claims'], topic['claims'])
        self.assertEqual(item['draft']['ready_to_use'], topic['ready_to_use'])
        self.assertEqual(inputs[6]['proposed_topics'][0]['ready_to_use']['body'], revised['ready_to_use']['body'])
        self.assertNotIn('scout_reports', json.dumps(edit_input))
        self.assertNotIn('selection', json.dumps(edit_input))

    def test_edit_requires_every_topic_once_and_no_unknown_id(self):
        second = candidate('P2')
        second['selection']['problem_key'] = 'different-task'
        for ids in ([], ['P1'], ['P1', 'P1'], ['P1', 'OTHER']):
            with self.subTest(ids=ids):
                items = [edited_topic(final_topic(identifier)) for identifier in ids]
                transport = self.full(candidates=[candidate(), second],
                                      topics=[final_topic(), final_topic('P2')],
                                      edited=response({'topics': items}))
                with self.assertRaises(ProviderError):
                    self.provider.discover_insights('operations')
                self.assertEqual(len(transport.requests), 6)

    def test_edit_cannot_overwrite_source_or_asset_scope(self):
        for field, value in [('sources', []), ('selection', {}), ('claims', [])]:
            with self.subTest(field=field):
                revised = edited_topic(final_topic())
                revised[field] = value
                transport = self.full(edited=response({'topics': [revised]}))
                with self.assertRaises(ProviderError):
                    self.provider.discover_insights('operations')
                self.assertEqual(len(transport.requests), 6)
        revised = edited_topic(final_topic())
        revised['ready_to_use']['format'] = 'brief'
        self.full(edited=response({'topics': [revised]}))
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')

    def test_unfinished_edit_is_rejected_before_audit(self):
        revised = edited_topic(final_topic())
        revised['ready_to_use']['body'] = '오류: ______\n연락처: ______'
        transport = self.full(edited=response({'topics': [revised]}))
        result = self.provider.discover_insights('operations')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['usage']['requests'], 6)
        self.assertEqual(len(transport.requests), 6)

    def test_final_audit_can_reject_unsupported_claim_introduced_by_edit(self):
        revised = edited_topic(final_topic())
        revised['summary'] = '이 연락문을 쓰면 수리 비용이 절반으로 줄어듭니다.'
        transport = self.full(edited=response({'topics': [revised]}),
                              audited=audit('P1', passed=False, reason='편집본의 비용 절감 주장은 근거가 없습니다.'))
        result = self.provider.discover_insights('operations')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['selection_report']['rejected'][0]['reason'], '편집본의 비용 절감 주장은 근거가 없습니다.')
        audit_input = json.loads(self.payloads(transport)[6]['input'][0]['content'])
        self.assertEqual(audit_input['proposed_topics'][0]['summary'], revised['summary'])
        self.assertEqual(len(transport.requests), 7)

    def test_failed_edit_does_not_retry_or_publish_the_unedited_draft(self):
        transport = self.full(edited=TimeoutError('private upstream details'))
        with self.assertRaises(ProviderError) as caught:
            self.provider.discover_insights('operations')
        self.assertNotIn('private', str(caught.exception))
        self.assertEqual(len(transport.requests), 6)

    def test_editorial_incompleteness_rejects_a_factually_supported_topic(self):
        checked = json.loads(audit('P1')['output'][0]['content'][0]['text'])
        checked['decisions'][0]['asset_complete'] = False
        checked['decisions'][0]['reason'] = '소식의 핵심보다 주의사항이 대부분을 차지합니다.'
        self.full(audited=response(checked))
        result = self.provider.discover_insights('briefing')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['selection_report']['rejected'][0]['reason'],
                         '소식의 핵심보다 주의사항이 대부분을 차지합니다.')

    def test_total_threshold_and_top_three_ranking_are_enforced_locally(self):
        items = []
        for index, score in enumerate([8, 9, 10, 11, 12], 1):
            item = candidate(f'P{index}')
            item['selection']['problem_key'] = f'distinct-task-{index}'
            values = [2, 2, 2, 2]
            for i in range(score - 8):
                values[i] += 1
            item['selection']['scores'] = dict(zip(('specificity', 'usability', 'novelty', 'evidence'), values))
            items.append(item)
        transport = self.transport(*scouts(), selected(*items),
                                   narrative(ANSWER, '공식 도움말에서 각 작업의 직접 근거를 확인했습니다.'),
                                   response({'topics': []}))
        result = self.provider.discover_insights('operations')
        request = self.payloads(transport)[3]
        questions = json.loads(request['input'][0]['content'])['selected_questions']
        self.assertEqual([x['id'] for x in questions], ['P5', 'P4', 'P3'])
        self.assertEqual(result['selection_report']['candidates_considered'], 5)
        self.assertEqual(len(result['selection_report']['rejected']), 5)
        self.assertEqual(result['usage']['requests'], 5)

    def test_exact_normalized_history_repeat_cannot_be_called_new(self):
        old = {'id': 'old1', 'title': '기존 출력 상태 연락', 'problem': '출력 상태 전달',
               'problem_key': 'PRINT status message', 'coverage_area': 'operations'}
        self.transport(*scouts(), selected(candidate()))
        result = self.provider.discover_insights('operations', history={'recent_topics': [old], 'feedback': []})
        self.assertEqual(result['topics'], [])
        self.assertIn('반복', result['selection_report']['rejected'][0]['reason'])

    def test_update_requires_known_history_and_explicit_change_source(self):
        for previous, change_sources in [('missing', ['S2']), ('old1', [])]:
            with self.subTest(previous=previous, change_sources=change_sources):
                item = candidate()
                item['selection'].update(novelty='update', previous_topic_id=previous, change='대기열 화면이 개정됐습니다.')
                item['change_source_ids'] = change_sources
                self.transport(*scouts(), selected(item))
                result = self.provider.discover_insights('operations', history={'recent_topics': [
                    {'id': 'old1', 'title': '이전 주제', 'problem': '출력 상태 전달',
                     'problem_key': 'print-status-message', 'coverage_area': 'operations'}], 'feedback': []})
                self.assertEqual(result['topics'], [])

    def test_sourced_update_retains_previous_topic_and_change(self):
        item = candidate()
        item['selection'].update(novelty='update', previous_topic_id='old1',
                                 change='공개 의원 안내에 출력 상태 확인 업무가 추가됐습니다.')
        item['change_source_ids'] = ['S1']
        self.full(candidates=[item])
        result = self.provider.discover_insights('operations', history={'recent_topics': [
            {'id': 'old1', 'title': '이전 주제', 'problem': '출력 상태 전달',
             'problem_key': 'print-status-message', 'coverage_area': 'operations'}], 'feedback': []})
        self.assertEqual(result['topics'][0]['selection']['novelty'], 'update')
        self.assertEqual(result['topics'][0]['selection']['previous_topic_id'], 'old1')

    def test_already_reported_exact_change_is_rejected_without_answer_research(self):
        item = candidate()
        item['selection'].update(novelty='update', previous_topic_id='old1',
                                 change='온라인 접수 경로가 추가됐습니다.')
        item['change_source_ids'] = ['S1']
        transport = self.transport(*scouts(), selected(item))
        result = self.provider.discover_insights('operations', history={'recent_topics': [
            {'id': 'old1', 'title': '기존 접수 경로', 'problem': '출력 상태 전달',
             'problem_key': 'print-status-message', 'coverage_area': 'operations',
             'summary': '전화와 온라인 경로가 이미 포함된 이전 공개 요약입니다.',
             'change': '온라인  접수 경로가 추가됐습니다.'}], 'feedback': []})
        self.assertEqual(result['topics'], [])
        self.assertEqual(len(transport.requests), 3)
        self.assertIn('이미', result['selection_report']['rejected'][0]['reason'])

    def test_selection_and_audit_receive_prior_coverage_with_thirty_large_public_records_bounded(self):
        history = {'recent_topics': [], 'feedback': []}
        for index in range(30):
            history['recent_topics'].append({'id': str(index), 'title': '제' * 300,
                'problem': '문' * 400, 'problem_key': f'other-{index}', 'coverage_area': 'operations',
                'summary': '요' * 400, 'change': '변' * 400, 'company_text': 'NEVER_PRIVATE'})
        transport = self.full()
        self.provider.discover_insights('operations', history=history)
        requests = self.payloads(transport)
        for index in [2, 6]:
            public = json.loads(requests[index]['input'][0]['content'])['history']['recent_topics'][0]
            self.assertEqual(public['summary'], '요' * 400)
            self.assertEqual(public['change'], '변' * 400)
        self.assertTrue(all(len(request.data) <= 150000 for request, _ in transport.requests))
        self.assertNotIn('NEVER_PRIVATE', str(requests))

    def test_unrelated_previous_key_cannot_be_used_to_pass_update_gate(self):
        item = candidate()
        item['selection'].update(novelty='update', previous_topic_id='old1', change='새 화면 설명입니다.')
        item['change_source_ids'] = ['S1']
        transport = self.transport(*scouts(), selected(item))
        result = self.provider.discover_insights('operations', history={'recent_topics': [
            {'id': 'old1', 'title': '완전히 다른 주제', 'problem': '예약 장소 전달',
             'problem_key': 'appointment-place', 'coverage_area': 'operations'}], 'feedback': []})
        self.assertEqual(result['topics'], [])
        self.assertEqual(len(transport.requests), 3)

    def test_history_strips_private_material_and_caps_public_records(self):
        history = {'recent_topics': [{'id': str(i), 'title': '공개 주제', 'problem': '공개 문제',
                                     'problem_key': f'other-{i}', 'coverage_area': 'operations',
                                     'company_text': 'NEVER_PRIVATE_COMPANY'} for i in range(35)],
                   'feedback': [{'problem_key': 'other', 'verdict': 'not_useful', 'count': 2,
                                 'owner': 'NEVER_OWNER', 'comment': 'NEVER_PRIVATE_COMMENT'}],
                   'notes': 'NEVER_PRIVATE_NOTES'}
        transport = self.full()
        self.provider.discover_insights('communication', history=history)
        request_text = '\n'.join(request.data.decode() for request, _ in transport.requests)
        self.assertNotIn('NEVER_', request_text)
        data = json.loads(self.payloads(transport)[2]['input'][0]['content'])
        self.assertEqual(len(data['history']['recent_topics']), 30)
        self.assertEqual(data['history']['feedback'], [{'problem_key': 'other', 'verdict': 'not_useful', 'count': 2}])

    def test_snippets_only_are_not_used_for_signals_or_answers(self):
        transport = self.transport(narrative(CLINIC, '검색 결과 요약뿐입니다.', opened=False),
                                   narrative(TOOLS, '다른 검색 결과 요약뿐입니다.', opened=False))
        result = self.provider.discover_insights('briefing')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['selection_report']['sources_read'], 0)
        self.assertEqual(len(transport.requests), 2)

    def test_answer_without_body_access_stops_without_final_generation(self):
        transport = self.transport(*scouts(), selected(candidate()),
                                   narrative(ANSWER, '검색 결과에만 답이 있습니다.', opened=False))
        result = self.provider.discover_insights('operations')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['usage']['requests'], 4)
        self.assertIn('본문', result['selection_report']['rejected'][0]['reason'])
        self.assertEqual(len(transport.requests), 4)

    def test_unread_signal_source_is_rejected_before_answer_call(self):
        item = candidate()
        item['selection']['signals'][0]['source_id'] = 'UNREAD'
        transport = self.transport(*scouts(), selected(item))
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')
        self.assertEqual(len(transport.requests), 3)

    def test_unusable_problem_key_is_safe_provider_error(self):
        item = candidate()
        item['selection']['problem_key'] = '---'
        self.transport(*scouts(), selected(item))
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')

    def test_final_source_id_cannot_be_rebound_to_other_verified_url(self):
        item = final_topic()
        item['sources'][0]['url'] = ANSWER
        transport = self.full(topics=[item])
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')
        self.assertEqual(len(transport.requests), 5)

    def test_final_topic_must_retain_signal_and_focused_answer_source(self):
        for remove_id in ['S1', 'A1']:
            with self.subTest(remove_id=remove_id):
                item = final_topic()
                item['sources'] = [s for s in item['sources'] if s['id'] != remove_id]
                item['claims'] = [c for c in item['claims'] if remove_id not in c['source_ids']]
                self.full(topics=[item])
                result = self.provider.discover_insights('operations')
                self.assertEqual(result['topics'], [])
                self.assertEqual(result['usage']['requests'], 5)

    def test_blank_worksheet_and_generic_asset_are_not_finished_outputs(self):
        for body in ['확인 항목: ______\n문제: ______\n다음 단계: ______', '출력 상태를 확인하고 사용 방법을 배워 보세요.']:
            with self.subTest(body=body):
                item = final_topic()
                item['ready_to_use']['body'] = body
                self.full(topics=[item])
                result = self.provider.discover_insights('operations')
                self.assertEqual(result['topics'], [])
                self.assertEqual(result['usage']['requests'], 5)
                self.assertIn('완성', result['selection_report']['rejected'][0]['reason'])

    def test_independent_audit_rejects_paraphrased_repeat_or_invented_policy(self):
        transport = self.full(audited=audit('P1', passed=False, reason='과거 주제와 같은 문제이며 실제 정책 근거가 없습니다.'))
        result = self.provider.discover_insights('operations')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['selection_report']['rejected'][0]['reason'], '과거 주제와 같은 문제이며 실제 정책 근거가 없습니다.')
        self.assertEqual(len(transport.requests), 7)

    def test_empty_selection_is_success_and_does_not_spend_remaining_requests(self):
        transport = self.transport(*scouts(), selected())
        result = self.provider.discover_insights('ai-literacy')
        self.assertEqual(result['topics'], [])
        self.assertEqual(result['selection_report']['selected_count'], 0)
        self.assertEqual(len(transport.requests), 3)

    def test_audit_missing_or_duplicate_decision_cannot_publish(self):
        transport = self.full(audited=audit())
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')
        self.assertEqual(len(transport.requests), 7)

    def test_one_audit_failure_does_not_discard_an_independently_accepted_topic(self):
        second = candidate('P2')
        second['selection']['problem_key'] = 'different-task'
        decisions = audit('P1', 'P2')
        parsed = json.loads(decisions['output'][-1]['content'][0]['text'])
        parsed['decisions'][1].update(asset_complete=False, reason='다른 자료는 완성되지 않았습니다.')
        self.full(candidates=[candidate(), second], topics=[final_topic(), final_topic('P2')],
                  audited=response(parsed))
        result = self.provider.discover_insights('operations')
        self.assertEqual([t['id'] for t in result['topics']], ['P1'])
        self.assertEqual(result['selection_report']['selected_count'], 1)
        self.assertEqual(len(result['selection_report']['rejected']), 1)

    def test_tool_action_cap_is_enforced_even_if_upstream_exceeds_request(self):
        raw = scouts()[0]
        raw['output'] = raw['output'][:-1] * 9 + raw['output'][-1:]
        transport = self.transport(raw, scouts()[1])
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')
        names = [request_stage(request) for request, _ in transport.requests]
        self.assertIn('insight_clinic_scout', names)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(set(names) <= set(STAGES[:2]))

    def test_answer_source_cap_fails_before_final_generation(self):
        raw = narrative(ANSWER, '여섯 원문이 확인된 보고서입니다.')
        message = raw['output'][-1]
        raw['output'] = []
        message['content'][0]['annotations'] = []
        for i in range(6):
            url = f'https://maker.example.org/help/page-{i}'
            raw['output'].append({'type': 'web_search_call', 'status': 'completed',
                                  'action': {'type': 'open_page', 'url': url}})
            message['content'][0]['annotations'].append({'type': 'url_citation', 'url': url,
                                                         'start_index': 0, 'end_index': 5})
        raw['output'].append(message)
        transport = self.transport(*scouts(), selected(candidate()), raw)
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')
        self.assertEqual(len(transport.requests), 4)

    def test_failed_transport_does_not_retry(self):
        transport = self.transport(TimeoutError('sensitive upstream details'), scouts()[1])
        with self.assertRaises(ProviderError) as caught:
            self.provider.discover_insights('briefing')
        self.assertNotIn('sensitive', str(caught.exception))
        names = [request_stage(request) for request, _ in transport.requests]
        self.assertIn('insight_clinic_scout', names)
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(set(names) <= set(STAGES[:2]))

    def test_failed_parallel_scout_cannot_publish_or_start_selection(self):
        barrier = threading.Barrier(2, timeout=2)
        fixture = InsightHTTPFixtures(scouts()[0], TimeoutError('private failure details'))

        def request(request, timeout):
            self.assertIn(request_stage(request), STAGES[:2])
            barrier.wait()
            return fixture(request, timeout)

        with patch('brochure.provider.urlopen', request), self.assertRaises(ProviderError) as caught:
            self.provider.discover_insights('operations')
        self.assertNotIn('private failure', str(caught.exception))
        self.assertEqual(sorted(request_stage(request) for request, _ in fixture.requests),
                         list(STAGES[:2]))


if __name__ == '__main__':
    unittest.main()
