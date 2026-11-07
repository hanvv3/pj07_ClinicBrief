import copy
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from brochure.catalog import load_topics
from brochure.service import BrochureService, AppError
from brochure.workflows import Workflows
from brochure.jobs import JobError, JobRunner
from brochure.insight_store import InsightStore
from test_insight_store import selected_topic


class FakeProvider:
    configured = True
    model = 'test-provider'

    def __init__(self):
        self.calls = []
        self.fail = False
        self.histories = []
        self.selected_topics = []
        topic = copy.deepcopy(load_topics()[0])
        topic.pop('brochure'); topic.pop('notes')
        topic.update({key: value for key, value in selected_topic().items()
                      if key in ('selection', 'ready_to_use', 'coverage_area')})
        topic['why_now'] = '공개된 접수 안내 사례를 바로 쓸 답장에 연결합니다.'
        topic['selection']['signals'][0]['source_id'] = topic['sources'][0]['id']
        self.topics = [topic]

    def discover_insights(self, category, *, history=None, progress=None):
        self.calls.append(('research', category))
        self.histories.append(copy.deepcopy(history))
        return {'topics': copy.deepcopy(self.topics),
                'usage': {'input_tokens': 10, 'output_tokens': 20, 'debug': 'PRIVATE'},
                'selection_report': {'sources_read': 4, 'candidates_considered': len(self.topics),
                                     'selected_count': len(self.topics), 'rejected': [], 'debug': 'PRIVATE'}}

    def compose(self, topic, company_text='', instructions='', previous=None, progress=None):
        self.calls.append(('compose', company_text, instructions))
        self.selected_topics.append(copy.deepcopy(topic))
        if self.fail:
            raise RuntimeError('PRIVATE provider prompt must not appear')
        example = load_topics()[0]
        brochure = copy.deepcopy(example['brochure'])
        notes = copy.deepcopy(example['notes'])
        if instructions:
            brochure['title'] = '수정된 안내문'
            notes['explanation'] = '수정된 안내문의 담당자 설명'
        return {'brochure': brochure, 'notes': notes, 'quality_notes': [], 'usage': {}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.service = BrochureService(root)
        self.jobs = JobRunner(root / 'jobs.sqlite3')
        self.addCleanup(self.jobs.shutdown)
        self.provider = FakeProvider()
        self.insights = InsightStore(root / 'insights.sqlite3')
        self.flow = Workflows(self.service, self.provider, self.jobs, insights=self.insights)

    def finish(self, owner, job):
        until = time.monotonic() + 4
        while time.monotonic() < until:
            result = self.jobs.get(owner, job['id'])
            if result['status'] not in ('queued', 'running'):
                return result
            time.sleep(.01)
        self.fail('Job did not finish')

    def request(self, **overrides):
        body = dict(topic_id='plain-language', source='example', mode='ai',
                    company_text='', input_confirmed=True, sender_name='',
                    sender_contact='', request_id='compose-request')
        body.update(overrides)
        return body

    def test_owner_isolation_including_legacy_and_downloads(self):
        legacy = self.service.create({'topic_id': 'plain-language', 'request_id': 'legacy-request'})
        self.assertEqual(self.service.list(owner='alice'), [])
        with self.assertRaises(AppError):
            self.service.get(legacy['id'], owner='alice')
        draft = self.service.create({'topic_id': 'plain-language', 'request_id': 'new-request'}, owner='alice')
        for action in [lambda: self.service.get(draft['id'], owner='bob'),
                       lambda: self.service.review(draft['id'], 1, owner='bob'),
                       lambda: self.service.download(draft['id'], 'docx', 1, owner='bob'),
                       lambda: self.service.delete(draft['id'], owner='bob')]:
            with self.assertRaises(AppError) as error:
                action()
            self.assertEqual(error.exception.status, 404)
        self.assertEqual(self.service.get(draft['id'], owner='alice'), draft)

    def test_research_saved_per_owner_and_company_never_sent_to_search(self):
        job = self.flow.research('alice', {'category': 'communication', 'request_id': 'research-request'})
        result = self.finish('alice', job)
        self.assertEqual(result['status'], 'succeeded')
        topic = result['result']['topics'][0]
        self.assertEqual(self.flow.research_topics('bob'), [])
        self.assertEqual(self.flow.research_topics('alice')[0]['id'], topic['id'])
        composed = self.finish('alice', self.flow.compose('alice', self.request(
            topic_id=topic['id'], source='research', mode='company', company_text='직원용 일반 접수 안내 문구')))
        self.assertEqual(composed['status'], 'succeeded')
        self.assertEqual(self.provider.calls[0], ('research', 'communication'))
        self.assertEqual(self.provider.calls[1][0], 'compose')
        self.assertEqual(composed['result']['draft']['origin'], 'company')
        self.assertEqual(composed['result']['draft']['selected_topic']['ready_to_use'], topic['ready_to_use'])
        self.assertEqual(self.provider.selected_topics[-1]['selection'], topic['selection'])
        with self.assertRaises(AppError):
            self.flow.compose('bob', self.request(topic_id=topic['id'], source='research'))

    def test_research_history_and_feedback_are_limited_to_the_requesting_account(self):
        alice = self.finish('alice', self.flow.research('alice', {
            'category': 'communication', 'request_id': 'alice-first'}))['result']['topics'][0]
        self.provider.topics[0]['title'] = '다른 사용자의 주제'
        self.provider.topics[0]['selection']['problem_key'] = 'bob-private-task'
        bob = self.finish('bob', self.flow.research('bob', {
            'category': 'communication', 'request_id': 'bob-first'}))['result']['topics'][0]
        self.insights.set_feedback('alice', alice['id'], alice['selection']['problem_key'], 'useful')
        self.insights.set_feedback('bob', bob['id'], 'bob-private-task', 'not_useful')
        shared = selected_topic()
        shared['id'] = 'feed-shared'
        self.flow.briefing = SimpleNamespace(snapshot=lambda: {'items': [shared]})
        self.finish('alice', self.flow.research('alice', {'category': 'operations',
            'request_id': 'alice-second', 'company_text': 'PRIVATE-COMPANY'}))
        history = self.provider.histories[-1]
        self.assertEqual([item['id'] for item in history['recent_topics']], [alice['id'], shared['id']])
        self.assertEqual(history['feedback'], [{'problem_key': alice['selection']['problem_key'],
                                               'verdict': 'useful', 'count': 1}])
        self.assertNotIn('bob', str(history))
        self.assertNotIn('PRIVATE', str(history))

    def test_research_replay_precedes_readiness_and_history_lookup(self):
        body = {'category': 'communication', 'request_id': 'research-replay'}
        finished = self.finish('alice', self.flow.research('alice', body))
        self.provider.configured = False
        with patch.object(self.service.store, 'topics', side_effect=AssertionError('history should not be read')):
            self.assertEqual(self.flow.research('alice', body), finished)
        self.assertEqual(len(self.provider.calls), 1)
        with self.assertRaises(AppError):
            self.flow.research('alice', {**body, 'request_id': 'new-no-key'})

    def test_private_briefing_discovery_uses_account_jobs_and_scoped_history(self):
        own = selected_topic()
        own['id'] = 'research-own'
        foreign = selected_topic()
        foreign['id'] = 'research-foreign'
        foreign['selection']['problem_key'] = 'foreign-private-task'
        shared = selected_topic()
        shared['id'] = 'feed-shared'
        self.service.store.save_topics('alice', [own])
        self.service.store.save_topics('bob', [foreign])
        self.flow.briefing = SimpleNamespace(snapshot=lambda: {'items': [shared]})
        self.insights.set_feedback('alice', own['id'], own['selection']['problem_key'], 'seen')
        self.insights.set_feedback('bob', foreign['id'], 'foreign-private-task', 'useful')
        result = self.finish('alice', self.flow.research('alice', {
            'category': 'briefing', 'request_id': 'private-broad-research'}))
        self.assertEqual(result['status'], 'succeeded', result.get('error'))
        self.assertEqual(self.provider.calls, [('research', 'briefing')])
        history = self.provider.histories[0]
        self.assertEqual([item['id'] for item in history['recent_topics']], [own['id'], shared['id']])
        self.assertEqual(history['feedback'], [{'problem_key': own['selection']['problem_key'],
                                               'verdict': 'seen', 'count': 1}])
        self.assertNotIn('foreign', str(history))
        self.assertEqual(self.jobs.list('__briefing__'), [])
        self.assertEqual([job['id'] for job in self.jobs.list('alice')], [result['id']])
        self.assertEqual([item['id'] for item in self.flow.research_topics('bob')], [foreign['id']])
        self.assertIn(result['result']['topics'][0]['id'],
                      [item['id'] for item in self.flow.research_topics('alice')])

    def test_empty_selection_keeps_saved_research_and_public_result_fields(self):
        first = self.finish('alice', self.flow.research('alice', {
            'category': 'communication', 'request_id': 'first'}))
        before = self.flow.research_topics('alice')
        self.provider.topics = []
        empty = self.finish('alice', self.flow.research('alice', {
            'category': 'communication', 'request_id': 'empty'}))
        self.assertEqual(empty['status'], 'succeeded')
        self.assertEqual(empty['result']['topics'], [])
        self.assertEqual(empty['result']['selection_report']['selected_count'], 0)
        self.assertEqual(self.flow.research_topics('alice'), before)
        self.assertNotIn('PRIVATE', str(first['result']))
        self.assertNotIn('PRIVATE', str(empty['result']))

    def test_invalid_new_metadata_fails_without_saving_partial_research(self):
        self.provider.topics.append(copy.deepcopy(self.provider.topics[0]))
        self.provider.topics[-1]['selection']['signals'][0]['source_id'] = 'not-a-source'
        failed = self.finish('alice', self.flow.research('alice', {
            'category': 'communication', 'request_id': 'invalid-new-metadata'}))
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(self.flow.research_topics('alice'), [])

    def test_briefing_selection_snapshots_evidence_and_replay_survives_feed_expiry(self):
        topic = copy.deepcopy(load_topics()[0])
        topic['id'] = 'feed-' + 'a' * 32
        current = {'topic': topic}
        self.flow.briefing = SimpleNamespace(get_topic=lambda identifier: current.get('topic'))
        body = self.request(source='briefing', topic_id=topic['id'])
        result = self.finish('alice', self.flow.compose('alice', body))
        self.assertEqual(result['status'], 'succeeded', result.get('error'))
        draft = result['result']['draft']
        topic['summary'] = 'Changed public feed after composition'
        current.clear()
        self.assertNotEqual(draft['selected_topic']['summary'], topic['summary'])
        self.assertEqual(self.flow.compose('alice', body)['id'], result['id'])
        before = len(self.provider.calls)
        with self.assertRaises(AppError) as error:
            self.flow.compose('alice', {**body, 'request_id': 'new-after-feed-expiry'})
        self.assertEqual(error.exception.status, 404)
        self.assertEqual(len(self.provider.calls), before)

    def test_revision_updates_both_materials_and_invalidates_review(self):
        result = self.finish('alice', self.flow.compose('alice', self.request()))
        self.assertEqual(result['status'], 'succeeded')
        draft = result['result']['draft']
        self.service.review(draft['id'], 1, owner='alice')
        job = self.flow.revise('alice', draft['id'], {
            'revision': 1, 'instructions': '더 쉽게 설명해주세요.',
            'input_confirmed': True, 'request_id': 'revise-request'})
        revised = self.finish('alice', job)['result']['draft']
        self.assertEqual(revised['revision'], 2)
        self.assertEqual(revised['status'], 'draft')
        self.assertEqual(revised['brochure']['title'], '수정된 안내문')
        self.assertEqual(revised['notes']['explanation'], '수정된 안내문의 담당자 설명')
        self.assertEqual(revised['exports']['pdf']['status'], 'pending')
        with self.assertRaises(AppError):
            self.flow.revise('alice', draft['id'], {'revision': 1, 'instructions': 'old',
                'input_confirmed': True, 'request_id': 'stale-request'})

    def test_completed_revision_replay_checks_identity_before_current_revision(self):
        draft = self.service.create({'topic_id': 'plain-language', 'request_id': 'example-request'}, owner='alice')
        body = {'revision': 1, 'instructions': '더 쉽게 설명해주세요.',
                'input_confirmed': True, 'request_id': 'revision-request'}
        finished = self.finish('alice', self.flow.revise('alice', draft['id'], body))
        self.assertEqual(finished['result']['draft']['revision'], 2)
        replayed = self.flow.revise('alice', draft['id'], body)
        self.assertEqual(replayed, finished)
        with self.assertRaises(JobError) as changed:
            self.flow.revise('alice', draft['id'], {**body, 'instructions': '다른 요청'})
        self.assertEqual(changed.exception.status, 409)
        with self.assertRaises(AppError) as stale:
            self.flow.revise('alice', draft['id'], {**body, 'request_id': 'new-stale-request'})
        self.assertEqual(stale.exception.status, 409)
        self.assertEqual(len(self.jobs.list('alice')), 1)
        self.assertEqual(len(self.provider.calls), 1)

    def test_company_composition_cannot_reuse_prepared_draft_request_namespace(self):
        prepared = self.service.create({'topic_id': 'plain-language',
            'request_id': 'ai-compose-collision'}, owner='alice')
        composed = self.finish('alice', self.flow.compose('alice', self.request(
            request_id='compose-collision', mode='company', company_text='중립적인 회사 입력')))
        self.assertEqual(composed['status'], 'succeeded')
        draft = composed['result']['draft']
        self.assertNotEqual(draft['id'], prepared['id'])
        self.assertEqual(draft['origin'], 'company')
        self.assertEqual(draft['company_text'], '중립적인 회사 입력')
        self.assertEqual(len(self.service.list('alice')), 2)

    def test_saved_composition_rejects_changed_request_payload(self):
        topic = self.service.topics[0]
        result = self.provider.compose(topic)
        sender = {'name': '', 'contact': ''}
        self.service.save_composition('alice', topic, result, sender, '원래 입력', 'compose:unique')
        with self.assertRaises(AppError) as conflict:
            self.service.save_composition('alice', topic, result, sender, '변경된 입력', 'compose:unique')
        self.assertEqual(conflict.exception.status, 409)
        self.assertEqual(self.service.list('alice')[0]['company_text'], '원래 입력')

    def test_provider_failure_keeps_existing_draft_and_redacts_errors(self):
        draft = self.service.create({'topic_id':'plain-language','request_id':'example-request'}, owner='alice')
        self.provider.fail = True
        job = self.flow.revise('alice',draft['id'], {'revision':1,'instructions':'수정해주세요',
                  'input_confirmed':True,'request_id':'failed-request'})
        failed = self.finish('alice',job)
        self.assertEqual(failed['status'],'failed')
        self.assertNotIn('PRIVATE', str(failed))
        self.assertEqual(self.service.get(draft['id'],owner='alice'),draft)

    def test_consent_and_input_limits_checked_before_paid_work(self):
        for changes in [{'input_confirmed':False}, {'mode':'company','company_text':'x'*6001},
                        {'mode':'company','company_text':''}, {'mode':'ai','company_text':'private'}]:
            with self.assertRaises(AppError):
                self.flow.compose('alice', self.request(**changes))
        self.assertEqual(self.provider.calls, [])

    def test_deletion_removes_saved_draft_and_job_snapshots(self):
        job = self.flow.compose('alice', self.request(mode='company', company_text='일반 안내'))
        done = self.finish('alice', job)
        self.flow.delete_draft('alice', done['result']['draft']['id'])
        self.assertEqual(self.jobs.list('alice'), [])
        self.assertEqual(self.service.list(owner='alice'), [])

    def test_deletion_rejects_active_work_before_removing_any_saved_data(self):
        draft = self.service.create({'topic_id': 'plain-language', 'request_id': 'existing-draft'}, 'alice')
        self.service.store.save_topics('alice', [dict(self.service.topics[0], id='existing-research')])
        started, release = threading.Event(), threading.Event()

        def held_work(progress):
            started.set()
            if not release.wait(3):
                raise RuntimeError('test work timed out')
            return {}

        job = self.jobs.submit('alice', 'research', 'held-work', {}, held_work)
        try:
            self.assertTrue(started.wait(2))
            for remove in (lambda: self.flow.delete_draft('alice', draft['id']),
                           lambda: self.flow.delete_research('alice')):
                with self.assertRaises((AppError, JobError)) as denied:
                    remove()
                self.assertEqual(denied.exception.status, 409)
            self.assertEqual(self.service.get(draft['id'], 'alice'), draft)
            self.assertIsNotNone(self.service.store.topic('alice', 'existing-research'))
        finally:
            release.set()
        self.finish('alice', job)

    def test_compose_cannot_admit_a_research_candidate_deleted_before_submission(self):
        self.service.store.save_topics('alice', [dict(self.service.topics[0], id='selected-research')])
        reached_submit, release_submit = threading.Event(), threading.Event()
        original_submit = self.jobs.submit

        def delayed_submit(*args, **kwargs):
            reached_submit.set()
            if not release_submit.wait(3):
                raise RuntimeError('test submission timed out')
            return original_submit(*args, **kwargs)

        with patch.object(self.jobs, 'submit', side_effect=delayed_submit), ThreadPoolExecutor(max_workers=1) as pool:
            composition = pool.submit(self.flow.compose, 'alice', self.request(
                topic_id='selected-research', source='research'))
            try:
                self.assertTrue(reached_submit.wait(2))
                self.flow.delete_research('alice')
            finally:
                release_submit.set()
            with self.assertRaises(AppError) as missing:
                composition.result(timeout=2)
            self.assertEqual(missing.exception.status, 404)
        self.assertEqual(self.jobs.list('alice'), [])
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.service.list('alice'), [])

    def test_deletion_holds_new_admission_until_saved_data_and_results_are_removed(self):
        for kind in ('draft', 'research'):
            with self.subTest(kind=kind):
                reached_delete, release_delete, reached_submit, admitted = [threading.Event() for _ in range(4)]
                if kind == 'draft':
                    draft = self.service.create({'topic_id': 'plain-language', 'request_id': 'delete-race'}, 'alice')
                    target, method = self.service, 'delete'
                    delete = lambda: self.flow.delete_draft('alice', draft['id'])
                else:
                    self.service.store.save_topics('alice', [dict(self.service.topics[0], id='delete-race')])
                    target, method = self.service.store, 'delete_topics'
                    delete = lambda: self.flow.delete_research('alice')
                original_delete = getattr(target, method)
                original_submit = self.jobs.submit

                def delayed_delete(*args):
                    reached_delete.set()
                    if not release_delete.wait(3):
                        raise RuntimeError('test removal timed out')
                    return original_delete(*args)

                def observed_submit(*args, **kwargs):
                    reached_submit.set()
                    result = original_submit(*args, **kwargs)
                    admitted.set()
                    return result

                with patch.object(target, method, side_effect=delayed_delete), patch.object(
                        self.jobs, 'submit', side_effect=observed_submit), ThreadPoolExecutor(max_workers=2) as pool:
                    removal = pool.submit(delete)
                    try:
                        self.assertTrue(reached_delete.wait(2))
                        submission = pool.submit(self.flow.research, 'alice', {
                            'category': 'communication', 'request_id': 'after-delete-' + kind})
                        self.assertTrue(reached_submit.wait(2))
                        admitted_during_delete = admitted.wait(.1)
                    finally:
                        release_delete.set()
                    removal.result(timeout=2)
                    self.assertEqual(self.finish('alice', submission.result(timeout=2))['status'], 'succeeded')
                    self.assertFalse(admitted_during_delete, 'new work admitted before deletion completed')


if __name__ == '__main__':
    unittest.main()
