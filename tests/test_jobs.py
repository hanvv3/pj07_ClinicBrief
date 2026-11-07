import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from brochure.jobs import JobError, JobRunner
from brochure.provider import ProviderError
from brochure.service import AppError


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'jobs.sqlite3'
        self.runner = JobRunner(self.path)
        self.addCleanup(self.runner.shutdown)

    def wait_terminal(self, job, owner='alice', runner=None):
        runner = runner or self.runner
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            current = runner.get(owner, job['id'])
            if current['status'] not in ('queued', 'running'):
                return current
            time.sleep(.01)
        self.fail('job did not reach a terminal state')

    def blocked_work(self, stage='자료를 확인하고 있습니다.'):
        started, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def work(progress):
            progress(stage)
            started.set()
            if not release.wait(5):
                raise RuntimeError('test work timed out')
            return {'value': 'finished'}

        return work, started, release

    def test_progress_and_result_are_owned_and_payload_is_not_persisted(self):
        work, started, release = self.blocked_work()
        job = self.runner.submit('alice', 'compose', 'request-one',
                                 {'company_text': 'PRIVATE-INPUT-918421'}, work)
        self.assertTrue(started.wait(2))
        current = self.runner.get('alice', job['id'])
        self.assertEqual(current['status'], 'running')
        self.assertEqual(current['stage'], '자료를 확인하고 있습니다.')
        self.assertEqual(set(current), {'id', 'kind', 'status', 'stage', 'error',
                                        'result', 'created_at', 'updated_at'})
        self.assertEqual(self.runner.list('bob'), [])
        for operation in [lambda: self.runner.get('bob', job['id']),
                          lambda: self.runner.delete('bob', job['id'])]:
            with self.assertRaises(JobError) as denied:
                operation()
            self.assertEqual(denied.exception.status, 404)
        self.assertNotIn(b'PRIVATE-INPUT-918421', self.path.read_bytes())
        release.set()
        final = self.wait_terminal(job)
        self.assertEqual(final['status'], 'succeeded')
        self.assertEqual(final['result'], {'value': 'finished'})
        self.assertFalse(self.runner.active('alice'))

    def test_trace_write_failure_keeps_successful_research_and_reports_missing_record(self):
        original = self.runner.traces._update

        def fail_only_trace_completion(*args, **kwargs):
            if kwargs.get('status') == 'completed':
                raise sqlite3.OperationalError('fixture trace-only storage failure')
            return original(*args, **kwargs)

        with patch.object(self.runner.traces, '_update', side_effect=fail_only_trace_completion):
            job = self.runner.submit('alice', 'research', 'trace-write-failure', {},
                                     lambda progress: {'topics': [], 'complete': True})
            result = self.wait_terminal(job)
        self.assertEqual(result['status'], 'succeeded')
        self.assertIs(result['result']['complete'], True)
        self.assertIn('기록', result['result']['trace_notice'])
        self.assertNotIn('fixture', result['result']['trace_notice'])

    def test_concurrent_duplicate_submission_runs_work_once(self):
        work, started, release = self.blocked_work()
        calls = []
        admitted = []

        def admit_once():
            if admitted:
                raise AppError('중복 요청에 새 작업 검증을 적용했습니다.', 409)
            admitted.append(True)

        def count(progress):
            calls.append('called')
            return work(progress)

        with ThreadPoolExecutor(max_workers=8) as submitters:
            jobs = list(submitters.map(lambda _: self.runner.submit(
                'alice', 'research', 'same-request', {'category': 'communication'}, count,
                before_submit=admit_once), range(8)))
        self.assertEqual(len({job['id'] for job in jobs}), 1)
        self.assertTrue(started.wait(2))
        release.set()
        self.assertEqual(self.wait_terminal(jobs[0])['status'], 'succeeded')
        self.assertEqual(calls, ['called'])
        repeated = self.runner.submit('alice', 'research', 'same-request',
                                      {'category': 'communication'}, count, before_submit=admit_once)
        self.assertEqual(repeated['id'], jobs[0]['id'])
        self.assertEqual(calls, ['called'])

    def test_reordered_payload_deduplicates_but_changed_payload_conflicts(self):
        job = self.runner.submit('alice', 'compose', 'request-one', {'a': 1, 'b': 2},
                                 lambda progress: {'ok': True})
        self.wait_terminal(job)
        same = self.runner.submit('alice', 'compose', 'request-one', {'b': 2, 'a': 1},
                                  lambda progress: self.fail('duplicate executed'))
        self.assertEqual(job['id'], same['id'])
        with self.assertRaises(JobError) as conflict:
            self.runner.submit('alice', 'compose', 'request-one', {'a': 3}, lambda _: {})
        self.assertEqual(conflict.exception.status, 409)

    def test_one_active_job_per_owner_and_two_workers_globally(self):
        first, started1, release1 = self.blocked_work()
        second, started2, release2 = self.blocked_work()
        third, started3, release3 = self.blocked_work()
        job1 = self.runner.submit('alice', 'research', 'one', {}, first)
        self.assertTrue(started1.wait(2))
        self.assertTrue(self.runner.active('alice'))
        with self.assertRaises(JobError) as conflict:
            self.runner.submit('alice', 'compose', 'two', {}, second)
        self.assertEqual(conflict.exception.status, 409)
        self.runner.submit('bob', 'research', 'one', {}, second)
        self.assertTrue(started2.wait(2))
        queued = self.runner.submit('carol', 'research', 'one', {}, third)
        self.assertFalse(started3.wait(.1))
        self.assertEqual(self.runner.get('carol', queued['id'])['status'], 'queued')
        self.assertTrue(self.runner.active('carol'))
        release1.set()
        self.wait_terminal(job1)
        self.assertTrue(started3.wait(2))
        release2.set()
        release3.set()

    def test_queue_is_bounded(self):
        work, started, release = self.blocked_work()
        for number in range(16):
            self.runner.submit(f'owner-{number}', 'research', 'one', {}, work)
        with self.assertRaises(JobError) as full:
            self.runner.submit('overflow-owner', 'research', 'one', {}, work)
        self.assertEqual(full.exception.status, 429)
        release.set()

    def test_daily_quota_counts_failed_and_deleted_work(self):
        self.runner.shutdown()
        self.runner = JobRunner(self.path, daily_limit=2)
        self.addCleanup(self.runner.shutdown)
        first = self.runner.submit('alice', 'research', 'one', {}, lambda _: {})
        self.wait_terminal(first)
        self.runner.delete('alice', first['id'])

        def failure(progress):
            raise RuntimeError('secret provider response')

        failed = self.runner.submit('alice', 'research', 'two', {}, failure)
        self.assertEqual(self.wait_terminal(failed)['status'], 'failed')
        with self.assertRaises(JobError) as limited:
            self.runner.submit('alice', 'research', 'three', {}, lambda _: {})
        self.assertEqual(limited.exception.status, 429)
        with patch('brochure.jobs.time.time', return_value=time.time() + 86401):
            next_day = self.runner.submit('alice', 'research', 'four', {}, lambda _: {})
        self.assertEqual(self.wait_terminal(next_day)['status'], 'succeeded')

    def test_failure_is_safe_and_does_not_retry_on_reopen(self):
        calls = []

        def failure(progress):
            calls.append('called')
            raise RuntimeError('sk-sensitive-provider-response')

        failed = self.runner.submit('alice', 'compose', 'one', {}, failure)
        result = self.wait_terminal(failed)
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('sensitive', result['error'])
        self.runner.shutdown()
        reopened = JobRunner(self.path)
        self.addCleanup(reopened.shutdown)
        again = reopened.submit('alice', 'compose', 'one', {}, failure)
        self.assertEqual(again['status'], 'failed')
        self.assertEqual(calls, ['called'])

    def test_known_safe_failure_reasons_survive_without_exposing_unknown_errors(self):
        cases = [ProviderError('환자 기록을 제거해 주세요.'),
                 AppError('작업 버전이 변경되었습니다.', 409),
                 JobError('작업 데이터를 확인해 주세요.')]
        for number, error in enumerate(cases):
            with self.subTest(error=type(error).__name__):
                def failure(progress, error=error):
                    raise error
                job = self.runner.submit('alice', 'compose', f'safe-{number}', {}, failure)
                failed = self.wait_terminal(job)
                self.assertEqual(failed['status'], 'failed')
                self.assertEqual(failed['error'], str(error))

    def test_admission_precondition_applies_only_to_new_matching_requests(self):
        allowed = True

        def validate_new():
            if not allowed:
                raise AppError('작업 버전이 변경되었습니다.', 409)

        job = self.runner.submit('alice', 'revise', 'request-one', {'revision': 1},
                                 lambda _: {'revision': 2}, before_submit=validate_new)
        finished = self.wait_terminal(job)
        allowed = False
        self.assertEqual(self.runner.submit('alice', 'revise', 'request-one', {'revision': 1},
            lambda _: self.fail('duplicate work executed'), before_submit=validate_new), finished)
        with self.assertRaises(JobError):
            self.runner.submit('alice', 'revise', 'request-one', {'revision': 2},
                lambda _: {}, before_submit=validate_new)
        with self.assertRaises(AppError):
            self.runner.submit('alice', 'revise', 'request-two', {'revision': 1},
                lambda _: {}, before_submit=validate_new)
        self.assertEqual(self.runner.list('alice'), [finished])

    def test_idle_operation_and_new_job_admission_cannot_overlap(self):
        deleting, release, submitting, admitted = [threading.Event() for _ in range(4)]
        self.addCleanup(release.set)

        def remove_saved_data():
            deleting.set()
            if not release.wait(3):
                raise RuntimeError('test removal timed out')

        def submit_job():
            submitting.set()
            job = self.runner.submit('alice', 'research', 'after-removal', {}, lambda _: {})
            admitted.set()
            return job

        with ThreadPoolExecutor(max_workers=2) as pool:
            removal = pool.submit(self.runner.run_if_idle, 'alice', remove_saved_data)
            try:
                self.assertTrue(deleting.wait(2))
                submission = pool.submit(submit_job)
                self.assertTrue(submitting.wait(2))
                self.assertFalse(admitted.wait(.1), 'new work was admitted during removal')
            finally:
                release.set()
            removal.result(timeout=2)
            self.assertEqual(self.wait_terminal(submission.result(timeout=2))['status'], 'succeeded')

    def test_restart_marks_inflight_interrupted_without_repeating_work(self):
        job = self.runner.submit('alice', 'research', 'one', {}, lambda _: {})
        self.wait_terminal(job)
        self.runner.shutdown()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE jobs SET status='running', result=NULL WHERE id=?", (job['id'],))
        reopened = JobRunner(self.path)
        self.addCleanup(reopened.shutdown)
        restored = reopened.submit('alice', 'research', 'one', {},
                                   lambda _: self.fail('restart repeated work'))
        self.assertEqual(restored['status'], 'interrupted')
        self.assertFalse(reopened.active('alice'))
        self.assertIsNone(restored['result'])

    def test_delete_terminal_result_preserves_idempotency(self):
        work, started, release = self.blocked_work()
        job = self.runner.submit('alice', 'compose', 'one', {}, work)
        self.assertTrue(started.wait(2))
        with self.assertRaises(JobError) as active:
            self.runner.delete('alice', job['id'])
        self.assertEqual(active.exception.status, 409)
        release.set()
        self.wait_terminal(job)
        self.runner.delete('alice', job['id'])
        self.assertEqual(self.runner.list('alice'), [])
        with self.assertRaises(JobError) as missing:
            self.runner.get('alice', job['id'])
        self.assertEqual(missing.exception.status, 404)
        with self.assertRaises(JobError) as reused:
            self.runner.submit('alice', 'compose', 'one', {}, lambda _: self.fail('deleted job reran'))
        self.assertEqual(reused.exception.status, 409)
        with sqlite3.connect(self.path) as db:
            result, error = db.execute('SELECT result, error FROM jobs WHERE id=?', (job['id'],)).fetchone()
        self.assertIsNone(result)
        self.assertIsNone(error)

    def test_invalid_submission_is_rejected_before_work(self):
        for request, payload in [('', {}), ('x' * 129, {}), ('valid', []),
                                 ('valid', {'text': 'x' * 40000}), ('valid', {'n': float('nan')})]:
            with self.subTest(request=request[:20], payload_type=type(payload)):
                with self.assertRaises(JobError):
                    self.runner.submit('alice', 'compose', request, payload,
                                       lambda _: self.fail('invalid request executed'))
        self.assertEqual(self.runner.list('alice'), [])


if __name__ == '__main__':
    unittest.main()
