"""Research tracing uses real SQLite and provider parsing, never paid requests."""
import contextvars
import io
import json
import os
import tempfile
import threading
import unittest
import sqlite3
from contextlib import ExitStack, closing, contextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

# Match the SDK's transport dependency: current releases prefer httpx2 while
# older supported environments can still provide httpx.
try:
    import httpx2 as httpx
except ImportError:
    import httpx

from brochure.provider import OpenAIProvider, ProviderError
from brochure import tracing


def response(text='공개 조사 결과'):
    return {'id': 'resp_trace', 'status': 'completed', 'error': None,
            'incomplete_details': None,
            'output': [
                {'type': 'reasoning', 'summary': [{'text': 'NEVER_STORE_REASONING'}]},
                {'type': 'message', 'status': 'completed', 'role': 'assistant',
                 'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}],
            'usage': {'input_tokens': 40, 'output_tokens': 20, 'total_tokens': 60}}


PROJECT_ID = '1f06389f-1301-49bf-ae51-36b9ef83e715'
CLOUD_URL = 'https://smith.langchain.com/o/test/r/confirmed'


@contextmanager
def cloud_read_transport(handler=None):
    """Exercise the real sync SDK's wire contract without any external traffic."""
    from langsmith import Langsmith
    requests, readers = [], []

    def transport(request):
        requests.append(request)
        if request.method != 'GET':
            raise AssertionError('Cloud verification must only read')
        if handler is not None:
            result = handler(request)
            if result is not None:
                return result
        path = request.url.path
        if path == '/api/v1/sessions/resolutions':
            return httpx.Response(200, json={'session_id': PROJECT_ID})
        if not path.startswith('/api/v2/runs/'):
            raise AssertionError('Unexpected endpoint: ' + path)
        if path.endswith('/url'):
            return httpx.Response(200, json={'url': CLOUD_URL})
        identifier = path.rsplit('/', 1)[-1]
        return httpx.Response(200, json={'id': identifier, 'project_id': PROJECT_ID,
                              'trace_id': identifier, 'start_time': request.url.params['start_time']})

    def make_reader(**kwargs):
        reader = Langsmith(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        readers.append(reader)
        return reader

    with patch('langsmith.Langsmith', side_effect=make_reader), \
         patch('langsmith.client.Client.read_project', return_value=SimpleNamespace(id=PROJECT_ID)) as project, \
         patch('langsmith.client.Client.request_with_retries', side_effect=AssertionError('Unexpected legacy transport')):
        yield requests, readers, project


class TracingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'OPENAI_API_KEY': 'sk-test-tracing-credential-00000'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = tracing.TraceStore(self.root / 'traces.sqlite3', workspace=self.root)
        self.provider = OpenAIProvider(self.root)

    def request(self, text='공개 조사 입력', **kwargs):
        return self.provider._request('insight_clinic_scout', None, '공개 조사 지시', {'text': text}, **kwargs)

    def transport(self, value):
        return patch('brochure.provider.urlopen', return_value=io.BytesIO(json.dumps(value).encode()))

    def test_records_request_before_validation_and_removes_reasoning(self):
        invalid = response('{not valid json')
        with self.transport(invalid), self.assertRaises(ProviderError):
            with tracing.research_trace(self.store, 'run-one', 'alice', 'research'):
                self.provider._request('insight_selection', {'type': 'object', 'properties': {}},
                                       'Public instructions', {'query': 'Public query'})
        result = self.store.get('alice', 'run-one')
        self.assertEqual(result['status'], 'failed')
        self.assertIsNotNone(result['finished_at'])
        call = result['calls'][0]
        self.assertEqual(call['status'], 'failed')
        self.assertEqual(call['response_id'], 'resp_trace')
        self.assertEqual(call['request']['instructions'], 'Public instructions')
        self.assertEqual(call['response']['output'][0]['content'][0]['text'], '{not valid json')
        self.assertNotIn('NEVER_STORE_REASONING', json.dumps(result))
        self.assertEqual(result['usage'], {'requests': 1, 'input_tokens': 40,
                                           'output_tokens': 20, 'total_tokens': 60})
        self.assertEqual(len(call['instructions_hash']), 64)
        self.assertEqual(len(call['input_hash']), 64)

    def test_trace_is_visible_while_request_is_running_and_owner_scoped(self):
        def http(request, timeout):
            current = self.store.get('alice', 'running')
            self.assertEqual(current['status'], 'running')
            self.assertEqual(current['calls'][0]['status'], 'running')
            self.assertIsNone(current['calls'][0]['response'])
            return io.BytesIO(json.dumps(response()).encode())
        with patch('brochure.provider.urlopen', http):
            with tracing.research_trace(self.store, 'running', 'alice', 'research'):
                self.request()
        self.assertIsNone(self.store.get('bob', 'running'))
        self.assertEqual(self.store.list('bob'), [])
        self.assertFalse(self.store.delete('bob', 'running'))
        self.assertEqual(self.store.list('alice')[0]['id'], 'running')
        self.assertEqual(self.store.get('alice', 'running')['status'], 'completed')
        self.assertTrue(self.store.delete('alice', 'running'))
        self.assertIsNone(self.store.get('alice', 'running'))

    def test_no_implicit_trace_or_private_composition_capture(self):
        with self.transport(response()):
            self.request('UNTRACED_PRIVATE_TEXT')
        with tracing.research_trace(self.store, 'public', 'alice', 'research'):
            with self.transport(response()):
                self.provider._request('brochure_composition', None, 'PRIVATE_COMPANY', {'company_text': 'PRIVATE_TEXT'})
        self.assertEqual(self.store.get('alice', 'public')['calls'], [])
        with self.assertRaises(ValueError):
            with tracing.research_trace(self.store, 'private', 'alice', 'compose'):
                pass
        self.assertIsNone(self.store.get('alice', 'private'))

    def test_http_error_body_and_exception_credentials_are_never_stored(self):
        failure = HTTPError('https://api.openai.com/SECRET_URL', 401, 'SECRET_REASON', {},
                            io.BytesIO(b'SECRET_ERROR_BODY'))
        self.addCleanup(failure.close)
        with patch('brochure.provider.urlopen', side_effect=failure), self.assertRaises(ProviderError):
            with tracing.research_trace(self.store, 'bad', 'alice', 'research'):
                self.request()
        result = self.store.get('alice', 'bad')
        self.assertEqual(result['calls'][0]['error_code'], 'http_auth')
        self.assertIsNone(result['calls'][0]['response'])
        self.assertNotIn('SECRET_', json.dumps(result))
        self.assertNotIn('sk-test-', json.dumps(result))
        with self.assertRaises(RuntimeError):
            with tracing.research_trace(self.store, 'exception', 'alice', 'research'):
                raise RuntimeError('TOP_SECRET_APPLICATION_INPUT')
        self.assertNotIn('TOP_SECRET', json.dumps(self.store.get('alice', 'exception')))

    def test_root_trace_preserves_failed_request_rate_limit_cause(self):
        failure = HTTPError('https://api.openai.com/responses', 429, 'PRIVATE_REASON', {},
                            io.BytesIO(b'PRIVATE_ERROR_BODY'))
        self.addCleanup(failure.close)
        with patch('brochure.provider.urlopen', side_effect=failure), self.assertRaises(ProviderError):
            with tracing.research_trace(self.store, 'rate-limited', 'alice', 'research'):
                self.request()
        stored = self.store.get('alice', 'rate-limited')
        self.assertEqual(stored['error_code'], 'http_rate_limit')
        self.assertEqual(stored['error'], stored['calls'][0]['error'])
        self.assertNotIn('PRIVATE_', json.dumps(stored))

    def test_root_trace_keeps_validation_cause_for_checks_after_successful_request(self):
        with self.transport(response()), self.assertRaises(ProviderError):
            with tracing.research_trace(self.store, 'local-validation', 'alice', 'research'):
                self.request()
                raise ProviderError('PRIVATE_VALIDATION_CONTEXT')
        stored = self.store.get('alice', 'local-validation')
        self.assertEqual(stored['calls'][0]['status'], 'completed')
        self.assertEqual(stored['error_code'], 'validation_error')
        self.assertNotIn('PRIVATE_VALIDATION_CONTEXT', json.dumps(stored))

    def test_parallel_graph_failure_root_matches_actual_propagated_exception(self):
        from tests.test_insights import request_stage
        clinic_entered, tools_entered, clinic_failed = (threading.Event() for _ in range(3))
        failures = {name: HTTPError('https://api.openai.com/responses', code, 'PRIVATE_REASON', {}, io.BytesIO())
                    for name, code in [('insight_clinic_scout', 401), ('insight_tools_scout', 429)]}
        for failure in failures.values():
            self.addCleanup(failure.close)
        request = self.provider._request

        def ordered_request(name, *args, **kwargs):
            if name == 'insight_tools_scout':
                self.assertTrue(clinic_entered.wait(5))
            try:
                return request(name, *args, **kwargs)
            finally:
                if name == 'insight_clinic_scout':
                    clinic_failed.set()

        def http(request, timeout):
            name = request_stage(request)
            if name == 'insight_clinic_scout':
                clinic_entered.set()
                self.assertTrue(tools_entered.wait(5))
            else:
                tools_entered.set()
                self.assertTrue(clinic_failed.wait(5))
                # The first failure must reach the graph future before the
                # second independently failing request completes.
                threading.Event().wait(0.03)
            raise failures[name]

        with patch.object(self.provider, '_request', ordered_request), patch('brochure.provider.urlopen', http):
            with self.assertRaisesRegex(ProviderError, '인증 또는 권한'):
                with tracing.research_trace(self.store, 'parallel-failures', 'alice', 'research'):
                    self.provider.discover_insights('operations')
        stored = self.store.get('alice', 'parallel-failures')
        self.assertEqual([call['error_code'] for call in stored['calls']], ['http_auth', 'http_rate_limit'])
        self.assertEqual(stored['error_code'], 'http_auth')
        self.assertEqual(stored['error'], stored['calls'][0]['error'])

    def test_records_only_api_provided_web_actions(self):
        value = response()
        value['output'][:0] = [
            {'type': 'web_search_call', 'status': 'completed', 'action': {'type': 'search', 'queries': ['q1', 'q2']}},
            {'type': 'web_search_call', 'status': 'completed', 'action': {'type': 'open_page', 'url': 'https://example.org/a'}},
            {'type': 'web_search_call', 'status': 'completed', 'action': {'type': 'find_in_page', 'url': 'https://example.org/a', 'pattern': 'needle'}},
        ]
        with self.transport(value):
            with tracing.research_trace(self.store, 'tools', 'alice', 'briefing'):
                self.request(search=True)
        self.assertEqual(self.store.get('alice', 'tools')['calls'][0]['tools'], [
            {'type': 'search', 'query': 'q1', 'url': None},
            {'type': 'search', 'query': 'q2', 'url': None},
            {'type': 'open', 'query': None, 'url': 'https://example.org/a'},
            {'type': 'find', 'query': 'needle', 'url': 'https://example.org/a'},
        ])

    def test_parallel_runs_on_shared_provider_do_not_mix(self):
        barrier = threading.Barrier(2)
        def http(request, timeout):
            barrier.wait(timeout=5)
            return io.BytesIO(json.dumps(response()).encode())
        def work(owner):
            with tracing.research_trace(self.store, owner + '-run', owner, 'research'):
                self.request(owner + '-public-input')
        with patch('brochure.provider.urlopen', http), ThreadPoolExecutor(2) as pool:
            list(pool.map(work, ['alice', 'bob']))
        for owner, other in [('alice', 'bob'), ('bob', 'alice')]:
            stored = self.store.get(owner, owner + '-run')
            self.assertEqual(len(stored['calls']), 1)
            self.assertIn(owner + '-public-input', json.dumps(stored))
            self.assertNotIn(other + '-public-input', json.dumps(stored))

    def test_context_children_capture_and_plain_threads_do_not_inherit(self):
        def http(request, timeout):
            return io.BytesIO(json.dumps(response()).encode())
        with patch('brochure.provider.urlopen', http), ThreadPoolExecutor(2) as pool:
            with tracing.research_trace(self.store, 'children', 'alice', 'research'):
                pool.submit(contextvars.copy_context().run, self.request, 'child-public').result()
                pool.submit(self.request, 'OUTSIDE_CONTEXT').result()
        result = self.store.get('alice', 'children')
        self.assertEqual(len(result['calls']), 1)
        self.assertIn('child-public', json.dumps(result))
        self.assertNotIn('OUTSIDE_CONTEXT', json.dumps(result))

    def test_redaction_masks_nested_secrets_and_bounds_large_payloads(self):
        value = response('x' * 50000 + ' sk-test-private-secret-000000')
        with self.transport(value), self.assertRaises(ProviderError):
            with tracing.research_trace(self.store, 'bounded', 'alice', 'research'):
                self.request('Bearer TOPSECRET_TOKEN sk-test-private-secret-000000')
        call = self.store.get('alice', 'bounded')['calls'][0]
        encoded = json.dumps(call)
        self.assertNotIn('TOPSECRET_TOKEN', encoded)
        self.assertNotIn('sk-test-private-secret', encoded)
        self.assertTrue(call['truncated'])
        self.assertLess(len(encoded), 80000)

    def test_hashes_distinguish_full_requests_with_same_truncated_prefix(self):
        prefix = 'x' * 17000
        for suffix in ('first', 'second'):
            with self.transport(response()):
                with tracing.research_trace(self.store, suffix, 'alice', 'research'):
                    self.provider._request('insight_clinic_scout', None, prefix + suffix,
                                           {'text': prefix + suffix})
        first = self.store.get('alice', 'first')['calls'][0]
        second = self.store.get('alice', 'second')['calls'][0]
        self.assertTrue(first['truncated'])
        self.assertTrue(second['truncated'])
        self.assertEqual(first['request'], second['request'])
        self.assertNotEqual(first['instructions_hash'], second['instructions_hash'])
        self.assertNotEqual(first['input_hash'], second['input_hash'])

    def test_capture_budget_counts_numeric_arrays_and_object_keys(self):
        numeric = [[[0] * 256 for _ in range(256)] for _ in range(8)]
        wide = [{('key-' + str(index)).ljust(160, 'x'): index for index in range(256)}
                for _ in range(32)]
        for value in (numeric, wide, {'text': '한글' * 50000}):
            with self.subTest(kind=type(value).__name__):
                safe, limits = tracing._safe_capture(value)
                encoded = json.dumps(safe, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
                self.assertLessEqual(len(encoded), tracing.MAX_CAPTURE)
                self.assertTrue(limits['truncated'])
                self.assertTrue(limits['truncated_fields'])

    def test_trace_storage_failures_do_not_discard_successful_work(self):
        cases = [
            ('_start', lambda args, fields: True),
            ('_update', lambda args, fields: 'status' not in fields),
            ('_call_start', lambda args, fields: True),
            ('_call_update', lambda args, fields: args[2]['response'] is not None and args[2]['status'] == 'running'),
            ('_call_update', lambda args, fields: args[2]['status'] == 'completed'),
            ('_update', lambda args, fields: fields.get('status') == 'completed'),
            ('get', lambda args, fields: True),
        ]
        for index, (method, should_fail) in enumerate(cases):
            original = getattr(self.store, method)
            def fail_recording(*args, **fields):
                if should_fail(args, fields):
                    raise sqlite3.OperationalError('PRIVATE_STORAGE_FAILURE')
                return original(*args, **fields)
            with self.subTest(method=method, index=index), patch.object(self.store, method, fail_recording), self.transport(response()):
                with tracing.research_trace(self.store, 'storage-' + str(index), 'alice', 'research') as run:
                    result, _, _, _ = self.request()
                self.assertEqual(result, '공개 조사 결과')
                self.assertTrue(run.recording_failed)

    def test_trace_storage_failure_preserves_actual_provider_failure(self):
        failure = HTTPError('https://api.openai.com/responses', 401, 'SECRET_REASON', {},
                            io.BytesIO(b'SECRET_ERROR_BODY'))
        self.addCleanup(failure.close)
        with patch.object(self.store, '_call_update', side_effect=sqlite3.OperationalError('DB_FAILURE')), \
             patch('brochure.provider.urlopen', side_effect=failure):
            with self.assertRaisesRegex(ProviderError, '인증 또는 권한'):
                with tracing.research_trace(self.store, 'provider-failure', 'alice', 'research') as run:
                    self.request()
        self.assertTrue(run.recording_failed)

    def test_failed_response_root_reasoning_is_never_recorded(self):
        value = {'type': 'reasoning', 'summary': [{'text': 'ROOT_REASONING_SHOULD_BE_REMOVED'}]}
        with self.transport(value), self.assertRaises(ProviderError):
            with tracing.research_trace(self.store, 'root-reasoning', 'alice', 'research'):
                self.request()
        stored = self.store.get('alice', 'root-reasoning')
        self.assertEqual(stored['status'], 'failed')
        self.assertNotIn('ROOT_REASONING_SHOULD_BE_REMOVED', json.dumps(stored))

    def test_literal_local_provider_key_is_redacted_even_without_recognizable_prefix(self):
        os.environ.pop('OPENAI_API_KEY')
        secret = 'locally_configured_private_credential_0000'
        (self.root / '.env.local').write_text('OPENAI_API_KEY=' + secret + '\n')
        with self.transport(response('Provider echoed ' + secret)):
            with tracing.research_trace(self.store, 'local-secret', 'alice', 'research'):
                self.request('Do not expose ' + secret)
        stored = self.store.get('alice', 'local-secret')
        self.assertNotIn(secret, json.dumps(stored))
        self.assertTrue(stored['calls'][0]['redacted'])

    def test_unknown_usage_is_null_and_survives_reopening_database(self):
        value = response()
        value.pop('usage')
        with self.transport(value):
            with tracing.research_trace(self.store, 'unknown', 'alice', 'research'):
                self.request()
        reopened = tracing.TraceStore(self.store.path, workspace=self.root)
        result = reopened.get('alice', 'unknown')
        self.assertIsNone(result['calls'][0]['input_tokens'])
        self.assertIsNone(result['usage']['total_tokens'])
        self.assertEqual(result['usage']['requests'], 1)
        self.assertEqual(reopened.list_all()[0]['owner'], 'alice')
        self.assertEqual(reopened.get_for_operator('unknown')['id'], 'unknown')

    def test_langsmith_requires_explicit_enable_and_literal_valid_key(self):
        local = self.root / '.env.local'
        local.write_text('LANGSMITH_API_KEY=lsv2_test_private_credential_0000\n')
        self.assertFalse(tracing.langsmith_status(self.root)['enabled'])
        local.write_text('LANGSMITH_TRACING=true\nLANGSMITH_API_KEY=$(touch /tmp/NEVER_TRACE)\n')
        self.assertFalse(tracing.langsmith_status(self.root)['configured'])
        local.write_text('LANGSMITH_TRACING=true\nLANGSMITH_API_KEY=lsv2_test_private_credential_0000\n')
        status = tracing.langsmith_status(self.root)
        self.assertTrue(status['enabled'])
        self.assertTrue(status['configured'])
        self.assertNotIn('credential', json.dumps(status))

    def test_langsmith_agent_destination_requires_complete_unambiguous_configuration(self):
        with patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                    'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000',
                                    'LANGSMITH_AGENT_ID': 'clinic-research'}):
            self.assertFalse(tracing.langsmith_status(self.root)['configured'])
            os.environ['LANGSMITH_AGENT_ENVIRONMENT'] = 'development'
            status = tracing.langsmith_status(self.root)
            self.assertTrue(status['configured'])
            self.assertEqual(status['destination'], 'agent')
            self.assertEqual(status['agent_id'], 'clinic-research')
            os.environ['LANGSMITH_PROJECT'] = 'legacy-project'
            self.assertFalse(tracing.langsmith_status(self.root)['configured'])

    def test_malformed_response_shapes_retain_provider_error_and_trace(self):
        for index, value in enumerate([{'status': 'completed', 'output': None},
                                       {'status': 'completed', 'output': [{'type': []}]},
                                       {'status': 'completed', 'output': {'malformed': 'value'}}]):
            with self.subTest(value=value), self.transport(value), self.assertRaises(ProviderError):
                with tracing.research_trace(self.store, 'shape-' + str(index), 'alice', 'research'):
                    self.request()
            stored = self.store.get('alice', 'shape-' + str(index))
            self.assertEqual(stored['calls'][0]['status'], 'failed')
            self.assertIsNotNone(stored['calls'][0]['response'])

    def test_read_only_operator_access_never_creates_or_writes_database(self):
        absent = self.root / 'absent' / 'traces.sqlite3'
        reader = tracing.TraceStore(absent, read_only=True)
        self.assertEqual(reader.list_all(), [])
        self.assertIsNone(reader.get_for_operator('missing'))
        self.assertFalse(absent.parent.exists())
        with self.transport(response()):
            with tracing.research_trace(self.store, 'readable', 'alice', 'research'):
                self.request()
        before = self.store.path.read_bytes()
        reader = tracing.TraceStore(self.store.path, read_only=True)
        self.assertEqual(reader.get_for_operator('readable')['status'], 'completed')
        self.assertEqual(reader.list_all()[0]['owner'], 'alice')
        with self.assertRaises(sqlite3.OperationalError):
            reader.delete('alice', 'readable')
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_specific_interruption_preserves_completed_calls(self):
        snapshot = self.root / 'crashed.sqlite3'
        def snapshot_request(request, timeout):
            with closing(sqlite3.connect(self.store.path)) as source, closing(sqlite3.connect(snapshot)) as target:
                source.backup(target)
            return io.BytesIO(json.dumps(response()).encode())
        with tracing.research_trace(self.store, 'crashed', 'alice', 'research'):
            with self.transport(response()):
                self.request()
            with patch('brochure.provider.urlopen', snapshot_request):
                self.request()
        abandoned = tracing.TraceStore(snapshot)
        abandoned.interrupt('bob', 'crashed')
        self.assertEqual(abandoned.get('alice', 'crashed')['status'], 'running')
        abandoned.interrupt('alice', 'crashed')
        result = abandoned.get('alice', 'crashed')
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual([call['status'] for call in result['calls']], ['completed', 'interrupted'])
        self.assertIsNone(result['usage']['total_tokens'])
        self.assertEqual(result['calls'][0]['total_tokens'], 60)

    def test_call_limit_marks_omissions_instead_of_claiming_complete_usage(self):
        def http(request, timeout):
            return io.BytesIO(json.dumps(response()).encode())
        with patch.object(tracing, 'MAX_CALLS', 1), patch('brochure.provider.urlopen', http):
            with tracing.research_trace(self.store, 'capped', 'alice', 'research'):
                self.request()
                self.request()
        result = self.store.get('alice', 'capped')
        self.assertEqual(len(result['calls']), 1)
        self.assertEqual(result['dropped_calls'], 1)
        self.assertEqual(result['usage']['requests'], 2)
        self.assertIsNone(result['usage']['total_tokens'])

    def test_actual_langgraph_parallel_scouts_inherit_same_run(self):
        from tests.test_insights import InsightHTTPFixtures, scouts, selected
        fixture = InsightHTTPFixtures(*scouts(), selected())
        with patch('brochure.provider.urlopen', fixture):
            with tracing.research_trace(self.store, 'graph', 'alice', 'research'):
                self.provider.discover_insights('operations')
        result = self.store.get('alice', 'graph')
        self.assertEqual({call['name'] for call in result['calls']},
                         {'insight_clinic_scout', 'insight_tools_scout', 'insight_selection'})
        self.assertEqual(result['usage']['requests'], 3)

    def test_langsmith_failure_is_nonfatal_and_does_not_invent_cloud_link(self):
        with patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                    'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000'}), \
             patch('langsmith.client.Client.create_run', side_effect=RuntimeError('PRIVATE_CLOUD_FAILURE')), \
             patch('langsmith.client.Client.update_run', side_effect=RuntimeError('PRIVATE_CLOUD_FAILURE')), \
             self.transport(response()):
            with tracing.research_trace(self.store, 'cloud-failed', 'alice', 'research'):
                self.request()
        result = self.store.get('alice', 'cloud-failed')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['langsmith_status'], 'failed')
        self.assertIsNone(result['langsmith_url'])
        self.assertNotIn('PRIVATE_CLOUD_FAILURE', json.dumps(result))

    def test_langsmith_sanitized_tree_and_link_require_confirmed_server_run(self):
        created, updated = [], []
        def create(self, **kwargs):
            created.append(kwargs)
        def update(self, **kwargs):
            updated.append(kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000'}))
            stack.enter_context(patch('langsmith.client.Client.create_run', create))
            stack.enter_context(patch('langsmith.client.Client.update_run', update))
            requests, readers, project = stack.enter_context(cloud_read_transport())
            stack.enter_context(self.transport(response()))
            with tracing.research_trace(self.store, 'cloud-ok', 'alice', 'research'):
                self.request('sk-test-leaked-secret-000000')
        result = self.store.get('alice', 'cloud-ok')
        self.assertEqual(result['langsmith_status'], 'sent')
        self.assertEqual(result['langsmith_url'], 'https://smith.langchain.com/o/test/r/confirmed')
        self.assertEqual(len(created), 2)
        self.assertEqual(created[1]['parent_run_id'], created[0]['id'])
        llm_update = next(item for item in updated if item['run_type'] == 'llm')
        self.assertEqual(llm_update['extra']['metadata']['usage_metadata'],
                         {'input_tokens': 40, 'output_tokens': 20, 'total_tokens': 60})
        export = json.dumps(created + updated, default=str)
        self.assertNotIn('NEVER_STORE_REASONING', export)
        self.assertNotIn('sk-test-leaked-secret', export)
        self.assertNotIn('lsv2_test_private', export)
        project.assert_called_once_with(project_name='clinic-brief-research')
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].url.params.get_list('selects'),
                         ['ID', 'PROJECT_ID', 'TRACE_ID', 'START_TIME'])
        self.assertEqual(requests[0].url.params['project_id'], PROJECT_ID)
        self.assertEqual(requests[1].url.params['trace_id'], str(created[0]['id']))
        self.assertEqual(readers[0].max_retries, 0)
        self.assertEqual(readers[0].timeout, 2.0)
        self.assertTrue(readers[0].is_closed())

    def test_langsmith_agent_address_exports_manual_graph_calls_only(self):
        from tests.test_insights import InsightHTTPFixtures, scouts, selected
        created = []
        fixture = InsightHTTPFixtures(*scouts(), selected())
        def create(self, **kwargs):
            created.append(kwargs)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000',
                                'LANGSMITH_AGENT_ID': 'clinic-research', 'LANGSMITH_AGENT_ENVIRONMENT': 'local'}))
            stack.enter_context(patch('langsmith.client.Client.create_run', create))
            stack.enter_context(patch('langsmith.client.Client.update_run', return_value=None))
            requests, readers, project = stack.enter_context(cloud_read_transport())
            stack.enter_context(patch('brochure.provider.urlopen', fixture))
            with tracing.research_trace(self.store, 'cloud-agent', 'alice', 'research'):
                self.provider.discover_insights('operations')
        result = self.store.get('alice', 'cloud-agent')
        self.assertEqual(result['langsmith_status'], 'sent')
        self.assertEqual(len(created), 4)
        self.assertEqual(created[0]['address'], {'kind': 'AGENT', 'id': 'clinic-research', 'environment': 'LOCAL'})
        for child in created[1:]:
            self.assertEqual(child['parent_run_id'], created[0]['id'])
            self.assertEqual(child['address'], created[0]['address'])
        project.assert_not_called()
        self.assertEqual(requests[0].url.path, '/api/v1/sessions/resolutions')
        self.assertEqual(dict(requests[0].url.params),
                         {'kind': 'AGENT', 'id': 'clinic-research', 'environment': 'LOCAL'})
        self.assertEqual(requests[1].url.params['project_id'], PROJECT_ID)
        self.assertTrue(readers[0].is_closed())

    def test_langsmith_visibility_polling_retries_only_not_found_and_is_bounded(self):
        cases = [
            ('delayed', 404, 2, 'sent', 3, [0.25, 0.75]),
            ('absent', 404, 10, 'unverified', 4, [0.25, 0.75, 1.5]),
            ('auth', 401, 10, 'failed', 1, []),
            ('network', None, 10, 'failed', 1, []),
            ('rate-limit', 429, 10, 'failed', 1, []),
            ('server', 503, 10, 'failed', 1, []),
        ]
        for name, http_status, failures, expected_status, expected_reads, expected_waits in cases:
            reads, waits, writes = [], [], []
            def read(request):
                if request.url.path.endswith('/url'):
                    return None
                reads.append(request)
                if len(reads) <= failures:
                    if http_status is None:
                        raise httpx.ConnectError('PRIVATE_CLOUD_RESPONSE', request=request)
                    return httpx.Response(http_status, json={'detail': 'PRIVATE_CLOUD_RESPONSE'})
                return None
            def create(client, **kwargs):
                writes.append(('create', kwargs['id']))
            def update(client, **kwargs):
                writes.append(('update', kwargs['run_id']))
            with self.subTest(name=name), ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                    'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000'}))
                stack.enter_context(patch('langsmith.client.Client.create_run', create))
                stack.enter_context(patch('langsmith.client.Client.update_run', update))
                requests, readers, project = stack.enter_context(cloud_read_transport(read))
                stack.enter_context(patch('brochure.tracing.time.sleep', side_effect=waits.append))
                stack.enter_context(self.transport(response()))
                with tracing.research_trace(self.store, 'visibility-' + name, 'alice', 'research'):
                    self.request()
                stored = self.store.get('alice', 'visibility-' + name)
                self.assertEqual(stored['status'], 'completed')
                self.assertEqual(stored['langsmith_status'], expected_status)
                self.assertEqual(len(reads), expected_reads)
                self.assertEqual(waits, expected_waits)
                self.assertEqual(len(writes), 4)  # One create/update per root and model call.
                self.assertEqual(stored['usage']['requests'], 1)
                self.assertEqual(bool(stored['langsmith_url']), expected_status == 'sent')
                self.assertNotIn('PRIVATE_CLOUD_RESPONSE', json.dumps(stored))
                self.assertTrue(readers[0].is_closed())

    def test_langsmith_incomplete_or_mismatched_identity_never_exposes_link(self):
        for fields in ({}, {'project_id': PROJECT_ID},
                       {'project_id': 'wrong-project', 'trace_id': 'wrong-trace'}):
            def read(request):
                if not request.url.path.endswith('/url'):
                    return httpx.Response(200, json={'id': request.url.path.rsplit('/', 1)[-1], **fields})
                return None
            with self.subTest(fields=fields), ExitStack() as stack:
                stack.enter_context(patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                    'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000'}))
                stack.enter_context(patch('langsmith.client.Client.create_run'))
                stack.enter_context(patch('langsmith.client.Client.update_run'))
                requests, readers, project = stack.enter_context(cloud_read_transport(read))
                stack.enter_context(self.transport(response()))
                with tracing.research_trace(self.store, 'incomplete', 'alice', 'research'):
                    self.request()
                stored = self.store.get('alice', 'incomplete')
                self.assertEqual(stored['status'], 'completed')
                self.assertEqual(stored['langsmith_status'], 'unverified')
                self.assertIsNone(stored['langsmith_url'])
                self.assertEqual(len(requests), 1)
                self.assertTrue(readers[0].is_closed())

    def test_langsmith_read_verification_uses_configured_region(self):
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000',
                                'LANGSMITH_ENDPOINT': 'https://eu.api.smith.langchain.com'}))
            stack.enter_context(patch('langsmith.client.Client.create_run'))
            stack.enter_context(patch('langsmith.client.Client.update_run'))
            requests, readers, project = stack.enter_context(cloud_read_transport())
            stack.enter_context(self.transport(response()))
            with tracing.research_trace(self.store, 'region', 'alice', 'research'):
                self.request()
        self.assertEqual(self.store.get('alice', 'region')['langsmith_status'], 'sent')
        self.assertEqual({request.url.host for request in requests}, {'eu.api.smith.langchain.com'})

    def test_langsmith_unsupported_agent_resolution_preserves_local_result(self):
        def read(request):
            return httpx.Response(501, json={'detail': 'PRIVATE_CLOUD_RESPONSE'})
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'LANGSMITH_TRACING': 'true',
                                'LANGSMITH_API_KEY': 'lsv2_test_private_credential_0000',
                                'LANGSMITH_AGENT_ID': 'clinic-research', 'LANGSMITH_AGENT_ENVIRONMENT': 'local'}))
            stack.enter_context(patch('langsmith.client.Client.create_run'))
            stack.enter_context(patch('langsmith.client.Client.update_run'))
            requests, readers, project = stack.enter_context(cloud_read_transport(read))
            stack.enter_context(self.transport(response()))
            with tracing.research_trace(self.store, 'unsupported-agent', 'alice', 'research'):
                self.request()
        result = self.store.get('alice', 'unsupported-agent')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['langsmith_status'], 'failed')
        self.assertIsNone(result['langsmith_url'])
        self.assertEqual(len(requests), 1)
        self.assertTrue(readers[0].is_closed())
        project.assert_not_called()


if __name__ == '__main__':
    unittest.main()
