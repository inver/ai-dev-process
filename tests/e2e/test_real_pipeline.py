"""End-to-end tests using the real Claude Code and Codex CLIs.

Run with:
    RUN_REAL_TESTS=1 python3 -m pytest tests/e2e/ -v -s

No GitLab connection is required — the tests read the actual project files from
disk and construct the pipeline state directly.

Issue text used:
    Мигрируй на последнюю версию python и langchain
"""
import os
import subprocess
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Guard: skip unless explicitly opted in
# ---------------------------------------------------------------------------

RUN_REAL_TESTS = os.getenv("RUN_REAL_TESTS", "0") == "1"
real_only = pytest.mark.skipif(not RUN_REAL_TESTS, reason="set RUN_REAL_TESTS=1 to run")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parents[2]
EXAMPLES_DIR = Path(__file__).parent / "examples"

ISSUE_TITLE = "Мигрируй на последнюю версию python и langchain"
ISSUE_DESCRIPTION = ISSUE_TITLE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_tree() -> str:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _readme() -> str:
    path = PROJECT_ROOT / "README.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _settings():
    """Minimal Settings that satisfy required fields but don't touch GitLab."""
    from src.config import Settings
    return Settings(
        gitlab_token="unused-for-e2e",
        gitlab_project_id="0",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@real_only
def test_real_analysis(capsys):
    """Run Claude Code analyst against the real project files."""
    from src.pipeline.claude_code import run_claude_analysis
    from src.pipeline.prompts import ANALYST_SYSTEM, ANALYST_INITIAL

    prompt = ANALYST_INITIAL.format(
        issue_title=ISSUE_TITLE,
        issue_description=ISSUE_DESCRIPTION,
        comments_block="(no comments)",
        file_tree=_file_tree(),
        readme_content=_readme(),
    )

    analysis = run_claude_analysis(ANALYST_SYSTEM, prompt, settings=_settings())

    with capsys.disabled():
        print("\n--- Analysis ---")
        print(analysis.model_dump_json(indent=2))

    assert analysis.problem_statement, "problem_statement is empty"
    assert analysis.acceptance_criteria, "no acceptance_criteria"
    assert analysis.technical_approach, "no technical_approach"
    assert analysis.estimated_complexity in ("low", "medium", "high", "very_high")


@real_only
def test_real_review(capsys):
    """Run Codex reviewer against the pre-baked analysis in examples/analysis.json.

    Skips the analyst step entirely — useful for iterating on the reviewer
    without burning Claude Code credits.
    """
    from src.models.analysis import AnalysisOutput
    from src.pipeline.codex import run_codex_review
    from src.pipeline.prompts import REVIEWER_SYSTEM, REVIEWER_PROMPT

    analysis = AnalysisOutput.model_validate_json(
        (EXAMPLES_DIR / "analysis.json").read_text(encoding="utf-8")
    )

    review_prompt = REVIEWER_PROMPT.format(
        issue_title=ISSUE_TITLE,
        issue_description=ISSUE_DESCRIPTION,
        current_analysis=analysis.model_dump_json(),
    )
    review = run_codex_review(REVIEWER_SYSTEM, review_prompt, settings=_settings())

    with capsys.disabled():
        print("\n--- Review ---")
        print(review.model_dump_json(indent=2))

    assert 1 <= review.quality_score <= 10
    assert review.feedback
