"""Public insight projection and account-scoped feedback; no provider dependencies."""
import json
import re
import sqlite3
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path


_INVALID = '주제 선택 정보 또는 피드백 형식을 확인해 주세요.'
_VERDICTS = ('useful', 'not_useful', 'seen')
_COVERAGE = ('medical', 'ai', 'operations', 'economy', 'life')
_SCORES = ('specificity', 'usability', 'novelty', 'evidence')


def _text(value, limit, *, empty=False):
    if (not isinstance(value, str) or len(value) > limit or (not empty and not value.strip())
            or any((ord(char) < 32 and char not in '\n\r\t') or 127 <= ord(char) <= 159
                   or 0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF)
                   for char in value)):
        raise ValueError(_INVALID)
    return value.strip()


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value):
        raise ValueError(_INVALID)
    return value


def _number(value, maximum, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(_INVALID)
    return value


def normalize_problem_key(value):
    value = unicodedata.normalize('NFKC', _text(value, 80)).casefold()
    value = re.sub(r'[\W_]+', '-', value, flags=re.UNICODE).strip('-')
    if not value or len(value) > 80:
        raise ValueError(_INVALID)
    return value


def project_insight_fields(topic):
    """Project optional new fields; reject partial or invalid insight metadata."""
    if not isinstance(topic, dict):
        raise ValueError(_INVALID)
    if 'selection' not in topic and 'ready_to_use' not in topic:
        return {}
    selection, asset = topic.get('selection'), topic.get('ready_to_use')
    if not isinstance(selection, dict) or not isinstance(asset, dict):
        raise ValueError(_INVALID)
    if selection.get('audience') not in ('director', 'staff', 'both'):
        raise ValueError(_INVALID)
    if selection.get('novelty') not in ('new', 'update'):
        raise ValueError(_INVALID)
    previous = selection.get('previous_topic_id')
    if previous is not None:
        previous = _identifier(previous)
    change = _text(selection.get('change'), 400, empty=True)
    if ((selection['novelty'] == 'new' and previous is not None)
            or (selection['novelty'] == 'update' and (previous is None or not change))):
        raise ValueError(_INVALID)
    scores = selection.get('scores')
    if not isinstance(scores, dict):
        raise ValueError(_INVALID)
    scores = {key: _number(scores.get(key), 3) for key in _SCORES}
    total = _number(selection.get('total'), 12)
    if total != sum(scores.values()):
        raise ValueError(_INVALID)
    sources = topic.get('sources')
    if not isinstance(sources, list):
        raise ValueError(_INVALID)
    source_ids = {source['id'] for source in sources
                  if isinstance(source, dict) and isinstance(source.get('id'), str)}
    signals = selection.get('signals')
    if not isinstance(signals, list) or not 1 <= len(signals) <= 8:
        raise ValueError(_INVALID)
    public_signals = []
    for signal in signals:
        if (not isinstance(signal, dict) or not isinstance(signal.get('source_id'), str)
                or signal['source_id'] not in source_ids):
            raise ValueError(_INVALID)
        public_signals.append({'source_id': _text(signal['source_id'], 80),
                               'observation': _text(signal.get('observation'), 500)})
    if asset.get('format') not in ('prompt', 'message', 'checklist', 'comparison', 'brief'):
        raise ValueError(_INVALID)
    return {'selection': {
                'audience': selection['audience'], 'problem': _text(selection.get('problem'), 400),
                'problem_key': normalize_problem_key(selection.get('problem_key')),
                'reason': _text(selection.get('reason'), 600), 'novelty': selection['novelty'],
                'previous_topic_id': previous, 'change': change, 'signals': public_signals,
                'scores': scores, 'total': total},
            'ready_to_use': {'title': _text(asset.get('title'), 120), 'format': asset['format'],
                'body': _text(asset.get('body'), 3000),
                'adaptation_note': _text(asset.get('adaptation_note'), 500, empty=True)}}


def public_selection_report(value):
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict):
        raise ValueError(_INVALID)
    sources = _number(value.get('sources_read'), 64)
    considered = _number(value.get('candidates_considered'), 6)
    selected = _number(value.get('selected_count'), 3)
    rejected = value.get('rejected')
    if (not isinstance(rejected, list) or len(rejected) > 6
            or selected + len(rejected) > considered):
        raise ValueError(_INVALID)
    clean = []
    for item in rejected:
        if not isinstance(item, dict):
            raise ValueError(_INVALID)
        clean.append({'title': _text(item.get('title'), 150), 'reason': _text(item.get('reason'), 400)})
    return {'sources_read': sources, 'candidates_considered': considered,
            'rejected': clean, 'selected_count': selected}


def build_history(topics, feedback):
    """Keep whole recent public records, capped at 30 items and 24 KB total.

    Reserve 6 KB for aggregate feedback. Never truncate a prior summary/change:
    losing its ending could incorrectly make already-covered material seem new.
    Callers supply newest-first topics; the oldest excess records are omitted.
    """
    recent, votes, seen = [], [], set()
    for topic in topics if isinstance(topics, (list, tuple)) else []:
        if len(recent) >= 30:
            break
        if not isinstance(topic, dict):
            continue
        try:
            identifier = _identifier(topic.get('id'))
            title = _text(topic.get('title'), 300)
            selection = topic.get('selection') if isinstance(topic.get('selection'), dict) else topic
            problem = _text(selection.get('problem', title), 400)
            summary = _text(topic.get('summary', ''), 400, empty=True)
            change = _text(selection.get('change', ''), 400, empty=True)
            key = normalize_problem_key(selection.get('problem_key', title[:80]))
            coverage = topic.get('coverage_area', '')
            if coverage not in _COVERAGE:
                coverage = ''
        except ValueError:
            continue
        if identifier in seen:
            continue
        seen.add(identifier)
        record = {'id': identifier, 'title': title, 'problem': problem,
                  'problem_key': key, 'coverage_area': coverage,
                  'summary': summary, 'change': change}
        if len(json.dumps({'recent_topics': recent + [record], 'feedback': []},
                          ensure_ascii=False).encode('utf-8')) > 18000:
            break
        recent.append(record)
    for vote in feedback if isinstance(feedback, (list, tuple)) else []:
        if len(votes) >= 30:
            break
        if not isinstance(vote, dict) or vote.get('verdict') not in _VERDICTS:
            continue
        try:
            key = normalize_problem_key(vote.get('problem_key'))
            count = _number(vote.get('count'), 1_000_000, minimum=1)
        except ValueError:
            continue
        record = {'problem_key': key, 'verdict': vote['verdict'], 'count': count}
        if len(json.dumps({'recent_topics': recent, 'feedback': votes + [record]},
                          ensure_ascii=False).encode('utf-8')) > 24000:
            break
        votes.append(record)
    return {'recent_topics': recent, 'feedback': votes}


class InsightStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS insight_feedback (
                    owner TEXT NOT NULL, topic_id TEXT NOT NULL, problem_key TEXT NOT NULL,
                    verdict TEXT NOT NULL, shared INTEGER NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY(owner, topic_id));
                CREATE INDEX IF NOT EXISTS insight_feedback_shared ON insight_feedback(shared, updated_at);
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

    def set_feedback(self, owner, topic_id, problem_key, verdict, shared=False):
        owner, topic_id = _identifier(owner), _identifier(topic_id)
        problem_key = normalize_problem_key(problem_key)
        if verdict not in _VERDICTS or type(shared) is not bool:
            raise ValueError(_INVALID)
        with self._connect() as db:
            db.execute('''INSERT INTO insight_feedback VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner, topic_id) DO UPDATE SET problem_key=excluded.problem_key,
                verdict=excluded.verdict, shared=excluded.shared, updated_at=excluded.updated_at''',
                       (owner, topic_id, problem_key, verdict, int(shared), time.time()))

    def feedback_for(self, owner, topic_ids):
        owner = _identifier(owner)
        if not isinstance(topic_ids, (list, tuple, set)):
            raise ValueError(_INVALID)
        identifiers = list({_identifier(identifier) for identifier in topic_ids})
        result = {}
        with self._connect() as db:
            for offset in range(0, len(identifiers), 500):
                chunk = identifiers[offset:offset + 500]
                placeholders = ','.join('?' for _ in chunk)
                rows = db.execute(f'''SELECT topic_id, verdict FROM insight_feedback
                    WHERE owner=? AND topic_id IN ({placeholders})''', (owner, *chunk)).fetchall()
                result.update({row['topic_id']: row['verdict'] for row in rows})
        return result

    def history_feedback(self, owner=None, shared=False):
        if type(shared) is not bool:
            raise ValueError(_INVALID)
        if owner is None and not shared:
            return []
        clauses, parameters = [], []
        if owner is not None:
            clauses.append('owner=?')
            parameters.append(_identifier(owner))
        if shared:
            clauses.append('shared=1')
        with self._connect() as db:
            rows = db.execute(f'''SELECT problem_key, verdict, COUNT(*) AS count
                FROM insight_feedback WHERE {' AND '.join(clauses)}
                GROUP BY problem_key, verdict
                ORDER BY MAX(updated_at) DESC, problem_key, verdict LIMIT 30''', parameters).fetchall()
        return [dict(row) for row in rows]
