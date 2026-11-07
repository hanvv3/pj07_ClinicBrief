#!/usr/bin/env python3
"""Create a standalone editable editorial preview; never touches app exports."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/editorial-preview"
ASSETS = OUT / "assets"
SOURCE_IMAGE = Path("/home/seanhan/.codex/generated_images/01a19ceb-5113-7552-91cc-a9305d76aeeb/exec-9e6639ec-4a2c-47d8-b35d-213dc6f1c51c.png")
IMAGE = ASSETS / "printer-reception-editorial.png"
DOCX = OUT / "printer-service-brief.docx"
FONT = "Noto Sans CJK KR"
INK = "243B32"
SAGE = "557063"
MUTED = "66726C"
SOURCE_URL = "https://support.microsoft.com/ko-kr/windows/hardware/printer/fix-printer-not-found-and-printer-not-recognized-errors-in-windows"
SOURCE_TITLE = "Windows에서 프린터를 찾을 수 없거나 인식되지 않는 오류 해결"
IMAGE_PROMPT = "Use case: photorealistic-natural. Asset type: a panoramic editorial photograph for the upper quarter of a Korean A4 print brochure about deciding when to contact printer service. Primary request: one unbranded compact laser printer on an uncluttered Korean neighborhood clinic reception desk. Natural daylight, realistic ordinary workplace, quiet warm cream and soft sage palette, subtle material texture. Composition: very wide panoramic landscape, approximately 3:1 aspect ratio; the whole compact printer is visible slightly right of center, with generous uncluttered desk and softly blurred background on both sides. Printer body in warm off-white with restrained dark gray details, physically plausible paper tray and a few blank white sheets. No people, no patient records, no readable text, no logos or brands, no monitors, no visible screen content, no medical equipment, no dramatic breakdown, no advertising polish. Soft editorial photography, restrained and credible, gentle shadows, eye-level three-quarter view. Do not add a title, caption, border or watermark. This is a fictional editorial scene, not evidence of an actual clinic or product."


def font_run(run, size=None, *, bold=False, color=None):
    run.font.name = FONT
    run._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    if size is not None:
        run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def paragraph(doc, text="", *, size=11, color=None, before=0, after=0, line=1.16, bold=False, style=None):
    p = doc.add_paragraph(style=style)
    f = p.paragraph_format
    f.space_before = Pt(before)
    f.space_after = Pt(after)
    f.line_spacing = Pt(size * line * 1.15)
    f.widow_control = True
    if text:
        font_run(p.add_run(text), size, bold=bold, color=color)
    return p


def hyperlink(p, text, url, size=8):
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), p.part.relate_to(url, RT.HYPERLINK, is_external=True))
    r = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts")
    for name in ("ascii", "hAnsi", "eastAsia"):
        fonts.set(qn(f"w:{name}"), FONT)
    props.append(fonts)
    color = OxmlElement("w:color")
    color.set(qn("w:val"), SAGE)
    props.append(color)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(size * 2)))
    props.append(sz)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    props.append(underline)
    r.append(props)
    t = OxmlElement("w:t")
    t.text = text
    r.append(t)
    link.append(r)
    p._p.append(link)


def step(doc, number, heading, body):
    p = paragraph(doc, before=8, after=3, line=1.08, style="Heading 1")
    p.paragraph_format.line_spacing = Pt(16)
    p.paragraph_format.keep_with_next = True
    font_run(p.add_run(number + "  "), 12, bold=True, color=SAGE)
    font_run(p.add_run(heading), 12, bold=True, color=INK)
    p = paragraph(doc, body, size=11, line=1.17)
    p.paragraph_format.keep_together = True


def callout(doc):
    table = doc.add_table(rows=1, cols=1)
    table.autofit = False
    table.columns[0].width = Mm(178)
    table.cell(0, 0).width = Mm(178)
    cell = table.cell(0, 0)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    props = cell._tc.get_or_add_tcPr()
    shade = OxmlElement("w:shd")
    shade.set(qn("w:fill"), "EFF3EE")
    props.append(shade)
    margins = OxmlElement("w:tcMar")
    for side, value in (("top", 150), ("bottom", 150), ("start", 180), ("end", 180)):
        item = OxmlElement(f"w:{side}")
        item.set(qn("w:w"), str(value))
        item.set(qn("w:type"), "dxa")
        margins.append(item)
    props.append(margins)
    borders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        edge = OxmlElement(f"w:{side}")
        edge.set(qn("w:val"), "nil")
        borders.append(edge)
    props.append(borders)
    row_props = table.rows[0]._tr.get_or_add_trPr()
    row_props.append(OxmlElement("w:cantSplit"))

    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.line_spacing = Pt(14)
    p.paragraph_format.keep_with_next = True
    font_run(p.add_run("웹 검색이 되는 AI에 이렇게 물어보세요"), 10.5, bold=True, color=INK)
    p = cell.add_paragraph()
    p.paragraph_format.line_spacing = Pt(14.5)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    font_run(p.add_run("프린터 모델은 [   ], 오류 문구는 [   ]입니다. 제조사 공식 안내에서 이 증상을 찾아 링크를 보여주세요. 직접 확인할 부분과 서비스 점검이 필요한 부분을 나누고, 확인되지 않은 원인은 추측하지 마세요."), 10.5, color=INK)
    p = cell.add_paragraph()
    p.paragraph_format.line_spacing = Pt(13)
    p.paragraph_format.space_after = Pt(0)
    font_run(p.add_run("답변의 링크를 열어 모델명과 증상을 확인하세요. 분해가 필요하거나 판단이 어렵다면 서비스 담당자에게 맡기세요."), 9.5, color=MUTED)


def build():
    ASSETS.mkdir(parents=True, exist_ok=True)
    if not IMAGE.exists():
        shutil.copy2(SOURCE_IMAGE, IMAGE)
    image_sha = hashlib.sha256(IMAGE.read_bytes()).hexdigest()
    provenance = {
        "asset": IMAGE.name,
        "created_at": "2026-11-03",
        "tool": "built-in image_gen.imagegen",
        "generation_count": 1,
        "prompt": IMAGE_PROMPT,
        "original_generated_file": str(SOURCE_IMAGE),
        "sha256": image_sha,
        "pixel_edits": "none; original image copied unchanged and embedded at its native 3:1 aspect ratio",
        "disclosure": "AI-generated fictional editorial scene; no actual clinic, product or case is represented",
    }
    (ASSETS / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin, sec.bottom_margin = Mm(13), Mm(13)
    sec.left_margin, sec.right_margin = Mm(16), Mm(16)
    sec.header_distance = Mm(5)
    sec.footer_distance = Mm(6)
    for grid in list(sec._sectPr.findall(qn("w:docGrid"))):
        sec._sectPr.remove(grid)
    normal = doc.styles["Normal"]
    normal.font.name = FONT
    normal.font.size = Pt(11)
    normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.line_spacing = 1.16
    for name in ("Title", "Heading 1"):
        style = doc.styles[name]
        style.font.name = FONT
        style.font.color.rgb = RGBColor.from_string(INK)
        style._element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FONT)
        for border in list(style._element.xpath("./w:pPr/w:pBdr")):
            border.getparent().remove(border)
    doc.core_properties.title = "프린터가 또 멈췄다. 이번에도 기사님부터 부를까요?"
    doc.core_properties.subject = "프린터 증상 기록과 서비스 비교를 위한 편집용 제안"
    doc.core_properties.author = "Brochure Lander 편집 시안"
    doc.core_properties.keywords = "편집 시안, 프린터, 서비스, AI 생성 이미지"

    paragraph(doc, "일하는 공간의 작은 점검  /  프린터", size=9, bold=True, color=SAGE, after=7)
    title = paragraph(doc, style="Title", after=7, line=1.08)
    title.paragraph_format.line_spacing = Pt(29)
    title.paragraph_format.keep_with_next = True
    font_run(title.add_run("프린터가 또 멈췄다."), 23, bold=True, color=INK)
    title.add_run().add_break(WD_BREAK.LINE)
    font_run(title.add_run("이번에도 기사님부터 부를까요?"), 23, bold=True, color=INK)
    intro = paragraph(doc, "급하면 기사님을 부르는 게 맞습니다. 다만 같은 일이 반복된다면,\n다음에 확인할 수 있도록 증상을 짧게 남겨두세요.", size=11, after=9, line=1.18)
    intro.paragraph_format.keep_with_next = True
    p = paragraph(doc, line=1, after=0)
    p.paragraph_format.line_spacing = 1
    p.paragraph_format.left_indent = Mm(0)
    p.paragraph_format.right_indent = Mm(0)
    p.paragraph_format.first_line_indent = Mm(0)
    p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(str(IMAGE), width=Mm(178))
    for edge in ("distT", "distB", "distL", "distR"):
        shape._inline.set(edge, "0")
    shape._inline.docPr.set("descr", "AI로 제작한 가상의 편집 이미지. 밝은 진료기관 접수대 위에 상표 없는 소형 프린터가 놓여 있다.")
    paragraph(doc, "AI로 제작한 편집 이미지 · 실제 기관이나 제품을 촬영한 사진이 아닙니다.", size=7.5, color=MUTED, before=3, after=0)

    step(doc, "01", "오류 메시지부터 적어두세요", "모델명, 오류 문구, 어느 컴퓨터에서 안 되는지 기록하세요.\n화면을 찍을 때는 환자 이름과 처방 내용이 나오지 않게 합니다.")
    step(doc, "02", "연결 문제인지 살펴보세요", "Windows에서 프린터를 못 찾는다면 전원과 USB 연결을 확인하세요.\nWi-Fi를 쓴다면 컴퓨터와 프린터가 같은 네트워크에 있는지 보세요.[1]\n설정 변경이나 드라이버 재설치는 관리 담당자와 진행하세요.")
    step(doc, "03", "수리비는 포함 항목까지 비교하세요", "건별 출장과 월 관리 비용을 비교할 때는 부품·소모품·방문 횟수·추가 요금을 함께 적어보세요.")
    p = paragraph(doc, before=8, after=8, size=9.5, color=MUTED)
    font_run(p.add_run("기록할 것  "), 9.5, bold=True, color=SAGE)
    font_run(p.add_run("□ 모델명   □ 오류 문구   □ 발생 시점   □ 반복 여부   □ 담당자"), 9.5, color=MUTED)
    callout(doc)

    p = paragraph(doc, before=8, size=7.5, color=MUTED, line=1.12, after=2)
    font_run(p.add_run("[1] Microsoft · "), 7.5, color=MUTED)
    hyperlink(p, SOURCE_TITLE, SOURCE_URL, 7.5)
    paragraph(doc, "원문 확인 2026.11.03 · 기록·비용 비교·AI 질문은 편집용 제안이며, Microsoft의 수리·비용 기준이 아닙니다.", size=7.5, color=MUTED, line=1.12)
    doc.save(DOCX)
    (OUT / "source-and-editorial-notes.json").write_text(json.dumps({
        "title": doc.core_properties.title,
        "purpose": "standalone designed brochure preview; no production application changes",
        "source": {"publisher": "Microsoft", "title": SOURCE_TITLE, "url": SOURCE_URL, "checked_at": "2026-11-03", "supported_claim": "For Windows printer-not-found/unrecognized errors, check power/USB connections or the same Wi-Fi network."},
        "editorial_proposals": ["symptom record", "avoid patient details in screenshots", "consult the responsible manager before settings or driver changes", "compare per-visit/monthly contract inclusions", "AI search prompt and verification step"],
        "case_policy": "No user-specific symptom, cost, diagnosis, repair cause or service contact has been invented.",
        "typography": {"body_pt": 11, "font": FONT, "page": "A4", "image_ratio": "3:1"},
        "image_provenance": "assets/provenance.json",
        "pdf_method": "same DOCX converted by packaged render_docx.py / LibreOffice; no separate PDF composition",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(DOCX)


if __name__ == "__main__":
    build()
