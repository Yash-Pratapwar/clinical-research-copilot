"""Transparent LangGraph tool-routing workflow (deterministic router, not an autonomous agent)."""
from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .index import DocumentIndex, Evidence
from .llm import answer_question
from .resolution import resolve_documents


class CopilotState(TypedDict, total=False):
    question: str
    mode: str
    evidence: list[Evidence]
    answer: str
    selected_documents: list[str]
    selection_confirmed: bool
    resolved_documents: list[str]
    candidates: list[str]
    clarification: str


def choose_tool(question: str) -> Literal["lookup", "summary", "compare", "safety"]:
    q = question.lower()
    if any(phrase in q for phrase in ("compare", "difference", "changed between", " vs ", " versus ", "amendment")):
        return "compare"
    if any(phrase in q for phrase in ("deviation", "patient safety", "safety impact", "safety risk", "monitoring observation", "monitoring visit")):
        return "safety"
    if any(phrase in q for phrase in ("summarize", "summary", "overview of the protocol", "study overview")):
        return "summary"
    return "lookup"


def make_graph(index: DocumentIndex):
    def router(state: CopilotState) -> CopilotState:
        mode = choose_tool(state["question"])
        resolution = resolve_documents(
            state['question'], [f['filename'] for f in index.list_files()],
            mode=mode, selected=state.get('selected_documents'),
            confirmed=state.get('selection_confirmed', False))
        return {"mode": mode, "resolved_documents": resolution.documents,
                "candidates": resolution.candidates, "clarification": resolution.clarification}

    def retrieve_for(mode: str):
        def _run(state: CopilotState) -> CopilotState:
            if state.get('clarification'):
                return {'evidence': []}
            return {"evidence": index.retrieve(state["question"], mode=mode,
                        filenames=state.get('resolved_documents') or None)}
        return _run

    def generate(state: CopilotState) -> CopilotState:
        if state.get('clarification'):
            return {'answer': state['clarification'] + '\n\nAvailable matches: ' + ', '.join(state['candidates'])}
        if state.get('resolved_documents'):
            present = {e.metadata['filename'] for e in state.get('evidence', [])}
            missing = set(state['resolved_documents']) - present
            if missing:
                return {'answer': 'Insufficient relevant evidence from: ' + ', '.join(sorted(missing)) +
                        '. Please check the indexed text or ask about a specific section.'}
        return {"answer": answer_question(state["question"], state.get("evidence", []), mode=state["mode"])}

    graph = StateGraph(CopilotState)
    graph.add_node("route", router)
    for label in ("lookup", "summary", "compare", "safety"):
        graph.add_node(label, retrieve_for(label))
        graph.add_edge(label, "generate")
    graph.add_node("generate", generate)
    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", lambda state: state["mode"],
                                {mode: mode for mode in ("lookup", "summary", "compare", "safety")})
    graph.add_edge("generate", END)
    return graph.compile()
