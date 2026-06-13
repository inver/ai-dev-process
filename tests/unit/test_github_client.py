import base64
import pytest
import httpx
import respx
from src.github.client import GitHubClient, GitHubAPIError

BASE = "https://api.github.com/repos/myorg/myrepo"

@pytest.fixture
def client():
    return GitHubClient(token="ghp_test", owner="myorg", repo="myrepo")


@respx.mock
@pytest.mark.asyncio
async def test_get_issue_returns_normalized_dict(client):
    respx.get(f"{BASE}/issues/42").mock(return_value=httpx.Response(200, json={
        "number": 42,
        "title": "Fix the thing",
        "body": "Description here",
        "labels": [{"name": "bug"}, {"name": "analysis_todo"}],
    }))
    result = await client.get_issue(42)
    assert result == {
        "iid": 42,
        "title": "Fix the thing",
        "description": "Description here",
        "labels": ["bug", "analysis_todo"],
    }


@respx.mock
@pytest.mark.asyncio
async def test_get_issue_comments_normalizes_shape(client):
    respx.get(f"{BASE}/issues/42/comments").mock(return_value=httpx.Response(200, json=[
        {"id": 1, "user": {"login": "alice"}, "body": "LGTM", "created_at": "2024-01-01T00:00:00Z"},
    ]))
    comments = await client.get_issue_comments(42)
    assert len(comments) == 1
    assert comments[0]["author"] == "alice"
    assert comments[0]["body"] == "LGTM"


@respx.mock
@pytest.mark.asyncio
async def test_update_issue_description(client):
    respx.patch(f"{BASE}/issues/5").mock(return_value=httpx.Response(200, json={}))
    await client.update_issue_description(5, "New body")


@respx.mock
@pytest.mark.asyncio
async def test_set_labels(client):
    route = respx.put(f"{BASE}/issues/5/labels").mock(
        return_value=httpx.Response(200, json=[])
    )
    await client.set_labels(5, ["analysis_processed"])
    assert route.called
    import json
    body = json.loads(route.calls[0].request.content)
    assert body == {"labels": ["analysis_processed"]}


@respx.mock
@pytest.mark.asyncio
async def test_post_comment_returns_id(client):
    respx.post(f"{BASE}/issues/5/comments").mock(return_value=httpx.Response(201, json={
        "id": 99, "body": "hello"
    }))
    result = await client.post_comment(5, "hello")
    assert result["id"] == 99


@respx.mock
@pytest.mark.asyncio
async def test_get_file_content_decodes_base64(client):
    encoded = base64.b64encode(b"file contents here").decode()
    respx.get(f"{BASE}/contents/README.md").mock(return_value=httpx.Response(200, json={
        "content": encoded + "\n", "encoding": "base64", "sha": "abc"
    }))
    content = await client.get_file_content("README.md")
    assert content == "file contents here"


@respx.mock
@pytest.mark.asyncio
async def test_get_file_content_returns_empty_on_404(client):
    respx.get(f"{BASE}/contents/MISSING.md").mock(return_value=httpx.Response(404, json={}))
    content = await client.get_file_content("MISSING.md")
    assert content == ""


@respx.mock
@pytest.mark.asyncio
async def test_list_repository_tree_returns_blobs(client):
    respx.get(f"{BASE}/git/trees/main").mock(return_value=httpx.Response(200, json={
        "tree": [
            {"path": "src/main.py", "type": "blob", "sha": "aaa"},
            {"path": "src/", "type": "tree", "sha": "bbb"},
        ],
        "truncated": False,
    }))
    blobs = await client.list_repository_tree()
    assert blobs == [{"path": "src/main.py"}]


@respx.mock
@pytest.mark.asyncio
async def test_branch_exists_true(client):
    respx.get(f"{BASE}/branches/feature/42").mock(return_value=httpx.Response(200, json={}))
    assert await client.branch_exists("feature/42") is True


@respx.mock
@pytest.mark.asyncio
async def test_branch_exists_false(client):
    respx.get(f"{BASE}/branches/feature/42").mock(return_value=httpx.Response(404, json={}))
    assert await client.branch_exists("feature/42") is False


@respx.mock
@pytest.mark.asyncio
async def test_create_branch(client):
    respx.get(f"{BASE}/git/refs/heads/main").mock(return_value=httpx.Response(200, json={
        "object": {"sha": "deadbeef"}
    }))
    respx.post(f"{BASE}/git/refs").mock(return_value=httpx.Response(201, json={}))
    await client.create_branch("feature/42")


@respx.mock
@pytest.mark.asyncio
async def test_create_branch_idempotent(client):
    respx.get(f"{BASE}/git/refs/heads/main").mock(return_value=httpx.Response(200, json={
        "object": {"sha": "deadbeef"}
    }))
    respx.post(f"{BASE}/git/refs").mock(return_value=httpx.Response(422, json={
        "message": "Reference already exists"
    }))
    await client.create_branch("feature/42")  # should not raise


@respx.mock
@pytest.mark.asyncio
async def test_create_or_update_file_creates_when_absent(client):
    respx.get(f"{BASE}/contents/analysis/1/out.json").mock(
        return_value=httpx.Response(404, json={})
    )
    respx.put(f"{BASE}/contents/analysis/1/out.json").mock(
        return_value=httpx.Response(201, json={})
    )
    await client.create_or_update_file("analysis/1/out.json", "data", "feature/1", "msg")


@respx.mock
@pytest.mark.asyncio
async def test_create_or_update_file_updates_with_sha(client):
    respx.get(f"{BASE}/contents/analysis/1/out.json").mock(return_value=httpx.Response(200, json={
        "sha": "existingsha", "content": "", "encoding": "base64"
    }))
    put_route = respx.put(f"{BASE}/contents/analysis/1/out.json").mock(
        return_value=httpx.Response(200, json={})
    )
    await client.create_or_update_file("analysis/1/out.json", "data", "feature/1", "msg")
    import json
    body = json.loads(put_route.calls[0].request.content)
    assert body["sha"] == "existingsha"


@respx.mock
@pytest.mark.asyncio
async def test_raises_on_api_error(client):
    respx.get(f"{BASE}/issues/1").mock(return_value=httpx.Response(401, json={"message": "Unauthorized"}))
    with pytest.raises(GitHubAPIError) as exc_info:
        await client.get_issue(1)
    assert exc_info.value.status_code == 401
