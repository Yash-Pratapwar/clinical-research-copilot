"""Run with: python -m streamlit run app.py"""
from __future__ import annotations

import streamlit as st

from copilot.config import MODEL_NAME
from copilot.index import DocumentIndex
from copilot.workflow import make_graph
from copilot.resolution import named_documents

st.set_page_config(page_title="Clinical Research AI Copilot", page_icon="🧬", layout="wide")

@st.cache_resource(show_spinner=False)
def get_index() -> DocumentIndex:
    return DocumentIndex()

@st.cache_resource(show_spinner=False)
def get_workflow():
    return make_graph(get_index())

st.title("🧬 Clinical Research AI Copilot")
st.caption("100% local demo • PDF + DOCX • RAG citations • Multi-document reasoning • LangGraph routing")
st.warning("Research document support only — not clinical decision-making. Use synthetic / authorized documents only.", icon="⚠️")

with st.sidebar:
    st.header("Document library")
    st.caption(f"Local model: `{MODEL_NAME}`")
    st.caption("Embeddings and text are stored on this computer, not uploaded to a paid API.")
    uploaded = st.file_uploader("Upload PDF or DOCX documents", type=["pdf", "docx"],
                                accept_multiple_files=True)
    if st.button("Index selected documents", type="primary", use_container_width=True,
                 disabled=not uploaded):
        for item in uploaded or []:
            try:
                with st.spinner(f"Indexing {item.name} (first run downloads the embedding model)..."):
                    num_chunks, added = get_index().add_file(item.name, item.getvalue())
                if added:
                    st.success(f"Indexed {item.name}: {num_chunks} chunks")
                else:
                    st.info(f"Skipped duplicate: {item.name}")
            except Exception as exc:
                st.error(f"{item.name}: {exc}")

    files = get_index().list_files()
    st.write(f"**{len(files)} document(s) indexed**")
    for file in files:
        st.caption(f"📄 {file['filename']} · {file['chunks']} chunks")
    if st.button("Clear index and conversation", use_container_width=True):
        get_index().clear()
        st.session_state.pop("messages", None)
        st.session_state.pop("pending_question", None)
        st.session_state.pop("document_scope", None)
        st.session_state.pop("clarification_documents", None)
        st.rerun()
    st.divider()
    st.caption("This prototype has no authentication or access-control layer. Do not expose it publicly.")

st.subheader("Ask questions across your documents")
examples = [
    "What are the inclusion and exclusion criteria?",
    "What are the SAE reporting requirements?",
    "Which monitoring deviations may impact patient safety?",
    "Compare protocol version 1 and version 2.",
    "Summarize the study protocol.",
]
selection = st.selectbox("Example questions", ["Choose an example..."] + examples)

if "messages" not in st.session_state:
    st.session_state.messages = []
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if msg.get("sources"):
            with st.expander(f"Supporting excerpts ({len(msg['sources'])})"):
                for source in msg["sources"]:
                    st.markdown(f"**{source['label']} — {source['filename']}**")
                    st.caption(f"{source['location']} · {source['section']} · Similarity {source['score']:.2f}")
                    st.write(source["excerpt"])
        if msg.get("mode"):
            st.caption(f"Tool selected: `{msg['mode']}`")
        if msg.get('documents'):
            st.caption('Selected documents: ' + ', '.join(msg['documents']))

filenames = [f['filename'] for f in files]
scope = st.session_state.get('document_scope', [])
if scope:
    st.caption('Current document selection: ' + ', '.join(scope))
    if st.button('Search the whole library instead'):
        st.session_state.pop('document_scope', None)
        st.rerun()

resume_question = None
selection_confirmed = False
if st.session_state.get('pending_question'):
    st.info('Choose the documents for your unanswered question, or reply with their exact names.')
    with st.form('resolve_documents'):
        chosen = st.multiselect('Documents to use', filenames, key='clarification_documents')
        submitted = st.form_submit_button('Answer using selected documents')
    if submitted:
        if chosen:
            st.session_state.document_scope = chosen
            resume_question = st.session_state.pop('pending_question')
            selection_confirmed = True
        else:
            st.warning('Select at least one document.')
    if st.button('Cancel unanswered question'):
        st.session_state.pop('pending_question', None)
        st.rerun()

question = st.chat_input("Ask about your uploaded study documents...")
display_question = question
if question and st.session_state.get('pending_question'):
    named = named_documents(question, filenames)
    if named:
        # A filename reply resolves the original question instead of becoming
        # a new content question. New unrelated questions can still be asked.
        st.session_state.document_scope = named
        selection_confirmed = True
        question = st.session_state.pop('pending_question')
if resume_question:
    question = resume_question
    display_question = 'Use selected documents: ' + ', '.join(st.session_state.document_scope)
if not question and selection != "Choose an example...":
    if st.button("Ask selected example"):
        question = selection

if question:
    display_question = display_question or question
    st.session_state.messages.append({"role": "user", "text": display_question})
    with st.chat_message("user"):
        st.markdown(display_question)
    with st.chat_message("assistant"):
        documents = []
        if not get_index().list_files():
            answer = "Upload and index at least one PDF or DOCX first."
            sources, mode = [], None
            st.info(answer)
        else:
            try:
                with st.spinner("Searching indexed evidence and asking local Ollama..."):
                    result = get_workflow().invoke({"question": question,
                        "selected_documents": st.session_state.get('document_scope', []),
                        'selection_confirmed': selection_confirmed})
                answer, mode = result["answer"], result["mode"]
                documents = result.get('resolved_documents', [])
                if result.get('clarification'):
                    st.session_state.pending_question = question
                else:
                    st.session_state.pop('pending_question', None)
                    if documents:
                        st.session_state.document_scope = documents
                sources = [{
                    "label": f"[S{i}]", "filename": ev.metadata["filename"],
                    "location": ev.metadata["location"], "section": ev.metadata["section"],
                    "score": ev.similarity, "excerpt": ev.text,
                } for i, ev in enumerate(result.get("evidence", []), 1)]
                st.markdown(answer)
                st.caption(f"Tool selected: `{mode}`")
                if documents:
                    st.caption('Selected documents: ' + ', '.join(documents))
                if sources:
                    with st.expander(f"Supporting excerpts ({len(sources)})", expanded=True):
                        for source in sources:
                            st.markdown(f"**{source['label']} — {source['filename']}**")
                            st.caption(f"{source['location']} · {source['section']} · Similarity {source['score']:.2f}")
                            st.write(source["excerpt"])
            except Exception as exc:
                answer = f"**Error:** {exc}"
                st.error(answer)
                sources, mode = [], None
    st.session_state.messages.append({"role": "assistant", "text": answer,
                                      "sources": sources, "mode": mode, 'documents': documents})
    # Render the clarification controls immediately after the first response.
    if st.session_state.get('pending_question'):
        st.rerun()

st.divider()
st.caption("Citation references are retrieved metadata, not model-generated page numbers. Similarity is not a factuality score; verify claims in original documents.")
