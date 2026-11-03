"""Run with: python -m streamlit run app.py"""
from __future__ import annotations

import streamlit as st

from copilot.config import MODEL_NAME
from copilot.index import DocumentIndex
from copilot.workflow import make_graph

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

question = st.chat_input("Ask about your uploaded study documents...")
if not question and selection != "Choose an example...":
    if st.button("Ask selected example"):
        question = selection

if question:
    st.session_state.messages.append({"role": "user", "text": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        if not get_index().list_files():
            answer = "Upload and index at least one PDF or DOCX first."
            sources, mode = [], None
            st.info(answer)
        else:
            try:
                with st.spinner("Searching indexed evidence and asking local Ollama..."):
                    result = get_workflow().invoke({"question": question})
                answer, mode = result["answer"], result["mode"]
                sources = [{
                    "label": f"[S{i}]", "filename": ev.metadata["filename"],
                    "location": ev.metadata["location"], "section": ev.metadata["section"],
                    "score": ev.similarity, "excerpt": ev.text,
                } for i, ev in enumerate(result.get("evidence", []), 1)]
                st.markdown(answer)
                st.caption(f"Tool selected: `{mode}`")
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
                                      "sources": sources, "mode": mode})

st.divider()
st.caption("Citation references are retrieved metadata, not model-generated page numbers. Similarity is not a factuality score; verify claims in original documents.")
