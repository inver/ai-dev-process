import pytest
import respx
import httpx
from src.gitlab.client import GitLabClient, GitLabAPIError


BASE = "https://gitlab.com/api/v4/projects/123"


@pytest.fixture
def client():
    return GitLabClient(
        gitlab_url="https://gitlab.com",
        token="test-token",
        project_id="123",
    )


@respx.mock
def test_get_issue_returns_dict(client):
    respx.get(f"{BASE}/issues/1").mock(
        return_value=httpx.Response(200, json={
            "iid": 1, "title": "Fix bug", "description": "Details",
            "labels": [{"name": "analysis_todo"}],
        })
    )
    import asyncio
    issue = asyncio.run(client.get_issue(1))
    assert issue["title"] == "Fix bug"
    assert issue["labels"] == ["analysis_todo"]


@respx.mock
def test_get_issue_raises_on_404(client):
    respx.get(f"{BASE}/issues/99").mock(return_value=httpx.Response(404))
    import asyncio
    with pytest.raises(GitLabAPIError) as exc:
        asyncio.run(client.get_issue(99))
    assert exc.value.status_code == 404


@respx.mock
def test_set_labels(client):
    route = respx.put(f"{BASE}/issues/1").mock(return_value=httpx.Response(200, json={}))
    import asyncio
    asyncio.run(client.set_labels(1, ["analysis_processed"]))
    assert route.called
    sent_json = route.calls.last.request.read()
    import json
    body = json.loads(sent_json)
    assert body["labels"] == "analysis_processed"


@respx.mock
def test_post_comment(client):
    route = respx.post(f"{BASE}/issues/1/notes").mock(
        return_value=httpx.Response(201, json={"id": 42})
    )
    import asyncio
    result = asyncio.run(client.post_comment(1, "Analysis done"))
    assert result["id"] == 42
    assert route.called
