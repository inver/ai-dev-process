from src.pipeline.dev_edges import route_after_develop, route_after_mr_review
from src.pipeline.dev_graph import build_dev_graph


def test_build_dev_graph():
    graph = build_dev_graph()
    assert hasattr(graph, "invoke")


def test_route_approved():
    state = {
        "approved": True,
        "iteration": 1,
        "max_iterations": 3,
        "iteration_start_time": "2026-06-13T00:00:00+00:00",
        "iteration_timeout_seconds": 600,
    }
    assert route_after_mr_review(state) == "finalize"


def test_route_after_develop_failed():
    assert route_after_develop({"status": "failed"}) == "failed"


def test_route_after_develop_review():
    assert route_after_develop({"status": "developing"}) == "review_mr"


def test_route_revise():
    state = {
        "approved": False,
        "iteration": 1,
        "max_iterations": 3,
        "iteration_start_time": "2026-06-13T00:00:00+00:00",
        "iteration_timeout_seconds": 600000,
    }
    assert route_after_mr_review(state) == "revise"


def test_route_failed():
    state = {
        "approved": False,
        "iteration": 3,
        "max_iterations": 3,
        "iteration_start_time": "2026-06-13T00:00:00+00:00",
        "iteration_timeout_seconds": 600,
    }
    assert route_after_mr_review(state) == "failed"
