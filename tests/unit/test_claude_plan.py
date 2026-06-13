import json
from unittest.mock import MagicMock, patch

from src.models.plan import PlanOutput
from src.pipeline.claude_plan import PLANNER_ALLOWED_TOOLS, run_claude_plan


def _make_payload(plan: dict) -> str:
    return json.dumps({
        "result": json.dumps(plan),
        "is_error": False,
        "session_id": "s1",
        "num_turns": 3,
        "duration_api_ms": 1000,
        "total_cost_usd": 0.01,
    })


def test_planner_allowed_tools():
    assert "Read" in PLANNER_ALLOWED_TOOLS
    assert "Edit" not in PLANNER_ALLOWED_TOOLS


def test_run_claude_plan_parses_output():
    plan_data = {
        "summary": "Add login",
        "tasks": [],
        "total_estimated_minutes": 0,
        "test_plan": [],
        "assumptions": [],
    }
    mock_proc = MagicMock(returncode=0, stdout=_make_payload(plan_data), stderr="")
    with patch("subprocess.run", return_value=mock_proc):
        result = run_claude_plan("system", "user")
    assert isinstance(result, PlanOutput)
    assert result.summary == "Add login"
