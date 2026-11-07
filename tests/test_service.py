import copy
import tempfile
import unittest
from pathlib import Path

from brochure.service import BrochureService, AppError
from brochure.catalog import load_topics, validate_topic


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.calls = []
        self.fail_pdf = False

        def docx(draft, target):
            self.calls.append('docx')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'editable-docx')
            return target

        def pdf(source, target):
            self.calls.append('pdf')
            if self.fail_pdf:
                raise RuntimeError('provider details must not leak')
            target.write_bytes(b'%PDF-test')
            return target

        self.renderers = (docx, pdf)
        self.app = BrochureService(self.root, renderers=self.renderers)

    def create(self, key='request-one'):
        return self.app.create({'topic_id': 'plain-language', 'sender_name': '',
                                'sender_contact': '', 'request_id': key})

    def test_reopen_is_snapshot_and_create_is_idempotent(self):
        first = self.create()
        self.assertEqual(first, self.create())
        reopened = BrochureService(self.root, renderers=self.renderers).get(first['id'])
        self.assertEqual(first, reopened)
        self.assertEqual(len(self.app.list()), 1)
        with self.assertRaises(AppError) as raised:
            self.app.create({'topic_id': 'teach-back', 'request_id': 'request-one'})
        self.assertEqual(raised.exception.status, 409)

    def test_review_required_and_sender_edit_invalidates_downloads(self):
        draft = self.create()
        with self.assertRaises(AppError):
            self.app.export(draft['id'], 1)
        self.app.review(draft['id'], 1)
        ready = self.app.export(draft['id'], 1)
        self.assertEqual(ready['status'], 'exported')
        self.assertTrue(self.app.download(draft['id'], 'pdf', 1).exists())
        revised = self.app.update(draft['id'], {'revision': 1, 'sender_name': '홍길동',
                                              'sender_contact': 'hello@example.test'})
        self.assertEqual(revised['revision'], 2)
        self.assertEqual(revised['status'], 'draft')
        self.assertEqual(revised['exports']['pdf']['status'], 'pending')
        with self.assertRaises(AppError) as raised:
            self.app.review(draft['id'], 1)
        self.assertEqual(raised.exception.status, 409)
        with self.assertRaises(AppError):
            self.app.download(draft['id'], 'pdf', 1)

    def test_partial_pdf_failure_keeps_docx_and_retry_only_runs_pdf(self):
        draft = self.create()
        self.app.review(draft['id'], 1)
        self.fail_pdf = True
        partial = self.app.export(draft['id'], 1)
        self.assertEqual(partial['status'], 'reviewed')
        self.assertEqual(partial['exports']['docx']['status'], 'ready')
        self.assertEqual(partial['exports']['pdf']['status'], 'failed')
        self.assertNotIn('provider details', partial['exports']['pdf']['error'])
        self.assertTrue(self.app.download(draft['id'], 'docx', 1).exists())
        self.fail_pdf = False
        ready = self.app.export(draft['id'], 1)
        self.assertEqual(ready['status'], 'exported')
        self.assertEqual(self.calls, ['docx', 'pdf', 'pdf'])
        self.app.export(draft['id'], 1)
        self.assertEqual(self.calls, ['docx', 'pdf', 'pdf'])

    def test_missing_artifact_can_be_recovered(self):
        draft = self.create()
        self.app.review(draft['id'], 1)
        self.app.export(draft['id'], 1)
        self.app.download(draft['id'], 'pdf', 1).unlink()
        with self.assertRaises(AppError):
            self.app.download(draft['id'], 'pdf', 1)
        self.assertEqual(self.app.export(draft['id'], 1)['status'], 'exported')
        self.assertEqual(self.calls, ['docx', 'pdf', 'pdf'])

    def test_delete_removes_work_and_files(self):
        draft = self.create()
        self.app.review(draft['id'], 1)
        self.app.export(draft['id'], 1)
        path = self.app.download(draft['id'], 'docx', 1)
        self.app.delete(draft['id'])
        self.assertFalse(path.exists())
        self.assertEqual(self.app.list(), [])
        with self.assertRaises(AppError) as raised:
            self.app.get(draft['id'])
        self.assertEqual(raised.exception.status, 404)

    def test_invalid_sender_and_revision_rejected(self):
        for index, sender in enumerate(['x' * 41, '\x00', '\ud800', 'A\x7fB', 'A\x85B', 4]):
            with self.subTest(sender=repr(sender)):
                with self.assertRaises(AppError):
                    self.app.create({'topic_id': 'plain-language', 'sender_name': sender,
                                     'request_id': f'bad-input-{index}'})
        draft = self.create()
        with self.assertRaises(AppError):
            self.app.review(draft['id'], True)

    def test_unsupported_central_claim_rejected(self):
        topic = copy.deepcopy(load_topics()[0])
        topic['claims'][0]['source_ids'] = ['invented-source']
        with self.assertRaises(ValueError):
            validate_topic(topic)


if __name__ == '__main__':
    unittest.main()
