import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from src.pipeline import claude_code
from src.pipeline.claude_code import (
    run_claude_analysis,
    _extract_json,
    ClaudeCodeError,
)
from src.config import Settings


def _settings():
    return Settings(
        gitlab_token="x",
        gitlab_project_id="1",
        claude_code_oauth_token="oauth-tok",
    )


VALID_ANALYSIS = {
    "problem_statement": "Fix login",
    "acceptance_criteria": ["User can log in"],
    "technical_approach": ["Update auth"],
    "dependencies": [],
    "risks": [],
    "estimated_complexity": "low",
    "open_questions": [],
}


def test_extract_json_plain():
    assert json.loads(_extract_json(json.dumps(VALID_ANALYSIS)))["estimated_complexity"] == "low"


def test_extract_json_strips_fences_and_prose():
    fenced = "Here is the analysis:\n```json\n" + json.dumps(VALID_ANALYSIS) + "\n```\n"
    assert json.loads(_extract_json(fenced))["problem_statement"] == "Fix login"


def _mock_run(stdout="", returncode=0, stderr=""):
    return MagicMock(stdout=stdout, returncode=returncode, stderr=stderr)


def test_run_claude_analysis_parses_result():
    cli_output = json.dumps({"is_error": False, "result": json.dumps(VALID_ANALYSIS)})
    with patch("src.pipeline.claude_code.subprocess.run", return_value=_mock_run(stdout=cli_output)) as run:
        out = run_claude_analysis("SYS", "USER", settings=_settings())

    assert out.problem_statement == "Fix login"
    # OAuth token injected into the subprocess environment
    _, kwargs = run.call_args
    assert kwargs["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "oauth-tok"
    assert kwargs["input"] == "USER"


def test_run_claude_analysis_raises_on_nonzero_exit():
    with patch("src.pipeline.claude_code.subprocess.run",
               return_value=_mock_run(returncode=1, stderr="boom")):
        with pytest.raises(ClaudeCodeError):
            run_claude_analysis("SYS", "USER", settings=_settings())


def test_run_claude_analysis_raises_on_cli_error_payload():
    cli_output = json.dumps({"is_error": True, "result": "rate limited"})
    with patch("src.pipeline.claude_code.subprocess.run", return_value=_mock_run(stdout=cli_output)):
        with pytest.raises(ClaudeCodeError):
            run_claude_analysis("SYS", "USER", settings=_settings())


def test_run_claude_analysis_raises_on_bad_schema():
    cli_output = json.dumps({"is_error": False, "result": json.dumps({"foo": "bar"})})
    with patch("src.pipeline.claude_code.subprocess.run", return_value=_mock_run(stdout=cli_output)):
        with pytest.raises(ClaudeCodeError):
            run_claude_analysis("SYS", "USER", settings=_settings())


def test_run_claude_analysis_raises_when_cli_missing():
    with patch("src.pipeline.claude_code.subprocess.run", side_effect=FileNotFoundError()):
        with pytest.raises(ClaudeCodeError):
            run_claude_analysis("SYS", "USER", settings=_settings())
