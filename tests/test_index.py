"""Real Chroma client with an in-memory deterministic embedding model (no downloads)."""
import io

from docx import Document

from copilot.index import DocumentIndex


class FakeEmbeddings:
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
    assert len(index.list_files()) == 1
    assert '48 hours' in index.query('reporting requirements', threshold=-1)[0].text
    assert '24 hours' not in index.query('reporting requirements', threshold=-1)[0].text
    index.clear()
    assert index.list_files() == []
