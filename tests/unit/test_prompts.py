import pytest
from src.pipeline.prompts import (
    ANALYST_SYSTEM,
    ANALYST_INITIAL,
    ANALYST_REVISION,
    DEVELOPER_INITIAL,
    DEVELOPER_REVISION,
    DEVELOPER_SYSTEM,
    MR_REVIEWER_PROMPT,
    MR_REVIEWER_SYSTEM,
    PLANNER_INITIAL,
    PLANNER_REVISION,
    PLANNER_SYSTEM,
    PLAN_REVIEWER_PROMPT,
    PLAN_REVIEWER_SYSTEM,
    REVIEWER_SYSTEM,
    REVIEWER_PROMPT,
    format_comments,
)


@pytest.mark.parametrize("text,name", [
    (ANALYST_SYSTEM, "ANALYST_SYSTEM"),
    (ANALYST_INITIAL, "ANALYST_INITIAL"),
    (ANALYST_REVISION, "ANALYST_REVISION"),
    (REVIEWER_SYSTEM, "REVIEWER_SYSTEM"),
    (REVIEWER_PROMPT, "REVIEWER_PROMPT"),
])
def test_prompt_loaded_and_non_empty(text, name):
    assert isinstance(text, str), f"{name} should be a str"
    assert len(text.strip()) > 0, f"{name} must not be empty"


def test_format_comments_empty():
    assert format_comments([]) == "(no comments)"


def test_format_comments_single():
    comments = [{"author": "alice", "created_at": "2024-01-01", "body": "LGTM"}]
    result = format_comments(comments)
    assert result == "[alice at 2024-01-01]: LGTM"


def test_format_comments_multiple():
    comments = [
        {"author": "alice", "created_at": "2024-01-01", "body": "Looks good"},
        {"author": "bob", "created_at": "2024-01-02", "body": "Please revise"},
    ]
    result = format_comments(comments)
    lines = result.splitlines()
    assert len(lines) == 2
    assert "[alice at 2024-01-01]: Looks good" == lines[0]
    assert "[bob at 2024-01-02]: Please revise" == lines[1]


def test_new_prompts_load():
    for prompt in [
        PLANNER_SYSTEM,
        PLANNER_INITIAL,
        PLANNER_REVISION,
        PLAN_REVIEWER_SYSTEM,
        PLAN_REVIEWER_PROMPT,
        DEVELOPER_SYSTEM,
        DEVELOPER_INITIAL,
        DEVELOPER_REVISION,
        MR_REVIEWER_SYSTEM,
        MR_REVIEWER_PROMPT,
    ]:
        assert isinstance(prompt, str)
        assert len(prompt) > 20


def test_reviewer_system_prompts_format_with_quality_score():
    for prompt in [REVIEWER_SYSTEM, PLAN_REVIEWER_SYSTEM, MR_REVIEWER_SYSTEM]:
        rendered = prompt.format(min_quality_score=7)
        assert "quality_score" in rendered
        assert "{min_quality_score}" not in rendered
