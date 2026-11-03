from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest


def test_chat_reset_preserves_index_and_clears_pending_question(monkeypatch):
    class Index:
        def list_files(self):
            return [{'filename': 'Protocol.pdf', 'chunks': 1}]

        def clear(self):
            pytest.fail('Chat controls must preserve indexed documents')

    st.cache_resource.clear()
    monkeypatch.setattr('copilot.index.DocumentIndex', Index)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py'), default_timeout=20)
    try:
        app.run()
        app.chat_input[0].set_value('Hello').run()
        app.selectbox(key='example_question').select('What can you do?').run()
        app.session_state['document_scope'] = ['Protocol.pdf']
        app.session_state['pending_question'] = 'Compare versions'
        app.session_state['clarification_documents'] = ['Protocol.pdf']
        app.run()
        assert not any(item.label == 'Clear chat' for item in app.sidebar.button)
        next(item for item in app.sidebar.button if item.label == 'New chat').click().run()
        assert not app.exception
        assert app.session_state['messages'] == []
        assert 'pending_question' not in app.session_state
        assert 'clarification_documents' not in app.session_state
        assert len(app.chat_message) == 0
        assert app.selectbox(key='example_question').value == 'Choose an example...'
        assert not any(item.label == 'Ask selected example' for item in app.button)
        assert app.session_state['document_scope'] == ['Protocol.pdf']
        assert any('1 document(s) indexed' in item.value for item in app.sidebar.markdown)
    finally:
        st.cache_resource.clear()
