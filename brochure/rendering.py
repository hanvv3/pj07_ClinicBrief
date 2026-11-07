"""Editable Korean handouts and bounded PDF export from the same DOCX.

This boundary intentionally reads a small public-content allowlist. Draft notes,
claim maps and workflow metadata must never be added to the document model.
"""

from pathlib import Path
import os
import re
import shutil
import signal
import subprocess
import tempfile
from urllib.parse import urlsplit

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.shared import Mm, Pt, RGBColor
from pypdf import PdfReader


FONT = "Noto Sans CJK KR"
_UNSAFE_TEXT = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff\ufffe\uffff]")


def _text(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} 항목은 문자열이어야 합니다.")
    if _UNSAFE_TEXT.search(value):
        raise ValueError(f"{label} 항목에 사용할 수 없는 제어 문자가 있습니다.")
    return value.strip()


def _public_content(draft):
    """Copy named public fields, never serialize or traverse a complete draft."""
    try:
        brochure = draft["brochure"]
        sources = []
        seen = set()
        for item in draft["sources"]:
            source = {key: _text(item[key], "출처") for key in ("id", "title", "publisher", "url", "checked_at")}
            source["published_at"] = _text(item["published_at"], "출처 날짜") if item.get("published_at") is not None else None
            # Legacy examples store a displayed date without distinguishing publication/update.
            # Preserve schema presence: explicit updated_at (even null) identifies the new fields.
            if "updated_at" in item:
                source["updated_at"] = _text(item["updated_at"], "수정일") if item["updated_at"] is not None else None
            parsed = urlsplit(source["url"])
            if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or any(c.isspace() for c in source["url"]):
                raise ValueError("출처 URL은 유효한 공개 http 또는 https 주소여야 합니다.")
            if not source["id"] or source["id"] in seen:
                raise ValueError("출처 식별자가 비어 있거나 중복되었습니다.")
            seen.add(source["id"])
            sources.append(source)
        sections = []
        for section in brochure["sections"]:
            references = [_text(value, "출처 식별자") for value in section["source_ids"]]
            if any(reference not in seen for reference in references):
                raise ValueError("본문의 출처 식별자에 해당하는 자료가 없습니다.")
            sections.append({"heading": _text(section["heading"], "제목"), "body": _text(section["body"], "본문"), "source_ids": references})
        sender = brochure["sender"]
        example = {key: _text(brochure["example"][key], "제안 예시").strip()
                   for key in ("heading", "body")}
        if bool(example["heading"]) != bool(example["body"]):
            raise ValueError("예시를 넣으려면 제목과 내용을 함께 작성해 주세요.")
        return {
            "title": _text(brochure["title"], "자료 제목"),
            "intro": _text(brochure["intro"], "소개"),
            "sections": sections,
            "example": example,
            "limitations": [_text(value, "확인할 한계") for value in brochure["limitations"]],
            "sender": {key: _text(sender.get(key, ""), "담당자 정보") for key in ("name", "contact")},
            "sources": sources,
            "research_date": _text(draft["research_date"], "자료 확인일"),
            "evidence_notice": _text(draft["evidence_notice"], "근거 안내"),
        }
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError("내보낼 자료의 필수 항목이 없거나 형식이 올바르지 않습니다.") from error


def _font(style, size, *, bold=False, color="000000"):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor.from_string(color)
    properties = style.element.get_or_add_rPr()
    fonts = properties.find(qn("w:rFonts"))
    for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + attribute), FONT)
    for attribute in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(qn("w:" + attribute), None)
    language = OxmlElement("w:lang")
    language.set(qn("w:val"), "ko-KR")
    language.set(qn("w:eastAsia"), "ko-KR")
    properties.append(language)


def _document():
    document = Document()
    section = document.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.top_margin, section.bottom_margin = Mm(17), Mm(17)
    section.left_margin, section.right_margin = Mm(20), Mm(20)
    styles = document.styles
    _font(styles["Normal"], 11)
    normal = styles["Normal"].paragraph_format
    normal.line_spacing = 1.18
    normal.space_after = Pt(6)
    normal.widow_control = True
    _font(styles["Title"], 20, bold=True)
    styles["Title"].paragraph_format.space_after = Pt(10)
    styles["Title"].paragraph_format.keep_with_next = True
    _font(styles["Heading 1"], 12, bold=True)
    styles["Heading 1"].paragraph_format.space_before = Pt(11)
    styles["Heading 1"].paragraph_format.space_after = Pt(4)
    styles["Heading 1"].paragraph_format.keep_with_next = True
    for style_name in ("Normal", "Title", "Heading 1"):
        properties = styles[style_name].element.find(qn("w:pPr"))
        if properties is not None:
            for border in list(properties.findall(qn("w:pBdr"))):
                properties.remove(border)
    for name, size, color in (("Evidence", 9, "4B5563"), ("Attribution", 8.5, "4B5563"), ("Sender", 9.5, "000000")):
        style = styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        style.base_style = styles["Normal"]
        _font(style, size, color=color)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.1
    # Keep dates and Latin source names from breaking in the middle of a word.
    word_wrap = OxmlElement("w:wordWrap")
    word_wrap.set(qn("w:val"), "0")
    styles["Attribution"].element.get_or_add_pPr().append(word_wrap)
    # Clear python-docx template attribution; only user-supplied sender is visible.
    document.core_properties.author = ""
    document.core_properties.last_modified_by = ""
    document.core_properties.comments = ""
    document.core_properties.language = "ko-KR"
    return document


def _paragraphs(document, text, style=None):
    result = None
    for line in text.split("\n"):
        if line.strip():
            result = document.add_paragraph(line.strip(), style)
    return result


def _hyperlink(paragraph, label, url):
    relation = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relation)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for attribute in ("ascii", "hAnsi", "eastAsia"):
        fonts.set(qn("w:" + attribute), FONT)
    properties.append(fonts)
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "24526B")
    properties.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)
    run.append(properties)
    text = OxmlElement("w:t")
    text.text = label
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def render_docx(draft: dict, output_path: Path) -> Path:
    """Write an editable A4 handout atomically, excluding all private notes."""
    content = _public_content(draft)
    output_path = Path(output_path)
    document = _document()
    document.core_properties.title = content["title"]
    document.add_paragraph(content["title"], "Title")
    _paragraphs(document, content["intro"])
    for section in content["sections"]:
        document.add_paragraph(section["heading"], "Heading 1")
        paragraph = _paragraphs(document, section["body"])
        if section["source_ids"]:
            if paragraph is not None:
                paragraph.paragraph_format.keep_with_next = True
                paragraph.paragraph_format.space_after = Pt(2)
            citation = document.add_paragraph(" ".join(f"[{source_id}]" for source_id in section["source_ids"]), "Attribution")
            citation.paragraph_format.keep_together = True
    application_start = len(document.paragraphs)
    if content["example"]["body"]:
        document.add_paragraph("제안 예시  " + content["example"]["heading"], "Heading 1")
        _paragraphs(document, content["example"]["body"])
    if content["limitations"]:
        document.add_paragraph("검토 시 유의사항", "Heading 1")
        for limitation in content["limitations"]:
            _paragraphs(document, limitation)
    if content["sources"]:
        document.add_paragraph("참고 자료", "Heading 1")
        for source in content["sources"]:
            paragraph = document.add_paragraph(style="Attribution")
            paragraph.add_run(f"[{source['id']}] {source['publisher']}  ")
            _hyperlink(paragraph, source["title"], source["url"])
            if "updated_at" in source:
                dates = (f"발행일 {source['published_at'] or '미상'} · "
                         f"수정일 {source['updated_at'] or '미상'} · "
                         f"원문 확인일 {source['checked_at']}")
            else:
                dates = (f"출처 표시일 {source['published_at'] or '미상'} · "
                         f"원문 확인일 {source['checked_at']}")
            paragraph.add_run().add_break()
            paragraph.add_run(dates)
    document.add_paragraph(f"자료 확인일  {content['research_date']}", "Evidence")
    _paragraphs(document, content["evidence_notice"], "Evidence")
    sender = content["sender"]
    if sender["name"] or sender["contact"]:
        paragraph = document.add_paragraph(style="Sender")
        paragraph.paragraph_format.space_before = Pt(10)
        if sender["name"]:
            paragraph.add_run("담당자: " + sender["name"])
        if sender["name"] and sender["contact"]:
            paragraph.add_run("   ")
        if sender["contact"]:
            paragraph.add_run("연락처: " + sender["contact"])
    # Keep the suggested example with its qualifications and sources. For the
    # reviewed longer handouts this makes a coherent second page; short ones
    # remain on one page without hard-coded page breaks or smaller body type.
    application = document.paragraphs[application_start:]
    for paragraph in application:
        paragraph.paragraph_format.keep_together = True
        paragraph.paragraph_format.keep_with_next = True
    application[-1].paragraph_format.keep_with_next = False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".brochure-docx-", dir=output_path.parent) as directory:
        temporary = Path(directory) / "handout.docx"
        document.save(temporary)
        temporary.replace(output_path)
    return output_path


def _libreoffice():
    configured = os.environ.get("BROCHURE_LIBREOFFICE")
    bundled = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice"
    candidates = [configured] if configured else [str(bundled), shutil.which("libreoffice"), shutil.which("soffice")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise RuntimeError("PDF 변환에 필요한 LibreOffice를 찾지 못했습니다. LibreOffice를 설치하거나 BROCHURE_LIBREOFFICE 경로를 지정한 뒤 PDF를 다시 시도하세요. DOCX는 유지됩니다.")


def _run_conversion(command, timeout):
    # LibreOffice launchers may spawn soffice.bin. A separate process session
    # lets a timeout stop the full converter tree rather than only its launcher.
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            process.communicate()
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def render_pdf(docx_path: Path, output_path: Path, timeout: int = 45) -> Path:
    """Convert an existing DOCX, publishing only a nonempty readable PDF.

    Every attempt has its own LibreOffice profile/output directory. No failure
    can replace the source DOCX or a previous complete PDF, so callers can retry.
    """
    docx_path, output_path = Path(docx_path), Path(output_path)
    if not docx_path.is_file():
        raise RuntimeError("DOCX 파일이 없습니다. DOCX를 먼저 생성한 뒤 PDF를 다시 시도하세요.")
    if docx_path.resolve() == output_path.resolve():
        raise ValueError("PDF 저장 경로는 DOCX 경로와 달라야 합니다.")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("PDF 변환 제한 시간은 0보다 커야 합니다.")
    executable = _libreoffice()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".brochure-pdf-", dir=output_path.parent) as directory:
        temporary = Path(directory).resolve()
        profile = temporary / "profile"
        profile.mkdir()
        command = [executable, "--headless", "--nologo", "--nodefault", "--nofirststartwizard", f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "pdf:writer_pdf_Export", "--outdir", str(temporary), str(docx_path.resolve())]
        try:
            result = _run_conversion(command, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"PDF 변환이 {timeout}초 제한 시간을 초과했습니다. DOCX를 내려받거나 PDF를 다시 시도하세요.") from error
        except OSError as error:
            raise RuntimeError("LibreOffice 실행에 실패했습니다. 설치와 실행 권한을 확인한 뒤 PDF를 다시 시도하세요. DOCX는 유지됩니다.") from error
        if result.returncode != 0:
            raise RuntimeError("LibreOffice PDF 변환에 실패했습니다. DOCX를 내려받거나 PDF를 다시 시도하세요.")
        generated = temporary / (docx_path.stem + ".pdf")
        if not generated.is_file() or generated.stat().st_size == 0:
            raise RuntimeError("PDF 파일이 생성되지 않았습니다. LibreOffice 설치를 확인하고 PDF를 다시 시도하세요. DOCX는 유지됩니다.")
        try:
            with generated.open("rb") as stream:
                if stream.read(5) != b"%PDF-":
                    raise ValueError("missing PDF signature")
            reader = PdfReader(generated, strict=True)
            if reader.is_encrypted or not reader.pages:
                raise ValueError("empty or encrypted PDF")
        except Exception as error:
            raise RuntimeError("생성된 PDF를 읽을 수 없습니다. DOCX는 유지되며 PDF를 다시 시도할 수 있습니다.") from error
        generated.replace(output_path)
    return output_path
