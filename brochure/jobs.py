"""Durable local jobs with no automatic retries.

Run exactly one JobRunner per database/server process. Construction interrupts
old queued/running jobs, so a second live runner is not a supported worker pool.
At most two workers and sixteen admitted jobs bound the in-memory queue. Work
must provide its own finite I/O timeouts; Python cannot terminate a running thread.
"""
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .provider import ProviderError
from .service import AppError


MAX_PENDING_JOBS = 16
MAX_PAYLOAD_BYTES = 32 * 1024
MAX_RESULT_BYTES = 512 * 1024
_ACTIVE = ('queued', 'running')
_INTERRUPTED = '서버가 재시작되어 작업이 중단되었습니다. 새 작업으로 다시 요청해 주세요.'


class JobError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _encoded(value, limit):
    try:
        if not isinstance(value, dict):
            raise ValueError('object required')
        result = json.dumps(value, ensure_ascii=False, sort_keys=True,
                            separators=(',', ':'), allow_nan=False)
        if len(result.encode('utf-8')) > limit:
            raise ValueError('too large')
        return result
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise JobError('작업 데이터를 확인해 주세요.') from None


def _date(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec='seconds')


def _public(row):
    return {'id': row['id'], 'kind': row['kind'], 'status': row['status'],
            'stage': row['stage'], 'error': row['error'],
            'result': json.loads(row['result']) if row['result'] is not None else None,
            'created_at': _date(row['created_at']), 'updated_at': _date(row['updated_at'])}


class JobRunner:
    def __init__(self, path: Path, max_workers=2, daily_limit=20):
        if type(max_workers) is not int or not 1 <= max_workers <= 2:
            raise ValueError('max_workers must be 1 or 2')
        if type(daily_limit) is not int or not 1 <= daily_limit <= 20:
            raise ValueError('daily_limit must be between 1 and 20')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.daily_limit = daily_limit
        self._lock = threading.RLock()
        self._closed = False
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
                    request_id TEXT NOT NULL, signature TEXT NOT NULL,
                    status TEXT NOT NULL, stage TEXT NOT NULL, error TEXT, result TEXT,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL,
                    UNIQUE(owner, kind, request_id));
                CREATE INDEX IF NOT EXISTS jobs_owner_date ON jobs(owner, created_at);
                CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
            ''')
            db.execute('''UPDATE jobs SET status='interrupted', stage='작업 중단',
                error=?, result=NULL, updated_at=? WHERE status IN ('queued', 'running')''',
                       (_INTERRUPTED, time.time()))
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='brochure-job')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def submit(self, owner: str, kind: str, request_id: str, payload: dict, work, *, before_submit=None):
        if (not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', owner)
                or not isinstance(kind, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', kind)
                or not isinstance(request_id, str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', request_id)
                or not callable(work) or (before_submit is not None and not callable(before_submit))):
            raise JobError('작업 요청을 확인해 주세요.')
        signature = hashlib.sha256(_encoded(payload, MAX_PAYLOAD_BYTES).encode('utf-8')).hexdigest()
        now, identifier = time.time(), uuid.uuid4().hex
        with self._lock:
            if self._closed:
                raise JobError('서버를 종료하고 있습니다. 잠시 후 다시 요청해 주세요.', 503)
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                existing = db.execute('''SELECT * FROM jobs
                    WHERE owner=? AND kind=? AND request_id=?''', (owner, kind, request_id)).fetchone()
                if existing:
                    if existing['signature'] != signature:
                        raise JobError('같은 요청 번호의 내용이 다릅니다. 새 작업으로 요청해 주세요.', 409)
                    if existing['deleted_at'] is not None:
                        raise JobError('삭제한 작업입니다. 새 작업으로 요청해 주세요.', 409)
                    return _public(existing)
                # Mutable preconditions apply only to new work. Keep this check and
                # admission under one lock/transaction so duplicate requests cannot
                # validate independently or consume quota after a rejected check.
                if before_submit is not None:
                    before_submit()
                if db.execute("SELECT 1 FROM jobs WHERE owner=? AND status IN ('queued', 'running')",
                              (owner,)).fetchone():
                    raise JobError('진행 중인 작업이 있습니다. 완료 후 다시 요청해 주세요.', 409)
                daily_count = db.execute('SELECT COUNT(*) FROM jobs WHERE owner=? AND created_at>?',
                                         (owner, now - 24 * 3600)).fetchone()[0]
                if daily_count >= self.daily_limit:
                    raise JobError('오늘의 작업 한도에 도달했습니다. 나중에 다시 요청해 주세요.', 429)
                pending = db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'running')").fetchone()[0]
                if pending >= MAX_PENDING_JOBS:
                    raise JobError('대기 중인 작업이 많습니다. 잠시 후 다시 요청해 주세요.', 429)
                db.execute('''INSERT INTO jobs
                    (id, owner, kind, request_id, signature, status, stage, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'queued', '작업 대기 중', ?, ?)''',
                           (identifier, owner, kind, request_id, signature, now, now))
                job = _public(db.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone())
            try:
                self._executor.submit(self._run, identifier, work)
            except RuntimeError:
                with self._connect() as db:
                    db.execute("UPDATE jobs SET status='interrupted', stage='작업 중단', error=?, updated_at=? WHERE id=?",
                               (_INTERRUPTED, time.time(), identifier))
                raise JobError('작업을 시작할 수 없습니다. 작업 기록을 확인해 주세요.', 503) from None
        return job

    def _run(self, identifier, work):
        with self._connect() as db:
            changed = db.execute("UPDATE jobs SET status='running', stage='작업 시작', updated_at=? WHERE id=? AND status='queued'",
                                 (time.time(), identifier)).rowcount
        if not changed:
            return

        def progress(stage):
            if (not isinstance(stage, str) or not stage.strip() or len(stage) > 160
                    or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in stage)):
                return
            try:
                stage.encode('utf-8')
            except UnicodeError:
                return
            with self._connect() as db:
                db.execute("UPDATE jobs SET stage=?, updated_at=? WHERE id=? AND status='running'",
                           (stage, time.time(), identifier))

        try:
            result = _encoded(work(progress), MAX_RESULT_BYTES)
        except Exception as error:
            # These application exception types contain fixed, user-safe messages.
            # Unknown exceptions may contain prompts, credentials or response bodies.
            message = (str(error) if type(error) in (ProviderError, AppError, JobError)
                       else '작업을 완료하지 못했습니다. 새 작업으로 다시 요청해 주세요.')
            with self._connect() as db:
                db.execute("""UPDATE jobs SET status='failed', stage='작업 실패',
                    error=?, result=NULL, updated_at=? WHERE id=? AND status='running'""",
                           (message, time.time(), identifier))
        else:
            with self._connect() as db:
                db.execute("""UPDATE jobs SET status='succeeded', stage='작업 완료',
                    error=NULL, result=?, updated_at=? WHERE id=? AND status='running'""",
                           (result, time.time(), identifier))

    def get(self, owner, id):
        with self._connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE owner=? AND id=? AND deleted_at IS NULL',
                             (owner, id)).fetchone()
        if row is None:
            raise JobError('작업을 찾을 수 없습니다.', 404)
        return _public(row)

    def list(self, owner):
        with self._connect() as db:
            rows = db.execute('''SELECT * FROM jobs WHERE owner=? AND deleted_at IS NULL
                ORDER BY created_at DESC, rowid DESC''', (owner,)).fetchall()
        return [_public(row) for row in rows]

    def active(self, owner):
        with self._connect() as db:
            return db.execute("SELECT 1 FROM jobs WHERE owner=? AND status IN ('queued', 'running')",
                              (owner,)).fetchone() is not None

    def run_if_idle(self, owner, operation):
        # Use the same order as submit/before_submit: admission lock, then service
        # lock/storage. No new job can enter between the idle check and cleanup.
        with self._lock:
            if self.active(owner):
                raise JobError('진행 중인 작업이 끝난 뒤 삭제해 주세요.', 409)
            return operation()

    def delete(self, owner, id):
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM jobs WHERE owner=? AND id=? AND deleted_at IS NULL',
                             (owner, id)).fetchone()
            if row is None:
                raise JobError('작업을 찾을 수 없습니다.', 404)
            if row['status'] in _ACTIVE:
                raise JobError('진행 중인 작업은 삭제할 수 없습니다.', 409)
            # Keep only the submission ledger; deletion never resets paid-work limits.
            db.execute('''UPDATE jobs SET result=NULL, error=NULL, stage='', deleted_at=?, updated_at=?
                WHERE owner=? AND id=?''', (time.time(), time.time(), owner, id))

    def shutdown(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            with self._connect() as db:
                db.execute("""UPDATE jobs SET status='interrupted', stage='작업 중단', error=?,
                    updated_at=? WHERE status='queued'""", (_INTERRUPTED, time.time()))
        self._executor.shutdown(wait=True, cancel_futures=True)
