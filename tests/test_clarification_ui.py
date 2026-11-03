from pathlib import Path

import streamlit as st
import pytest
from streamlit.testing.v1 import AppTest

from copilot.index import Evidence


def test_rerun_uses_updated_workflow_factory(monkeypatch):
    class Index:
        def list_files(self):
            return [{'filename': 'Protocol.pdf', 'chunks': 1}]

    class Workflow:
        def __init__(self, answer):
            self.answer = answer

        def invoke(self, state):
            return {'answer': self.answer, 'mode': 'lookup'}

    st.cache_resource.clear()
    monkeypatch.setattr('copilot.index.DocumentIndex', Index)
    monkeypatch.setattr('copilot.workflow.make_graph', lambda index: Workflow('Old workflow'))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        app.chat_input[0].set_value('First question').run()
        assert not app.exception
        assert app.session_state['messages'][-1]['text'] == 'Old workflow'
        # Simulate the updated factory imported after a source-module reload.
        # Do not clear resource caches: the real app keeps its index cached.
        monkeypatch.setattr('copilot.workflow.make_graph', lambda index: Workflow('Updated workflow'))
        app.chat_input[0].set_value('Second question').run()
        assert not app.exception
        assert app.session_state['messages'][-1]['text'] == 'Updated workflow'
    finally:
        st.cache_resource.clear()


@pytest.mark.parametrize('question', [
    'Compare manual version 1 and 2',
    'whats the differenc between version 1 and 2',
])
def test_clarification_selection_and_followup(monkeypatch, question):
    files = ['Manual_v1.pdf', 'Manual_v1_copy.pdf', 'Manual_v2.pdf']
    calls = []

    class Index:
        def list_files(self):
            return [{'filename': f, 'chunks': 1} for f in files]

        def retrieve(self, question, **kwargs):
            calls.append((question, kwargs['filenames']))
            return [Evidence('source text', {'filename': f, 'location': 'Page 1',
                             'section': 'Overview'}, 0.9, f) for f in (kwargs['filenames'] or files)]

    st.cache_resource.clear()
    monkeypatch.setattr('copilot.index.DocumentIndex', Index)
    monkeypatch.setattr('copilot.workflow.answer_question', lambda *a, **k: 'Answer [S1] [S2]')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        app.chat_input[0].set_value(question).run()
        assert not app.exception
        assert not calls
        assert app.session_state['pending_question'] == question
        assert app.session_state['messages'][-1]['mode'] == 'compare'
        app.multiselect[0].set_value([files[1], files[2]])
        next(b for b in app.button if b.label == 'Answer using selected documents').click().run()
        assert not app.exception
        assert calls == [(question, [files[1], files[2]])]
        assert app.session_state['messages'][-1]['mode'] == 'compare'
        assert any(b.label == 'Deselect documents' for b in app.button)
        app.chat_input[0].set_value('What about reporting requirements?').run()
        assert not app.exception
        assert calls[-1][1] == [files[1], files[2]]
        assert any(b.label == 'Deselect documents' for b in app.button)
        app.session_state['pending_question'] = 'Compare versions'
        app.session_state['clarification_documents'] = [files[1], files[2]]
        next(b for b in app.button if b.label == 'Deselect documents').click().run()
        assert not app.exception
        assert 'document_scope' not in app.session_state
        assert 'pending_question' not in app.session_state
        assert 'clarification_documents' not in app.session_state
        app.chat_input[0].set_value('What are the reporting requirements?').run()
        assert not app.exception
        assert calls[-1][1] is None
    finally:
        st.cache_resource.clear()


def test_filename_reply_resumes_question(monkeypatch):
    files = ['Budget_v1.pdf', 'Budget_v1_copy.pdf', 'Budget_v2.pdf']
    calls = []

    class Index:
        def list_files(self):
            return [{'filename': f, 'chunks': 1} for f in files]

        def retrieve(self, question, **kwargs):
            calls.append(question)
            return [Evidence('text', {'filename': f, 'location': 'Page 1', 'section': 'Budget'},
                             0.9, f) for f in kwargs['filenames']]

    st.cache_resource.clear()
    monkeypatch.setattr('copilot.index.DocumentIndex', Index)
    monkeypatch.setattr('copilot.workflow.answer_question', lambda *a, **k: 'Answer')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        app.chat_input[0].set_value('Compare budget version 1 and 2').run()
        app.chat_input[0].set_value('Budget_v1_copy and Budget_v2').run()
        assert not app.exception
        assert calls == ['Compare budget version 1 and 2']
        assert app.session_state['document_scope'] == [files[1], files[2]]
    finally:
        st.cache_resource.clear()


def test_version_comparison_view(tmp_path, monkeypatch):
    from copilot.index import DocumentIndex
    from test_index import FakeEmbeddings, docx_bytes
    index = DocumentIndex(path=tmp_path / 'chroma', embedder=FakeEmbeddings())
    index.add_file('Protocol_v1.docx', docx_bytes('Report within 24 hours.'))
    index.add_file('Protocol_v2.docx', docx_bytes('Report within 48 hours.'))
    monkeypatch.setattr('copilot.index.DocumentIndex', lambda: index)
    st.cache_resource.clear()
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        assert not app.exception
        next(b for b in app.button if b.label == 'Compare complete versions').click().run()
        assert not app.exception
        texts = [item.value for item in app.text]
        assert any('24 hours' in text for text in texts)
        assert any('48 hours' in text for text in texts)
        app.chat_input[0].set_value('Compare Protocol_v1.docx and Protocol_v2.docx').run()
        assert not app.exception
        assert '24 hours' in app.session_state['messages'][-1]['text']
    finally:
        st.cache_resource.clear()
