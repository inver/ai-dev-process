from datetime import datetime, timezone, timedelta
from src.pipeline.edges import route_after_review


def _state(approved: bool, iteration: int, elapsed_seconds: int = 0, max_iter: int = 3, timeout: int = 600):
    start = (datetime.now(timezone.utc) - timedelta(seconds=elapsed_seconds)).isoformat()
    return {
        "approved": approved,
        "iteration": iteration,
        "max_iterations": max_iter,
        "iteration_timeout_seconds": timeout,
        "iteration_start_time": start,
        "failure_reason": None,
    }


def test_approved_routes_to_finalize():
    assert route_after_review(_state(True, 1)) == "finalize"


def test_not_approved_within_budget_routes_to_revise():
    assert route_after_review(_state(False, 1)) == "revise"


def test_max_iterations_reached_routes_to_failed():
    assert route_after_review(_state(False, 3)) == "failed"


def test_timeout_routes_to_failed():
    result = route_after_review(_state(False, 1, elapsed_seconds=700, timeout=600))
    assert result == "failed"


def test_approved_on_last_iteration_still_finalizes():
    assert route_after_review(_state(True, 3)) == "finalize"
