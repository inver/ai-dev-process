from langgraph.graph import END, StateGraph

from src.models.mr_review import DevelopmentState
from src.pipeline.dev_edges import route_after_mr_review
from src.pipeline.dev_nodes import (
    develop_node,
    finalize_node,
    gather_context_node,
    handle_failure_node,
    review_mr_node,
    revise_node,
)


def build_dev_graph() -> StateGraph:
    builder = StateGraph(DevelopmentState)

    builder.add_node("gather_context", gather_context_node)
    builder.add_node("develop", develop_node)
    builder.add_node("review_mr", review_mr_node)
    builder.add_node("revise", revise_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("handle_failure", handle_failure_node)

    builder.set_entry_point("gather_context")
    builder.add_edge("gather_context", "develop")
    builder.add_edge("develop", "review_mr")
    builder.add_edge("revise", "review_mr")
    builder.add_conditional_edges(
        "review_mr",
        route_after_mr_review,
        {"finalize": "finalize", "revise": "revise", "failed": "handle_failure"},
    )
    builder.add_edge("finalize", END)
    builder.add_edge("handle_failure", END)

    return builder.compile()
