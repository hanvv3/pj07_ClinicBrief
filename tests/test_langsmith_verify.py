"""Existing-run verification must never create traces or query retired APIs."""
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import httpx2 as httpx
except ImportError:
    import httpx
from langsmith import Langsmith


RUN_ID = '11111111-1111-4111-8111-111111111111'
PROJECT_ID = '22222222-2222-4222-8222-222222222222'
CHILD_ID = '33333333-3333-4333-8333-333333333333'
GRANDCHILD_ID = '44444444-4444-4444-8444-444444444444'


class LangSmithVerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        (self.workspace / '.env.local').write_text(
            'LANGSMITH_API_KEY=lsv2_test_verification_credential\n'
            'LANGSMITH_TRACING=false\n', encoding='utf-8')
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def execute(self, handler, *extra):
        module = importlib.import_module('scripts.verify_langsmith')
        reader = Langsmith(api_key='lsv2_test_verification_credential',
                           base_url='https://langsmith.example.test', max_retries=0,
                           http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        output, errors = io.StringIO(), io.StringIO()
        arguments = ['--workspace', str(self.workspace), '--run-id', RUN_ID,
                     '--project-id', PROJECT_ID, *extra]
        with patch.object(module, 'create_reader', return_value=reader), \
             patch('langsmith.Client.create_run', side_effect=AssertionError('No writes')), \
             patch('langsmith.Client.update_run', side_effect=AssertionError('No writes')), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = module.main(arguments)
        self.assertTrue(reader.is_closed())
        return status, output.getvalue(), errors.getvalue()

    def test_existing_run_uses_v2_reads_and_counts_direct_children(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.method, 'GET', 'Verification must only read')
            self.assertEqual(request.url.params['project_id'], PROJECT_ID)
            path = request.url.path
            if path == f'/api/v2/runs/{RUN_ID}':
                self.assertEqual(set(request.url.params.get_list('selects')),
                                 {'ID', 'PROJECT_ID', 'TRACE_ID', 'START_TIME'})
                return httpx.Response(200, json={'id': RUN_ID, 'project_id': PROJECT_ID,
                    'trace_id': RUN_ID, 'start_time': '2026-11-08T00:00:00Z'})
            if path == f'/api/v2/runs/{RUN_ID}/url':
                self.assertEqual(request.url.params['trace_id'], RUN_ID)
                return httpx.Response(200, json={'url': 'https://smith.langchain.com/example'})
            if path == f'/api/v2/traces/{RUN_ID}/runs':
                return httpx.Response(200, json={'items': [
                    {'id': RUN_ID, 'parent_run_ids': []},
                    {'id': CHILD_ID, 'parent_run_ids': [RUN_ID]},
                    {'id': GRANDCHILD_ID, 'parent_run_ids': [RUN_ID, CHILD_ID]}]})
            self.fail(f'Unexpected API: {path}')
        status, output, errors = self.execute(handler)
        self.assertEqual(status, 0, errors)
        report = json.loads(output)
        self.assertEqual(report['run_id'], RUN_ID)
        self.assertEqual(report['direct_child_count'], 1)
        self.assertEqual(report['descendant_count'], 2)
        self.assertEqual(report['url'], 'https://smith.langchain.com/example')
        self.assertEqual(len(requests), 3)

    def test_remote_error_is_safe_and_does_not_retry_or_write(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(401, json={'detail': 'PRIVATE_RESPONSE_DO_NOT_PRINT'})
        status, output, errors = self.execute(handler)
        self.assertEqual(status, 1)
        self.assertEqual(output, '')
        self.assertNotIn('PRIVATE_RESPONSE', errors)
        self.assertNotIn('lsv2_', errors)
        self.assertEqual(len(requests), 1)

    def test_mismatched_run_does_not_get_url_or_report_success(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'id': CHILD_ID, 'project_id': PROJECT_ID,
                'trace_id': RUN_ID, 'start_time': '2026-11-08T00:00:00Z'})
        status, output, errors = self.execute(handler)
        self.assertEqual(status, 1)
        self.assertEqual(output, '')
        self.assertEqual(len(requests), 1)


if __name__ == '__main__':
    unittest.main()
