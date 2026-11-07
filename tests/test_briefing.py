import copy
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from brochure.briefing import BriefingService
from brochure.jobs import JobError, JobRunner
from brochure.insight_store import InsightStore
from test_insight_store import selected_topic


KST = ZoneInfo('Asia/Seoul')


def topic(title='공공 안내문 점검', url='https://example.org/news/one', published='2026-11-01', updated=None):
    return {
        **{key: value for key, value in selected_topic().items() if key in ('selection', 'ready_to_use')},
        'id': 'provider-id', 'title': title, 'category': '일일 브리핑',
        'summary': '공개된 안내문 작성 지침을 살펴봅니다.',
        'director_value': '직원과 함께 안내문 표현을 점검할 때 참고할 수 있습니다.',
        'takeaway': '중요한 안내가 앞에 나오는지 확인해 보세요.', 'reading_minutes': 3,
        'evidence_notice': '현장 적용은 별도 판단이 필요합니다.',
        'research_date': '2026-11-03', 'evidence_status': 'needs_review',
        'coverage_area': 'operations', 'why_now': '공개 안내문의 수정 내용을 검토합니다.',
        'sources': [{'id': 'S1', 'title': 'Public guidance', 'publisher': 'Public agency',
                     'url': url, 'published_at': published, 'updated_at': updated,
                     'checked_at': '2026-11-03', 'context': 'The main message should appear first.',
                     'verification': 'body_access_and_cited'}],
        'claims': [{'id': 'C1', 'text': '지침은 핵심 메시지를 먼저 제시하도록 권고합니다.', 'source_ids': ['S1']}],
    }


class FakeProvider:
    configured = True

    def __init__(self):
        self.calls = []
        self.histories = []
        self.topics = [topic()]
        self.error = None
        self.report = None

    def discover_insights(self, category, *, history=None, progress=None):
        self.calls.append(category)
        self.histories.append(copy.deepcopy(history))
        if progress:
            progress('공개 자료를 확인하고 있습니다.')
        if self.error:
            raise self.error
        report = {'sources_read': 3, 'candidates_considered': len(self.topics),
                  'selected_count': len(self.topics), 'rejected': [], 'prompt': 'DO-NOT-PUBLISH'}
        return {'topics': copy.deepcopy(self.topics),
                'usage': {'requests': 3, 'total_tokens': 120, 'private_debug': 'DO-NOT-PUBLISH'},
                'selection_report': copy.deepcopy(self.report if self.report is not None else report)}


class BriefingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = datetime(2026, 11, 3, 8, 59, tzinfo=KST)
        patcher = patch('brochure.jobs.time.time', side_effect=lambda: self.now.timestamp())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.jobs = JobRunner(self.root / 'jobs.sqlite3')
        self.addCleanup(self.jobs.shutdown)
        self.provider = FakeProvider()
        self.insights = InsightStore(self.root / 'insights.sqlite3')
        self.feed = self.make_feed()

    def make_feed(self, enabled=True):
        feed = BriefingService(self.root / 'publicfeed.db', self.provider, self.jobs,
                               enabled=enabled, clock=lambda: self.now, insights=self.insights)
        self.addCleanup(feed.shutdown)
        return feed

    def finish(self, job):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = self.jobs.get('__briefing__', job['id'])
            if current['status'] not in ('queued', 'running'):
                return current
            time.sleep(.005)
        self.fail('feed job did not finish')

    def collect(self, key='manual-one'):
        job = self.finish(self.feed.refresh(key))
        self.assertEqual(job['status'], 'succeeded', job)
        return job

    def test_canonical_url_deduplicates_and_genuine_new_update_gets_new_id(self):
        self.provider.topics = [topic(url='https://EXAMPLE.org/news/one?b=2&utm_source=x&a=1#section')]
        self.collect()
        first = self.feed.snapshot()['items'][0]
        self.assertRegex(first['id'], r'^feed-[a-f0-9]{32}$')
        self.provider.topics = [topic(title='제목을 다듬은 안내문',
                                      url='https://example.org/news/one?a=1&b=2&fbclid=tracking')]
        self.collect('manual-two')
        items = self.feed.snapshot()['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], first['id'])
        self.now += timedelta(days=1)
        self.provider.topics[0]['sources'][0]['updated_at'] = '2026-11-04'
        self.collect('manual-three')
        items = self.feed.snapshot()['items']
        self.assertEqual(len(items), 2)
        self.assertEqual(len({item['id'] for item in items}), 2)

    def test_distinct_insight_problems_on_one_core_page_remain_separate(self):
        first, second = topic(), topic('대기 안내 답장')
        second['selection'].update(problem_key='waiting-time-message',
                                   problem='대기 순서를 문의하는 사람에게 답할 문장이 필요합니다.')
        self.provider.topics = [first, second]
        result = self.collect()
        self.assertEqual(result['result']['selection_report']['selected_count'], 2)
        self.assertEqual(result['result']['count'], 2)
        items = self.feed.snapshot()['items']
        self.assertEqual(len({item['id'] for item in items}), 2)
        self.assertCountEqual([item['selection']['problem_key'] for item in items],
                              ['appointment-change-message', 'waiting-time-message'])

    def test_insight_update_preserves_predecessor_and_its_vote_with_same_core_date(self):
        self.collect()
        previous = self.feed.snapshot()['items'][0]
        self.insights.set_feedback('alice', previous['id'], previous['selection']['problem_key'],
                                   'seen', shared=True)
        update = topic('추가된 변경 문의 경로 안내')
        secondary = copy.deepcopy(update['sources'][0])
        secondary.update(id='S2', url='https://example.org/new-procedure', published_at='2026-11-03',
                         context='The new procedure adds a dedicated channel for appointment changes.')
        update['sources'].append(secondary)
        update['claims'].append({'id': 'C2', 'text': '새 안내에는 예약 변경 문의 경로가 추가되어 있습니다.',
                                 'source_ids': ['S2']})
        update['selection'].update(novelty='update', previous_topic_id=previous['id'],
                                   change='예약 변경 문의 경로가 추가되었습니다.')
        update['selection']['signals'].append({'source_id': 'S2',
            'observation': '새 공개 안내에서 변경 문의 경로를 확인했습니다.'})
        self.provider.topics = [update]
        self.now += timedelta(hours=1)
        self.collect('updated-version')
        items = self.feed.snapshot()['items']
        self.assertEqual(len(items), 2)
        current = next(item for item in items if item['selection']['novelty'] == 'update')
        self.assertNotEqual(current['id'], previous['id'])
        self.assertEqual(current['selection']['previous_topic_id'], previous['id'])
        self.assertEqual(self.feed.get_topic(previous['id']), previous)
        self.assertEqual(self.insights.feedback_for('alice', [previous['id'], current['id']]),
                         {previous['id']: 'seen'})

        # A recollection of the same version remains stable despite normalized key,
        # whitespace, tracking URL and transient source-ID differences.
        self.now += timedelta(days=1)
        update['selection']['problem_key'] = ' Appointment__Change Message '
        update['selection']['change'] = '예약  변경 문의 경로가\n추가되었습니다.'
        update['sources'][0]['url'] += '?utm_source=refresh#section'
        update['sources'][1]['id'] = 'S3'
        update['claims'][1]['source_ids'] = ['S3']
        update['selection']['signals'][1]['source_id'] = 'S3'
        self.collect('same-updated-version')
        items = self.feed.snapshot()['items']
        self.assertEqual(len(items), 2)
        self.assertEqual(next(item['id'] for item in items if item['selection']['novelty'] == 'update'),
                         current['id'])

    def test_freshness_uses_primary_source_date_and_changes_when_read_later(self):
        self.provider.topics = [topic('오늘 자료', 'https://example.org/one', '2026-11-03'),
                                topic('14일 범위', 'https://example.org/two', '2026-10-21'),
                                topic('이전 자료', 'https://example.org/three', '2026-10-20')]
        self.collect()
        items = {item['title']: item for item in self.feed.snapshot()['items']}
        self.assertEqual(items['오늘 자료']['freshness']['kind'], 'recent')
        self.assertEqual(items['14일 범위']['freshness']['kind'], 'recent')
        self.assertEqual(items['이전 자료']['freshness']['kind'], 'older')
        self.assertEqual(items['이전 자료']['freshness']['date'], '2026-10-20')
        self.now += timedelta(days=1)
        items = {item['title']: item for item in self.feed.snapshot()['items']}
        self.assertEqual(items['14일 범위']['freshness']['kind'], 'older')

    def test_ambiguous_future_or_secondary_dates_do_not_claim_recent(self):
        old = topic('대표 원문은 오래됨', 'https://example.org/old', '2020-01-01')
        recent_secondary = copy.deepcopy(old['sources'][0])
        recent_secondary.update(id='S2', published_at='2026-11-03')
        old['sources'].append(recent_secondary)
        self.provider.topics = [topic('월만 확인됨', 'https://example.org/month', '2026-11'),
                                topic('미래 날짜', 'https://example.org/future', '2026-11-04'), old]
        self.collect()
        items = {item['title']: item for item in self.feed.snapshot()['items']}
        for title in ['월만 확인됨', '미래 날짜']:
            self.assertEqual(items[title]['freshness']['kind'], 'undated')
            self.assertIsNone(items[title]['freshness']['date'])
        self.assertEqual(items['대표 원문은 오래됨']['freshness']['kind'], 'older')
        self.assertEqual(items['대표 원문은 오래됨']['freshness']['date'], '2020-01-01')

    def test_failed_batch_is_atomic_and_preserves_last_success(self):
        self.collect()
        before = self.feed.snapshot()
        invalid = topic('검증 안 된 자료', 'https://example.org/invalid')
        invalid['sources'][0].pop('verification')
        self.provider.topics = [topic('저장되면 안 됨', 'https://example.org/new'), invalid]
        self.now += timedelta(minutes=1)
        failed = self.finish(self.feed.refresh('failed-batch'))
        self.assertEqual(failed['status'], 'failed')
        after = self.feed.snapshot()
        self.assertEqual(after['items'], before['items'])
        self.assertEqual(after['status']['last_success_at'], before['status']['last_success_at'])
        self.assertEqual(after['status']['last_attempt']['id'], failed['id'])
        self.assertEqual(after['status']['last_attempt']['status'], 'failed')

    def test_quota_counts_failed_work_and_replay_precedes_mutable_checks(self):
        first = self.collect()
        self.provider.error = RuntimeError('SECRET-RESPONSE')
        failed = self.finish(self.feed.refresh('second'))
        self.assertEqual(failed['status'], 'failed')
        self.assertNotIn('SECRET', failed['error'])
        with self.assertRaises(JobError) as quota:
            self.feed.refresh('third')
        self.assertEqual(quota.exception.status, 429)
        self.assertEqual(self.feed.snapshot()['status']['remaining_runs'], 0)
        self.provider.configured = False
        replay = self.feed.refresh('manual-one')
        self.assertEqual(replay['id'], first['id'])
        disabled = self.make_feed(enabled=False)
        self.assertEqual(disabled.refresh('second')['id'], failed['id'])
        self.assertEqual(self.provider.calls, ['briefing', 'briefing'])

    def test_missing_key_blocks_collection_and_disabled_schedule_allows_manual_refresh(self):
        self.provider.configured = False
        self.assertIsNone(self.feed.tick(self.now.replace(hour=9)))
        with self.assertRaises(JobError):
            self.feed.refresh('no-key')
        self.assertIsNone(self.feed.snapshot()['status']['next_run_at'])
        self.provider.configured = True
        disabled = self.make_feed(enabled=False)
        self.assertIsNone(disabled.tick(self.now.replace(hour=9)))
        self.assertIsNone(disabled.snapshot()['status']['next_run_at'])
        self.assertFalse(disabled.snapshot()['status']['auto_enabled'])
        self.assertEqual(self.finish(disabled.refresh('explicit-manual'))['status'], 'succeeded')
        self.assertEqual(self.provider.calls, ['briefing'])

    def test_invalid_editorial_fields_or_unlinked_primary_source_fail_closed(self):
        invalid_topics = []
        unknown_area = topic()
        unknown_area['coverage_area'] = 'unsupported-area'
        invalid_topics.append(unknown_area)
        too_long = topic()
        too_long['why_now'] = 'x' * 401
        invalid_topics.append(too_long)
        unlinked = topic()
        second = copy.deepcopy(unlinked['sources'][0])
        second.update(id='S2', url='https://example.org/background')
        unlinked['sources'].append(second)
        unlinked['claims'][0]['source_ids'] = ['S2']
        invalid_topics.append(unlinked)
        for index, invalid in enumerate(invalid_topics):
            with self.subTest(index=index):
                self.now += timedelta(days=1)
                self.provider.topics = [invalid]
                failed = self.finish(self.feed.refresh(f'invalid-{index}'))
                self.assertEqual(failed['status'], 'failed')
                self.assertEqual(self.feed.snapshot()['items'], [])

    def test_schedule_runs_once_at_nine_and_never_replays_prior_days(self):
        self.assertIsNone(self.feed.tick())
        self.assertEqual(self.feed.snapshot()['status']['next_run_at'], '2026-11-03T09:00:00+09:00')
        self.now = self.now.replace(hour=9, minute=0)
        self.assertEqual(self.finish(self.feed.tick())['status'], 'succeeded')
        self.assertIsNone(self.feed.tick())
        self.assertEqual(self.feed.snapshot()['status']['next_run_at'], '2026-11-04T09:00:00+09:00')
        self.now += timedelta(days=3)
        self.assertEqual(self.finish(self.feed.tick())['status'], 'succeeded')
        self.assertEqual(self.provider.calls, ['briefing', 'briefing'])

    def test_restart_interruption_does_not_retry_same_day(self):
        self.now = self.now.replace(hour=9, minute=0)
        job = self.finish(self.feed.tick())
        self.jobs.shutdown()
        with sqlite3.connect(self.root / 'jobs.sqlite3') as db:
            db.execute("UPDATE jobs SET status='running', result=NULL WHERE id=?", (job['id'],))
        self.jobs = JobRunner(self.root / 'jobs.sqlite3')
        self.addCleanup(self.jobs.shutdown)
        reopened = self.make_feed()
        self.assertIsNone(reopened.tick())
        self.assertEqual(reopened.snapshot()['status']['last_attempt']['status'], 'interrupted')
        self.assertEqual(reopened.refresh('scheduled-2026-11-03')['status'], 'interrupted')
        self.assertEqual(self.provider.calls, ['briefing'])

    def test_snapshot_contains_only_public_fields_and_topics_are_copied(self):
        self.provider.topics[0].update(company_text='PRIVATE-COMPANY', api_key='PRIVATE-KEY')
        self.provider.topics[0]['sources'][0]['private_input'] = 'PRIVATE-INPUT'
        job = self.collect()
        snapshot = self.feed.snapshot()
        self.assertEqual(set(snapshot), {'items', 'status'})
        self.assertEqual(set(snapshot['status']), {'auto_enabled', 'schedule_hour', 'timezone',
            'next_run_at', 'last_success_at', 'last_attempt', 'daily_limit', 'remaining_runs', 'configured'})
        self.assertEqual(job['result'], {'count': 1, 'usage': {'requests': 3, 'total_tokens': 120},
            'selection_report': {'sources_read': 3, 'candidates_considered': 1, 'selected_count': 1, 'rejected': []}})
        self.assertNotIn('PRIVATE', str(snapshot))
        self.assertNotIn('DO-NOT-PUBLISH', str(snapshot))
        item = snapshot['items'][0]
        self.assertEqual(set(item['freshness']), {'kind', 'date', 'label'})
        selected = self.feed.get_topic(item['id'])
        selected['sources'][0]['title'] = 'changed'
        self.assertEqual(self.feed.get_topic(item['id'])['sources'][0]['title'], 'Public guidance')
        self.assertIsNone(self.feed.get_topic('unknown'))
        self.assertEqual(self.jobs.list('some-user'), [])

    def test_shared_discovery_history_uses_only_public_topics_and_shared_feedback(self):
        self.collect()
        item = self.feed.snapshot()['items'][0]
        self.assertEqual(item['ready_to_use']['body'], self.provider.topics[0]['ready_to_use']['body'])
        self.assertEqual(self.provider.histories[0], {'recent_topics': [], 'feedback': []})
        problem = item['selection']['problem_key']
        self.insights.set_feedback('alice', item['id'], problem, 'useful', shared=True)
        self.insights.set_feedback('bob', item['id'], problem, 'useful', shared=True)
        self.insights.set_feedback('alice', 'research-private', 'PRIVATE-PROBLEM', 'seen')
        self.provider.topics[0]['company_text'] = 'PRIVATE-COMPANY'
        self.collect('second-with-history')
        history = self.provider.histories[-1]
        self.assertEqual(history['recent_topics'][0]['id'], item['id'])
        self.assertEqual(history['feedback'], [{'problem_key': problem, 'verdict': 'useful', 'count': 2}])
        self.assertNotIn('private', str(history).lower())
        self.assertNotIn('alice', str(history))
        self.assertNotIn('bob', str(history))

    def test_empty_selection_succeeds_and_preserves_previous_feed(self):
        self.collect()
        before = self.feed.snapshot()['items']
        self.provider.topics = []
        self.now += timedelta(minutes=1)
        empty = self.collect('empty-selection')
        self.assertEqual(empty['result']['count'], 0)
        self.assertEqual(empty['result']['selection_report']['selected_count'], 0)
        self.assertEqual(self.feed.snapshot()['items'], before)
        self.assertEqual(self.feed.snapshot()['status']['last_success_at'], self.now.isoformat(timespec='seconds'))

    def test_invalid_selection_report_preserves_existing_feed(self):
        self.collect()
        before = self.feed.snapshot()['items']
        self.provider.topics = [topic('다른 자료', 'https://example.org/other')]
        self.provider.report = {'sources_read': 4, 'candidates_considered': 1,
                                'selected_count': 0, 'rejected': []}
        failed = self.finish(self.feed.refresh('invalid-report'))
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(self.feed.snapshot()['items'], before)

    def test_legacy_saved_feed_without_selection_fields_remains_readable(self):
        self.provider.topics[0].pop('selection')
        self.provider.topics[0].pop('ready_to_use')
        self.collect()
        item = self.feed.snapshot()['items'][0]
        self.assertNotIn('selection', item)
        self.assertEqual(item['id'], 'feed-cdf3414e767d7ebf4cc7656e6b20063e')
        self.assertEqual(self.feed.get_topic(item['id'])['title'], item['title'])

    def test_retention_caps_items_and_expires_old_collections(self):
        for day in range(31):
            self.provider.topics = [topic(f'자료 {day}-{index}', f'https://example.org/{day}/{index}')
                                    for index in range(3)]
            self.collect(f'day-{day}')
            if day < 30:
                self.now += timedelta(days=1)
        self.assertEqual(len(self.feed.snapshot()['items']), 90)
        self.now += timedelta(days=31)
        self.assertEqual(self.feed.snapshot()['items'], [])
        self.assertEqual(self.feed.snapshot()['status']['remaining_runs'], 2)

    def test_recollection_after_expiry_survives_without_an_intervening_read(self):
        self.collect('first-collection')
        first = self.feed.snapshot()['items'][0]
        self.now += timedelta(days=1)
        self.collect('unexpired-duplicate')
        self.assertEqual(self.feed.snapshot()['items'][0]['collected_at'], first['collected_at'])
        self.now += timedelta(days=30)
        # No snapshot/get_topic call cleans up the expired record before collection.
        job = self.collect('expired-recollection')
        self.assertEqual(job['result']['count'], 1)
        items = self.feed.snapshot()['items']
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['id'], first['id'])
        self.assertEqual(items[0]['collected_at'], self.now.isoformat(timespec='seconds'))

    def test_shutdown_leaves_shared_job_runner_available(self):
        self.feed.shutdown()
        job = self.jobs.submit('account-user', 'research', 'one', {}, lambda _: {'ok': True})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.jobs.get('account-user', job['id'])['status'] == 'succeeded':
                return
            time.sleep(.005)
        self.fail('shared job runner was stopped')


if __name__ == '__main__':
    unittest.main()
