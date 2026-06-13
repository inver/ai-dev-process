from datetime import datetime, timezone


def route_after_review(state: dict) -> str:
    if state.get("approved"):
        return "finalize"

    start = datetime.fromisoformat(state["iteration_start_time"])
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()

    if elapsed > state["iteration_timeout_seconds"]:
        return "failed"
    if state["iteration"] >= state["max_iterations"]:
        return "failed"

    return "revise"
