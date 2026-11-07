"""Offline Responses fixtures exercise the real bounded insight orchestrator."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from brochure.provider import OpenAIProvider, ProviderError, _public_topic
from tests.test_provider import HTTPFixtures, response

CLINIC = 'https://clinic.example.org/notices/printing'
TOOLS = 'https://maker.example.org/help/print-status'
ANSWER = 'https://maker.example.org/help/print-queue'


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
        fixture = HTTPFixtures(*outputs)
        patched = patch('brochure.provider.urlopen', fixture)
        patched.start()
        self.addCleanup(patched.stop)
        return fixture

    def full(self, *, candidates=None, topics=None, audited=None):
        return self.transport(*scouts(), selected(*(candidates if candidates is not None else [candidate()])),
                              narrative(ANSWER, '공식 제품 도움말은 출력 대기열에서 문서 상태를 볼 수 있다고 설명합니다. 날짜 미상.'),
                              response({'topics': topics if topics is not None else [final_topic()]}),
                              audited if audited is not None else audit('P1'))

    @staticmethod
    def payloads(transport):
        return [json.loads(request.data) for request, _ in transport.requests]

    def test_six_bounded_stages_publish_complete_asset_with_exact_provenance(self):
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
        self.assertEqual(result['usage']['requests'], 6)
        self.assertEqual(result['usage']['total_tokens'], 360)
        requests = self.payloads(transport)
        self.assertEqual([p.get('max_tool_calls', 0) for p in requests], [8, 8, 0, 8, 0, 0])
        self.assertTrue(all(p['store'] is False for p in requests))
        inputs = [json.loads(p['input'][0]['content']) for p in requests]
        self.assertNotIn('scout_reports', inputs[1])
        self.assertEqual(inputs[0]['validation_context']['research_date'], '2026-11-03')
        self.assertEqual(inputs[0]['validation_context']['news_window']['start'], '2026-10-21')
        self.assertEqual(inputs[4]['verified_sources']['A1'], ANSWER)
        self.assertEqual(inputs[5]['history'], {'recent_topics': [], 'feedback': []})
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
        for index in [2, 5]:
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
        self.assertEqual(len(transport.requests), 6)

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
        self.assertEqual(len(transport.requests), 6)

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
        transport = self.transport(raw)
        with self.assertRaises(ProviderError):
            self.provider.discover_insights('operations')
        self.assertEqual(len(transport.requests), 1)

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
        transport = self.transport(TimeoutError('sensitive upstream details'))
        with self.assertRaises(ProviderError) as caught:
            self.provider.discover_insights('briefing')
        self.assertNotIn('sensitive', str(caught.exception))
        self.assertEqual(len(transport.requests), 1)


if __name__ == '__main__':
    unittest.main()
