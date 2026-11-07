"""Behavior checks for editable, audience-separated Korean handouts."""

from copy import deepcopy
from pathlib import Path
import importlib
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from pypdf import PdfReader

from brochure.catalog import load_topics

try:
    rendering = importlib.import_module("brochure.rendering")
except ModuleNotFoundError:
    rendering = None


def sample_draft():
    return {
        "id": "PRIVATE_METADATA_ID",
        "research_date": "2026-11-03",
        "evidence_notice": "공개 자료를 확인한 참고 자료이며 진료 지침이 아닙니다.",
        "brochure": {
            "title": "의료기관 안내 자료 점검",
            "intro": "원장님께 전달하는 안내 자료입니다. 예약 안내를 함께 점검해 보세요.",
            "sections": [
                {"heading": "확인할 내용", "body": "안내 문구가 실제 운영과 일치하는지 확인합니다.", "source_ids": ["S1"]},
                {"heading": "원내 검토 사항", "body": "직원과 환자가 같은 안내를 확인할 수 있도록 내용을 정리합니다.", "source_ids": ["S1"]},
            ],
            "example": {"heading": "예약 안내 문구 점검", "body": "접수 담당자와 예약 안내 초안을 함께 읽어 보고 질문을 모아 보세요."},
            "limitations": ["실제 운영 절차는 기관 상황에 맞게 검토해야 합니다.", "수익이나 치료 효과를 보장하지 않습니다."],
            "sender": {"name": "테스트 담당자", "contact": "sender@example.test"},
        },
        "sources": [{"id": "S1", "title": "공개 참고 자료", "publisher": "참고 기관", "url": "https://example.test/source?lang=ko&section=1", "published_at": None, "checked_at": "2026-11-03", "context": "공개 자료"}],
        "notes": {"opening_staff": "PRIVATE_STAFF_NOTE", "opening_director": "PRIVATE_DIRECTOR_NOTE", "qa": [{"question": "PRIVATE_QA", "answer": "PRIVATE_ANSWER"}], "cannot_claim": ["PRIVATE_LIMIT"]},
        "exports": {"private": "PRIVATE_EXPORT_METADATA"},
    }


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(rendering, "The renderer has not been implemented yet")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.draft = sample_draft()

    def render(self):
        output = self.directory / "handout.docx"
        self.assertEqual(rendering.render_docx(self.draft, output), output)
        return output

    def test_docx_is_editable_korean_with_section_attribution_and_real_links(self):
        output = self.render()
        with ZipFile(output) as archive:
            xml = archive.read("word/document.xml").decode()
            relationships = archive.read("word/_rels/document.xml.rels").decode()
            styles = archive.read("word/styles.xml").decode()
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        text = "".join(root.itertext())
        self.assertIn("의료기관 안내 자료 점검", text)
        self.assertIn("[S1]", text)
        self.assertGreaterEqual(len(root.findall(".//w:p", ns)), 12)
        self.assertGreaterEqual(len(root.findall(".//w:hyperlink", ns)), 1)
        self.assertNotIn("<w:drawing", xml)
        self.assertNotIn("documentProtection", xml)
        self.assertIn("https://example.test/source?lang=ko&amp;section=1", relationships)
        self.assertIn('TargetMode="External"', relationships)
        self.assertIn('w:eastAsia="Noto Sans CJK KR"', styles)
        self.assertIn('w:eastAsia="ko-KR"', styles)
        self.assertIn('w:w="11906"', xml)  # A4 width in twips.

    def test_private_notes_and_unknown_metadata_never_enter_any_docx_part(self):
        self.draft["notes"]["unsafe"] = "\x00PRIVATE_CONTROL"
        self.draft["brochure"]["internal"] = "PRIVATE_NESTED_METADATA"
        self.draft["sources"][0]["internal"] = "PRIVATE_SOURCE_METADATA"
        output = self.render()
        with ZipFile(output) as archive:
            xml = "\n".join(archive.read(name).decode() for name in archive.namelist() if name.endswith(".xml"))
        self.assertNotIn("PRIVATE_", xml)

    def test_title_has_no_inherited_decorative_border(self):
        with ZipFile(self.render()) as archive:
            styles = ET.fromstring(archive.read("word/styles.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        title = styles.find("w:style[@w:styleId='Title']", ns)
        self.assertIsNone(title.find(".//w:pBdr", ns))

    def test_news_can_omit_example_and_limitations_without_empty_headings(self):
        self.draft['brochure']['example'] = {'heading': '', 'body': ''}
        self.draft['brochure']['limitations'] = []
        with ZipFile(self.render()) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
        text = ''.join(root.itertext())
        self.assertNotIn('제안 예시', text)
        self.assertNotIn('검토 시 유의사항', text)
        self.assertIn(self.draft['brochure']['sections'][0]['body'], text)
        self.assertIn('참고 자료', text)
        self.assertGreater(text.index(self.draft['evidence_notice']),
                           text.index(self.draft['brochure']['sections'][0]['body']))

    def test_half_empty_example_is_not_exported_as_a_broken_section(self):
        for example in ({'heading': '예시', 'body': ''}, {'heading': '', 'body': '내용'}):
            with self.subTest(example=example):
                self.draft['brochure']['example'] = example
                with self.assertRaises(ValueError):
                    self.render()

    def test_suggestion_limitations_evidence_and_only_supplied_sender_are_visible(self):
        with ZipFile(self.render()) as archive:
            xml = archive.read("word/document.xml").decode()
        for expected in ("제안 예시", "수익이나 치료 효과를 보장하지 않습니다.", "2026-11-03", "진료 지침이 아닙니다", "테스트 담당자", "sender@example.test"):
            self.assertIn(expected, xml)
        self.draft["brochure"]["sender"] = {"name": "", "contact": ""}
        with ZipFile(self.render()) as archive:
            xml = archive.read("word/document.xml").decode()
        self.assertNotIn("sender@example.test", xml)
        self.assertNotIn("담당자:", xml)
        self.assertNotIn("연락처:", xml)

    def test_source_publication_update_and_check_dates_remain_distinct(self):
        cases = [
            ({'published_at': None, 'updated_at': '2025-07-21'},
             '발행일 미상 · 수정일 2025-07-21 · 원문 확인일 2026-11-03'),
            ({'published_at': '2024-02'},
             '출처 표시일 2024-02 · 원문 확인일 2026-11-03'),
            ({'published_at': None},
             '출처 표시일 미상 · 원문 확인일 2026-11-03'),
            ({'published_at': '2024-02', 'updated_at': None},
             '발행일 2024-02 · 수정일 미상 · 원문 확인일 2026-11-03'),
            ({'published_at': '2024-02', 'updated_at': '2025-07-21'},
             '발행일 2024-02 · 수정일 2025-07-21 · 원문 확인일 2026-11-03'),
            ({'published_at': None, 'updated_at': None},
             '발행일 미상 · 수정일 미상 · 원문 확인일 2026-11-03'),
        ]
        for dates, expected in cases:
            with self.subTest(dates=dates):
                self.draft = sample_draft()
                self.draft['sources'][0].update(dates)
                with ZipFile(self.render()) as archive:
                    text = ''.join(ET.fromstring(archive.read('word/document.xml')).itertext())
                self.assertIn(expected, text)
                self.assertNotIn('발행일 2026-11-03', text)
                self.assertNotIn('수정일 2026-11-03', text)

    def test_legacy_cdc_displayed_date_is_not_claimed_as_publication_date(self):
        self.draft = next(topic for topic in load_topics()
                          if any(source['id'] == 'cdc-plain-language' for source in topic['sources']))
        source = self.draft['sources'][0]
        self.assertNotIn('updated_at', source)
        self.assertEqual(source['published_at'], '2025-07-21')
        with ZipFile(self.render()) as archive:
            text = ''.join(ET.fromstring(archive.read('word/document.xml')).itertext())
        self.assertIn('출처 표시일 2025-07-21 · 원문 확인일 2026-11-03', text)
        self.assertNotIn('발행일 2025-07-21', text)
        self.assertNotIn('수정일', text)

    def test_updated_only_source_date_survives_pdf_conversion(self):
        self.draft['sources'][0]['updated_at'] = '2025-07-21'
        output = rendering.render_pdf(self.render(), self.directory / 'updated-only.pdf')
        text = ''.join(page.extract_text() for page in PdfReader(output).pages)
        self.assertIn('발행일 미상', text)
        self.assertIn('수정일 2025-07-21', text)
        self.assertIn('원문 확인일 2026-11-03', text)
        self.assertNotIn('발행일 2025-07-21', text)

    def test_rejects_control_characters_before_replacing_existing_docx(self):
        output = self.directory / "handout.docx"
        output.write_bytes(b"previous completed export")
        for invalid in ("\x00", "\x01", "\x0b", "\x7f", "\ud800"):
            with self.subTest(invalid=repr(invalid)):
                draft = deepcopy(self.draft)
                draft["brochure"]["sender"]["contact"] = "before" + invalid + "after"
                with self.assertRaisesRegex(ValueError, "문자"):
                    rendering.render_docx(draft, output)
                self.assertEqual(output.read_bytes(), b"previous completed export")

    def test_rejects_unknown_source_references_and_unsafe_urls(self):
        self.draft["brochure"]["sections"][0]["source_ids"] = ["MISSING"]
        with self.assertRaisesRegex(ValueError, "출처"):
            self.render()
        self.draft = sample_draft()
        self.draft["sources"][0]["url"] = "file:///etc/passwd"
        with self.assertRaisesRegex(ValueError, "URL|주소"):
            self.render()

    def test_pdf_timeout_preserves_docx_and_existing_output_for_retry(self):
        docx = self.render()
        original = docx.read_bytes()
        target = self.directory / "handout.pdf"
        target.write_bytes(b"previous completed pdf")
        with patch.object(rendering, "_run_conversion", side_effect=subprocess.TimeoutExpired("soffice", 1)):
            with self.assertRaisesRegex(RuntimeError, "시간|초과"):
                rendering.render_pdf(docx, target, timeout=1)
        self.assertEqual(docx.read_bytes(), original)
        self.assertEqual(target.read_bytes(), b"previous completed pdf")

    def test_nonzero_pdf_conversion_does_not_publish_output(self):
        docx = self.render()
        output = self.directory / "handout.pdf"
        with patch.object(rendering, "_run_conversion", return_value=subprocess.CompletedProcess(["soffice"], 1, "", "conversion failed")):
            with self.assertRaisesRegex(RuntimeError, "실패"):
                rendering.render_pdf(docx, output)
        self.assertTrue(docx.is_file())
        self.assertFalse(output.exists())

    @unittest.skipUnless(os.name == "posix", "Process-group lifetime check requires POSIX")
    def test_pdf_timeout_kills_converter_children_before_they_can_write(self):
        docx = self.render()
        child_pid_file = self.directory / "child.pid"
        sentinel = self.directory / "orphan-output"
        launcher = self.directory / "fake-libreoffice"
        child = f"import os,time; from pathlib import Path; Path({str(child_pid_file)!r}).write_text(str(os.getpid())); time.sleep(0.9); Path({str(sentinel)!r}).write_text('orphan survived')"
        launcher.write_text(f"#!{sys.executable}\nimport subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', {child!r}])\ntime.sleep(30)\n")
        launcher.chmod(0o700)
        try:
            with patch.dict(os.environ, {"BROCHURE_LIBREOFFICE": str(launcher)}):
                with self.assertRaisesRegex(RuntimeError, "時間|시간|초과"):
                    rendering.render_pdf(docx, self.directory / "timeout.pdf", timeout=0.35)
            self.assertTrue(child_pid_file.exists(), "The stand-in must actually launch its child")
            time.sleep(1)
            self.assertFalse(sentinel.exists(), "Timed-out converter left its child alive")
        finally:
            if child_pid_file.exists():
                try:
                    os.kill(int(child_pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_success_without_a_nonempty_valid_pdf_is_rejected(self):
        docx = self.render()
        output = self.directory / "handout.pdf"
        for data in (None, b"", b"%PDF-1.4\nnot a PDF"):
            def fake_convert(args, **kwargs):
                directory = Path(args[args.index("--outdir") + 1])
                if data is not None:
                    (directory / "handout.pdf").write_bytes(data)
                return subprocess.CompletedProcess(args, 0, "", "")
            with self.subTest(data=data), patch.object(rendering, "_run_conversion", side_effect=fake_convert):
                with self.assertRaisesRegex(RuntimeError, "PDF"):
                    rendering.render_pdf(docx, output)
                self.assertFalse(output.exists())

    def test_real_pdf_retry_is_korean_searchable_linked_and_short(self):
        docx = self.render()
        original = docx.read_bytes()
        output = self.directory / "handout.pdf"
        with patch.object(rendering, "_run_conversion", side_effect=subprocess.TimeoutExpired("soffice", 1)):
            with self.assertRaises(RuntimeError):
                rendering.render_pdf(docx, output, timeout=1)
        self.assertEqual(rendering.render_pdf(docx, output), output)
        self.assertEqual(docx.read_bytes(), original)
        reader = PdfReader(output)
        self.assertIn(len(reader.pages), (1, 2))
        text = "".join(page.extract_text() for page in reader.pages)
        self.assertIn("의료기관", text)
        self.assertIn("진료", text)
        self.assertNotIn("PRIVATE_", text)
        links = [str(annotation.get_object().get("/A", {}).get("/URI", "")) for page in reader.pages for annotation in page.get("/Annots", [])]
        self.assertIn("https://example.test/source?lang=ko&section=1", links)

    def test_long_handout_keeps_administrative_example_with_its_limitations(self):
        self.draft["brochure"]["sections"] = [
            {"heading": f"검토 항목 {index}", "body": "안내 문구가 실제 운영과 일치하는지 확인합니다. " * 6, "source_ids": ["S1"]}
            for index in range(3)
        ]
        self.draft["brochure"]["example"]["body"] *= 3
        self.draft["brochure"]["limitations"] *= 2
        docx = self.render()
        pdf = rendering.render_pdf(docx, self.directory / "long.pdf")
        reader = PdfReader(pdf)
        self.assertEqual(len(reader.pages), 2)
        self.assertNotIn("제안 예시", reader.pages[0].extract_text())
        self.assertIn("제안 예시", reader.pages[1].extract_text())
        self.assertIn("검토 시 유의사항", reader.pages[1].extract_text())


if __name__ == "__main__":
    unittest.main()
