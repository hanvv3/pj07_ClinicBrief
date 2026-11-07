#!/usr/bin/env python3
"""Export every reviewed example and check its audience and document structure.

Use --render-pages for the bundled DOCX renderer's PNG QA. Inspect every generated
page before accepting visual layout; this script cannot judge clipping or glyphs.
"""

from copy import deepcopy
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pypdf import PdfReader
from brochure.catalog import load_topics
from brochure.rendering import render_docx, render_pdf


def verify(topic, directory, render_pages):
    draft = deepcopy(topic)
    draft["brochure"]["sender"] = {"name": "", "contact": ""}
    draft["notes"]["export_boundary_sentinel"] = "PRIVATE_NOTES_MUST_NEVER_BE_EXPORTED"
    docx = render_docx(draft, directory / f"{topic['id']}.docx")
    pdf = render_pdf(docx, directory / f"{topic['id']}.pdf")
    with ZipFile(docx) as archive:
        xml = archive.read("word/document.xml")
        all_parts = "\n".join(archive.read(name).decode() for name in archive.namelist() if name.endswith(".xml"))
        relationships = ET.fromstring(archive.read("word/_rels/document.xml.rels"))
    document = ET.fromstring(xml)
    text = "".join(document.itertext())
    assert topic["brochure"]["title"] in text, "DOCX title missing"
    assert "PRIVATE_NOTES_MUST_NEVER_BE_EXPORTED" not in all_parts, "Private notes leaked"
    assert document.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"), "DOCX has no editable text"
    assert not document.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"), "Handout should use editable text"
    docx_links = {item.attrib["Target"] for item in relationships if item.attrib.get("TargetMode") == "External"}
    reader = PdfReader(pdf)
    assert 1 <= len(reader.pages) <= 2, f"Expected 1-2 pages, got {len(reader.pages)}"
    pdf_text = "".join(page.extract_text() for page in reader.pages)
    assert "제안" in pdf_text and "참고" in pdf_text, "Korean PDF text extraction failed"
    assert "PRIVATE_NOTES_MUST_NEVER_BE_EXPORTED" not in pdf_text, "Private notes leaked into PDF"
    pdf_links = {str(annotation.get_object().get("/A", {}).get("/URI", "")) for page in reader.pages for annotation in page.get("/Annots", [])}
    for source in topic["sources"]:
        assert source["url"] in docx_links, f"DOCX source link missing: {source['id']}"
        assert source["url"] in pdf_links, f"PDF source link missing: {source['id']}"
    result = {"id": topic["id"], "docx": str(docx), "pdf": str(pdf), "pages": len(reader.pages), "source_links": len(topic["sources"])}
    if render_pages:
        runtime = Path.home() / ".cache/codex-runtimes/codex-primary-runtime"
        renderer = runtime / "plugins/openai-primary-runtime/plugins/documents/skills/documents/render_docx.py"
        if not renderer.is_file():
            raise RuntimeError("Bundled document QA renderer not found; render the generated PDFs to PNGs with Poppler and inspect all pages.")
        environment = dict(os.environ)
        environment["PATH"] = str(runtime / "dependencies/bin/override") + os.pathsep + environment.get("PATH", "")
        qa_dir = directory / "qa" / topic["id"]
        subprocess.run([sys.executable, str(renderer), str(docx), "--output_dir", str(qa_dir)], check=True, env=environment, timeout=60)
        images = sorted(qa_dir.glob("page-*.png"))
        assert len(images) == len(reader.pages), "QA image count does not match PDF pages"
        result["qa_images"] = [str(path) for path in images]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/samples")
    parser.add_argument("--render-pages", action="store_true")
    args = parser.parse_args()
    directory = args.output_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    results = [verify(topic, directory, args.render_pages) for topic in load_topics()]
    (directory / "verification.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
