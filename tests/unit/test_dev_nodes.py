from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.dev_nodes import GitCommandError, _clone_repo, _commit_and_push


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
