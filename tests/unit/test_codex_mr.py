import json
from unittest.mock import MagicMock, mock_open, patch

from src.models.mr_review import MRReviewResult
from src.pipeline.codex_mr import run_codex_mr_review


def test_run_codex_mr_review_parses_output():
    review_data = {
        "approved": False,
        "quality_score": 5,
        "feedback": "Missing tests",
        "concerns": ["no tests"],
        "blocking_issues": ["add tests"],
        "suggestions": [],
    }
    mock_proc = MagicMock(returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=mock_proc), \
            patch("builtins.open", mock_open(read_data=json.dumps(review_data))), \
            patch("os.unlink"):
        result = run_codex_mr_review("system", "user")
    assert isinstance(result, MRReviewResult)
    assert not result.approved
    assert result.blocking_issues
