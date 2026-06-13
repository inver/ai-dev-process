from src.pipeline.plan_edges import route_after_plan_review
from src.pipeline.plan_graph import build_plan_graph


def test_build_plan_graph_returns_compiled():
    graph = build_plan_graph()
    assert hasattr(graph, "invoke")


def test_route_approved():
    state = {
        "approved": True,
        "iteration": 1,
        "max_iterations": 3,
        "iteration_start_time": "2026-06-13T00:00:00+00:00",
        "iteration_timeout_seconds": 600,
    }
    assert route_after_plan_review(state) == "finalize"


def test_route_max_iterations():
    state = {
        "approved": False,
        "iteration": 3,
        "max_iterations": 3,
        "iteration_start_time": "2026-06-13T00:00:00+00:00",
        "iteration_timeout_seconds": 600,
    }
    assert route_after_plan_review(state) == "failed"


def test_route_revise():
    state = {
        "approved": False,
        "iteration": 1,
        "max_iterations": 3,
        "iteration_start_time": "2026-06-13T00:00:00+00:00",
        "iteration_timeout_seconds": 600000,
    }
    assert route_after_plan_review(state) == "revise"
