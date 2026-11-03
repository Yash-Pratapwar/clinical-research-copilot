"""Transparent LangGraph tool-routing workflow (deterministic router, not an autonomous agent)."""
from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .index import DocumentIndex, Evidence
from .llm import answer_question


class CopilotState(TypedDict, total=False):
    question: str
    mode: str
    evidence: list[Evidence]
    answer: str


def choose_tool(question: str) -> Literal["lookup", "summary", "compare", "safety"]:
    q = question.lower()
    if any(phrase in q for phrase in ("compare", "difference between", "changed between", "v1 vs", "v2 vs", "amendment")):
        return "compare"
    if any(phrase in q for phrase in ("deviation", "patient safety", "safety impact", "safety risk", "monitoring observation", "monitoring visit")):
        return "safety"
    if any(phrase in q for phrase in ("summarize", "summary", "overview of the protocol", "study overview")):
        return "summary"
    return "lookup"


def make_graph(index: DocumentIndex):
    def router(state: CopilotState) -> CopilotState:
        return {"mode": choose_tool(state["question"])}

    def retrieve_for(mode: str):
        def _run(state: CopilotState) -> CopilotState:
            return {"evidence": index.retrieve(state["question"], mode=mode)}
        return _run

    def generate(state: CopilotState) -> CopilotState:
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
