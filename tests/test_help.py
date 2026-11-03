from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from copilot.help import general_response
from copilot.workflow import choose_tool, make_graph


@pytest.mark.parametrize('question', [
    'What can you do?', 'Hello! What can you do?',
    '  WHAT ARE YOUR CAPABILITIES? ', 'How do I use this app?', 'Hi!',
])
def test_help_bypasses_documents_and_generation(monkeypatch, question):
    class UnavailableIndex:
        def list_files(self):
            pytest.fail('Help must not resolve or retrieve documents')

    monkeypatch.setattr('copilot.workflow.answer_question',
                        lambda *a, **k: pytest.fail('Help must not call Ollama'))
    result = make_graph(UnavailableIndex()).invoke({'question': question})
    assert result['answer'] == general_response(question)
    assert result['mode'] == choose_tool(question) == 'help'
    assert result['evidence'] == []
    assert result['resolved_documents'] == []


@pytest.mark.parametrize('question', [
    'Hi, summarize Protocol.pdf', 'What can you do about deviations in Protocol.pdf?',
    'How do I use this medication?', 'What are the eligibility criteria?',
    'Write a birthday poem', 'What is in help.pdf?',
])
def test_other_questions_keep_document_routing(question):
    assert general_response(question) is None
    assert choose_tool(question) != 'help'


@pytest.mark.parametrize('indexed', [False, True])
def test_help_in_ui_preserves_document_context(monkeypatch, indexed):
    class Index:
        def list_files(self):
            return [{'filename': 'Protocol.pdf', 'chunks': 1}] if indexed else []

    st.cache_resource.clear()
    monkeypatch.setattr('copilot.index.DocumentIndex', Index)
    monkeypatch.setattr('copilot.workflow.make_graph',
                        lambda *a: pytest.fail('UI help must bypass workflow'))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        if indexed:
            app.session_state['document_scope'] = ['Protocol.pdf']
            app.session_state['pending_question'] = 'Compare versions'
        app.chat_input[0].set_value('What can you do?').run()
        assert not app.exception
        message = app.session_state['messages'][-1]
        assert message['mode'] == 'help'
        assert 'source citations' in message['text']
        assert message['sources'] == []
        if indexed:
            assert app.session_state['document_scope'] == ['Protocol.pdf']
            assert app.session_state['pending_question'] == 'Compare versions'
    finally:
        st.cache_resource.clear()
