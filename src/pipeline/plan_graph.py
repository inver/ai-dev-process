from langgraph.graph import END, START, StateGraph

from src.models.plan import PlanState
from src.pipeline.plan_edges import route_after_plan_review
from src.pipeline.plan_nodes import (
    finalize_node,
    gather_context_node,
    handle_failure_node,
    plan_node,
    review_node,
    revise_node,
)


def build_plan_graph() -> StateGraph:
    builder = StateGraph(PlanState)

    builder.add_node("gather_context", gather_context_node)
    builder.add_node("plan", plan_node)
    builder.add_node("review", review_node)
    builder.add_node("revise", revise_node)
    builder.add_node("finalize", finalize_node)
    builder.add_node("handle_failure", handle_failure_node)

    builder.add_edge(START, "gather_context")
    builder.add_edge("gather_context", "plan")
    builder.add_edge("plan", "review")
    builder.add_edge("revise", "review")
    builder.add_conditional_edges(
        "review",
        route_after_plan_review,
        {"finalize": "finalize", "revise": "revise", "failed": "handle_failure"},
    )
    builder.add_edge("finalize", END)
    builder.add_edge("handle_failure", END)

    return builder.compile()
