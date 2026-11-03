"""Transparent LangGraph tool-routing workflow (deterministic router, not an autonomous agent)."""
from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .index import DocumentIndex, Evidence
from .llm import answer_question
from .resolution import resolve_documents
from .routing import detect_intent


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
    return detect_intent(question).mode


def make_graph(index: DocumentIndex):
    def router(state: CopilotState) -> CopilotState:
        intent = detect_intent(state["question"])
        mode = intent.mode
        resolution = resolve_documents(
            state['question'], [f['filename'] for f in index.list_files()],
            mode=mode, selected=state.get('selected_documents'),
            confirmed=state.get('selection_confirmed', False))
        clarification = resolution.clarification
        if intent.clarification and not state.get('selection_confirmed'):
            clarification = intent.clarification
        return {"mode": mode, "resolved_documents": resolution.documents,
                "candidates": resolution.candidates or resolution.documents,
                "clarification": clarification}

    def retrieve_for(mode: str):
        def _run(state: CopilotState) -> CopilotState:
            if state.get('clarification'):
                return {'evidence': []}
            if mode == "compare" and len(state.get("resolved_documents", [])) == 2 and hasattr(index, "compare_versions"):
                return {"evidence": []}
            return {"evidence": index.retrieve(state["question"], mode=mode,
                        filenames=state.get('resolved_documents') or None)}
        return _run

    def generate(state: CopilotState) -> CopilotState:
        if state.get('clarification'):
            return {'answer': state['clarification'] + '\n\nAvailable matches: ' + ', '.join(state['candidates'])}
        if state["mode"] == "compare" and len(state.get("resolved_documents", [])) == 2 and hasattr(index, "compare_versions"):
            versions = {v["label"]: v for v in index.list_versions()}
            left, right = [versions[name] for name in state["resolved_documents"]]
            try:
                changes = index.compare_versions(left["version_id"], right["version_id"])
            except ValueError as exc:
                return {"answer": str(exc)}
            heading = f'Comparing {left["label"]} to {right["label"]}.'
            if not changes:
                return {"answer": heading + "\n\nNo extracted text differences."}
            lines = [heading, "Exact extracted-text changes (review originals for layout and image changes):"]
            for change in changes:
                before, after = change["before"], change["after"]
                if change["ambiguous"]:
                    lines.append("Repeated content has multiple possible matches; review source locations.")
                lines.append(f'### {change["kind"].title()}: {(after or before)["section"]}')
                for label, part, version in (("Before", before, left), ("After", after, right)):
                    location = ", ".join(part["locations"]) if part else "Absent"
                    lines.append(f'**{label}: {version["label"]} - {location}**')
                    lines.append(part["text"] if part else "(Absent)")
                lines.append("~~~~diff\n" + change["diff"] + "\n~~~~")
            return {"answer": "\n\n".join(lines)}
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
