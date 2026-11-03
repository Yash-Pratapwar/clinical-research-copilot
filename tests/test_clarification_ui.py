from pathlib import Path

import streamlit as st
from streamlit.testing.v1 import AppTest

from copilot.index import Evidence


def test_clarification_selection_and_followup(monkeypatch):
    files = ['Manual_v1.pdf', 'Manual_v1_copy.pdf', 'Manual_v2.pdf']
    calls = []

    class Index:
        def list_files(self):
            return [{'filename': f, 'chunks': 1} for f in files]

        def retrieve(self, question, **kwargs):
            calls.append((question, kwargs['filenames']))
            return [Evidence('source text', {'filename': f, 'location': 'Page 1',
                             'section': 'Overview'}, 0.9, f) for f in kwargs['filenames']]

    st.cache_resource.clear()
    monkeypatch.setattr('copilot.index.DocumentIndex', Index)
    monkeypatch.setattr('copilot.workflow.answer_question', lambda *a, **k: 'Answer [S1] [S2]')
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        app.chat_input[0].set_value('Compare manual version 1 and 2').run()
        assert not app.exception
        assert not calls
        assert app.session_state['pending_question'] == 'Compare manual version 1 and 2'
        app.multiselect[0].set_value([files[1], files[2]])
        next(b for b in app.button if b.label == 'Answer using selected documents').click().run()
        assert not app.exception
        assert calls == [('Compare manual version 1 and 2', [files[1], files[2]])]
        app.chat_input[0].set_value('What about reporting requirements?').run()
        assert not app.exception
        assert calls[-1][1] == [files[1], files[2]]
        next(b for b in app.button if b.label == 'Search the whole library instead').click().run()
        assert not app.exception
        assert 'document_scope' not in app.session_state
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
