"""Real Chroma client with an in-memory deterministic embedding model (no downloads)."""
import io

from docx import Document

from copilot.index import DocumentIndex


class FakeTokenizer:
    def encode(self, text, add_special_tokens=True):
        import re
        ids = re.findall(r"\w+|[^\w\s]", text)
        return ["CLS"] + ids + ["SEP"] if add_special_tokens else ids


class FakeEmbeddings:
    tokenizer = FakeTokenizer()
    max_seq_length = 256
    def embed(self, texts):
        # Pure test vectors, not a production model.
        import hashlib
        import math
        import re
        outputs = []
        for text in texts:
            vec = [0.0] * 32
            for word in re.findall(r"\w+", text.lower()):
                v = int(hashlib.sha256(word.encode()).hexdigest()[:8], 16)
                vec[v % 32] += 1.0
            magnitude = math.sqrt(sum(x*x for x in vec)) or 1.0
            outputs.append([x/magnitude for x in vec])
        return outputs


def docx_bytes(text):
    doc = Document()
    doc.add_heading('Safety Requirements', level=1)
    doc.add_paragraph(text)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


def test_index_deduplication_and_update(tmp_path):
    index = DocumentIndex(path=tmp_path / 'chroma', embedder=FakeEmbeddings())
    one = docx_bytes('Report serious adverse events within 24 hours to study sponsor.')
    count, added = index.add_file('Protocol.docx', one)
    assert added and count > 0
    assert index.add_file('Protocol.docx', one) == (0, False)
    assert len(index.list_files()) == 1
    matches = index.query('serious adverse events reporting', threshold=-1)
    assert matches[0].metadata['filename'] == 'Protocol.docx'
    assert matches[0].metadata['location'].startswith('Paragraph')

    two = docx_bytes('Report serious adverse events within 48 hours to study sponsor.')
    count, added = index.add_file('Protocol.docx', two)
    assert added and count > 0
    versions = index.list_versions()
    assert len(versions) == 2
    assert versions[0]['document_id'] == versions[1]['document_id']
    assert '24 hours' in index.query('reporting requirements', filename=versions[0]['label'], threshold=-1)[0].text
    assert '48 hours' in index.query('reporting requirements', filename=versions[1]['label'], threshold=-1)[0].text
    changes = index.compare_versions(versions[0]['version_id'], versions[1]['version_id'])
    assert changes[0]['kind'] == 'modified'
    assert '24 hours' in changes[0]['before']['text']
    assert '48 hours' in changes[0]['after']['text']
    index.clear()
    assert index.list_files() == []


def test_shared_content_and_explicit_identical_version(tmp_path):
    index = DocumentIndex(path=tmp_path / 'chroma', embedder=FakeEmbeddings())
    payload = docx_bytes('Report serious adverse events within 24 hours.')
    index.add_file('Protocol_v1.docx', payload)
    count = index.collection.count()
    first = index.list_versions()[0]
    index.add_file('Protocol_v2.docx', payload)
    index.add_file('Protocol_v2.docx', payload, document_id=first['document_id'], version_label='approved')
    versions = index.list_versions()
    assert len(versions) == 3
    assert len({v['sha256'] for v in versions}) == 1
    assert len({v['document_id'] for v in versions}) == 1
    assert index.collection.count() == count
    assert len(list(index.store.blobs.iterdir())) == 1
    for v in versions:
        assert index.original_file(v['version_id']) == payload
        hit = index.query('adverse events', filename=v['label'], threshold=-1)[0]
        assert hit.metadata['version_id'] == v['version_id']
        assert hit.metadata['filename'] == v['label']
    assert index.compare_versions(versions[0]['version_id'], versions[1]['version_id']) == []
    reopened = DocumentIndex(path=tmp_path / 'chroma', embedder=FakeEmbeddings())
    assert len(reopened.list_versions()) == 3


def test_exact_comparison_bypasses_retrieval_and_llm(tmp_path, monkeypatch):
    from copilot.workflow import make_graph
    index = DocumentIndex(path=tmp_path / 'chroma', embedder=FakeEmbeddings())
    index.add_file('Protocol_v1.docx', docx_bytes('Report within 24 hours.'))
    index.add_file('Protocol_v2.docx', docx_bytes('Report within 48 hours.'))
    monkeypatch.setattr(index, 'retrieve', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no retrieval')))
    monkeypatch.setattr('copilot.workflow.answer_question', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no model')))
    result = make_graph(index).invoke({'question': 'Compare Protocol_v1.docx and Protocol_v2.docx'})
    assert '24 hours' in result['answer'] and '48 hours' in result['answer']


def test_legacy_index_preserved_and_reupload_recovers_original(tmp_path):
    import hashlib
    import pytest
    from copilot.chunking import chunk_parts
    from copilot.documents import extract_document
    path = tmp_path / 'chroma'
    index = DocumentIndex(path=path, embedder=FakeEmbeddings())
    payload = docx_bytes('Original legacy text.')
    digest = hashlib.sha256(payload).hexdigest()
    chunks = chunk_parts(extract_document('Legacy.docx', payload))
    index.collection.add(ids=[f'{digest[:20]}_0'], documents=[chunks[0].text],
                         embeddings=FakeEmbeddings().embed([chunks[0].text]),
                         metadatas=[dict(filename='Legacy.docx', file_type='docx',
                                         section=chunks[0].section, location=chunks[0].location,
                                         page=0, sha256=digest)])
    reopened = DocumentIndex(path=path, embedder=FakeEmbeddings())
    legacy = reopened.list_versions()[0]
    assert not legacy['original']
    with pytest.raises(ValueError):
        reopened.original_file(legacy['version_id'])
    reopened.add_file('Legacy.docx', payload)
    assert reopened.original_file(legacy['version_id']) == payload
