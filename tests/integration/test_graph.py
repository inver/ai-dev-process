import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.models.analysis import AnalysisOutput
from src.models.review import ReviewResult


def _mock_analysis():
    return AnalysisOutput(
        problem_statement="Fix login",
        acceptance_criteria=["User can log in with valid credentials"],
        technical_approach=["Update JWT middleware"],
        dependencies=["PyJWT"],
        risks=[],
        estimated_complexity="low",
        open_questions=[],
    )


def _mock_review(approved: bool):
    return ReviewResult(
        approved=approved, feedback="Good analysis" if approved else "Missing edge cases",
        quality_score=8 if approved else 4,
        missing_sections=[] if approved else ["edge cases"],
        concerns=[], suggestions=[],
    )


def _mock_client():
    mc = MagicMock()
    mc.get_issue = AsyncMock(return_value={
        "iid": 10, "title": "Fix login", "description": "Users can't log in",
        "labels": ["analysis_todo"],
    })
    mc.get_issue_comments = AsyncMock(return_value=[])
    mc.get_file_content = AsyncMock(return_value="# README")
    mc.list_repository_tree = AsyncMock(return_value=[])
    mc.set_labels = AsyncMock()
    mc.post_comment = AsyncMock(return_value={"id": 99})
    mc.branch_exists = AsyncMock(return_value=False)
    mc.create_branch = AsyncMock()
    mc.create_or_update_file = AsyncMock()
    mc.update_issue_description = AsyncMock()
    return mc


async def _run_graph(analyst_returns, reviewer_returns: list):
    from src.pipeline.graph import build_graph

    mock_client = _mock_client()
    review_iter = iter(reviewer_returns)

    initial_state = {
        "issue_iid": 10,
        "project_id": "123",
        "project_path": "group/repo",
        "trigger_type": "analysis",
        "issue_title": "", "issue_description": "", "issue_labels": [],
        "issue_comments": [], "readme_content": "", "file_tree": "",
        "max_iterations": 3, "iteration_timeout_seconds": 600,
        "iteration": 0, "iteration_start_time": "",
        "current_analysis": "", "current_analysis_structured": {},
        "review_result": None, "analysis_history": [],
        "approved": False, "status": "analyzing", "failure_reason": None,
        "branch_name": "feature/10",
        "artifact_json_url": None, "artifact_md_url": None, "gitlab_comment_id": None,
    }

    with patch("src.pipeline.nodes.build_forge_client", return_value=mock_client):
        with patch("src.pipeline.nodes.run_claude_analysis", return_value=analyst_returns):
            with patch("src.pipeline.nodes.run_codex_review") as mock_rv:
                mock_rv.side_effect = lambda sys, usr, settings=None: next(review_iter)
                graph = build_graph()
                return await graph.ainvoke(initial_state)


async def test_happy_path_approve_on_first_iteration():
    final = await _run_graph(
        analyst_returns=_mock_analysis(),
        reviewer_returns=[_mock_review(True)],
    )
    assert final["status"] == "approved"
    assert final["iteration"] == 1


async def test_approve_after_one_revision():
    final = await _run_graph(
        analyst_returns=_mock_analysis(),
        reviewer_returns=[_mock_review(False), _mock_review(True)],
    )
    assert final["status"] == "approved"
    assert final["iteration"] == 2


async def test_fails_after_max_iterations():
    final = await _run_graph(
        analyst_returns=_mock_analysis(),
        reviewer_returns=[_mock_review(False)] * 3,
    )
    assert final["status"] == "failed"
