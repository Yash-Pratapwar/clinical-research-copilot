from types import SimpleNamespace

from copilot.citations import cited_saved_sources, source_citations
import pytest


def test_only_cited_evidence_is_shown_without_renumbering():
    evidence = [SimpleNamespace(text=f'Data {i}', metadata={
        'filename': f'file{i}.pdf', 'location': f'Page {i}', 'section': 'Results',
    }) for i in range(1, 4)]
    sources = source_citations('Result [S3]. Repeated [S3]. Invalid [S9].', evidence)
    assert sources == [{'label': '[S3]', 'filename': 'file3.pdf',
                        'location': 'Page 3', 'section': 'Results', 'excerpt': 'Data 3'}]
    assert len(source_citations('Answer without source markers.', evidence)) == 3


def test_saved_conversations_hide_uncited_sources():
    sources = [{'label': '[S1]'}, {'label': '[S2]'}]
    assert cited_saved_sources('Result [S2]', sources) == [sources[1]]
    assert cited_saved_sources('Answer without source markers.', sources) == sources


@pytest.mark.parametrize('answer, count', [('Report within 24 hours [S2].', 1),
                                          ('Report within 24 hours.', 2)])
def test_citations_remain_visible_below_answer_with_or_without_markers(monkeypatch, answer, count):
    from pathlib import Path
    import streamlit as st
    from streamlit.testing.v1 import AppTest

    class Index:
        def list_files(self):
            return [{'filename': 'Used.pdf', 'chunks': 1}]

    class Workflow:
        def invoke(self, state):
            return {'answer': answer, 'mode': 'lookup',
                    'evidence': [SimpleNamespace(text='Unrelated retrieved data', metadata={
                        'filename': 'Unused.pdf', 'location': 'Page 1', 'section': 'Other'}),
                        SimpleNamespace(text='Report within 24 hours. Unused budget details.',
                                        metadata={'filename': 'Used.pdf', 'location': 'Page 2',
                                                  'section': 'Reporting'})]}

    st.cache_resource.clear()
    monkeypatch.setattr('copilot.index.DocumentIndex', Index)
    monkeypatch.setattr('copilot.workflow.make_graph', lambda index: Workflow())
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        app.chat_input[0].set_value('What is the reporting deadline?').run()
        for rerun in (False, True):
            if rerun:
                app.run()
            assert not app.exception
            message = app.chat_message[-1]
            assert message.markdown[0].value == answer
            assert len(message.expander) == 1
            assert message.expander[0].label == f'Source citations ({count})'
            assert message.expander[0].proto.expanded
            citations = message.expander[0]
            rendered = ' '.join(item.value for item in citations.markdown)
            assert 'Used.pdf' in rendered
            assert any('Page 2 · Reporting' == item.value for item in citations.caption)
            assert any('Report within 24 hours.' in item.value for item in citations.markdown)
            if count == 1:
                assert 'Unused.pdf' not in rendered
                assert not message.info
            else:
                assert 'Unused.pdf' in rendered
                assert any('did not mark' in item.value for item in message.info)
    finally:
        st.cache_resource.clear()
