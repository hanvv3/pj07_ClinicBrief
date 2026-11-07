"""Local accounts and twelve-hour sessions; no email or external identity service."""
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 12 * 60 * 60
MAX_SESSIONS_PER_USER = 10
LOGIN_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_ATTEMPTS = 5
MAX_LOGIN_BUCKETS = 1024
_LOGIN_ERROR = '이메일 또는 비밀번호를 확인해 주세요.'
_REGISTER_ERROR = '계정을 만들 수 없습니다. 이메일과 비밀번호를 확인해 주세요.'


class AuthError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _email(value):
    if not isinstance(value, str):
        raise ValueError('email')
    value = value.strip().lower()
    if len(value) > 254 or value.count('@') != 1:
        raise ValueError('email')
    local, domain = value.split('@')
    if (not 1 <= len(local) <= 64 or local.startswith('.') or local.endswith('.')
            or '..' in local or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local)):
        raise ValueError('email')
    labels = domain.split('.')
    if len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                              for label in labels):
        raise ValueError('email')
    return value


def _password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128 or not value.strip():
        raise ValueError('password')
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        raise ValueError('password')
    return value.encode('utf-8')


def _token_hash(token):
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        return None
    return hashlib.sha256(token.encode('ascii')).hexdigest()


class AuthStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
                    password_hash BLOB NOT NULL, salt BLOB NOT NULL,
                    iterations INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    csrf_token TEXT NOT NULL, created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE);
                CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
                CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires_at);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    identifier TEXT PRIMARY KEY, window_start REAL NOT NULL,
                    attempts INTEGER NOT NULL);
            ''')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA secure_delete=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, email, password):
        try:
            email, password = _email(email), _password(password)
        except (ValueError, UnicodeError):
            raise AuthError(_REGISTER_ERROR) from None
        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac('sha256', password, salt, PASSWORD_ITERATIONS)
        user = {'id': uuid.uuid4().hex, 'email': email}
        try:
            with self._connect() as db:
                db.execute('INSERT INTO users VALUES (?, ?, ?, ?, ?)',
                           (user['id'], email, password_hash, salt, PASSWORD_ITERATIONS))
        except sqlite3.IntegrityError:
            raise AuthError(_REGISTER_ERROR) from None
        return user

    def _reserve_login_attempt(self, identifier):
        now = time.time()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE window_start <= ?',
                       (now - LOGIN_WINDOW_SECONDS,))
            row = db.execute('SELECT attempts FROM login_attempts WHERE identifier=?',
                             (identifier,)).fetchone()
            if row and row['attempts'] >= MAX_LOGIN_ATTEMPTS:
                raise AuthError('잠시 후 다시 로그인해 주세요.', 429)
            if not row:
                count = db.execute('SELECT COUNT(*) FROM login_attempts').fetchone()[0]
                if count >= MAX_LOGIN_BUCKETS:
                    raise AuthError('잠시 후 다시 로그인해 주세요.', 429)
                db.execute('INSERT INTO login_attempts VALUES (?, ?, 1)', (identifier, now))
            else:
                db.execute('UPDATE login_attempts SET attempts=attempts+1 WHERE identifier=?',
                           (identifier,))

    def login(self, email, password):
        try:
            email, password = _email(email), _password(password)
        except (ValueError, UnicodeError):
            raise AuthError(_LOGIN_ERROR, 401) from None
        identifier = hashlib.sha256(email.encode('ascii')).hexdigest()
        self._reserve_login_attempt(identifier)
        with self._connect() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        # Missing accounts still incur the same password derivation cost.
        derived = hashlib.pbkdf2_hmac('sha256', password,
                                     bytes(row['salt']) if row else b'\x00' * 16,
                                     row['iterations'] if row else PASSWORD_ITERATIONS)
        expected = bytes(row['password_hash']) if row else b'\x00' * 32
        if not hmac.compare_digest(derived, expected) or row is None:
            raise AuthError(_LOGIN_ERROR, 401)
        with self._connect() as db:
            db.execute('DELETE FROM login_attempts WHERE identifier=?', (identifier,))
        return {'id': row['id'], 'email': row['email']}

    def new_session(self, user_id):
        token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            user = db.execute('SELECT id, email FROM users WHERE id=?', (user_id,)).fetchone()
            if user is None:
                raise AuthError('로그인이 필요합니다.', 401)
            db.execute('DELETE FROM sessions WHERE expires_at <= ?', (now,))
            db.execute('''DELETE FROM sessions WHERE user_id=? AND token_hash NOT IN (
                SELECT token_hash FROM sessions WHERE user_id=?
                ORDER BY created_at DESC, rowid DESC LIMIT ?)''',
                       (user_id, user_id, MAX_SESSIONS_PER_USER - 1))
            db.execute('INSERT INTO sessions VALUES (?, ?, ?, ?, ?)',
                       (_token_hash(token), user_id, csrf_token, now, now + SESSION_SECONDS))
        return {'token': token, 'csrf_token': csrf_token, 'user': dict(user)}

    def session(self, token):
        token_hash = _token_hash(token)
        if token_hash is None:
            return None
        with self._connect() as db:
            db.execute('DELETE FROM sessions WHERE expires_at <= ?', (time.time(),))
            row = db.execute('''SELECT users.id, users.email, sessions.csrf_token
                FROM sessions JOIN users ON users.id=sessions.user_id
                WHERE sessions.token_hash=?''', (token_hash,)).fetchone()
        if row is None:
            return None
        return {'csrf_token': row['csrf_token'], 'user': {'id': row['id'], 'email': row['email']}}

    def logout(self, token):
        token_hash = _token_hash(token)
        if token_hash:
            with self._connect() as db:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash,))
