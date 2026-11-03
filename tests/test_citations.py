from types import SimpleNamespace

from copilot.citations import cited_saved_sources, source_citations


def test_only_cited_evidence_is_shown_without_renumbering():
    evidence = [SimpleNamespace(text=f'Data {i}', metadata={
        'filename': f'file{i}.pdf', 'location': f'Page {i}', 'section': 'Results',
    }) for i in range(1, 4)]
    sources = source_citations('Result [S3]. Repeated [S3]. Invalid [S9].', evidence)
    assert sources == [{'label': '[S3]', 'filename': 'file3.pdf',
                        'location': 'Page 3', 'section': 'Results', 'excerpt': 'Data 3'}]
    assert source_citations('No supported result.', evidence) == []


def test_saved_conversations_hide_uncited_sources():
    sources = [{'label': '[S1]'}, {'label': '[S2]'}]
    assert cited_saved_sources('Result [S2]', sources) == [sources[1]]
    assert cited_saved_sources('No evidence.', sources) == []
