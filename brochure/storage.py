"""SQLite stores actual composed snapshots, never regeneration instructions."""
import json
import sqlite3
from pathlib import Path

LEGACY_OWNER = '__legacy__'


class DraftStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                signature TEXT NOT NULL, document TEXT NOT NULL)''')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(drafts)')}
            if 'owner' not in columns:
                db.execute("ALTER TABLE drafts ADD COLUMN owner TEXT NOT NULL DEFAULT '__legacy__'")
            db.execute('CREATE INDEX IF NOT EXISTS drafts_owner ON drafts(owner)')
            db.execute('''CREATE TABLE IF NOT EXISTS research_topics (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, document TEXT NOT NULL)''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def all(self, owner=LEGACY_OWNER):
        with self.connect() as db:
            rows = db.execute('SELECT document FROM drafts WHERE owner=? ORDER BY rowid DESC', (owner,)).fetchall()
        return [json.loads(row['document']) for row in rows]

    def get(self, identifier, owner=LEGACY_OWNER):
        with self.connect() as db:
            row = db.execute('SELECT document FROM drafts WHERE id=? AND owner=?', (identifier, owner)).fetchone()
        return json.loads(row['document']) if row else None

    def by_request(self, request_id, owner=LEGACY_OWNER):
        with self.connect() as db:
            row = db.execute('SELECT signature, document FROM drafts WHERE request_id=? AND owner=?',
                             (owner + ':' + request_id, owner)).fetchone()
        return (row['signature'], json.loads(row['document'])) if row else None

    def insert(self, request_id, signature, draft, owner=LEGACY_OWNER):
        with self.connect() as db:
            db.execute('INSERT INTO drafts (id, request_id, signature, document, owner) VALUES (?, ?, ?, ?, ?)',
                       (draft['id'], owner + ':' + request_id, signature, json.dumps(draft, ensure_ascii=False), owner))

    def save(self, draft, owner=LEGACY_OWNER):
        with self.connect() as db:
            db.execute('UPDATE drafts SET document=? WHERE id=? AND owner=?',
                       (json.dumps(draft, ensure_ascii=False), draft['id'], owner))

    def delete(self, identifier, owner=LEGACY_OWNER):
        with self.connect() as db:
            db.execute('DELETE FROM drafts WHERE id=? AND owner=?', (identifier, owner))

    def save_topics(self, owner, topics):
        with self.connect() as db:
            for topic in topics:
                db.execute('INSERT INTO research_topics VALUES (?, ?, ?)',
                           (topic['id'], owner, json.dumps(topic, ensure_ascii=False)))

    def topics(self, owner):
        with self.connect() as db:
            rows = db.execute('SELECT document FROM research_topics WHERE owner=? ORDER BY rowid DESC', (owner,))
            return [json.loads(row['document']) for row in rows]

    def topic(self, owner, identifier):
        with self.connect() as db:
            row = db.execute('SELECT document FROM research_topics WHERE owner=? AND id=?', (owner, identifier)).fetchone()
        return json.loads(row['document']) if row else None

    def delete_topics(self, owner):
        with self.connect() as db:
            db.execute('DELETE FROM research_topics WHERE owner=?', (owner,))
