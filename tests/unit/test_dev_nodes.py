from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.mr_review import DeveloperOutput
from src.pipeline.dev_nodes import GitCommandError, _clone_repo, _commit_and_push, develop_node


def _settings():
    token = MagicMock()
    token.get_secret_value.return_value = "tok"
    return SimpleNamespace(
        platform="github",
        github_token=token,
        github_owner="owner",
        github_repo="repo",
        git_user_email="bot@example.com",
        git_user_name="Bot",
    )


def test_clone_repo_reuses_existing_remote_branch():
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if "ls-remote" in args:
            return SimpleNamespace(returncode=0, stdout="abc refs/heads/develop/1", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("src.pipeline.dev_nodes.tempfile.mkdtemp", return_value="/tmp/repo"), \
            patch("src.pipeline.dev_nodes.subprocess.run", side_effect=fake_run):
        repo_dir = _clone_repo(_settings(), "develop/1")

    assert repo_dir == "/tmp/repo"
    assert ["git", "-C", "/tmp/repo", "fetch", "origin", "develop/1"] in calls
    assert [
        "git", "-C", "/tmp/repo", "checkout", "-B", "develop/1", "origin/develop/1",
    ] in calls
    assert ["git", "-C", "/tmp/repo", "checkout", "-b", "develop/1"] not in calls


def test_commit_and_push_surfaces_push_stderr():
    def fake_run(args, **kwargs):
        if "diff" in args:
            return SimpleNamespace(returncode=0, stdout="src/app.py\n", stderr="")
        if "push" in args:
            return SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="! [rejected] develop/1 -> develop/1 (non-fast-forward)",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("src.pipeline.dev_nodes.subprocess.run", side_effect=fake_run):
        with pytest.raises(GitCommandError, match="non-fast-forward"):
            _commit_and_push("/tmp/repo", "develop/1", 1)


def test_commit_and_push_returns_false_when_no_changes():
    def fake_run(args, **kwargs):
        if "diff" in args:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch("src.pipeline.dev_nodes.subprocess.run", side_effect=fake_run):
        assert _commit_and_push("/tmp/repo", "develop/1", 1) is False


def _dev_state():
    return {
        "issue_iid": 1,
        "issue_title": "Fix issue",
        "issue_description": "desc",
        "issue_comments": [],
        "file_tree": "",
        "readme_content": "",
        "plan_content": "",
        "analysis_content": "",
        "dev_branch_name": "develop/1",
        "iteration": 0,
    }


@pytest.mark.asyncio
async def test_develop_node_fails_without_creating_pr_when_nothing_pushed():
    client = MagicMock()
    client.create_merge_request = AsyncMock()
    output = DeveloperOutput(implementation_summary="No changes needed")

    with patch("src.pipeline.dev_nodes.get_settings", return_value=_settings()), \
            patch("src.pipeline.dev_nodes._clone_repo", return_value="/tmp/missing-repo"), \
            patch("src.pipeline.dev_nodes.os.path.exists", return_value=False), \
            patch("src.pipeline.dev_nodes.run_claude_dev", return_value=output), \
            patch("src.pipeline.dev_nodes._commit_and_push", return_value=False), \
            patch("src.pipeline.dev_nodes.build_forge_client", return_value=client):
        result = await develop_node(_dev_state())

    assert result["status"] == "failed"
    assert "no pull request was created" in result["failure_reason"]
    client.create_merge_request.assert_not_called()


@pytest.mark.asyncio
async def test_develop_node_waits_for_branch_before_creating_pr():
    client = MagicMock()
    client.branch_exists = AsyncMock(return_value=True)
    client.create_merge_request = AsyncMock(return_value={"id": 10, "url": "https://example/pr/10"})
    output = DeveloperOutput(implementation_summary="Implemented")

    with patch("src.pipeline.dev_nodes.get_settings", return_value=_settings()), \
            patch("src.pipeline.dev_nodes._clone_repo", return_value="/tmp/missing-repo"), \
            patch("src.pipeline.dev_nodes.os.path.exists", return_value=False), \
            patch("src.pipeline.dev_nodes.run_claude_dev", return_value=output), \
            patch("src.pipeline.dev_nodes._commit_and_push", return_value=True), \
            patch("src.pipeline.dev_nodes.build_forge_client", return_value=client):
        result = await develop_node(_dev_state())

    assert result["status"] == "reviewing_mr"
    assert result["mr_id"] == 10
    client.branch_exists.assert_awaited_once_with("develop/1")
    client.create_merge_request.assert_awaited_once()
