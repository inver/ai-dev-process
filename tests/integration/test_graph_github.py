import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipeline.graph import build_graph


@pytest.fixture
def github_initial_state():
    return {
        "issue_iid": 7,
        "project_id": "myorg/myrepo",
        "project_path": "myorg/myrepo",
        "trigger_type": "analysis",
        "issue_title": "", "issue_description": "", "issue_labels": [],
        "issue_comments": [], "readme_content": "", "file_tree": "",
        "max_iterations": 3,
        "iteration_timeout_seconds": 600,
        "iteration": 0, "iteration_start_time": "",
        "current_analysis": "", "current_analysis_structured": {},
        "review_result": None, "analysis_history": [],
        "approved": False, "status": "analyzing", "failure_reason": None,
        "branch_name": "feature/7",
        "artifact_json_url": None, "artifact_md_url": None, "gitlab_comment_id": None,
    }


async def test_github_pipeline_happy_path(github_initial_state, monkeypatch):
    monkeypatch.setenv("PLATFORM", "github")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    monkeypatch.setenv("GITHUB_OWNER", "myorg")
    monkeypatch.setenv("GITHUB_REPO", "myrepo")
    monkeypatch.setenv("GITLAB_TOKEN", "")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "")

    mock_client = MagicMock()
    mock_client.get_issue = AsyncMock(return_value={
        "iid": 7, "title": "Test", "description": "desc", "labels": ["analysis_todo"]
    })
    mock_client.get_issue_comments = AsyncMock(return_value=[])
    mock_client.list_repository_tree = AsyncMock(return_value=[])
    mock_client.get_file_content = AsyncMock(return_value="")
    mock_client.branch_exists = AsyncMock(return_value=False)
    mock_client.create_branch = AsyncMock()
    mock_client.create_or_update_file = AsyncMock()
    mock_client.set_labels = AsyncMock()
    mock_client.update_issue_description = AsyncMock()
    mock_client.post_comment = AsyncMock(return_value={"id": 1})

    from src.models.analysis import AnalysisOutput
    from src.models.review import ReviewResult

    mock_analysis = AnalysisOutput(
        problem_statement="p", acceptance_criteria=["a"],
        technical_approach=["t"], dependencies=[], estimated_complexity="low",
    )
    mock_review = ReviewResult(
        approved=True, feedback="good", quality_score=9,
        missing_sections=[], concerns=[], suggestions=[],
    )

    with (
        patch("src.pipeline.nodes.build_forge_client", return_value=mock_client),
        patch("src.pipeline.nodes.run_claude_analysis", return_value=mock_analysis),
        patch("src.pipeline.nodes.run_codex_review", return_value=mock_review),
    ):
        graph = build_graph()
        final_state = await graph.ainvoke(github_initial_state)

    assert final_state["status"] == "approved"
    mock_client.post_comment.assert_called_once()
