from langgraph.graph import StateGraph, END, START

from src.models.state import AnalysisState
from src.pipeline.edges import route_after_review
from src.pipeline.nodes import (
    gather_context_node,
    analyze_node,
    review_node,
    revise_node,
    finalize_node,
    handle_failure_node,
)


def build_graph() -> StateGraph:
    builder = StateGraph(AnalysisState)

    builder.add_node("gather_context", gather_context_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("review", review_node)
    builder.add_node("revise", revise_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("handle_failure", handle_failure_node)

    builder.add_edge(START, "gather_context")
    builder.add_edge("gather_context", "analyze")
    builder.add_edge("analyze", "review")
    builder.add_edge("revise", "review")
    builder.add_conditional_edges(
        "review",
        route_after_review,
        {"finalize": "finalize", "revise": "revise", "failed": "handle_failure"},
    )
    builder.add_edge("finalize", END)
    builder.add_edge("handle_failure", END)

    return builder.compile()
