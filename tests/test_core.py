"""Offline tests (the Chroma integration tests use fake vectors, no downloads)."""
import io
from pathlib import Path

import pymupdf
import pytest
from docx import Document

from copilot.chunking import chunk_parts
from test_index import FakeTokenizer
from copilot.documents import DocumentPart, extract_document, validate_upload
from copilot.llm import sanitized_citations
from copilot.workflow import choose_tool


def test_routes():
    assert choose_tool('What are inclusion criteria?') == 'lookup'
    assert choose_tool('Summarize protocol') == 'summary'
    assert choose_tool('Compare protocol v1 vs v2') == 'compare'
    assert choose_tool('whats the differenc between version 1 and 2') == 'compare'
    assert choose_tool('What is the diffrence between v1 and v2?') == 'compare'
    assert choose_tool('How do version 1 and 2 differ?') == 'compare'
    assert choose_tool('Which monitoring deviations may impact patient safety?') == 'safety'


def test_chunks_preserve_page():
    parts = [DocumentPart('word ' * 340, 'protocol.pdf', 'pdf', '4.1 Inclusion', 'Page 3', 3)]
    chunks = chunk_parts(parts, size=100, overlap=20, tokenizer=FakeTokenizer())
    assert len(chunks) > 3
    assert all(c.page == 3 and c.location == 'Page 3' for c in chunks)
    assert chunks[0].token_count <= 100


def test_docx_paragraph_locations():
    d = Document()
    d.add_heading('Safety Reporting', level=1)
    d.add_paragraph('Serious adverse events are reported in 24 hours.')
    buf = io.BytesIO()
    d.save(buf)
    parts = extract_document('sample.docx', buf.getvalue())
    assert any(p.section == 'Safety Reporting' for p in parts)
    assert all(p.page == 0 and p.location.startswith('Paragraph ') for p in parts)


def test_pdf_page():
    p = pymupdf.open()
    page = p.new_page()
    page.insert_text((70, 80), '4.1 Inclusion Criteria')
    page.insert_text((70, 110), 'Patients must be 18 to 65 years.')
    content = p.tobytes()
    p.close()
    parts = extract_document('study.pdf', content)
    assert len(parts) >= 1
    assert all(p.page == 1 for p in parts)
    assert parts[0].section == '4.1 Inclusion Criteria'


def test_upload_validation():
    with pytest.raises(ValueError):
        validate_upload('malware.exe', b'MZ')
    with pytest.raises(ValueError):
        validate_upload('fake.pdf', b'not pdf')


def test_unknown_citations_removed():
    evidence = [object(), object()]
    assert sanitized_citations('Hello [S1] [S9]', evidence) == 'Hello [S1] '


def test_demo_files_exist():
    folder = Path(__file__).resolve().parents[1] / 'sample_docs'
    names = [p.name for p in folder.iterdir()]
    assert any(n.endswith('.pdf') for n in names)
    assert any(n.endswith('.docx') for n in names)
