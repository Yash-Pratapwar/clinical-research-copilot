"""Extract PDF and DOCX contents with traceable source locations."""
from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .config import MAX_FILE_BYTES


@dataclass(frozen=True)
class DocumentPart:
    text: str
    filename: str
    file_type: str
    section: str
    location: str
    page: int  # 0 for DOCX: original physical page cannot be established reliably


def validate_upload(filename: str, payload: bytes) -> str:
    """Reject unsupported extensions, oversize, and obvious wrong-content uploads."""
    ext = Path(filename).suffix.lower()
    if ext not in {".pdf", ".docx"}:
        raise ValueError("Only searchable PDF and Word (.docx) documents are supported.")
    if not payload:
        raise ValueError("File is empty.")
    if len(payload) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the 15 MB local-demo limit.")
    if ext == ".pdf" and not payload.lstrip().startswith(b"%PDF-"):
        raise ValueError("The file does not appear to be a valid PDF.")
    if ext == ".docx" and not payload.startswith(b"PK"):
        raise ValueError("The file does not appear to be a valid DOCX.")
    return ext


def _tidy(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s.replace("\x00", "")).strip()


def _section_heading(line: str) -> bool:
    txt = _tidy(line)
    # Keep only fairly short headings; normal sentences beginning with numerals are ignored.
    if len(txt) > 100:
        return False
    if re.match(r"^(?:section\s+)?\d+(?:\.\d+){0,3}\s*[:.)-]?\s+[A-Za-z]", txt, re.I):
        return True
    return False


def _load_pdf(filename: str, payload: bytes) -> list[DocumentPart]:
    parts: list[DocumentPart] = []
    heading = "Unsectioned text"
    try:
        with fitz.open(stream=payload, filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")
            for page_index, page in enumerate(pdf):
                text = page.get_text("text", sort=True).strip()
                if not text:
                    continue
                current_lines: list[str] = []
                current_section = heading

                def flush():
                    if current_lines:
                        parts.append(DocumentPart(
                            text="\n".join(current_lines), filename=filename,
                            file_type="pdf", section=current_section,
                            location=f"Page {page_index + 1}", page=page_index + 1,
                        ))

                for raw_line in text.splitlines():
                    line = _tidy(raw_line)
                    if not line:
                        continue
                    if _section_heading(line):
                        flush()
                        current_lines = [line]
                        current_section = line[:110]
                        heading = current_section
                    else:
                        current_lines.append(line)
                flush()
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"Unable to read PDF: {exc}") from exc
    if not parts:
        raise ValueError("No searchable text was found; scanned/image-only PDFs need OCR (not included).")
    return parts


def _iter_docx_blocks(doc: Document):
    """Paragraphs and tables in original body order."""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _load_docx(filename: str, payload: bytes) -> list[DocumentPart]:
    try:
        document = Document(BytesIO(payload))
    except Exception as exc:
        raise ValueError("Could not open the Word document.") from exc

    parts = []
    heading = "Unsectioned text"
    paragraph_number = 0
    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            paragraph_number += 1
            text = _tidy(block.text)
            if not text:
                continue
            if block.style is not None and block.style.name.lower().startswith("heading"):
                heading = text[:110]
            parts.append(DocumentPart(text=text, filename=filename, file_type="docx",
                                      section=heading, location=f"Paragraph {paragraph_number}", page=0))
        else:
            rows = [" | ".join(_tidy(cell.text) for cell in row.cells)
                    for row in block.rows]
            content = "\n".join(r for r in rows if r.strip(" |"))
            if content:
                parts.append(DocumentPart(text=content, filename=filename, file_type="docx",
                                          section=heading, location=f"Table near paragraph {paragraph_number}", page=0))
    if not parts:
        raise ValueError("No readable text found in the DOCX.")
    return parts


def extract_document(filename: str, payload: bytes) -> list[DocumentPart]:
    ext = validate_upload(filename, payload)
    if ext == ".pdf":
        return _load_pdf(filename, payload)
    return _load_docx(filename, payload)
