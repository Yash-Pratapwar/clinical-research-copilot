"""Extract PDF and DOCX contents with traceable source locations."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from .config import MAX_FILE_BYTES
from .pdf_layout import parse_pdf_layout


@dataclass(frozen=True)
class DocumentPart:
    text: str
    filename: str
    file_type: str
    section: str
    location: str
    page: int  # 0 for DOCX: original physical page cannot be established reliably
    section_id: str = ""
    paragraph_index: int = 0
    bbox: tuple[float, ...] = ()
    block_type: str = "paragraph"
    table_rows: tuple[tuple[str, ...], ...] = ()


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


def _load_pdf(filename: str, payload: bytes) -> list[DocumentPart]:
    parts: list[DocumentPart] = []
    heading = "Unsectioned text"
    section_number = 0
    heading_id = "section-000000"
    try:
        with pymupdf.open(stream=payload, filetype="pdf") as pdf:
            if pdf.is_encrypted:
                raise ValueError("Password-protected PDFs are not supported.")
            for page_index, items in enumerate(parse_pdf_layout(pdf)):
                for item in items:
                    if item.kind == "heading":
                        heading = item.text[:110]
                        section_number += 1
                        heading_id = f"section-{section_number:06d}"
                    parts.append(DocumentPart(
                        text=item.text, filename=filename, file_type="pdf",
                        section=heading, location=f"Page {page_index + 1}",
                        page=page_index + 1, section_id=heading_id,
                        bbox=item.bbox, block_type=item.kind, table_rows=item.rows))
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
    section_number = 0
    for block in _iter_docx_blocks(document):
        if isinstance(block, Paragraph):
            paragraph_number += 1
            text = _tidy(block.text)
            if not text:
                continue
            is_heading = block.style is not None and block.style.name.lower().startswith("heading")
            if is_heading:
                heading = text[:110]
                section_number += 1
            parts.append(DocumentPart(text=text, filename=filename, file_type="docx",
                                      section=heading, location=f"Paragraph {paragraph_number}", page=0,
                                      section_id=f"section-{section_number:06d}",
                                      block_type="heading" if is_heading else "paragraph"))
        else:
            rows = [" | ".join(_tidy(cell.text) for cell in row.cells)
                    for row in block.rows]
            content = "\n".join(r for r in rows if r.strip(" |"))
            if content:
                parts.append(DocumentPart(text=content, filename=filename, file_type="docx",
                                          section=heading, location=f"Table near paragraph {paragraph_number}", page=0,
                                          section_id=f"section-{section_number:06d}", block_type="table",
                                          table_rows=tuple(tuple(_tidy(c.text) for c in row.cells)
                                                           for row in block.rows)))
    if not parts:
        raise ValueError("No readable text found in the DOCX.")
    return parts


def extract_document(filename: str, payload: bytes) -> list[DocumentPart]:
    ext = validate_upload(filename, payload)
    parts = _load_pdf(filename, payload) if ext == ".pdf" else _load_docx(filename, payload)
    section_number = 0
    previous = None
    ordered = []
    for position, part in enumerate(parts, 1):
        identity = part.section_id or part.section
        if identity != previous:
            section_number += 1
            previous = identity
        ordered.append(replace(part, section_id=f"section-{section_number:06d}",
                               paragraph_index=position))
    return ordered
