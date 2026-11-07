import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from brochure.auth import AuthError, AuthStore


class AuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'auth.sqlite3'
        self.auth = AuthStore(self.path)
        self.password = 'a long private password'

    def test_accounts_normalize_email_and_keep_sessions_isolated(self):
        alice = self.auth.register(' Alice@Example.test ', self.password)
        bob = self.auth.register('bob@example.test', self.password)
        self.assertEqual(alice['email'], 'alice@example.test')
        self.assertEqual(self.auth.login('ALICE@example.test', self.password), alice)
        self.assertNotEqual(alice['id'], bob['id'])
        first = self.auth.new_session(alice['id'])
        second = self.auth.new_session(bob['id'])
        self.assertEqual(self.auth.session(first['token'])['user'], alice)
        self.assertEqual(self.auth.session(second['token'])['user'], bob)
        self.assertNotEqual(first['csrf_token'], second['csrf_token'])
        self.auth.logout(first['token'])
        self.assertIsNone(self.auth.session(first['token']))
        self.assertEqual(self.auth.session(second['token'])['user'], bob)

    def test_passwords_are_salted_and_session_tokens_are_hashed_at_rest(self):
        first = self.auth.register('first@example.test', self.password)
        self.auth.register('second@example.test', self.password)
        session = self.auth.new_session(first['id'])
        with sqlite3.connect(self.path) as db:
            rows = db.execute('SELECT password_hash, salt FROM users').fetchall()
        self.assertNotEqual(rows[0][0], rows[1][0])
        self.assertNotEqual(rows[0][1], rows[1][1])
        contents = self.path.read_bytes()
        self.assertNotIn(self.password.encode(), contents)
        self.assertNotIn(session['token'].encode(), contents)
        self.assertEqual(set(session), {'token', 'csrf_token', 'user'})
        self.assertEqual(set(session['user']), {'id', 'email'})

    def test_sessions_expire_after_twelve_hours_and_survive_reopen(self):
        user = self.auth.register('alice@example.test', self.password)
        now = time.time()
        with patch('brochure.auth.time.time', return_value=now):
            session = self.auth.new_session(user['id'])
        reopened = AuthStore(self.path)
        with patch('brochure.auth.time.time', return_value=now + 12 * 3600 - 1):
            self.assertEqual(reopened.session(session['token'])['user'], user)
        with patch('brochure.auth.time.time', return_value=now + 12 * 3600):
            self.assertIsNone(reopened.session(session['token']))

    def test_invalid_registration_never_creates_an_account(self):
        invalid = [('missing-at', self.password), ('a@b', self.password),
                   ('a\x00@example.test', self.password), ('a@example.test', 'short'),
                   ('a@example.test', 'x' * 129), ('a@example.test', '\ud800' * 12),
                   (None, self.password), ('a@example.test', 123)]
        for email, password in invalid:
            with self.subTest(email=repr(email), password=repr(password)):
                with self.assertRaises(AuthError) as raised:
                    self.auth.register(email, password)
                self.assertEqual(raised.exception.status, 400)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM users').fetchone()[0], 0)

    def test_duplicate_identifier_and_failed_login_have_safe_errors(self):
        self.auth.register('alice@example.test', self.password)
        with self.assertRaises(AuthError) as duplicate:
            self.auth.register('ALICE@example.test', self.password)
        self.assertNotIn('alice', str(duplicate.exception))
        failures = []
        for email in ['alice@example.test', 'absent@example.test']:
            with self.assertRaises(AuthError) as raised:
                self.auth.login(email, 'incorrect password')
            self.assertEqual(raised.exception.status, 401)
            failures.append(str(raised.exception))
        self.assertEqual(failures[0], failures[1])

    def test_failed_login_limit_expires_and_accounting_is_bounded(self):
        user = self.auth.register('alice@example.test', self.password)
        now = time.time()
        with patch('brochure.auth.time.time', return_value=now):
            for _ in range(5):
                with self.assertRaises(AuthError) as failed:
                    self.auth.login(user['email'], 'incorrect password')
                self.assertEqual(failed.exception.status, 401)
            with self.assertRaises(AuthError) as blocked:
                self.auth.login(user['email'], self.password)
            self.assertEqual(blocked.exception.status, 429)
        with patch('brochure.auth.time.time', return_value=now + 901):
            self.assertEqual(self.auth.login(user['email'], self.password), user)
        with patch('brochure.auth.MAX_LOGIN_BUCKETS', 4):
            for number in range(8):
                with self.assertRaises(AuthError):
                    self.auth.login(f'absent{number}@example.test', self.password)
            with sqlite3.connect(self.path) as db:
                self.assertLessEqual(db.execute('SELECT COUNT(*) FROM login_attempts').fetchone()[0], 4)

    def test_unknown_malformed_and_revoked_tokens_do_not_authenticate(self):
        for token in [None, '', 'x' * 5000, '\ud800', 'missing']:
            self.assertIsNone(self.auth.session(token))
            self.auth.logout(token)
        with self.assertRaises(AuthError):
            self.auth.new_session('unknown-user')
        user = self.auth.register('alice@example.test', self.password)
        oldest = self.auth.new_session(user['id'])
        for _ in range(10):
            newest = self.auth.new_session(user['id'])
        self.assertIsNone(self.auth.session(oldest['token']))
        self.assertIsNotNone(self.auth.session(newest['token']))


if __name__ == '__main__':
    unittest.main()
