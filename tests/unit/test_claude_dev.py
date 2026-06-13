import json
from unittest.mock import MagicMock, patch

from src.models.mr_review import DeveloperOutput
from src.pipeline.claude_dev import DEVELOPER_ALLOWED_TOOLS, run_claude_dev


def _make_payload(dev_output: dict) -> str:
    return json.dumps({
        "result": json.dumps(dev_output),
        "is_error": False,
        "session_id": "s1",
        "num_turns": 10,
        "duration_api_ms": 5000,
        "total_cost_usd": 0.05,
    })


def test_developer_allowed_tools_has_write():
    assert "Edit" in DEVELOPER_ALLOWED_TOOLS
    assert "Write" in DEVELOPER_ALLOWED_TOOLS
    assert "Bash" in DEVELOPER_ALLOWED_TOOLS


def test_run_claude_dev_parses_output():
    dev_data = {
        "implementation_summary": "Added login",
        "files_modified": ["src/auth.py"],
        "files_created": [],
        "tests_run": True,
        "test_summary": "All pass",
        "open_questions": [],
    }
    mock_proc = MagicMock(returncode=0, stdout=_make_payload(dev_data), stderr="")
    with patch("subprocess.run", return_value=mock_proc):
        result = run_claude_dev("system", "user", repo_dir="/tmp/repo")
    assert isinstance(result, DeveloperOutput)
    assert result.tests_run
