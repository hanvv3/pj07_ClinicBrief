"""Shared public-source feed with bounded collection and an in-process KST schedule.

The application owns the shared JobRunner lifecycle. This service never retries
provider work, starts no thread until start(), and exposes no internal job owner.
"""
import copy
import hashlib
import ipaddress
import json
import re
import sqlite3
import threading
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from .jobs import JobError
from .insight_store import build_history, project_insight_fields, public_selection_report
from .provider import ProviderError
from .provider_schema import COVERAGE_AREAS


KST = ZoneInfo('Asia/Seoul')
_OWNER = '__briefing__'
_DAILY_LIMIT = 2
_INVALID = '원문 확인을 마친 공개 자료만 브리핑에 저장할 수 있습니다. 다시 조사해 주세요.'
_TRACKING = {'fbclid', 'gclid', 'dclid', 'msclkid', 'mc_cid', 'mc_eid', 'ref_src', 'ref_url'}
_TOPIC_TEXT = {'title': 300, 'summary': 2000, 'director_value': 2000, 'takeaway': 1600,
               'evidence_notice': 4000, 'coverage_area': 100, 'why_now': 400}


def _text(value, maximum):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum
            or any((ord(char) < 32 and char not in '\n\r\t') or 127 <= ord(char) <= 159
                   or 0xD800 <= ord(char) <= 0xDFFF for char in value)):
        raise ProviderError(_INVALID)
    return value.strip()


def _canonical_url(value):
    try:
        parsed = urlsplit(_text(value, 4096))
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or not host or '.' not in host or parsed.username
                or parsed.password or parsed.port not in (None, 443)
                or host.endswith(('.localhost', '.local', '.internal'))):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError()
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True,
                                                        max_num_fields=100)
                 if not key.lower().startswith('utm_') and key.lower() not in _TRACKING]
        return urlunsplit(('https', host.lower(), parsed.path or '/', urlencode(sorted(query)), ''))
    except (ValueError, TypeError, AttributeError):
        raise ProviderError(_INVALID) from None


def _source_date(source, today):
    dates = []
    for key in ('published_at', 'updated_at'):
        value = source.get(key)
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            continue
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            continue
        if parsed <= today:
            dates.append(parsed)
    return max(dates) if dates else None


def _freshness(topic, today):
    source_date = _source_date(topic['sources'][0], today)
    if source_date is None:
        return {'kind': 'undated', 'date': None, 'label': '발행·수정일 미상'}
    recent = source_date >= today - timedelta(days=13)
    return {'kind': 'recent' if recent else 'older', 'date': source_date.isoformat(),
            'label': '최근 14일 자료' if recent else '이전 자료'}


def _public_topic(topic, today):
    if not isinstance(topic, dict):
        raise ProviderError(_INVALID)
    public = {key: _text(topic.get(key), maximum) for key, maximum in _TOPIC_TEXT.items()}
    if public['coverage_area'] not in COVERAGE_AREAS:
        raise ProviderError(_INVALID)
    for key, default in [('category', '일일 브리핑'), ('research_date', today.isoformat()),
                         ('evidence_status', 'needs_review')]:
        public[key] = _text(topic.get(key, default), 100)
    minutes = topic.get('reading_minutes')
    if type(minutes) is not int or not 1 <= minutes <= 10:
        raise ProviderError(_INVALID)
    public['reading_minutes'] = minutes
    sources, claims = topic.get('sources'), topic.get('claims')
    if (not isinstance(sources, list) or not 1 <= len(sources) <= 5
            or not isinstance(claims, list) or not 1 <= len(claims) <= 8):
        raise ProviderError(_INVALID)
    public['sources'], identifiers = [], set()
    for source in sources:
        if not isinstance(source, dict) or source.get('verification') != 'body_access_and_cited':
            raise ProviderError(_INVALID)
        clean = {key: _text(source.get(key), maximum) for key, maximum in
                 [('id', 80), ('title', 2000), ('publisher', 2000), ('url', 4096), ('context', 4000)]}
        _canonical_url(clean['url'])
        if clean['id'] in identifiers:
            raise ProviderError(_INVALID)
        identifiers.add(clean['id'])
        clean['verification'] = 'body_access_and_cited'
        for key in ('published_at', 'updated_at', 'checked_at'):
            value = source.get(key)
            clean[key] = _text(value, 32) if value is not None else None
        public['sources'].append(clean)
    public['claims'], claim_ids = [], set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise ProviderError(_INVALID)
        identifier, text = _text(claim.get('id'), 80), _text(claim.get('text'), 2000)
        refs = claim.get('source_ids')
        if (identifier in claim_ids or not isinstance(refs, list) or not 1 <= len(refs) <= 5
                or any(not isinstance(ref, str) or ref not in identifiers for ref in refs)
                or len(set(refs)) != len(refs)):
            raise ProviderError(_INVALID)
        claim_ids.add(identifier)
        public['claims'].append({'id': identifier, 'text': text, 'source_ids': list(refs)})
    primary = public['sources'][0]
    if not any(primary['id'] in claim['source_ids'] for claim in public['claims']):
        raise ProviderError(_INVALID)
    source_date = _source_date(primary, today)
    identity = [_canonical_url(primary['url']), source_date.isoformat() if source_date else None]
    try:
        public.update(project_insight_fields(topic))
    except ValueError:
        raise ProviderError(_INVALID) from None
    if 'selection' in public:
        selection = public['selection']
        identity = ['insight-v1', selection['problem_key'], *identity]
        if selection['novelty'] == 'update':
            change = ' '.join(unicodedata.normalize('NFKC', selection['change']).casefold().split())
            basis = set()
            for source in public['sources']:
                dated = _source_date(source, today)
                basis.add((_canonical_url(source['url']), dated.isoformat() if dated else ''))
            # A version stays separate from its predecessor even when the core page
            # has not changed; transient source IDs/order and tracking URLs do not matter.
            identity.extend(['update', selection['previous_topic_id'], change, sorted(basis)])
    # The original URL/date identity remains unchanged for legacy stored topics.
    fingerprint = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()
    public['id'] = 'feed-' + fingerprint[:32]
    return public


def _usage(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ('requests', 'input_tokens', 'output_tokens', 'total_tokens')
            if type(value.get(key)) is int and 0 <= value[key] < 100_000_000}


class BriefingService:
    def __init__(self, path: Path, provider, jobs, *, enabled=True, clock=None, insights=None):
        self.path, self.provider, self.jobs = Path(path), provider, jobs
        self.insights = insights
        self.enabled = bool(enabled)
        self._clock = clock or (lambda: datetime.now(KST))
        self._stop = threading.Event()
        self._thread = None
        self._lifecycle = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS feed_items (
                    id TEXT PRIMARY KEY, document TEXT NOT NULL, collected_at REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS feed_collected ON feed_items(collected_at);
                CREATE TABLE IF NOT EXISTS feed_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scheduled_days (day TEXT PRIMARY KEY, attempted_at REAL NOT NULL);
            ''')

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

    def _now(self, value=None):
        value = self._clock() if value is None else value
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('clock must return a timezone-aware datetime')
        return value.astimezone(KST)

    def _ledger(self):
        return [job for job in self.jobs.list(_OWNER) if job['kind'] == 'briefing']

    def _remaining(self, now, ledger):
        cutoff = now - timedelta(days=1)
        used = sum(datetime.fromisoformat(job['created_at']) > cutoff for job in ledger)
        return max(0, _DAILY_LIMIT - used)

    def _items(self, now):
        with self._connect() as db:
            db.execute('DELETE FROM feed_items WHERE collected_at < ?',
                       ((now - timedelta(days=30)).timestamp(),))
            rows = db.execute('SELECT * FROM feed_items ORDER BY collected_at DESC, rowid DESC LIMIT 90').fetchall()
        result = []
        for row in rows:
            topic = json.loads(row['document'])
            topic['collected_at'] = datetime.fromtimestamp(row['collected_at'], KST).isoformat(timespec='seconds')
            topic['freshness'] = _freshness(topic, now.date())
            result.append(topic)
        return result

    def snapshot(self):
        now = self._now()
        configured = bool(self.provider.configured)
        ledger = self._ledger()
        next_run = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        with self._connect() as db:
            row = db.execute("SELECT value FROM feed_state WHERE key='last_success_at'").fetchone()
        return {'items': self._items(now), 'status': {
            'auto_enabled': self.enabled, 'schedule_hour': 9, 'timezone': 'Asia/Seoul',
            'next_run_at': next_run.isoformat(timespec='seconds') if self.enabled and configured else None,
            'last_success_at': row['value'] if row else None,
            'last_attempt': ledger[0] if ledger else None,
            'daily_limit': _DAILY_LIMIT, 'remaining_runs': self._remaining(now, ledger),
            'configured': configured}}

    def get_topic(self, id):
        return next((copy.deepcopy(topic) for topic in self._items(self._now()) if topic['id'] == id), None)

    def get_trace(self, identifier):
        # Shared runs contain only public research. Personal jobs never enter this ledger.
        if not any(job['id'] == identifier for job in self._ledger()):
            return None
        return self.jobs.traces.get(_OWNER, identifier)

    def refresh(self, request_id):
        history = None

        def prepare():
            nonlocal history
            if not self.provider.configured:
                raise JobError('OpenAI API 키 설정 후 브리핑을 수집할 수 있습니다.', 503)
            if self._remaining(self._now(), self._ledger()) == 0:
                raise JobError('브리핑 수집은 24시간에 두 번까지 가능합니다. 나중에 다시 요청해 주세요.', 429)
            feedback = self.insights.history_feedback(shared=True) if self.insights is not None else []
            history = build_history(self._items(self._now()), feedback)

        def work(progress):
            result = self.provider.discover_insights('briefing', history=history, progress=progress)
            if (not isinstance(result, dict) or not isinstance(result.get('topics'), list)
                    or not 0 <= len(result['topics']) <= 3):
                raise ProviderError(_INVALID)
            try:
                report = public_selection_report(result.get('selection_report'))
                if report and report['selected_count'] != len(result['topics']):
                    raise ValueError()
            except ValueError:
                raise ProviderError(_INVALID) from None
            now = self._now()
            # Validate/project the complete batch before modifying the last good feed.
            topics = [_public_topic(topic, now.date()) for topic in result['topics']]
            documents = [(topic['id'], json.dumps(topic, ensure_ascii=False, allow_nan=False), now.timestamp())
                         for topic in topics]
            progress('확인한 공개 자료를 브리핑에 저장하고 있습니다.')
            with self._connect() as db:
                db.execute('BEGIN IMMEDIATE')
                if documents:
                    # An empty selection is successful but does not replace prior items.
                    # Expired recollections start a new retention period; current ones do not.
                    db.execute('DELETE FROM feed_items WHERE collected_at < ?',
                               ((now - timedelta(days=30)).timestamp(),))
                    db.executemany('''INSERT INTO feed_items VALUES (?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET document=excluded.document''', documents)
                    db.execute('''DELETE FROM feed_items WHERE id NOT IN (
                        SELECT id FROM feed_items ORDER BY collected_at DESC, rowid DESC LIMIT 90)''')
                db.execute("INSERT OR REPLACE INTO feed_state VALUES ('last_success_at', ?)",
                           (now.isoformat(timespec='seconds'),))
            return {'count': len({topic['id'] for topic in topics}), 'usage': _usage(result.get('usage')),
                    'selection_report': report}

        return self.jobs.submit(_OWNER, 'briefing', request_id, {'category': 'briefing'},
                                work, before_submit=prepare)

    def tick(self, now=None):
        now = self._now(now)
        if (not self.enabled or not self.provider.configured or now.hour < 9
                or self.jobs.active(_OWNER)):
            return None
        day = now.date().isoformat()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM scheduled_days WHERE day < ?',
                       ((now.date() - timedelta(days=32)).isoformat(),))
            created = db.execute('INSERT OR IGNORE INTO scheduled_days VALUES (?, ?)',
                                 (day, now.timestamp())).rowcount
        if not created:
            return None
        try:
            return self.refresh('scheduled-' + day)
        except JobError:
            # A denied admission is not a reason to loop into new paid attempts.
            return None

    def start(self):
        with self._lifecycle:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()

            def run():
                while not self._stop.is_set():
                    try:
                        self.tick()
                    except Exception:
                        # Keep the scheduler alive without publishing internal errors.
                        pass
                    self._stop.wait(30)

            self._thread = threading.Thread(target=run, name='brochure-briefing-schedule', daemon=True)
            self._thread.start()

    def shutdown(self):
        with self._lifecycle:
            self._stop.set()
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=15)
