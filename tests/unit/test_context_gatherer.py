import pytest
from unittest.mock import AsyncMock, MagicMock
from src.context.gatherer import ContextGatherer, build_file_tree_string


def test_build_file_tree_string():
    blobs = [
        {"path": "src/main.py"},
        {"path": "src/models/state.py"},
        {"path": "README.md"},
        {"path": ".gitignore"},
    ]
    result = build_file_tree_string(blobs)
    assert "src/main.py" in result or "main.py" in result
    assert "README.md" in result


@pytest.mark.asyncio
async def test_gather_returns_partial_state():
    mock_client = MagicMock()
    mock_client.get_issue = AsyncMock(return_value={
        "iid": 5, "title": "My Task", "description": "Do something",
        "labels": ["analysis_todo"],
    })
    mock_client.get_issue_comments = AsyncMock(return_value=[
        {"id": 1, "author": "alice", "body": "Please clarify", "created_at": "2026-06-01"}
    ])
    mock_client.get_file_content = AsyncMock(return_value="# My Project")
    mock_client.list_repository_tree = AsyncMock(return_value=[
        {"path": "README.md"}, {"path": "src/main.py"}
    ])

    gatherer = ContextGatherer(mock_client)
    state = await gatherer.gather(issue_iid=5)

    assert state["issue_title"] == "My Task"
    assert state["issue_description"] == "Do something"
    assert len(state["issue_comments"]) == 1
    assert "# My Project" in state["readme_content"]
    assert "main.py" in state["file_tree"]
