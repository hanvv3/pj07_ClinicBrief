"""Trace endpoints retain account scope and do not start billable work."""
import json
import time
import unittest

from tests import test_http as http_fixtures


class TraceHttpTests(unittest.TestCase):
    setUp = http_fixtures.HttpTests.setUp
    stop = http_fixtures.HttpTests.stop
    request = http_fixtures.HttpTests.request

    def research(self, request_id='trace-test'):
        status, _, payload = self.request('POST', '/api/research', {
            'category': 'communication', 'request_id': request_id})
        self.assertEqual(status, 202, payload)
        job = json.loads(payload)
        for _ in range(100):
            status, _, payload = self.request('GET', '/api/jobs/' + job['id'])
            current = json.loads(payload)
            if current['status'] not in ('queued', 'running'):
                self.assertEqual(current['status'], 'succeeded', current)
                return current
            time.sleep(.01)
        self.fail('Fixture research did not finish')

    def test_own_trace_read_is_repeatable_and_cross_account_is_denied(self):
        job = self.research()
        path = '/api/jobs/' + job['id'] + '/trace'
        status, _, payload = self.request('GET', path)
        self.assertEqual(status, 200, payload)
        trace = json.loads(payload)['trace']
        self.assertEqual(trace['id'], job['id'])
        self.assertEqual(trace['status'], 'completed')
        self.assertEqual(trace['calls'], [])  # Fixture provider makes no external request.
        self.assertEqual(self.request('GET', path)[0], 200)
        self.assertEqual(len(json.loads(self.request('GET', '/api/jobs')[2])['jobs']), 1)
        self.request('POST', '/api/auth/register', {
            'email': 'bob-trace@example.test', 'password': 'Example password 456!'})
        self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.request('GET', '/api/briefing/trace/' + job['id'])[0], 404)

    def test_job_deletion_removes_trace_and_anonymous_cannot_read(self):
        job = self.research()
        prefix = '/api/jobs/' + job['id']
        cookie, csrf = self.cookie, self.csrf
        self.cookie = self.csrf = ''
        self.assertEqual(self.request('GET', prefix + '/trace')[0], 401)
        self.cookie, self.csrf = cookie, csrf
        self.assertEqual(self.request('DELETE', prefix)[0], 200)
        self.assertEqual(self.request('GET', prefix + '/trace')[0], 404)
        from brochure.tracing import TraceStore
        from pathlib import Path
        reader = TraceStore(Path(self.tmp.name) / 'traces.sqlite3', read_only=True)
        self.assertIsNone(reader.get_for_operator(job['id']))

    def test_shared_trace_is_public_to_signed_in_accounts_only(self):
        status, _, payload = self.request('POST', '/api/briefing/refresh', {'request_id': 'shared-trace'})
        self.assertEqual(status, 202, payload)
        identifier = json.loads(payload)['job']['id']
        path = '/api/briefing/trace/' + identifier
        for _ in range(100):
            status, _, payload = self.request('GET', path)
            if status == 200 and json.loads(payload)['trace']['status'] == 'completed':
                break
            time.sleep(.01)
        else:
            self.fail('Shared fixture trace did not finish')
        self.assertEqual(self.request('GET', '/api/jobs/' + identifier + '/trace')[0], 404)
        self.request('POST', '/api/auth/register', {
            'email': 'shared-reader@example.test', 'password': 'Example password 789!'})
        self.assertEqual(self.request('GET', path)[0], 200)
        self.cookie = self.csrf = ''
        self.assertEqual(self.request('GET', path)[0], 401)


if __name__ == '__main__':
    unittest.main()
