"""Provider boundary tests: realistic HTTP Responses fixtures, no live paid calls."""
import copy
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from brochure.catalog import load_topics


URL = 'https://www.cdc.gov/health-literacy/php/develop-materials/plain-language.html'
BRIEFING_URL = 'https://www.kdca.go.kr/guidelines/example-update'


def candidate():
    return {
        'id': 'plain-language', 'title': '읽기 쉬운 안내문', 'summary': '행정 안내문의 표현을 점검합니다.',
        'director_value': '직원과 함께 안내문을 점검하는 데 사용할 수 있습니다.',
        'takeaway': '핵심 행동을 먼저 보여주는지 점검해 보세요.', 'reading_minutes': 3,
        'evidence_notice': '기존 지침을 행정 안내에 적용하는 제안이며 국내 효과 검증은 아닙니다.',
        'sources': [{'id': 'S1', 'title': 'Plain Language Materials & Resources',
                     'publisher': 'CDC', 'url': URL, 'published_at': None, 'updated_at': '2025-07-21',
                     'context': 'Plain language checklist recommends putting the most important message first and using familiar words.'}],
        'claims': [{'id': 'C1', 'text': 'CDC는 가장 중요한 메시지를 먼저 제시하도록 권고합니다.', 'source_ids': ['S1']}],
    }


def unsupported_live_candidate():
    # Public candidate captured from the live research smoke test. Its benefits,
    # reception attribution, and review/update date distinction need rejection.
    return {'id': 'research-8e514989896245d0ba2f0e0bc15e506c',
     'title': 'Tool: Teach‑Back 적용(관리자 관점 요약)',
     'summary': 'AHRQ의 Tool: Teach‑Back 자료는 예약·접수 등 비임상 대면·전화 안내에서 ‘환자(내원자)가 설명을 자신의 말로 다시 말하도록 요청하는’ '
                '표준화된 방법을 제안하며, 환자 이해 검증과 구두·서면 안내의 결합을 권장합니다.',
     'director_value': '행정·접수 프로세스에 간단한 검증 단계(teach‑back)를 표준화하면 환자 이해도를 빠르게 확인할 수 있어 반복 '
                       '연락·오해·재예약·업무수정 비용을 줄이는 데 도움이 될 수 있습니다 (AHRQ 자료의 정의·권고에 근거).',
     'takeaway': '예약안내 핵심 1–3개 항목을 평이한 문장으로 전달하고, 행정직원이 “제가 안내한 대로 어떻게 준비하실 건지 한 번 설명해 주시겠어요?” 같은 개방형 '
                 '문구로 환자에게 자신의 말로 되돌려 말하게 요청하도록 표준 스크립트를 도입하세요. 구두 안내는 서면 지침으로 보강하는 것을 권장합니다.',
     'reading_minutes': 3,
     'evidence_notice': '이 후보는 AHRQ의 Tool: Teach‑Back(S1)에 직접 근거합니다. 원 보고서에서 언급된 CDC 평이한 언어 자료 등 다른 '
                        '출처는 본 제출물의 검증된 출처 목록에 포함되지 않아 이 후보의 근거로 사용되지 않았습니다. 이 자료는 미국 연방기관(AHRQ) 문서이며, '
                        '지역 규정·언어·문화적 맥락·업무흐름에 따라 현장 적용 시 조정이 필요합니다. 원문 열람·인용 기록을 확인한 AI 조사 후보입니다. '
                        '조사일은 발행일·수정일과 다르며 최신성이나 현재 유효성을 보증하지 않습니다. 날짜 미상과 적용 범위는 원문에서 검토해 주세요.',
     'sources': [{'id': 'S1',
                  'title': 'Tool: Teach‑Back',
                  'publisher': 'Agency for Healthcare Research and Quality (AHRQ)',
                  'url': 'https://www.ahrq.gov/teamstepps-program/curriculum/communication/tools/teachback.html',
                  'published_at': '2023-05',
                  'updated_at': '2023-05',
                  'context': "페이지 본문에서 'Teach‑back is an evidence‑based health literacy intervention … "
                             "ask the patient … to explain … in their own words.'와 'Reinforcing this "
                             "oral message with written instructions is important …' 같은 문장이 명시되어 있으며, "
                             '페이지의 표기( Page last reviewed: 2023-05; Page originally created: 2023-05 '
                             ')가 포함되어 있습니다.'}],
     'claims': [{'id': 'C1',
                 'text': "Teach‑back은 환자에게 설명한 내용을 '자신의 말로 다시 설명하도록 요청'하는 방식으로 AHRQ가 'evidence‑based "
                         "health literacy intervention'으로 규정한 기법입니다.",
                 'source_ids': ['S1']},
                {'id': 'C2',
                 'text': 'AHRQ는 구두 설명을 서면 지침으로 보강하는 것을 권장합니다(oral message reinforced with written '
                         'instructions).',
                 'source_ids': ['S1']},
                {'id': 'C3',
                 'text': "해당 AHRQ 페이지에는 문서의 검토 날짜로 'Page last reviewed: 2023-05'와 생성일로 'Page "
                         "originally created: 2023-05'가 표기되어 있습니다.",
                 'source_ids': ['S1']}]}


def composed():
    topic = load_topics()[0]
    return {'brochure': copy.deepcopy(topic['brochure']), 'notes': copy.deepcopy(topic['notes']),
            'quality_notes': ['AI 작성 자료입니다. 원문과 실제 현장에 맞는지 검토해 주세요.']}


def accepted_audit():
    return {'factual_support': True, 'non_promotional': True, 'non_clinical': True,
            'injection_safe': True, 'consistent': True, 'quality_notes': []}


def response(data, *, opened=True, cited=True, search=False):
    text = json.dumps(data, ensure_ascii=False)
    output = []
    if search:
        output.append({'id': 'ws_search', 'type': 'web_search_call', 'status': 'completed',
                       'action': {'type': 'search', 'queries': ['CDC plain language guidance'],
                                  'sources': [{'type': 'url', 'url': URL}]}})
        if opened:
            output.append({'id': 'ws_open', 'type': 'web_search_call', 'status': 'completed',
                           'action': {'type': 'open_page', 'url': URL}})
    annotations = ([{'type': 'url_citation', 'url': URL, 'title': 'Plain Language Materials & Resources',
                     'start_index': 0, 'end_index': min(10, len(text))}] if cited and search else [])
    output.append({'id': 'msg_1', 'type': 'message', 'status': 'completed', 'role': 'assistant',
                   'content': [{'type': 'output_text', 'text': text, 'annotations': annotations}]})
    return {'id': 'resp_fixture', 'object': 'response', 'status': 'completed', 'error': None,
            'incomplete_details': None, 'output': output,
            'usage': {'input_tokens': 40, 'output_tokens': 20, 'total_tokens': 60}}


def research_response(*, opened=True, cited=True):
    result = response({}, opened=opened, cited=cited, search=True)
    part = result['output'][-1]['content'][0]
    part['text'] = ('CDC의 Plain Language Materials & Resources는 핵심 메시지를 먼저 제시하고 '
                    '익숙한 표현을 쓰도록 권고합니다. 행정 안내문에 적용하는 제안이며 효과 보장은 아닙니다. '
                    '발행일 미상, 수정일 2025-07-21. 원문: ' + URL)
    if part['annotations']:
        part['annotations'][0].update(start_index=0, end_index=62)
    return result


def source_read_response(*, opened=True, cited=True):
    result = research_response(opened=opened, cited=cited)
    result['output'] = [item for item in result['output']
                        if not (item.get('type') == 'web_search_call'
                                and item.get('action', {}).get('type') == 'search')]
    return result


def briefing_candidate():
    # Synthetic educational guideline story, never a live-source fallback.
    topic = candidate()
    topic.update(id='guideline-update', coverage_area='medical',
                 why_now='2026-11-02 발표된 지침의 변경 내용과 근거 범위를 살펴볼 시점입니다.',
                 title='새 지침에서 바뀐 내용, 근거와 함께 한 장으로 읽기',
                 summary='지침 개정 보고서는 연구 대상과 근거의 한계를 함께 제시합니다.',
                 director_value='진료 지식을 읽는 자료로 연구 결과와 권고 변경을 구분합니다.',
                 takeaway='개정 내용·근거·미해결 질문을 나란히 적은 한 장 요약을 제공합니다.',
                 evidence_notice='의학 지식 학습을 위한 요약이며 개별 환자의 진단·치료 지시가 아닙니다.')
    topic['sources'][0].update(url=BRIEFING_URL, title='Guideline evidence update',
                              publisher='질병관리청', published_at='2026-11-02', updated_at=None,
                              context='Synthetic official guideline report published 2026-11-02 describes the study population, evidence limits and general recommendations.')
    topic['claims'][0]['text'] = '지침 개정 보고서는 연구 대상과 근거의 한계를 함께 제시합니다.'
    return topic


def briefing_report(*, opened=True, cited=True):
    result = research_response(opened=opened, cited=cited)
    for item in result['output']:
        if item.get('type') == 'web_search_call' and item['action'].get('type') == 'open_page':
            item['action']['url'] = BRIEFING_URL
    part = result['output'][-1]['content'][0]
    part['text'] = briefing_candidate()['sources'][0]['context']
    for annotation in part['annotations']:
        annotation.update(url=BRIEFING_URL, start_index=0, end_index=30)
    return result


class HTTPFixtures:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return io.BytesIO(json.dumps(result, ensure_ascii=False).encode())


class ProviderTests(unittest.TestCase):
    def setUp(self):
        from brochure.provider import OpenAIProvider, ProviderError
        self.ProviderError = ProviderError
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-provider-credential-00000'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider = OpenAIProvider(Path(self.tmp.name))

    def transport(self, *responses):
        fixtures = HTTPFixtures(*responses)
        patcher = patch('brochure.provider.urlopen', fixtures)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fixtures

    def test_configuration_reload_is_literal_and_environment_takes_precedence(self):
        os.environ.pop('OPENAI_API_KEY')
        self.assertFalse(self.provider.configured)
        envfile = Path(self.tmp.name) / '.env.local'
        envfile.write_text('OPENAI_API_KEY="sk-local-existing-credential-00000"\nOPENAI_MODEL=gpt-5-mini\n')
        self.assertTrue(self.provider.configured)
        os.environ['OPENAI_MODEL'] = 'custom-model'
        self.assertEqual(self.provider.model, 'custom-model')
        envfile.write_text('OPENAI_API_KEY=$(touch /tmp/NEVER_EXECUTE_PROVIDER)\n')
        self.assertFalse(self.provider.configured)

    def test_discovery_requires_opened_and_cited_sources_and_sets_actual_dates(self):
        transport = self.transport(research_response(), response({'topics': [candidate()]}), response(accepted_audit()))
        progress = []
        result = self.provider.discover('communication', progress.append)
        topic = result['topics'][0]
        today = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        self.assertEqual(topic['research_date'], today)
        self.assertEqual(topic['sources'][0]['checked_at'], today)
        self.assertIsNone(topic['sources'][0]['published_at'])
        self.assertEqual(topic['sources'][0]['updated_at'], '2025-07-21')
        self.assertEqual(topic['sources'][0]['verification'], 'body_access_and_cited')
        self.assertIn('최신', topic['evidence_notice'])
        request, timeout = transport.requests[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
        self.assertFalse(body['store'])
        self.assertEqual(body['tools'][0]['type'], 'web_search')
        self.assertEqual(body['max_tool_calls'], 6)
        self.assertEqual(body.get('tool_choice'), 'required')
        self.assertEqual(body['text']['format']['type'], 'text')
        extracted = json.loads(transport.requests[1][0].data)
        self.assertEqual(extracted['tools'], [])
        self.assertEqual(extracted['tool_choice'], 'none')
        self.assertTrue(extracted['text']['format']['strict'])
        source_schema = extracted['text']['format']['schema']['properties']['topics']['items']['properties']['sources']['items']['properties']
        self.assertEqual(source_schema['id']['enum'], ['S1'])
        self.assertEqual(source_schema['url']['enum'], [URL])
        self.assertIn('web_search_call.action.sources', body['include'])
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 120)
        self.assertTrue(progress)
        self.assertEqual(result['usage']['total_tokens'], 180)
        self.assertEqual(result['usage']['requests'], 3)
        audit_request = json.loads(transport.requests[2][0].data)
        self.assertEqual(audit_request['tools'], [])
        self.assertEqual(audit_request['tool_choice'], 'none')
        self.assertFalse(audit_request['store'])
        self.assertIn('proposed_candidates', json.loads(audit_request['input'][0]['content']))

    def test_candidate_audit_receives_trusted_clock_and_editorial_reading_time_context(self):
        report = research_response()
        report['output'][-1]['content'][0]['text'] += ' 보고서 작성일 2026-11-02.'
        topic = candidate()
        topic['reading_minutes'] = 5
        transport = self.transport(report, response({'topics': [topic]}), response(accepted_audit()))
        with patch('brochure.provider._today', return_value='2026-11-03'):
            result = self.provider.discover('communication')
        audit_payload = json.loads(transport.requests[2][0].data)
        audit_input = json.loads(audit_payload['input'][0]['content'])
        self.assertEqual(audit_input['validation_context'], {
            'research_date': '2026-11-03', 'checked_at': '2026-11-03', 'timezone': 'Asia/Seoul',
            'reading_minutes': {'kind': 'editorial_estimate', 'requires_source_citation': False,
                                'minimum': 1, 'maximum': 10},
        })
        self.assertEqual(result['topics'][0]['research_date'], '2026-11-03')
        self.assertEqual(result['topics'][0]['sources'][0]['checked_at'], '2026-11-03')
        self.assertIsNone(result['topics'][0]['sources'][0]['published_at'])
        self.assertEqual(result['topics'][0]['sources'][0]['updated_at'], '2025-07-21')
        self.assertEqual(result['topics'][0]['reading_minutes'], 5)

    def test_briefing_has_dated_rotating_query_and_its_own_topic_schema(self):
        from brochure.provider import QUERIES
        self.assertIn('briefing', QUERIES)
        priorities = []
        for today, start in (('2026-11-03', '2026-10-21'), ('2026-11-04', '2026-10-22')):
            transport = self.transport(briefing_report(), response({'topics': [briefing_candidate()]}),
                                       response(accepted_audit()))
            with patch('brochure.provider._today', return_value=today):
                result = self.provider.discover('briefing')
            self.assertEqual(len(transport.requests), 3)
            research = json.loads(transport.requests[0][0].data)
            data = json.loads(research['input'][0]['content'])
            self.assertEqual(data['validation_context']['news_window'], {'start': start, 'end': today, 'days': 14})
            self.assertIn(today, data['query'])
            self.assertIn(start, data['query'])
            self.assertIn('Asia/Seoul', data['query'])
            priorities.append(data['validation_context']['priority_beats'])
            self.assertEqual(set(priorities[-1][:2]), {'medical', 'ai'})
            self.assertEqual(set(priorities[-1]), {'medical', 'ai', 'operations', 'economy', 'life'})
            self.assertEqual(research['max_tool_calls'], 6)
            extracted = json.loads(transport.requests[1][0].data)
            fields = extracted['text']['format']['schema']['properties']['topics']['items']['properties']
            self.assertEqual(fields['coverage_area']['enum'], ['medical', 'ai', 'operations', 'economy', 'life'])
            self.assertEqual(fields['why_now']['maxLength'], 400)
            self.assertEqual(fields['sources']['items']['properties']['url']['enum'], [BRIEFING_URL])
            self.assertEqual(result['topics'][0]['coverage_area'], 'medical')
            self.assertEqual(result['topics'][0]['category'], '의학·진료 지식')
            self.assertEqual(result['topics'][0]['sources'][0]['verification'], 'body_access_and_cited')
            self.assertEqual(result['usage']['requests'], 3)
            for request, _ in transport.requests[1:]:
                self.assertEqual(json.loads(request.data)['tools'], [])
        self.assertNotEqual(priorities[0], priorities[1])

    def test_briefing_allows_medical_education_and_requires_primary_story_and_finished_asset(self):
        transport = self.transport(briefing_report(), response({'topics': [briefing_candidate()]}),
                                   response(accepted_audit()))
        self.provider.discover('briefing')
        requests = [json.loads(request.data) for request, _ in transport.requests]
        for request in requests:
            self.assertIn('Educational summaries of medical research and guideline updates are permitted', request['instructions'])
            self.assertIn('patient-specific', request['instructions'])
            self.assertIn('personalized investment allocations', request['instructions'])
        self.assertIn('first source', requests[1]['instructions'])
        self.assertIn('primary basis for the core story', requests[2]['instructions'])
        self.assertIn('finished asset', requests[1]['instructions'])
        self.assertIn('official journals', requests[0]['instructions'])
        self.assertIn('manufacturer', requests[0]['instructions'])
        self.assertIn('central banks', requests[0]['instructions'])
        self.assertNotIn('when the proposed application is clearly nonclinical', requests[2]['instructions'])

    def test_briefing_keeps_old_reference_dates_and_rejects_false_freshness_audit(self):
        topic = briefing_candidate()
        topic['sources'][0].update(published_at='2020-06-01')
        topic['why_now'] = '참고 자료: 2020-06-01 발표 문서이며 최근 14일의 새 발표로 확인되지 않았습니다.'
        report = briefing_report()
        report['output'][-1]['content'][0]['text'] = topic['sources'][0]['context'].replace('2026-11-02', '2020-06-01')
        transport = self.transport(report, response({'topics': [topic]}), response(accepted_audit()))
        result = self.provider.discover('briefing')
        self.assertEqual(result['topics'][0]['sources'][0]['published_at'], '2020-06-01')
        self.assertIn('참고 자료', result['topics'][0]['why_now'])
        self.assertIn('Do not manufacture freshness', json.loads(transport.requests[2][0].data)['instructions'])
        rejected = accepted_audit()
        rejected.update(factual_support=False, quality_notes=['오래된 본문을 최근 발표처럼 소개했고 첫 출처가 중심 주장과 무관합니다.'])
        transport = self.transport(report, response({'topics': [topic]}), response(rejected))
        with self.assertRaises(self.ProviderError):
            self.provider.discover('briefing')
        self.assertEqual(len(transport.requests), 3)

    def test_briefing_preserves_source_read_fallback_and_search_only_rejection(self):
        reading = briefing_report()
        reading['output'] = [item for item in reading['output'] if item.get('action', {}).get('type') != 'search']
        transport = self.transport(briefing_report(opened=False), reading,
                                   response({'topics': [briefing_candidate()]}), response(accepted_audit()))
        result = self.provider.discover('briefing')
        self.assertEqual(result['usage']['requests'], 4)
        payloads = [json.loads(request.data) for request, _ in transport.requests]
        self.assertEqual(sum(item.get('max_tool_calls', 0) for item in payloads), 8)
        self.assertEqual(json.loads(payloads[1]['input'][0]['content'])['source_url'], BRIEFING_URL)
        transport = self.transport(briefing_report(opened=False, cited=False))
        with self.assertRaises(self.ProviderError):
            self.provider.discover('briefing')
        self.assertEqual(len(transport.requests), 1)

    def test_briefing_fields_are_not_added_to_legacy_discovery(self):
        transport = self.transport(research_response(), response({'topics': [candidate()]}), response(accepted_audit()))
        result = self.provider.discover('communication')
        fields = json.loads(transport.requests[1][0].data)['text']['format']['schema']['properties']['topics']['items']['properties']
        self.assertNotIn('coverage_area', fields)
        self.assertNotIn('why_now', fields)
        self.assertNotIn('coverage_area', result['topics'][0])
        self.assertEqual(json.loads(transport.requests[0][0].data)['model'], 'gpt-6.1-sol')

    def test_briefing_first_source_must_have_a_claim_link_before_audit(self):
        report = briefing_report()
        background_url = 'https://www.who.int/news/item/example-background'
        report['output'].insert(1, {'id': 'ws_background', 'type': 'web_search_call', 'status': 'completed',
                                    'action': {'type': 'open_page', 'url': background_url}})
        report['output'][-1]['content'][0]['annotations'].append(
            {'type': 'url_citation', 'url': background_url, 'title': 'Background', 'start_index': 31, 'end_index': 40})
        topic = briefing_candidate()
        background = copy.deepcopy(topic['sources'][0])
        background.update(id='S2', url=background_url, title='Unrelated newer background')
        topic['sources'].insert(0, background)
        transport = self.transport(report, response({'topics': [topic]}), response(accepted_audit()))
        with self.assertRaises(self.ProviderError):
            self.provider.discover('briefing')
        self.assertEqual(len(transport.requests), 2)

    def test_briefing_requires_valid_coverage_and_why_now_before_audit(self):
        for change in (lambda topic: topic.update(coverage_area='advertising'),
                       lambda topic: topic.pop('why_now'),
                       lambda topic: topic.update(why_now='x' * 401)):
            topic = briefing_candidate()
            change(topic)
            transport = self.transport(briefing_report(), response({'topics': [topic]}))
            with self.assertRaises(self.ProviderError):
                self.provider.discover('briefing')
            self.assertEqual(len(transport.requests), 2)

    def test_candidate_audit_rejects_captured_unproved_value_and_misattributed_dates(self):
        topic = unsupported_live_candidate()
        report = research_response()
        source_url = topic['sources'][0]['url']
        report['output'][1]['action']['url'] = source_url
        part = report['output'][-1]['content'][0]
        part['text'] = topic['sources'][0]['context']
        part['annotations'][0].update(url=source_url, start_index=0, end_index=30)
        audit = accepted_audit()
        audit.update(factual_support=False, consistent=False,
                     quality_notes=['반복 연락·재예약·비용 감소의 측정 근거가 없으며, 임상 설명을 접수 안내에 적용하는 것은 별도 제안입니다.',
                                    'Page last reviewed는 수정일이 아닙니다. updated_at는 미상이어야 합니다.'])
        transport = self.transport(report, response({'topics': [topic]}), response(audit))
        with self.assertRaises(self.ProviderError):
            self.provider.discover('communication')
        self.assertEqual(len(transport.requests), 3)

    def test_review_date_is_cleared_before_audit_without_changing_source_context(self):
        topic = candidate()
        source_url = 'https://www.ahrq.gov/health-literacy/improve/precautions/tool5.html'
        context = ('AHRQ Tool 5 defines teach-back and includes appointment staff examples. '
                   'Page last reviewed: 2024‑04; Page originally created: 2024‑02.')
        topic['sources'][0].update(url=source_url, published_at='2024-02', updated_at='2024-04', context=context)
        report = research_response()
        report['output'][1]['action']['url'] = source_url
        report['output'][-1]['content'][0]['text'] = context
        report['output'][-1]['content'][0]['annotations'][0].update(url=source_url, start_index=0, end_index=30)
        transport = self.transport(report, response({'topics': [topic]}), response(accepted_audit()))
        result = self.provider.discover('communication')
        source = result['topics'][0]['sources'][0]
        self.assertIsNone(source['updated_at'])
        self.assertEqual(source['published_at'], '2024-02')
        self.assertEqual(source['context'], context)
        audit_input = json.loads(json.loads(transport.requests[2][0].data)['input'][0]['content'])
        self.assertIsNone(audit_input['proposed_candidates'][0]['sources'][0]['updated_at'])

    def test_date_normalization_preserves_explicit_update_and_does_not_infer_unknown_dates(self):
        from brochure.provider import normalize_source_dates
        cases = [
            ('Page last reviewed: 2024-04; Page last updated: 2024-04.', '2024-04', '2024-04'),
            ('Reviewed on 2024-04. Modified: 2024-04.', '2024-04', '2024-04'),
            ('Page last reviewed: 2024-03; Page originally created: 2024-02.', '2024-04', '2024-04'),
            ('Page last reviewed: 2024-04-19; no explicit update label.', '2024-04', '2024-04'),
            ('The date semantics are uncertain; no precise review label was found.', '2024-04', '2024-04'),
            ('Page last reviewed: 2024-04; Page originally created: 2024-02.', None, None),
        ]
        for context, updated, expected in cases:
            source = {'updated_at': updated, 'context': context, 'published_at': None}
            normalize_source_dates(source)
            with self.subTest(context=context):
                self.assertEqual(source['updated_at'], expected)
                self.assertIsNone(source['published_at'])
                self.assertEqual(source['context'], context)

    def test_any_failed_candidate_audit_boundary_prevents_returning_topics(self):
        for flag in ('factual_support', 'non_promotional', 'non_clinical', 'injection_safe', 'consistent'):
            audit = accepted_audit()
            audit[flag] = False
            transport = self.transport(research_response(), response({'topics': [candidate()]}), response(audit))
            with self.subTest(flag=flag), self.assertRaises(self.ProviderError):
                self.provider.discover('communication')
            self.assertEqual(len(transport.requests), 3)

    def test_snippets_missing_citation_or_uncompleted_open_fail_without_fallback(self):
        responses = [research_response(opened=False), research_response(cited=False), research_response()]
        responses[-1]['output'][1]['status'] = 'failed'
        for index, fixture in enumerate(responses):
            with self.subTest(index=index):
                transport = self.transport(fixture, source_read_response(opened=False))
                with self.assertRaises(self.ProviderError):
                    self.provider.discover('operations')
                self.assertEqual(len(transport.requests), 1 if index == 1 else 2)

    def test_completed_find_in_page_with_exact_native_citation_qualifies_as_body_access(self):
        report = research_response()
        report['output'][1]['action'] = {'type': 'find_in_page', 'url': URL, 'pattern': 'Plain language'}
        transport = self.transport(report, response({'topics': [candidate()]}), response(accepted_audit()))
        result = self.provider.discover('communication')
        self.assertEqual(result['topics'][0]['sources'][0]['verification'], 'body_access_and_cited')
        self.assertEqual(result['usage']['requests'], 3)
        self.assertEqual(len(transport.requests), 3)

    def test_failed_or_url_less_find_in_page_never_qualifies_as_body_access(self):
        for status, url in (('failed', URL), ('incomplete', URL), ('completed', None)):
            report = research_response()
            report['output'][1].update(status=status, action={'type': 'find_in_page', 'url': url, 'pattern': 'message'})
            transport = self.transport(report, source_read_response(opened=False))
            with self.subTest(status=status, url=url), self.assertRaises(self.ProviderError):
                self.provider.discover('communication')
            self.assertEqual(len(transport.requests), 2)

    def test_explicit_read_rejects_an_additional_found_page(self):
        read = source_read_response()
        read['output'].insert(0, {'id': 'ws_found_other', 'type': 'web_search_call', 'status': 'completed',
                                  'action': {'type': 'find_in_page', 'pattern': 'toolkit',
                                             'url': 'https://www.ahrq.gov/unselected-source.html'}})
        transport = self.transport(research_response(opened=False), read,
                                   response({'topics': [candidate()]}), response(accepted_audit()))
        with self.assertRaises(self.ProviderError):
            self.provider.discover('communication')
        self.assertEqual(len(transport.requests), 2)

    def test_explicit_source_read_uses_only_cited_url_and_replaces_discovery_report(self):
        discovery = research_response(opened=False)
        part = discovery['output'][-1]['content'][0]
        part['text'] += ' UNVERIFIED_DISCOVERY_CONTENT'
        part['annotations'].append({'type': 'url_citation', 'title': 'AHRQ PDF',
                                    'url': 'https://www.ahrq.gov/toolkit.pdf',
                                    'start_index': 0, 'end_index': 5})
        transport = self.transport(discovery, source_read_response(),
                                   response({'topics': [candidate()]}), response(accepted_audit()))
        result = self.provider.discover('communication')
        self.assertEqual(result['usage']['requests'], 4)
        self.assertEqual(result['usage']['total_tokens'], 240)
        payloads = [json.loads(request.data) for request, _ in transport.requests]
        self.assertEqual([payload['max_tool_calls'] for payload in payloads if payload.get('tools')], [6, 2])
        read_input = json.loads(payloads[1]['input'][0]['content'])
        self.assertEqual(read_input['source_url'], URL)
        self.assertNotIn('query', read_input)
        self.assertEqual(payloads[1]['tools'][0]['filters']['allowed_domains'], ['www.cdc.gov'])
        for payload in payloads[1:]:
            self.assertNotIn('UNVERIFIED_DISCOVERY_CONTENT', payload['input'][0]['content'])
        for payload in payloads[2:]:
            self.assertEqual(payload['tools'], [])
            self.assertEqual(json.loads(payload['input'][0]['content'])['verified_sources'], {'S1': URL})

    def test_failed_explicit_read_stops_before_extraction_and_never_repeats(self):
        other = source_read_response()
        other_url = 'https://www.ahrq.gov/unselected-source.html'
        other['output'][0]['action']['url'] = other_url
        other['output'][-1]['content'][0]['annotations'][0]['url'] = other_url
        malformed_action = source_read_response()
        malformed_action['output'][0]['action'] = None
        for failed_read in (source_read_response(opened=False), source_read_response(cited=False),
                            other, malformed_action, research_response(),
                            URLError('private diagnostic detail')):
            transport = self.transport(research_response(opened=False), failed_read)
            with self.assertRaises(self.ProviderError):
                self.provider.discover('communication')
            self.assertEqual(len(transport.requests), 2)

    def test_explicit_read_rejects_additional_opened_or_cited_urls(self):
        extra_url = 'https://www.ahrq.gov/unselected-source.html'
        for extra_open, extra_citation in ((True, False), (False, True), (True, True)):
            read = source_read_response()
            if extra_open:
                read['output'].insert(0, {'id': 'ws_extra', 'type': 'web_search_call', 'status': 'completed',
                                          'action': {'type': 'open_page', 'url': extra_url}})
            if extra_citation:
                read['output'][-1]['content'][0]['annotations'].append(
                    {'type': 'url_citation', 'url': extra_url, 'title': 'Unselected source',
                     'start_index': 63, 'end_index': 70})
            transport = self.transport(research_response(opened=False), read,
                                       response({'topics': [candidate()]}), response(accepted_audit()))
            with self.subTest(extra_open=extra_open, extra_citation=extra_citation), self.assertRaises(self.ProviderError):
                self.provider.discover('communication')
            self.assertEqual(len(transport.requests), 2)

    def test_extraction_cannot_add_a_source_that_was_not_opened_and_cited(self):
        topic = candidate()
        topic['sources'][0]['url'] = 'https://www.ahrq.gov/health-literacy/improve/precautions/toolkit.html'
        transport = self.transport(research_response(), response({'topics': [topic]}))
        with self.assertRaises(self.ProviderError):
            self.provider.discover('communication')
        self.assertEqual(len(transport.requests), 2)

    def test_extraction_cannot_reassign_two_valid_source_urls_to_wrong_ids(self):
        second_url = 'https://www.ahrq.gov/health-literacy/improve/precautions/toolkit.html'
        research = research_response()
        research['output'].insert(1, {'id': 'ws_second', 'type': 'web_search_call', 'status': 'completed',
                                      'action': {'type': 'open_page', 'url': second_url}})
        research['output'][-1]['content'][0]['annotations'].append(
            {'type': 'url_citation', 'url': second_url, 'title': 'AHRQ Toolkit',
             'start_index': 63, 'end_index': 70})
        # The sorted server map gives AHRQ S1 and CDC S2; this returned S1/CDC
        # pair must fail even though both values independently belong to enums.
        transport = self.transport(research, response({'topics': [candidate()]}))
        with self.assertRaises(self.ProviderError):
            self.provider.discover('communication')
        self.assertEqual(len(transport.requests), 2)

    def test_json_research_without_native_citations_never_triggers_extraction(self):
        # Actual live response shape: JSON output, no annotations, search + one
        # completed open_page. Do not manufacture citations from model JSON.
        raw = response({'topics': [candidate()]}, search=True, cited=False)
        transport = self.transport(raw)
        with self.assertRaises(self.ProviderError):
            self.provider.discover('communication')
        self.assertEqual(len(transport.requests), 1)

    def test_discovery_rejects_invalid_categories_before_any_request(self):
        transport = self.transport()
        with self.assertRaises(self.ProviderError):
            self.provider.discover('private company patient record')
        self.assertEqual(transport.requests, [])

    def test_discovery_rejects_unknown_ids_invalid_urls_dates_and_surplus_fields(self):
        modifications = [lambda t: t['claims'][0].update(source_ids=['invented']),
                         lambda t: t['sources'][0].update(url='https://127.0.0.1/private'),
                         lambda t: t['sources'][0].update(updated_at='tomorrow'),
                         lambda t: t['sources'][0].update(published_at='March 1,  '),
                         lambda t: t['claims'][0].update(source_ids=['tur932946view2']),
                         lambda t: t['sources'][0].update(published_at='2099-01-01'),
                         lambda t: t.update(company_text='not a public research field')]
        for modify in modifications:
            data = candidate()
            modify(data)
            self.transport(research_response(), response({'topics': [data]}))
            with self.assertRaises(self.ProviderError):
                self.provider.discover('communication')

    def test_composition_and_audit_have_no_tools_private_inputs_or_sender_leakage(self):
        old = composed()
        old['brochure']['sender'] = {'name': 'PRIVATE SENDER', 'contact': 'private@example.com'}
        old['company_text'] = 'OLDER PRIVATE INPUT'
        old['owner_id'] = 'PRIVATE OWNER'
        old['notes']['internal_metadata'] = 'PRIVATE NESTED METADATA'
        transport = self.transport(response(composed()), response(accepted_audit()))
        topic = load_topics()[0]
        topic['internal_metadata'] = 'PRIVATE TOPIC METADATA'
        topic['claims'][0]['internal_metadata'] = 'PRIVATE CLAIM METADATA'
        result = self.provider.compose(topic, company_text='회사 내부 안내문 작성 원칙: 핵심 행동을 먼저 씁니다.',
                                       instructions='표현을 쉽게 바꿔 주세요.', previous=old)
        self.assertEqual(result['brochure']['sender'], {'name': '', 'contact': ''})
        self.assertEqual(result['usage']['total_tokens'], 120)
        for request, _ in transport.requests:
            payload = json.loads(request.data)
            self.assertEqual(payload.get('tools', []), [])
            self.assertFalse(payload['store'])
            self.assertNotIn('previous_response_id', payload)
            encoded = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn('PRIVATE SENDER', encoded)
            self.assertNotIn('private@example.com', encoded)
            self.assertNotIn('PRIVATE OWNER', encoded)
            self.assertNotIn('OLDER PRIVATE INPUT', encoded)
            self.assertNotIn('PRIVATE TOPIC METADATA', encoded)
            self.assertNotIn('PRIVATE NESTED METADATA', encoded)
            self.assertNotIn('PRIVATE CLAIM METADATA', encoded)
        composition_payload = json.loads(transport.requests[0][0].data)
        user_input = composition_payload['input'][0]['content']
        self.assertIn('회사 내부 안내문', user_input)
        self.assertNotIn('회사 내부 안내문', composition_payload['instructions'])
        schema = composition_payload['text']['format']['schema']['properties']
        self.assertEqual(schema['brochure']['properties']['sections']['items']['properties']['source_ids']['items']['enum'], ['cdc-plain-language'])
        self.assertEqual(schema['notes']['properties']['claim_map']['items']['properties']['source_ids']['items']['enum'], ['cdc-plain-language'])

    def test_audit_rejects_promotion_or_unsupported_claims_and_unsafe_requests(self):
        for flag in ('non_promotional', 'factual_support', 'non_clinical', 'injection_safe', 'consistent'):
            audit = accepted_audit()
            audit[flag] = False
            transport = self.transport(response(composed()), response(audit))
            with self.assertRaises(self.ProviderError):
                self.provider.compose(load_topics()[0], company_text='중립적인 업무 참고 자료')
            self.assertEqual(len(transport.requests), 2)

    def test_revision_request_can_narrow_scope_without_becoming_evidence(self):
        revision = '결제 방식과 즉시 사용할 수 있다는 표현을 삭제하고 예약 안내 점검으로 범위를 좁혀 주세요.'
        transport = self.transport(response(composed()), response(accepted_audit()))
        self.provider.compose(load_topics()[0], company_text='중립적인 회사 안내 원칙',
                              instructions=revision, previous=composed())
        generation = json.loads(transport.requests[0][0].data)
        audit = json.loads(transport.requests[1][0].data)
        self.assertEqual(json.loads(generation['input'][0]['content'])['revision_request'], revision)
        self.assertNotIn('requested revisions are', generation['instructions'])
        self.assertIn('Honor the dedicated revision_request', generation['instructions'])
        self.assertIn('scope-narrowing', generation['instructions'])
        self.assertIn('not evidence', generation['instructions'])
        self.assertIn('standalone natural Korean', generation['instructions'])
        self.assertIn('Unverified origin alone', generation['instructions'])
        self.assertIn('neutral scope and examples', generation['instructions'])
        self.assertIn('finished copyable example', generation['instructions'])
        self.assertIn('inaccessible private notes', audit['instructions'])

    def test_public_brochure_rejects_internal_fields_before_audit(self):
        changes = [lambda b: b.update(title='company_text를 바탕으로 한 안내'),
                   lambda b: b.update(intro='검토 상태는 needs_review입니다.'),
                   lambda b: b['sections'][0].update(body='한계는 quality_notes에서 확인하세요.'),
                   lambda b: b['example'].update(body='COMPANY_TEXT를 참고한 예시입니다.'),
                   lambda b: b.update(limitations=['품질 노트 참조'])]
        for change in changes:
            with self.subTest(change=change):
                data = composed()
                change(data['brochure'])
                transport = self.transport(response(data), response(accepted_audit()))
                with self.assertRaises(self.ProviderError):
                    self.provider.compose(load_topics()[0])
                self.assertEqual(len(transport.requests), 1)

    def test_internal_terms_remain_allowed_in_private_notes_only(self):
        data = composed()
        data['notes']['explanation'] += ' company_text는 공개 근거로 사용하지 않았습니다.'
        data['quality_notes'] = ['needs_review 상태의 출처를 담당자가 재검토해야 합니다.']
        transport = self.transport(response(data), response(accepted_audit()))
        result = self.provider.compose(load_topics()[0])
        self.assertIn('company_text', result['notes']['explanation'])
        self.assertEqual(len(transport.requests), 2)

    def test_public_brochure_rejects_copied_private_openings_before_audit(self):
        # Actual R3 delivery scripts were duplicated in a public brochure section.
        openings = {
            'opening_staff': '예약 안내 문구를 검토할 수 있는 자료입니다. 원장님께 전달해 주실 수 있을까요?',
            'opening_director': '예약 안내를 직원과 함께 검토할 수 있도록 정리했습니다. 예시는 현장에 맞게 확인해 주세요.',
        }
        for field, script in openings.items():
            for separator in (' ', '\n\t'):
                with self.subTest(field=field, separator=repr(separator)):
                    data = composed()
                    data['notes'][field] = script
                    data['brochure']['sections'][0]['body'] = '시작 문장 예시: "' + script.replace(' ', separator) + '"'
                    transport = self.transport(response(data), response(accepted_audit()))
                    with self.assertRaises(self.ProviderError):
                        self.provider.compose(load_topics()[0])
                    self.assertEqual(len(transport.requests), 1)

    def test_short_shared_greeting_does_not_count_as_private_script_copy(self):
        data = composed()
        data['notes']['opening_staff'] = '안녕하세요.'
        data['brochure']['intro'] = '안녕하세요. ' + data['brochure']['intro']
        transport = self.transport(response(data), response(accepted_audit()))
        result = self.provider.compose(load_topics()[0])
        self.assertEqual(result['brochure']['intro'], data['brochure']['intro'])
        self.assertEqual(len(transport.requests), 2)

    def test_composition_rejects_unknown_citations_and_missing_companion_before_audit(self):
        invalid = composed()
        invalid['notes']['claim_map'][0]['source_ids'] = ['invented']
        missing = composed()
        missing.pop('notes')
        for data in (invalid, missing):
            transport = self.transport(response(data))
            with self.assertRaises(self.ProviderError):
                self.provider.compose(load_topics()[0])
            self.assertEqual(len(transport.requests), 1)

    def test_unsafe_characters_sizes_and_patient_records_are_rejected_before_transport(self):
        from brochure.provider import validate_company_text
        for value in ('bad\x00text', 'bad\ud800text', 'a' * 6001, '환자명: 홍길동\n진단명: 고혈압\n주민등록번호: 900101-1234567', 123):
            with self.subTest(value=repr(value)[:50]), self.assertRaises(self.ProviderError):
                validate_company_text(value)
        self.assertEqual(validate_company_text('  안내문 작성 원칙\n직원 교육  '), '안내문 작성 원칙\n직원 교육')
        transport = self.transport()
        for instructions in ('a' * 1001, '환자명: 홍길동. 이 환자에게 맞춰 수정하세요.'):
            with self.assertRaises(self.ProviderError):
                self.provider.compose(load_topics()[0], instructions=instructions)
        self.assertEqual(transport.requests, [])

    def test_incomplete_refused_bogus_and_unexpected_tool_responses_fail_safely(self):
        incomplete = response(composed())
        incomplete['status'] = 'incomplete'
        refused = response(composed())
        refused['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'private rejection details'}]
        unexpected_tool = response(composed())
        unexpected_tool['output'].insert(0, {'type': 'web_search_call', 'status': 'completed',
                                            'action': {'type': 'search', 'query': 'private'}})
        malformed_json = response(composed())
        malformed_json['output'][0]['content'][0]['text'] = 'not json secret'
        for fixture in (incomplete, refused, unexpected_tool, malformed_json, [], {'status': 'completed', 'output': []}):
            self.transport(fixture)
            with self.assertRaises(self.ProviderError) as caught:
                self.provider.compose(load_topics()[0])
            self.assertNotIn('private', str(caught.exception))
            self.assertNotIn('secret', str(caught.exception))

    def test_invalid_citation_metadata_and_response_size_fail_safely(self):
        missing_list = research_response()
        missing_list['output'][-1]['content'][0]['annotations'] = None
        bogus_range = research_response()
        bogus_range['output'][-1]['content'][0]['annotations'][0]['start_index'] = -99
        for fixture in (missing_list, bogus_range):
            self.transport(fixture)
            with self.assertRaises(self.ProviderError):
                self.provider.discover('communication')
        with patch('brochure.provider.urlopen', return_value=io.BytesIO(b'x' * 2_000_001)):
            with self.assertRaises(self.ProviderError):
                self.provider.compose(load_topics()[0])

    def test_transport_errors_are_redacted_and_never_retried(self):
        errors = [HTTPError('https://api.openai.com/v1/responses', 401, 'sk-secret-company-text', {}, io.BytesIO(b'private')),
                  URLError('sk-secret-company-text'), TimeoutError('sk-secret-company-text')]
        for error in errors:
            transport = self.transport(error)
            with self.assertRaises(self.ProviderError) as caught:
                self.provider.discover('ai-literacy')
            self.assertNotIn('sk-secret', str(caught.exception))
            self.assertEqual(len(transport.requests), 1)


if __name__ == '__main__':
    unittest.main()
