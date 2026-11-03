"""Real, in-memory PDF fixtures validate layout and traceability without downloads."""
import json
from collections import Counter
from pathlib import Path
import re

import pymupdf
import pytest

from copilot.chunking import chunk_parts
from copilot.comparison import compare_parts, section_body_hash
from copilot.documents import extract_document
from copilot.pdf_layout import LayoutItem, _column_order, _paragraphs
from test_index import FakeEmbeddings, FakeTokenizer


def make_pdf(pages):
    with pymupdf.open() as document:
        for content in pages:
            page = document.new_page(width=600, height=800)
            content(page)
        return document.tobytes()


def test_wrapped_lines_merge_but_spaced_paragraphs_remain_separate():
    def draw(page):
        page.insert_text((50, 90), '4.1 Safety Reporting', fontsize=14, fontname='hebo')
        page.insert_text((50, 120), 'Report serious adverse events within', fontsize=11)
        page.insert_text((50, 134), '24 hours of first awareness.', fontsize=11)
        page.insert_text((50, 168), 'Record follow-up information in the', fontsize=11)
        page.insert_text((50, 182), 'trial safety record.', fontsize=11)
    parts = extract_document('layout.pdf', make_pdf([draw]))
    assert [p.text for p in parts] == ['4.1 Safety Reporting',
        'Report serious adverse events within 24 hours of first awareness.',
        'Record follow-up information in the trial safety record.']
    assert len({p.section_id for p in parts}) == 1
    assert [p.paragraph_index for p in parts] == [1, 2, 3]
    assert all(len(p.bbox) == 4 and p.page == 1 for p in parts)


def test_columns_read_down_left_then_down_right():
    def draw(page):
        for x, prefix in ((50, 'Left'), (340, 'Right')):
            page.insert_text((x, 120), prefix + ' first line continues', fontsize=11)
            page.insert_text((x, 134), prefix + ' second line.', fontsize=11)
    parts = extract_document('columns.pdf', make_pdf([draw]))
    assert [p.text for p in parts] == [
        'Left first line continues Left second line.',
        'Right first line continues Right second line.']


def test_spanning_heading_separates_column_regions():
    items = [LayoutItem('Top right', (340, 100, 480, 112)),
             LayoutItem('Top left', (50, 100, 190, 112)),
             LayoutItem('Full width heading', (50, 150, 550, 170)),
             LayoutItem('Bottom right', (340, 190, 480, 202)),
             LayoutItem('Bottom left', (50, 190, 190, 202))]
    assert [x.text for x in _column_order(items)] == [
        'Top left', 'Top right', 'Full width heading', 'Bottom left', 'Bottom right']


def test_repeated_margins_are_retained_but_excluded_from_search_and_diff():
    def draw(number):
        def content(page):
            page.insert_text((50, 32), 'Synthetic Study ABC', fontsize=10)
            page.insert_text((50, 120), 'Body text stays searchable.', fontsize=11)
            page.insert_text((50, 775), f'Page {number} of 2', fontsize=10)
        return content
    parts = extract_document('margins.pdf', make_pdf([draw(1), draw(2)]))
    assert sum(p.block_type == 'header' for p in parts) == 2
    assert sum(p.block_type == 'footer' for p in parts) == 2
    chunks = chunk_parts(parts, tokenizer=FakeTokenizer())
    assert not any('Synthetic Study' in c.text or 'Page ' in c.text for c in chunks)
    from dataclasses import asdict
    before = [asdict(p) for p in parts]
    after = [dict(p, text='Different footer') if p['block_type'] == 'footer' else p for p in before]
    assert compare_parts(before, after) == []


def test_single_page_margin_is_not_silently_removed():
    def draw(page):
        page.insert_text((50, 32), 'Important title', fontsize=11)
        page.insert_text((50, 120), 'Body text.', fontsize=11)
    parts = extract_document('one.pdf', make_pdf([draw]))
    assert parts[0].text == 'Important title'
    assert parts[0].block_type != 'header'


def test_list_items_keep_hanging_continuations_and_do_not_become_headings():
    def draw(page):
        page.insert_text((50, 120), '1. Obtain written consent before', fontsize=11)
        page.insert_text((64, 134), 'performing study procedures.', fontsize=11)
        page.insert_text((50, 148), '2. Record the consent date.', fontsize=11)
    parts = extract_document('list.pdf', make_pdf([draw]))
    assert [p.block_type for p in parts] == ['list_item', 'list_item']
    assert parts[0].text == '1. Obtain written consent before performing study procedures.'


def test_unnumbered_typographic_heading_and_indented_paragraph():
    def draw(page):
        page.insert_text((50, 90), 'Safety Reporting', fontsize=14, fontname='hebo')
        page.insert_text((50, 120), 'First paragraph.', fontsize=11)
        page.insert_text((66, 134), 'Indented new paragraph continues', fontsize=11)
        page.insert_text((50, 148), 'on the next line.', fontsize=11)
    parts = extract_document('indent.pdf', make_pdf([draw]))
    assert parts[0].block_type == 'heading'
    assert parts[-1].text == 'Indented new paragraph continues on the next line.'
    assert len(parts) == 3


def test_ruled_table_rows_preserved_without_duplicate_cell_text():
    def draw(page):
        for y in (100, 130, 160):
            page.draw_line((50, y), (350, y))
        for x in (50, 200, 350):
            page.draw_line((x, 100), (x, 160))
        for x, y, text in ((60, 120, 'Visit'), (210, 120, 'Day'),
                           (60, 150, 'Baseline'), (210, 150, '1')):
            page.insert_text((x, y), text, fontsize=11)
        page.insert_text((50, 200), 'Prose after table.', fontsize=11)
    parts = extract_document('table.pdf', make_pdf([draw]))
    tables = [p for p in parts if p.block_type == 'table']
    assert len(tables) == 1
    assert tables[0].table_rows == (('Visit', 'Day'), ('Baseline', '1'))
    assert sum(p.text.count('Baseline') for p in parts) == 1
    chunks = chunk_parts(parts, tokenizer=FakeTokenizer())
    table_chunk = next(c for c in chunks if c.block_type == 'table')
    assert 'Prose after table' not in table_chunk.text
    assert json.loads(table_chunk.source_regions)[0]['bbox'] == list(tables[0].bbox)


def test_normalized_hash_ignores_pdf_line_wraps():
    assert section_body_hash({'section': 'Safety', 'text': 'Safety\nReport within\n24 hours.'}) == section_body_hash(
        {'section': 'Safety', 'text': 'Safety\nReport within 24 hours.'})


def test_font_family_change_starts_a_new_paragraph():
    def draw(page):
        page.insert_text((50, 120), 'Normal paragraph.', fontsize=11, fontname='helv')
        page.insert_text((50, 134), 'Monospaced text block.', fontsize=11, fontname='cour')
    assert len(extract_document('font.pdf', make_pdf([draw]))) == 2


def test_quantity_at_start_of_sentence_is_not_a_heading():
    def draw(page):
        page.insert_text((50, 120), '18 years old is the minimum age', fontsize=11)
        page.insert_text((50, 134), 'for the study.', fontsize=11)
    parts = extract_document('age.pdf', make_pdf([draw]))
    assert len(parts) == 1
    assert parts[0].block_type == 'paragraph'


def test_table_detection_failure_keeps_native_text(monkeypatch):
    def draw(page):
        page.insert_text((50, 120), 'Do not discard this text.', fontsize=11)
    payload = make_pdf([draw])
    def fail(*args, **kwargs):
        raise ValueError('Detection unavailable')
    monkeypatch.setattr(pymupdf.Page, 'find_tables', fail)
    parts = extract_document('fallback.pdf', payload)
    assert parts[0].text == 'Do not discard this text.'


@pytest.mark.parametrize('path', sorted((Path(__file__).resolve().parents[1] / 'sample_docs').glob('*.pdf')),
                         ids=lambda path: path.name)
def test_all_sample_pdf_words_preserved(path):
    with pymupdf.open(path) as doc:
        source = Counter(re.findall(r'\S+', ' '.join(page.get_text('text') for page in doc)))
    parts = extract_document(path.name, path.read_bytes())
    parsed = Counter(re.findall(r'\S+', ' '.join(p.text for p in parts)))
    assert source == parsed


def test_pdf_extraction_upgrade_keeps_original_and_version_but_refreshes_derived_text(tmp_path):
    from copilot.index import DocumentIndex
    from copilot.pdf_layout import PDF_LAYOUT_SCHEMA
    def draw(page):
        page.insert_text((50, 120), 'A wrapped paragraph continues', fontsize=11)
        page.insert_text((50, 134), 'on this line.', fontsize=11)
    payload = make_pdf([draw])
    index = DocumentIndex(tmp_path / 'chroma', embedder=FakeEmbeddings())
    index.add_file('upgrade.pdf', payload)
    version = index.list_versions()[0]
    with index.store.connect() as db:
        db.execute("UPDATE contents SET parts='[]', extraction_schema='legacy-blocks'")
    reopened = DocumentIndex(tmp_path / 'chroma', embedder=FakeEmbeddings())
    assert reopened.list_versions()[0]['version_id'] == version['version_id']
    assert reopened.original_file(version['version_id']) == payload
    assert reopened.store.extraction_schema(version['sha256']) == PDF_LAYOUT_SCHEMA
    assert reopened.store.parts(version['version_id'])[0]['text'] == 'A wrapped paragraph continues on this line.'
    hit = reopened.query('wrapped', threshold=-1)[0]
    assert json.loads(hit.metadata['source_regions'])[0]['bbox']
