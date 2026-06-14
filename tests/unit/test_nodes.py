import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.pipeline import nodes


def _base_state(**overrides) -> dict:
    state = {
        "issue_iid": 7,
        "project_id": "123",
        "project_path": "group/repo",
        "trigger_type": "analysis",
        "issue_title": "Add login",
        "issue_description": "Users need to log in",
        "issue_comments": [],
        "issue_labels": ["analysis_todo"],
        "readme_content": "# My App",
        "file_tree": "src/main.py",
        "max_iterations": 3,
        "iteration_timeout_seconds": 600,
        "iteration": 0,
        "iteration_start_time": "",
        "current_analysis": "",
        "current_analysis_structured": {},
        "review_result": None,
        "analysis_history": [],
        "approved": False,
        "status": "analyzing",
        "failure_reason": None,
        "branch_name": "feature/7",
        "artifact_json_url": None,
        "artifact_md_url": None,
        "gitlab_comment_id": None,
    }
    state.update(overrides)
    return state


async def test_gather_context_node_populates_state():
    from unittest.mock import patch, AsyncMock

    mock_client = MagicMock()
    mock_client.get_issue = AsyncMock(return_value={
        "iid": 7, "title": "Add login", "description": "Details",
        "labels": ["analysis_todo"],
    })
    mock_client.get_issue_comments = AsyncMock(return_value=[])
    mock_client.get_file_content = AsyncMock(return_value="# README")
    mock_client.list_repository_tree = AsyncMock(return_value=[])
    mock_client.branch_exists = AsyncMock(return_value=True)
    mock_client.create_branch = AsyncMock()

    with patch("src.pipeline.nodes.build_forge_client", return_value=mock_client):
        with patch("src.pipeline.nodes.get_settings") as mock_settings:
            mock_settings.return_value.platform = "gitlab"
            mock_settings.return_value.gitlab_url = "https://gitlab.com"
            mock_settings.return_value.gitlab_token.get_secret_value.return_value = "tk"
            mock_settings.return_value.gitlab_project_id = "123"
            mock_settings.return_value.gitlab_project_path = "group/repo"
            result = await nodes.gather_context_node(_base_state())

    assert result["issue_title"] == "Add login"
    assert result["status"] == "analyzing"


async def test_gather_context_node_creates_missing_branch():
    mock_client = MagicMock()
    mock_client.get_issue = AsyncMock(return_value={
        "iid": 7, "title": "Add login", "description": "Details",
        "labels": ["analysis_todo"],
    })
    mock_client.get_issue_comments = AsyncMock(return_value=[])
    mock_client.get_file_content = AsyncMock(return_value="# README")
    mock_client.list_repository_tree = AsyncMock(return_value=[])
    mock_client.branch_exists = AsyncMock(return_value=False)
    mock_client.create_branch = AsyncMock()

    with patch("src.pipeline.nodes.build_forge_client", return_value=mock_client):
        with patch("src.pipeline.nodes.get_settings") as mock_settings:
            mock_settings.return_value.platform = "gitlab"
            mock_settings.return_value.gitlab_url = "https://gitlab.com"
            mock_settings.return_value.gitlab_token.get_secret_value.return_value = "tk"
            mock_settings.return_value.gitlab_project_id = "123"
            mock_settings.return_value.gitlab_project_path = "group/repo"
            await nodes.gather_context_node(_base_state())

    mock_client.create_branch.assert_called_once()


def _settings_for_persist(mock_settings):
    mock_settings.return_value.gitlab_url = "https://gitlab.com"
    mock_settings.return_value.gitlab_project_path = "group/repo"
    mock_settings.return_value.min_review_quality_score = 7
    mock_settings.return_value.reviewer_model = "gpt-5.5"


def _written_paths(branch_manager) -> list:
    return [call.args[1] for call in branch_manager.write_artifact.call_args_list]


async def test_analyze_node_persists_iteration_snapshot():
    from src.models.analysis import AnalysisOutput
    analysis = AnalysisOutput.model_validate_json(json.dumps({
        "problem_statement": "Fix login",
        "acceptance_criteria": ["User can log in"],
        "technical_approach": ["Update auth"],
        "dependencies": [], "risks": [],
        "estimated_complexity": "low", "open_questions": [],
    }))

    with patch("src.pipeline.nodes.run_claude_analysis", return_value=analysis), \
         patch("src.pipeline.nodes.build_forge_client"), \
         patch("src.pipeline.nodes.get_settings") as mock_settings, \
         patch("src.pipeline.nodes.BranchManager") as MockBM:
        _settings_for_persist(mock_settings)
        bm = MockBM.return_value
        bm.write_artifact = AsyncMock()
        result = await nodes.analyze_node(_base_state(iteration=0))

    paths = _written_paths(bm)
    assert "analysis/7/analysis_iter1.json" in paths
    assert "analysis/7/analysis_iter1.md" in paths
    assert result["iteration"] == 1


async def test_revise_node_persists_iteration_snapshot():
    from src.models.analysis import AnalysisOutput
    analysis = AnalysisOutput.model_validate_json(json.dumps({
        "problem_statement": "Fix login v2",
        "acceptance_criteria": ["User can log in"],
        "technical_approach": ["Update auth"],
        "dependencies": [], "risks": [],
        "estimated_complexity": "low", "open_questions": [],
    }))
    state = _base_state(
        iteration=1,
        current_analysis='{"problem_statement": "Fix login"}',
        review_result={
            "approved": False, "feedback": "More detail", "quality_score": 5,
            "missing_sections": [], "concerns": ["thin"], "suggestions": [],
        },
    )

    with patch("src.pipeline.nodes.run_claude_analysis", return_value=analysis), \
         patch("src.pipeline.nodes.build_forge_client"), \
         patch("src.pipeline.nodes.get_settings") as mock_settings, \
         patch("src.pipeline.nodes.BranchManager") as MockBM:
        _settings_for_persist(mock_settings)
        bm = MockBM.return_value
        bm.write_artifact = AsyncMock()
        result = await nodes.revise_node(state)

    paths = _written_paths(bm)
    assert "analysis/7/analysis_iter2.json" in paths
    assert "analysis/7/analysis_iter2.md" in paths
    assert result["iteration"] == 2


async def test_review_node_persists_review_snapshot():
    from src.models.review import ReviewResult
    mock_result = ReviewResult(
        approved=True, feedback="Great", quality_score=9,
        missing_sections=[], concerns=[], suggestions=[],
    )
    state = _base_state(iteration=1, current_analysis='{"problem_statement": "x"}')

    with patch("src.pipeline.nodes.run_codex_review", return_value=mock_result), \
         patch("src.pipeline.nodes.build_forge_client"), \
         patch("src.pipeline.nodes.get_settings") as mock_settings, \
         patch("src.pipeline.nodes.BranchManager") as MockBM:
        _settings_for_persist(mock_settings)
        bm = MockBM.return_value
        bm.write_artifact = AsyncMock()
        result = await nodes.review_node(state)

    assert "analysis/7/review_iter1.json" in _written_paths(bm)
    assert result["approved"] is True


async def test_analyze_node_snapshot_failure_is_swallowed():
    from src.models.analysis import AnalysisOutput
    analysis = AnalysisOutput.model_validate_json(json.dumps({
        "problem_statement": "Fix login",
        "acceptance_criteria": [], "technical_approach": [],
        "dependencies": [], "risks": [],
        "estimated_complexity": "low", "open_questions": [],
    }))

    with patch("src.pipeline.nodes.run_claude_analysis", return_value=analysis), \
         patch("src.pipeline.nodes.build_forge_client"), \
         patch("src.pipeline.nodes.get_settings") as mock_settings, \
         patch("src.pipeline.nodes.BranchManager") as MockBM:
        _settings_for_persist(mock_settings)
        bm = MockBM.return_value
        bm.write_artifact = AsyncMock(side_effect=RuntimeError("GitLab 500"))
        result = await nodes.analyze_node(_base_state(iteration=0))

    # Intermediate write failed, but the node still produced its normal output.
    assert result["iteration"] == 1
    assert result["status"] == "reviewing"


async def test_analyze_node_increments_iteration():
    fake_output = json.dumps({
        "problem_statement": "Fix login",
        "acceptance_criteria": ["User can log in"],
        "technical_approach": ["Update auth"],
        "dependencies": [],
        "risks": [],
        "estimated_complexity": "low",
        "open_questions": [],
    })

    from src.models.analysis import AnalysisOutput
    analysis = AnalysisOutput.model_validate_json(fake_output)

    with patch("src.pipeline.nodes.run_claude_analysis", return_value=analysis) as mock_run, \
            patch("src.pipeline.nodes._persist_analysis_snapshot", new_callable=AsyncMock):
        result = await nodes.analyze_node(_base_state())

    mock_run.assert_called_once()
    assert result["iteration"] == 1
    assert result["status"] == "reviewing"
    assert "problem_statement" in result["current_analysis"]


async def test_review_node_sets_approved_and_appends_history():
    from src.models.review import ReviewResult
    mock_result = ReviewResult(
        approved=True, feedback="Great", quality_score=9,
        missing_sections=[], concerns=[], suggestions=[],
    )

    state = _base_state(
        iteration=1,
        current_analysis='{"problem_statement": "Fix login"}',
    )

    with patch("src.pipeline.nodes.run_codex_review", return_value=mock_result), \
            patch("src.pipeline.nodes._persist_review_snapshot", new_callable=AsyncMock):
        result = await nodes.review_node(state)

    assert result["approved"] is True
    assert len(result["analysis_history"]) == 1
    assert result["analysis_history"][0]["approved"] is True
