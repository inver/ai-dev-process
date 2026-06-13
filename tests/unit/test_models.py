import operator
from typing import get_type_hints
from src.models.analysis import AnalysisOutput
from src.models.review import ReviewResult
from src.models.state import AnalysisState


def test_analysis_output_validates():
    out = AnalysisOutput(
        problem_statement="Fix login bug",
        acceptance_criteria=["User can log in"],
        technical_approach=["Update auth middleware"],
        dependencies=[],
        risks=[],
        estimated_complexity="low",
        open_questions=[],
    )
    assert out.estimated_complexity == "low"


def test_review_result_validates():
    r = ReviewResult(
        approved=True,
        feedback="Looks good",
        quality_score=8,
        missing_sections=[],
        concerns=[],
        suggestions=[],
    )
    assert r.approved is True
    assert 1 <= r.quality_score <= 10


def test_review_result_score_bounds():
    import pytest
    with pytest.raises(Exception):
        ReviewResult(
            approved=False, feedback="", quality_score=11,
            missing_sections=[], concerns=[], suggestions=[],
        )


def test_analysis_state_is_typeddict():
    # AnalysisState must be a TypedDict (keys inspectable)
    hints = get_type_hints(AnalysisState)
    assert "issue_iid" in hints
    assert "iteration" in hints
    assert "approved" in hints
