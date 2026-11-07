import http.client
import copy
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from brochure.catalog import load_topics
from brochure.server import make_server
from brochure.service import BrochureService


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        def write_docx(draft, path):
            path.write_bytes(b'editable')

        def write_pdf(source, path):
            path.write_bytes(b'%PDF-ok')

        service = BrochureService(Path(self.tmp.name), (write_docx, write_pdf))
        # HTTP verification must never reach a configured billable provider.
        example = load_topics()[0]
        def discover(category, progress=None, history=None):
            topic = copy.deepcopy(example)
            topic.pop('brochure'); topic.pop('notes')
            if category == 'briefing':
                topic.update(coverage_area='medical', why_now='새 소식의 원문과 적용 범위를 살펴봅니다.')
                for source in topic['sources']:
                    source['verification'] = 'body_access_and_cited'
            topic['selection'] = {
                'audience': 'staff', 'problem': '접수 안내에서 해야 할 행동을 찾기 어렵습니다.',
                'problem_key': 'reception_instructions', 'reason': '직원이 바로 붙여 쓸 안내문을 제공합니다.',
                'novelty': 'new', 'previous_topic_id': None, 'change': '',
                'signals': [{'source_id': topic['sources'][0]['id'], 'observation': '쉬운 안내 원칙을 설명합니다.'}],
                'scores': {'specificity': 3, 'usability': 3, 'novelty': 3, 'evidence': 3}, 'total': 12}
            topic['ready_to_use'] = {'title': '접수 안내', 'format': 'message',
                'body': '도착하시면 접수 창구에 알려 주세요. 안내가 필요하면 가까운 직원에게 말씀해 주세요.',
                'adaptation_note': '실제 접수 방식에 맞는지 확인해 주세요.'}
            return {'topics': [topic]}

        def compose(topic, company_text='', instructions='', previous=None, progress=None):
            result = {key: copy.deepcopy(example[key]) for key in ('brochure', 'notes')}
            result['quality_notes'] = []
            if instructions:
                result['brochure']['title'] = '수정된 안내문'
                result['notes']['explanation'] = '수정된 안내문의 설명'
            return result

        provider = SimpleNamespace(configured=True, model='http-test-fixture',
                                   discover=discover, discover_insights=discover, compose=compose)
        self.server = make_server(service, port=0, provider=provider)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.port = self.server.server_port
        self.cookie = ''
        self.csrf = ''
        self.request('POST', '/api/auth/register', {'email':'alice@example.test','password':'Example password 123!'})

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        self.addCleanup(conn.close)
        data = json.dumps(body) if body is not None else None
        values = {'Content-Type': 'application/json'} if body is not None else {}
        if self.cookie:
            values['Cookie'] = self.cookie
        if self.csrf:
            values['X-CSRF-Token'] = self.csrf
        values.update(headers or {})
        conn.request(method, path, body=data, headers=values)
        res = conn.getresponse()
        payload = res.read()
        if res.getheader('Set-Cookie'):
            self.cookie = res.getheader('Set-Cookie').split(';')[0]
            parsed = json.loads(payload)
            self.csrf = parsed.get('csrf_token','')
        return res.status, res.getheader('Content-Type'), payload

    def test_complete_api_and_private_notes_not_in_download(self):
        status, _, payload = self.request('GET', '/api/topics')
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(payload)['topics']), 4)
        status, _, payload = self.request('POST', '/api/drafts',
                                        {'topic_id': 'plain-language', 'request_id': 'http-test'})
        self.assertEqual(status, 201)
        draft = json.loads(payload)
        prefix = '/api/drafts/' + draft['id']
        self.assertEqual(self.request('POST', prefix + '/review', {'revision': 1})[0], 200)
        status, _, payload = self.request('POST', prefix + '/exports', {'revision': 1})
        ready = json.loads(payload)
        self.assertEqual(status, 200)
        self.assertEqual(ready['status'], 'exported')
        status, mime, data = self.request('GET', ready['exports']['pdf']['url'])
        self.assertEqual(status, 200)
        self.assertEqual(mime, 'application/pdf')
        self.assertEqual(data, b'%PDF-ok')
        self.assertEqual(self.request('DELETE', prefix)[0], 200)
        self.assertEqual(self.request('GET', prefix)[0], 404)

    def test_reject_foreign_origin_and_host(self):
        self.assertEqual(self.request('GET', '/api/topics', headers={'Host': 'attacker.test'})[0], 403)
        self.assertEqual(self.request('POST', '/api/drafts', {},
                                      {'Origin': 'https://attacker.test'})[0], 403)
        self.assertEqual(self.request('GET', '/api/topics', headers={'Sec-Fetch-Site': 'cross-site'})[0], 403)

    def test_json_types_limits_and_bad_revision_are_actionable(self):
        for body in [[], None, {'topic_id': '../secrets', 'request_id': 'http-test'}]:
            self.assertEqual(self.request('POST', '/api/drafts', body)[0], 400)
        self.assertEqual(self.request('POST', '/api/drafts', {'x': 'x' * 34000})[0], 413)
        status, _, payload = self.request('POST', '/api/drafts',
                                        {'topic_id': 'plain-language', 'request_id': 'http-test'})
        identifier = json.loads(payload)['id']
        self.assertEqual(self.request('GET', f'/api/drafts/{identifier}/download/pdf?revision=oops')[0], 400)

    def test_no_arbitrary_static_paths(self):
        for path in ['/data/drafts.sqlite3', '/../specs/approval_candidate_spec.en.md', '/api/nope']:
            self.assertEqual(self.request('GET', path)[0], 404)

    def test_sessions_csrf_and_other_account_access(self):
        status, _, payload = self.request('POST','/api/drafts',{'topic_id':'plain-language','request_id':'owned-work'})
        self.assertEqual(status,201)
        identifier = json.loads(payload)['id']
        self.assertEqual(self.request('POST',f'/api/drafts/{identifier}/review',{'revision':1},
                                      {'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.request('POST','/api/auth/logout',{})[0],200)
        self.assertEqual(self.request('GET','/api/drafts')[0],401)
        self.request('POST','/api/auth/register',{'email':'bob@example.test','password':'Example password 456!'})
        self.assertEqual(json.loads(self.request('GET','/api/drafts')[2])['drafts'],[])
        for method,path,body in [('GET',f'/api/drafts/{identifier}',None),
                                 ('POST',f'/api/drafts/{identifier}/review',{'revision':1}),
                                 ('GET',f'/api/drafts/{identifier}/download/docx?revision=1',None),
                                 ('DELETE',f'/api/drafts/{identifier}',None)]:
            self.assertEqual(self.request(method,path,body)[0],404)

    def test_session_exposes_readiness_not_credentials(self):
        status,_,payload = self.request('GET','/api/session')
        session=json.loads(payload)
        self.assertEqual(status,200)
        self.assertEqual(session['user']['email'],'alice@example.test')
        self.assertIsInstance(session['provider']['configured'],bool)
        self.assertNotIn('api_key',session['provider'])

    def test_research_feedback_is_private_validated_and_persistent(self):
        status, _, payload = self.request('POST', '/api/research',
            {'category': 'operations', 'request_id': 'research-feedback-one'})
        self.assertEqual(status, 202)
        job = json.loads(payload)
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            job = json.loads(self.request('GET', '/api/jobs/' + job['id'])[2])
            if job['status'] not in ('queued', 'running'):
                break
            time.sleep(.01)
        self.assertEqual(job['status'], 'succeeded', job.get('error'))
        topic = job['result']['topics'][0]
        body = {'topic_id': topic['id'], 'source': 'research', 'verdict': 'useful'}
        self.assertEqual(self.request('POST', '/api/topic-feedback', body)[0], 200)
        feedback = json.loads(self.request('GET', '/api/research')[2])['feedback']
        self.assertEqual(feedback, {topic['id']: 'useful'})
        self.assertEqual(self.request('POST', '/api/topic-feedback',
            {**body, 'verdict': 'invented'})[0], 400)
        self.assertEqual(self.request('POST', '/api/topic-feedback',
            {**body, 'company_text': 'PRIVATE must not be accepted'})[0], 400)
        self.assertEqual(self.request('POST', '/api/topic-feedback', body,
            {'X-CSRF-Token': 'wrong'})[0], 403)
        self.request('POST', '/api/auth/logout', {})
        self.assertEqual(self.request('POST', '/api/topic-feedback', body)[0], 401)
        self.request('POST', '/api/auth/register',
            {'email': 'feedback-bob@example.test', 'password': 'Other sample password!'})
        self.assertEqual(self.request('POST', '/api/topic-feedback', body)[0], 404)
        self.assertEqual(json.loads(self.request('GET', '/api/research')[2])['feedback'], {})
        self.request('POST', '/api/auth/logout', {})
        self.request('POST', '/api/auth/login',
            {'email': 'alice@example.test', 'password': 'Example password 123!'})
        self.assertEqual(json.loads(self.request('GET', '/api/research')[2])['feedback'], feedback)

    def test_shared_topic_feedback_is_per_viewer(self):
        self.request('POST', '/api/briefing/refresh', {'request_id': 'feedback-shared-one'})
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            feed = json.loads(self.request('GET', '/api/briefing')[2])
            if feed['status']['last_attempt']['status'] not in ('queued', 'running'):
                break
            time.sleep(.01)
        self.assertEqual(feed['status']['last_attempt']['status'], 'succeeded')
        topic = feed['items'][0]
        body = {'topic_id': topic['id'], 'source': 'briefing', 'verdict': 'seen'}
        self.assertEqual(self.request('POST', '/api/topic-feedback', body)[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/briefing')[2])['feedback'],
                         {topic['id']: 'seen'})
        self.request('POST', '/api/auth/logout', {})
        self.request('POST', '/api/auth/register',
            {'email': 'shared-feedback-bob@example.test', 'password': 'Other sample password!'})
        self.assertEqual(json.loads(self.request('GET', '/api/briefing')[2])['feedback'], {})
        self.assertEqual(self.request('POST', '/api/topic-feedback',
            {**body, 'verdict': 'not_useful'})[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/briefing')[2])['feedback'],
                         {topic['id']: 'not_useful'})

    def test_public_briefing_requires_session_csrf_and_rejects_private_fields(self):
        status, _, payload = self.request('GET', '/api/briefing')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)['items'], [])
        self.assertEqual(self.request('POST', '/api/briefing/refresh',
            {'request_id': 'feed-csrf'}, {'X-CSRF-Token': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', '/api/briefing/refresh',
            {'request_id': 'feed-private', 'company_text': 'PRIVATE content'})[0], 400)
        self.assertEqual(self.request('POST', '/api/briefing/refresh',
            {'request_id': 'scheduled-2099-01-01'})[0], 400)
        self.assertIsNone(json.loads(self.request('GET', '/api/briefing')[2])['status']['last_attempt'])
        self.request('POST', '/api/auth/logout', {})
        self.assertEqual(self.request('GET', '/api/briefing')[0], 401)
        self.assertEqual(self.request('POST', '/api/briefing/refresh', {'request_id': 'feed-anon'})[0], 401)

    def test_shared_news_creates_private_draft_and_replays_refresh(self):
        body = {'request_id': 'shared-news-collection'}
        status, _, payload = self.request('POST', '/api/briefing/refresh', body)
        self.assertEqual(status, 202)
        job = json.loads(payload)['job']
        until = time.monotonic() + 4
        while time.monotonic() < until:
            feed = json.loads(self.request('GET', '/api/briefing')[2])
            if feed['status']['last_attempt']['status'] not in ('queued', 'running'):
                break
            time.sleep(.01)
        self.assertEqual(feed['status']['last_attempt']['status'], 'succeeded')
        self.assertEqual(len(feed['items']), 1)
        topic = feed['items'][0]
        self.assertTrue(topic['id'].startswith('feed-'))
        self.assertEqual(json.loads(self.request('GET', '/api/jobs')[2])['jobs'], [])
        self.assertEqual(self.request('GET', '/api/jobs/' + job['id'])[0], 404)
        replay = json.loads(self.request('POST', '/api/briefing/refresh', body)[2])['job']
        self.assertEqual(replay['id'], job['id'])
        status, _, payload = self.request('POST', '/api/compose',
            {'topic_id': topic['id'], 'source': 'briefing', 'mode': 'company',
             'company_text': 'PRIVATE company example', 'input_confirmed': True,
             'request_id': 'compose-shared-news'})
        self.assertEqual(status, 202)
        compose_job = json.loads(payload)
        until = time.monotonic() + 4
        while time.monotonic() < until:
            composed = json.loads(self.request('GET', '/api/jobs/' + compose_job['id'])[2])
            if composed['status'] not in ('queued', 'running'):
                break
            time.sleep(.01)
        self.assertEqual(composed['status'], 'succeeded', composed.get('error'))
        draft = composed['result']['draft']
        self.assertEqual(draft['selected_topic']['id'], topic['id'])
        self.assertEqual(draft['company_text'], 'PRIVATE company example')
        self.request('POST', '/api/auth/logout', {})
        self.request('POST', '/api/auth/register',
            {'email': 'feed-bob@example.test', 'password': 'Other sample password!'})
        public = json.loads(self.request('GET', '/api/briefing')[2])
        self.assertEqual(public['items'][0]['id'], topic['id'])
        self.assertNotIn('PRIVATE company example', json.dumps(public))
        self.assertEqual(self.request('GET', '/api/drafts/' + draft['id'])[0], 404)


    def test_authenticated_job_journey_revision_replay_and_private_results(self):
        def finish(job):
            deadline = time.monotonic() + 4
            while time.monotonic() < deadline:
                status, _, payload = self.request('GET', '/api/jobs/' + job['id'])
                self.assertEqual(status, 200)
                current = json.loads(payload)
                if current['status'] not in ('queued', 'running'):
                    self.assertEqual(current['status'], 'succeeded', current.get('error'))
                    return current
                time.sleep(.01)
            self.fail('HTTP job did not finish')

        research_body = {'category': 'communication', 'request_id': 'http-research'}
        self.assertEqual(self.request('POST', '/api/research', research_body,
                                      {'X-CSRF-Token': 'wrong'})[0], 403)
        self.assertEqual(json.loads(self.request('GET', '/api/jobs')[2])['jobs'], [])
        status, _, payload = self.request('POST', '/api/research', research_body)
        self.assertEqual(status, 202)
        research = finish(json.loads(payload))
        topic = research['result']['topics'][0]
        self.assertEqual(json.loads(self.request('GET', '/api/research')[2])['topics'][0], topic)
        compose_body = {'topic_id': topic['id'], 'source': 'research', 'mode': 'company',
                        'company_text': '가상 회사의 일반 접수 안내', 'input_confirmed': True,
                        'request_id': 'http-compose'}
        status, _, payload = self.request('POST', '/api/compose', compose_body)
        self.assertEqual(status, 202)
        composed = finish(json.loads(payload))
        draft = composed['result']['draft']
        self.assertEqual(draft['origin'], 'company')
        prefix = '/api/drafts/' + draft['id']
        revision_body = {'revision': 1, 'instructions': '더 쉽게 설명해 주세요.',
                         'input_confirmed': True, 'request_id': 'http-revise'}
        status, _, payload = self.request('POST', prefix + '/revise', revision_body)
        self.assertEqual(status, 202)
        revised = finish(json.loads(payload))
        status, _, payload = self.request('POST', prefix + '/revise', revision_body)
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(payload), revised)
        current = json.loads(self.request('GET', prefix)[2])
        self.assertEqual(current['revision'], 2)
        self.assertEqual(current['brochure']['title'], '수정된 안내문')
        self.assertEqual(current['notes']['explanation'], '수정된 안내문의 설명')
        self.assertEqual(self.request('POST', prefix + '/review', {'revision': 2})[0], 200)
        exported = json.loads(self.request('POST', prefix + '/exports', {'revision': 2})[2])
        self.assertEqual(exported['status'], 'exported')
        self.request('POST', '/api/auth/logout', {})
        self.request('POST', '/api/auth/register',
                     {'email': 'job-bob@example.test', 'password': 'Other example password!'})
        self.assertEqual(json.loads(self.request('GET', '/api/research')[2])['topics'], [])
        self.assertEqual(json.loads(self.request('GET', '/api/jobs')[2])['jobs'], [])
        for path in [prefix, '/api/jobs/' + research['id'], '/api/jobs/' + composed['id'],
                     '/api/jobs/' + revised['id'], exported['exports']['pdf']['url']]:
            self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.request('POST', '/api/compose',
                                      {**compose_body, 'request_id': 'bob-compose'})[0], 404)


if __name__ == '__main__':
    unittest.main()
