import json
from unittest.mock import MagicMock, mock_open, patch

from src.models.plan import PlanReviewResult
from src.pipeline.codex_plan import run_codex_plan_review


def test_run_codex_plan_review_parses_output():
    review_data = {
        "approved": True,
        "quality_score": 8,
        "feedback": "Good plan",
        "concerns": [],
        "missing_sections": [],
        "suggestions": [],
    }
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=mock_proc), \
            patch("builtins.open", mock_open(read_data=json.dumps(review_data))), \
            patch("os.unlink"):
        result = run_codex_plan_review("system", "user")
    assert isinstance(result, PlanReviewResult)
    assert result.approved
    assert result.quality_score == 8
