"""Paragraph boundaries, tokenizer limits, order and migration are behavioral contracts."""
import io
from dataclasses import replace

from docx import Document

from copilot.chunking import chunk_parts
from copilot.documents import DocumentPart, extract_document
from test_index import FakeTokenizer, FakeEmbeddings, docx_bytes


def paragraphs(texts, file_type='docx'):
    return [DocumentPart(text, 'Study.' + file_type, file_type, 'Safety',
                         f'Paragraph {i}', 0 if file_type == 'docx' else 1,
                         'section-1', i) for i, text in enumerate(texts, 1)]


def test_four_paragraphs_pack_two_at_a_time():
    parts = paragraphs(['one two three', 'four five six', 'seven eight nine', 'ten eleven twelve'])
    chunks = chunk_parts(parts, size=10, overlap=0, tokenizer=FakeTokenizer())
    assert [c.text for c in chunks] == ['one two three\n\nfour five six',
                                       'seven eight nine\n\nten eleven twelve']
    assert [(c.paragraph_start, c.paragraph_end) for c in chunks] == [(1, 2), (3, 4)]
    assert [c.chunk_index for c in chunks] == [0, 1]
    assert not any(c.paragraph_split for c in chunks)


def test_whole_paragraph_overlap_with_room_for_new_content():
    chunks = chunk_parts(paragraphs(['one two', 'three four', 'five six']),
                         size=6, overlap=4, tokenizer=FakeTokenizer())
    assert [c.text for c in chunks] == ['one two\n\nthree four', 'three four\n\nfive six']
    assert all(c.token_count <= 6 for c in chunks)


def test_long_paragraph_prefers_sentences_and_preserves_content():
    text = 'First sentence here. Second sentence here. Third sentence here.'
    chunks = chunk_parts(paragraphs([text]), size=7, overlap=0, tokenizer=FakeTokenizer())
    assert [c.text for c in chunks] == [
        'First sentence here.', 'Second sentence here.', 'Third sentence here.']
    assert all(c.paragraph_split and c.paragraph_start == c.paragraph_end == 1 for c in chunks)


def test_wordpieces_and_long_unbroken_words_fit_actual_token_budget():
    class CharacterTokenizer:
        def encode(self, text, add_special_tokens=True):
            return list(text) + (['CLS', 'SEP'] if add_special_tokens else [])
    text = 'abcdefghijklmnopqrstuvwxyz'
    chunks = chunk_parts(paragraphs([text]), size=10, overlap=0, tokenizer=CharacterTokenizer())
    assert ''.join(c.text for c in chunks) == text
    assert all(c.token_count <= 10 for c in chunks)


def test_chunks_never_cross_sections_documents_or_pdf_pages():
    parts = paragraphs(['one two', 'three four'], 'pdf')
    parts[1] = replace(parts[1], page=2)
    assert len(chunk_parts(parts, size=20, overlap=0, tokenizer=FakeTokenizer())) == 2
    parts = paragraphs(['one two', 'three four'])
    parts[1] = replace(parts[1], section_id='section-2')
    assert len(chunk_parts(parts, size=20, overlap=0, tokenizer=FakeTokenizer())) == 2


def test_parser_reading_order_includes_tables_and_repeated_headings():
    doc = Document()
    doc.add_heading('Safety', 1)
    doc.add_paragraph('First paragraph.')
    doc.add_table(rows=1, cols=1).cell(0, 0).text = 'Table text.'
    doc.add_heading('Safety', 1)
    doc.add_paragraph('Second paragraph.')
    output = io.BytesIO()
    doc.save(output)
    parts = extract_document('Study.docx', output.getvalue())
    assert [p.paragraph_index for p in parts] == [1, 2, 3, 4, 5]
    assert parts[0].section_id != parts[-1].section_id
    assert parts[2].text == 'Table text.'


def test_rechunk_keeps_versions_originals_and_full_comparison_text(tmp_path):
    from copilot.index import DocumentIndex
    path = tmp_path / 'chroma'
    index = DocumentIndex(path=path, embedder=FakeEmbeddings())
    index.add_file('Study.docx', docx_bytes('Report within 24 hours.'))
    version = index.list_versions()[0]
    original_parts = index.store.parts(version['version_id'])
    with index.store.connect() as db:
        db.execute("UPDATE contents SET chunk_schema='legacy-words'")
    reopened = DocumentIndex(path=path, embedder=FakeEmbeddings())
    assert reopened.list_versions()[0]['version_id'] == version['version_id']
    assert reopened.store.parts(version['version_id']) == original_parts
    assert reopened.original_file(version['version_id']) == index.original_file(version['version_id'])
    evidence = reopened.query('report', threshold=-1)[0]
    assert evidence.metadata['section_id'].startswith(version['version_id'] + ':')
    assert evidence.metadata['paragraph_start'] > 0
    assert evidence.metadata['token_count'] <= 256
    assert reopened.collection.count() == reopened.list_versions()[0]['chunks']
