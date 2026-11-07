"""Bounded public-research records, isolated by account and execution context.

Only explicitly scoped research is recorded. Transport headers, HTTP error bodies,
exception text and model reasoning never enter this store or the optional cloud
export. LangSmith uses its official run-tree API; urllib calls need manual spans.
"""
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit


MAX_CALLS = 32
MAX_TEXT = 16000
MAX_CAPTURE = 100000
_ACTIVE_TRACE = ContextVar('brochure_research_trace', default=None)
_LABELS = {
    'insight_clinic_scout': '의원 현장 조사', 'insight_tools_scout': '기술·기관 조사',
    'insight_answer_research': '선정 주제 근거 조사', 'insight_selection': '주제 선정',
    'insight_topics': '자료 작성', 'insight_edit': '문장 편집', 'insight_audit': '최종 검수',
    'research_report': '공개 자료 조사', 'source_read': '출처 원문 확인',
    'research_candidates': '주제 정리', 'candidate_audit': '근거 검수',
}
_ERRORS = {
    'http_auth': 'API 인증 또는 권한을 확인해 주세요.',
    'http_rate_limit': 'API 사용 한도에 도달했습니다.',
    'http_error': 'API 요청을 처리하지 못했습니다.',
    'connection_error': 'API 연결이 실패하거나 시간이 초과되었습니다.',
    'invalid_response': 'API 응답을 읽을 수 없습니다.',
    'response_too_large': 'API 응답이 허용 크기를 초과했습니다.',
    'validation_error': '응답이 자료 형식 또는 근거 검수를 통과하지 못했습니다.',
    'interrupted': '서버가 재시작되어 조사 작업이 중단되었습니다.',
    'internal_error': '조사 작업을 완료하지 못했습니다.',
}
_SECRET_FIELD = re.compile(r'(?:authorization|cookie|password|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|headers)', re.I)
_SECRET_VALUE = re.compile(r'\b(?:sk-[A-Za-z0-9_-]{8,}|lsv2_[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~+/=-]+)', re.I)
_JSON_SECRET = re.compile(r'("(?:api[_-]?key|password|secret|authorization|access[_-]?token)"\s*:\s*")[^"\n]*(")', re.I)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def _dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _hash(value):
    """SHA-256 of the complete request field's UTF-8 JSON, before redaction/limits.

    The digest compares actual provider inputs; the separately stored request is
    only a sanitized, possibly truncated view. No extra original text is stored.
    """
    return hashlib.sha256(_dump(value).encode('utf-8')).hexdigest()


def _safe_capture(value, secrets=()):
    """Bound the UTF-8 JSON bytes of every captured value, including containers."""
    state = {'left': MAX_CAPTURE, 'truncated': [], 'redacted': False}
    known_secrets = tuple(secrets) + tuple(v for k, v in os.environ.items()
                                          if _SECRET_FIELD.search(k) and len(v) >= 12)
    omitted = object()

    def truncate(path):
        if len(state['truncated']) < 32:
            state['truncated'].append(path[:512])

    def size(item):
        return len(_dump(item).encode('utf-8'))

    def reserve(count):
        if count > state['left']:
            return False
        state['left'] -= count
        return True

    def clean(item, path='$', depth=0):
        if isinstance(item, dict) and item.get('type') in ('reasoning', 'reasoning_text', 'reasoning_summary_text'):
            state['redacted'] = True
            return omitted
        if depth > 20:
            truncate(path)
            item = '[truncated]'
        if isinstance(item, str):
            original = item
            for secret in known_secrets:
                item = item.replace(secret, '[redacted]')
            item = _SECRET_VALUE.sub('[redacted]', item)
            item = _JSON_SECRET.sub(r'\1[redacted]\2', item)
            if item != original:
                state['redacted'] = True
            if len(item) <= MAX_TEXT and reserve(size(item)):
                return item
            truncate(path)
            suffix = '… [truncated]'
            low, high = 0, min(MAX_TEXT, len(item))
            if size(suffix) > state['left']:
                return '' if reserve(2) else omitted
            # UTF-8 multibyte characters and JSON escaping both consume space.
            while low < high:
                middle = (low + high + 1) // 2
                if size(item[:middle] + suffix) <= state['left']:
                    low = middle
                else:
                    high = middle - 1
            result = item[:low] + suffix
            reserve(size(result))
            return result
        if isinstance(item, dict):
            if not reserve(2):  # Opening/closing braces are reserved together.
                truncate(path)
                return omitted
            result = {}
            for index, (key, entry) in enumerate(item.items()):
                if index >= 256:
                    truncate(path)
                    break
                key = str(key)
                if len(key) > 160:
                    truncate(path)
                    key = key[:160]
                if key in {'reasoning', 'reasoning_summary', 'encrypted_content'}:
                    state['redacted'] = True
                    continue
                if _SECRET_FIELD.search(key):
                    entry = '[redacted]'
                    state['redacted'] = True
                overhead = size(key) + 1 + bool(result)  # Key, colon, comma.
                if not reserve(overhead):
                    truncate(path)
                    break
                child = clean(entry, path + '.' + key, depth + 1)
                if child is omitted:
                    state['left'] += overhead
                else:
                    result[key] = child
            return result
        if isinstance(item, (list, tuple)):
            if not reserve(2):
                truncate(path)
                return omitted
            result = []
            for index, entry in enumerate(item):
                if index >= 256:
                    truncate(path)
                    break
                separator = int(bool(result))
                if not reserve(separator):
                    truncate(path)
                    break
                child = clean(entry, path + '[' + str(index) + ']', depth + 1)
                if child is omitted:
                    state['left'] += separator
                else:
                    result.append(child)
            return result
        if type(item) is float:
            item = item if abs(item) < float('inf') else None
        elif item is not None and type(item) not in (bool, int):
            item = '[unsupported value]'
        if reserve(size(item)):
            return item
        truncate(path)
        return omitted

    safe = clean(value)
    if safe is omitted:
        safe = None
    return safe, {'truncated': bool(state['truncated']),
                  'truncated_fields': state['truncated'], 'redacted': state['redacted']}


def _public_error(error):
    # Never persist exception strings: even provider wrappers can carry inputs.
    code = getattr(error, '_research_trace_error_code', None)
    if isinstance(code, str) and code in _ERRORS:
        return code
    if error.__class__.__name__ in {'ProviderError', 'AppError'}:
        return 'validation_error'
    return 'internal_error'


def _tokens(response):
    usage = response.get('usage', {}) if isinstance(response, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    return {key: value if type(value := usage.get(key)) is int and 0 <= value < 100_000_000 else None
            for key in ('input_tokens', 'output_tokens', 'total_tokens')}


def _tools(response):
    result = []
    output = response.get('output') if isinstance(response, dict) else None
    for item in output if isinstance(output, list) else []:
        if not isinstance(item, dict) or item.get('type') != 'web_search_call':
            continue
        action = item.get('action')
        if not isinstance(action, dict):
            continue
        kind = action.get('type')
        if kind == 'search':
            queries = action.get('queries', [action.get('query')])
            if not isinstance(queries, list):
                queries = [queries]
            for query in queries:
                result.append({'type': 'search', 'query': query if isinstance(query, str) else None, 'url': None})
        elif kind in ('open_page', 'find_in_page'):
            result.append({'type': 'open' if kind == 'open_page' else 'find',
                           'query': action.get('pattern') if kind == 'find_in_page' else None,
                           'url': action.get('url')})
        if len(result) >= 256:
            break
    return result[:256]


class TraceStore:
    def __init__(self, path, *, workspace=None, read_only=False):
        self.path = Path(path)
        self.workspace = Path(workspace) if workspace is not None else self.path.parent.parent
        self.read_only = read_only
        if read_only:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS research_traces (
                    owner TEXT NOT NULL, id TEXT NOT NULL, started_at TEXT NOT NULL,
                    document TEXT NOT NULL, PRIMARY KEY(owner,id));
                CREATE INDEX IF NOT EXISTS research_traces_date ON research_traces(started_at);
                CREATE TABLE IF NOT EXISTS research_trace_calls (
                    owner TEXT NOT NULL, run_id TEXT NOT NULL, id TEXT NOT NULL,
                    started_at TEXT NOT NULL, document TEXT NOT NULL,
                    PRIMARY KEY(owner,run_id,id),
                    FOREIGN KEY(owner,run_id) REFERENCES research_traces(owner,id) ON DELETE CASCADE);
            ''')

    @contextmanager
    def _connect(self):
        if self.read_only:
            db = sqlite3.connect('file:' + quote(str(self.path.resolve())) + '?mode=ro', uri=True, timeout=10)
        else:
            db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        if not self.read_only:
            db.execute('PRAGMA secure_delete=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, owner, identifier):
        if self.read_only and not self.path.exists():
            return None
        with self._connect() as db:
            row = db.execute('SELECT document FROM research_traces WHERE owner=? AND id=?', (owner, identifier)).fetchone()
            if not row:
                return None
            result = json.loads(row['document'])
            rows = db.execute('''SELECT document FROM research_trace_calls WHERE owner=? AND run_id=?
                                 ORDER BY started_at,id''', (owner, identifier)).fetchall()
        result['calls'] = [json.loads(row['document']) for row in rows]
        result['usage'] = {'requests': len(rows) + result.get('dropped_calls', 0)}
        for key in ('input_tokens', 'output_tokens', 'total_tokens'):
            values = [call[key] for call in result['calls']]
            result['usage'][key] = (sum(values) if all(value is not None for value in values)
                                    and not result.get('dropped_calls') else None)
        return result

    def list(self, owner, limit=20):
        return self._list(owner, limit)

    def list_all(self, limit=20):
        """Local-operator interface. Never expose this through account HTTP routes."""
        return self._list(None, limit)

    def _list(self, owner, limit):
        limit = max(1, min(int(limit), 100))
        if self.read_only and not self.path.exists():
            return []
        with self._connect() as db:
            rows = db.execute('SELECT owner,id FROM research_traces ' +
                              ('WHERE owner=? ' if owner is not None else '') +
                              'ORDER BY started_at DESC,id DESC LIMIT ?',
                              (owner, limit) if owner is not None else (limit,)).fetchall()
        result = []
        for row in rows:
            record = self.get(row['owner'], row['id'])
            if record is not None:
                record['call_count'] = len(record.pop('calls'))
                if owner is None:
                    record['owner'] = row['owner']
                result.append(record)
        return result

    def get_for_operator(self, identifier):
        if self.read_only and not self.path.exists():
            return None
        with self._connect() as db:
            row = db.execute('SELECT owner FROM research_traces WHERE id=? LIMIT 1', (identifier,)).fetchone()
        return self.get(row['owner'], identifier) if row else None

    def delete(self, owner, identifier):
        with self._connect() as db:
            return bool(db.execute('DELETE FROM research_traces WHERE owner=? AND id=?', (owner, identifier)).rowcount)

    def _start(self, owner, identifier, kind):
        doc = {'id': identifier, 'kind': kind, 'status': 'running', 'started_at': _now(),
               'finished_at': None, 'duration_ms': None, 'error': None, 'error_code': None,
               'langsmith_url': None, 'langsmith_status': 'disabled', 'dropped_calls': 0}
        with self._connect() as db:
            db.execute('INSERT INTO research_traces VALUES(?,?,?,?)',
                       (owner, identifier, doc['started_at'], _dump(doc)))

    def _update(self, owner, identifier, **fields):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document FROM research_traces WHERE owner=? AND id=?', (owner, identifier)).fetchone()
            if row:
                doc = json.loads(row['document'])
                doc.update(fields)
                db.execute('UPDATE research_traces SET document=? WHERE owner=? AND id=?', (_dump(doc), owner, identifier))

    def _call_start(self, owner, run_id, document):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document FROM research_traces WHERE owner=? AND id=?', (owner, run_id)).fetchone()
            if not row:
                return False
            count = db.execute('SELECT COUNT(*) FROM research_trace_calls WHERE owner=? AND run_id=?', (owner, run_id)).fetchone()[0]
            if count >= MAX_CALLS:
                run = json.loads(row['document'])
                run['dropped_calls'] += 1
                db.execute('UPDATE research_traces SET document=? WHERE owner=? AND id=?', (_dump(run), owner, run_id))
                return False
            db.execute('INSERT INTO research_trace_calls VALUES(?,?,?,?,?)',
                       (owner, run_id, document['id'], document['started_at'], _dump(document)))
            return True

    def _call_update(self, owner, run_id, document):
        with self._connect() as db:
            db.execute('UPDATE research_trace_calls SET document=? WHERE owner=? AND run_id=? AND id=?',
                       (_dump(document), owner, run_id, document['id']))

    def interrupt(self, owner, identifier):
        """Interrupt only a job the caller has already established is abandoned."""
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT document FROM research_traces WHERE owner=? AND id=?', (owner, identifier)).fetchone()
            if not row:
                return
            doc = json.loads(row['document'])
            if doc['status'] != 'running':
                return
            now = _now()
            doc.update(status='interrupted', finished_at=now, error=_ERRORS['interrupted'], error_code='interrupted')
            doc['duration_ms'] = max(0, round((datetime.fromisoformat(now) - datetime.fromisoformat(doc['started_at'])).total_seconds() * 1000))
            db.execute('UPDATE research_traces SET document=? WHERE owner=? AND id=?', (_dump(doc), owner, identifier))
            calls = db.execute('SELECT id,document FROM research_trace_calls WHERE owner=? AND run_id=?', (owner, identifier)).fetchall()
            for row in calls:
                call = json.loads(row['document'])
                if call['status'] == 'running':
                    call.update(status='interrupted', finished_at=now, error=_ERRORS['interrupted'], error_code='interrupted')
                    call['duration_ms'] = max(0, round((datetime.fromisoformat(now) - datetime.fromisoformat(call['started_at'])).total_seconds() * 1000))
                    db.execute('UPDATE research_trace_calls SET document=? WHERE owner=? AND run_id=? AND id=?',
                               (_dump(call), owner, identifier, row['id']))


def _langsmith_config(workspace=None):
    values = {}
    names = {'LANGSMITH_API_KEY', 'LANGSMITH_TRACING', 'LANGSMITH_PROJECT', 'LANGSMITH_ENDPOINT',
             'LANGSMITH_AGENT_ID', 'LANGSMITH_AGENT_ENVIRONMENT', 'LANGCHAIN_PROJECT', 'LANGCHAIN_SESSION'}
    if workspace is not None:
        try:
            with (Path(workspace) / '.env.local').open(encoding='utf-8') as file:
                contents = file.read(16385)
            if len(contents) <= 16384:
                for line in contents.splitlines():
                    match = re.fullmatch(r'\s*(?:export\s+)?([A-Z_]+)\s*=\s*(.*?)\s*', line)
                    if match and match[1] in names:
                        value = match[2]
                        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                            value = value[1:-1]
                        values[match[1]] = value
        except (OSError, UnicodeError):
            pass
    values.update({key: os.environ[key] for key in names if key in os.environ})
    key = values.get('LANGSMITH_API_KEY', '').strip()
    key = key if re.fullmatch(r'[A-Za-z0-9_-]{20,512}', key) else ''
    project = values.get('LANGSMITH_PROJECT', 'clinic-brief-research').strip()
    if not re.fullmatch(r'[A-Za-z0-9가-힣_. -]{1,100}', project):
        project = 'clinic-brief-research'
    endpoint = values.get('LANGSMITH_ENDPOINT', 'https://api.smith.langchain.com').strip()
    try:
        url = urlsplit(endpoint)
        valid = url.scheme == 'https' and bool(url.hostname) and not (url.username or url.password or url.query or url.fragment)
    except ValueError:
        valid = False
    enabled = values.get('LANGSMITH_TRACING', '').lower() in {'true', '1', 'yes'}
    address = None
    destination = 'project'
    destination_valid = True
    if values.get('LANGSMITH_AGENT_ID') or values.get('LANGSMITH_AGENT_ENVIRONMENT'):
        destination = 'agent'
        try:
            from langsmith import agent_address
            address = agent_address(values.get('LANGSMITH_AGENT_ID', ''),
                                    values.get('LANGSMITH_AGENT_ENVIRONMENT', ''))
        except Exception:
            destination_valid = False
        if any(values.get(name) for name in ('LANGSMITH_PROJECT', 'LANGCHAIN_PROJECT', 'LANGCHAIN_SESSION')):
            destination_valid = False
        project = None
    return {'key': key, 'enabled': enabled, 'configured': bool(key) and valid and destination_valid,
            'endpoint': endpoint if valid else None, 'project': project,
            'address': address, 'destination': destination}


def langsmith_status(workspace=None):
    """Configuration only. A configured key is not evidence of successful upload."""
    config = _langsmith_config(workspace)
    address = config['address'] or {}
    return {'enabled': config['enabled'], 'configured': config['configured'], 'project': config['project'],
            'destination': config['destination'], 'agent_id': address.get('id'),
            'environment': address.get('environment'),
            'status': ('disabled' if not config['enabled'] else 'configured' if config['configured'] else 'not_configured')}


def _langsmith_client(config):
    from langsmith import Client
    from urllib3.util.retry import Retry
    return Client(api_url=config['endpoint'], api_key=config['key'], auto_batch_tracing=False,
                  retry_config=Retry(total=0), timeout_ms=(2000, 2000),
                  tracing_sampling_rate=1.0, omit_traced_runtime_info=True,
                  hide_inputs=lambda value: _safe_capture(value)[0],
                  hide_outputs=lambda value: _safe_capture(value)[0],
                  hide_metadata=lambda value: _safe_capture(value)[0])


class _CloudTrace:
    def __init__(self, store, run_id, owner, kind):
        self.store, self.run_id, self.owner = store, run_id, owner
        self.client = self.tree = self.scope = self.context = None
        self.failed = False
        self.lock = threading.Lock()
        config = self.config = _langsmith_config(store.workspace)
        self.status = langsmith_status(store.workspace)['status']
        try:
            from langsmith import trace, tracing_context
            # LangChain's automatic callback tracer does not treat "local" as
            # disabled. Disable it outright; export only explicit safe RunTrees.
            active = config['enabled'] and config['configured']
            self.context = tracing_context(enabled=False, parent=False)
            self.context.__enter__()
            if not active:
                return
            self.status = 'pending'
            self.client = _langsmith_client(config)
            destination = ({'address': config['address']} if config['destination'] == 'agent'
                           else {'project_name': config['project']})
            self.scope = trace('clinic-public-' + kind, run_type='chain', inputs={'kind': kind},
                               client=self.client, parent='ignore', **destination)
            self.tree = self.scope.__enter__()
            self.tree.post()
        except Exception:
            self.failed = True
            self.status = 'failed'

    @contextmanager
    def call(self, document):
        tree = None
        try:
            if self.tree is not None and not self.failed:
                tree = self.tree.create_child(document['name'], run_type='llm', inputs=document['request'],
                              extra={'metadata': {'ls_provider': 'openai', 'ls_model_name': document['model'],
                                        'instructions_hash': document['instructions_hash'], 'input_hash': document['input_hash']}})
                tree.post()
        except Exception:
            with self.lock:
                self.failed = True
        try:
            yield
        finally:
            try:
                if tree is not None:
                    usage = {key: document[key] for key in ('input_tokens', 'output_tokens', 'total_tokens')
                             if document[key] is not None}
                    if usage:
                        tree.set(usage_metadata=usage)
                    tree.end(outputs={'response': document['response'], 'tools': document['tools'],
                                      'usage': {key: document[key] for key in ('input_tokens', 'output_tokens', 'total_tokens')},
                                      'truncated': document['truncated']}, error=document['error'])
                    tree.patch()
            except Exception:
                with self.lock:
                    self.failed = True

    def finish(self, error, usage):
        url = None
        try:
            if self.tree is not None:
                from langsmith import NotFoundError
                from .langsmith_reads import create_reader, resolve_project_id
                self.tree.end(outputs={'usage': usage}, error=error)
                self.tree.patch()
                # Non-batched post/patch report errors, but only a server read
                # establishes that a real run exists before exposing its URL.
                # Newly ingested runs can briefly be invisible. Retry only this
                # read on NotFound, with at most 2.5 seconds of waiting; writes
                # and model requests are never repeated here.
                with create_reader(self.config) as reader:
                    project_id = resolve_project_id(self.config, reader, self.client)
                    saved = None
                    for delay in (0, 0.25, 0.75, 1.5):
                        if delay:
                            time.sleep(delay)
                        try:
                            saved = reader.runs.retrieve_v2(
                                str(self.tree.id), project_id=project_id,
                                selects=['ID', 'PROJECT_ID', 'TRACE_ID', 'START_TIME'],
                                start_time=self.tree.start_time)
                            break
                        except NotFoundError:
                            continue
                    if (saved is not None and str(saved.id) == str(self.tree.id)
                            and str(saved.project_id) == project_id
                            and str(saved.trace_id) == str(self.tree.trace_id)):
                        start_time = saved.start_time or self.tree.start_time
                        candidate = reader.runs.get_url(
                            str(saved.id), project_id=str(saved.project_id),
                            trace_id=str(saved.trace_id),
                            start_time=start_time.isoformat()).url
                        if isinstance(candidate, str) and candidate.startswith('https://'):
                            url = candidate
                        self.status = 'failed' if self.failed else 'sent'
                    else:
                        self.status = 'failed' if self.failed else 'unverified'
        except Exception:
            self.status = 'failed'
        finally:
            for scope in (self.scope, self.context):
                if scope is not None:
                    try:
                        scope.__exit__(None, None, None)
                    except Exception:
                        self.status = 'failed'
        return self.status, url


class _Run:
    def __init__(self, store, run_id, owner, kind):
        self.store, self.id, self.owner = store, run_id, owner
        # Public integration flag: inspect after the context exits to report a
        # missing/partial record without discarding successfully generated work.
        self.recording_failed = False
        self.cloud = _CloudTrace(store, run_id, owner, kind)

    def record(self, operation, *args, **fields):
        """Guard only persistence, never the user's work or provider exceptions."""
        try:
            return operation(*args, **fields)
        except (sqlite3.Error, OSError):
            self.recording_failed = True
            return None


@contextmanager
def research_trace(store, run_id, owner, kind):
    if kind not in {'research', 'briefing'}:
        raise ValueError('Only public research and briefing may be traced')
    started = time.monotonic()
    run = _Run(store, run_id, owner, kind)
    run.record(store._start, owner, run_id, kind)
    run.record(store._update, owner, run_id, langsmith_status=run.cloud.status)
    token = _ACTIVE_TRACE.set(run)
    error_code = None
    try:
        yield run
    except BaseException as error:
        error_code = _public_error(error)
        raise
    finally:
        _ACTIVE_TRACE.reset(token)
        record = run.record(store.get, owner, run_id)
        error = _ERRORS.get(error_code)
        run.record(store._update, owner, run_id, status='failed' if error_code else 'completed',
                   finished_at=_now(), duration_ms=round((time.monotonic() - started) * 1000),
                   error=error, error_code=error_code)
        status, url = run.cloud.finish(error, record['usage'] if record else {})
        run.record(store._update, owner, run_id, langsmith_status=status, langsmith_url=url)


class _Call:
    def __init__(self, run, name, payload, secrets=()):
        self.run = run
        self.secrets = secrets
        self.started = time.monotonic()
        request, limits = _safe_capture(payload, secrets)
        self.document = {'id': uuid.uuid4().hex, 'name': name, 'label': _LABELS.get(name, name),
                         'status': 'running', 'started_at': _now(), 'finished_at': None,
                         'duration_ms': None, 'model': request.get('model'),
                         'input_tokens': None, 'output_tokens': None, 'total_tokens': None,
                         'error': None, 'error_code': None, 'tools': [], 'request': request,
                         'response': None, 'response_id': None,
                         'instructions_hash': _hash(payload.get('instructions')),
                         'input_hash': _hash(payload.get('input')), **limits}
        self.saved = run.record(run.store._call_start, run.owner, run.id, self.document)

    def received(self, raw):
        try:
            response = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            # Unparsed bytes may include reasoning or credentials. Record their
            # presence/size, never an unsafe body excerpt.
            self.document.update(response={'unparsed': True, 'bytes': len(raw)}, truncated=True)
            self.document['truncated_fields'].append('response: invalid JSON omitted')
        else:
            safe, limits = _safe_capture(response, self.secrets)
            self.document.update(response=safe, tools=_tools(safe), **_tokens(response))
            self.document['response_id'] = safe.get('id') if isinstance(safe, dict) else None
            self.document['truncated'] |= limits['truncated']
            self.document['redacted'] |= limits['redacted']
            self.document['truncated_fields'].extend(limits['truncated_fields'])
        self._save()

    def failure(self, code):
        self.document['error_code'] = code if code in _ERRORS else 'internal_error'

    def _save(self):
        if self.saved:
            self.run.record(self.run.store._call_update, self.run.owner, self.run.id, self.document)

    def finish(self, error=None):
        code = (self.document['error_code'] or _public_error(error)) if error else None
        self.document.update(status='failed' if error else 'completed', finished_at=_now(),
                             duration_ms=round((time.monotonic() - self.started) * 1000),
                             error_code=code, error=_ERRORS.get(code))
        self._save()


class _NullCall:
    def received(self, raw):
        pass

    def failure(self, code):
        pass


@contextmanager
def request_trace(name, payload, *, secrets=()):
    run = _ACTIVE_TRACE.get()
    if run is None or name not in _LABELS:
        yield _NullCall()
        return
    call = _Call(run, name, payload, secrets)
    with run.cloud.call(call.document) if call.saved else nullcontext():
        try:
            yield call
        except BaseException as error:
            call.finish(error)
            # Parallel requests may fail independently. Carry this request's
            # safe code on the exact exception the graph propagates, rather
            # than inferring the root cause from call timing or row order.
            code = call.document['error_code']
            if code in _ERRORS:
                try:
                    error._research_trace_error_code = code
                except (AttributeError, TypeError):
                    pass
            raise
        else:
            call.finish()
