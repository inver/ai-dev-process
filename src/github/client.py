import base64
import httpx
import logging
import urllib.parse

logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"GitHub API {status_code}: {message}")


class GitHubClient:
    def __init__(self, token: str, owner: str, repo: str):
        self._base = f"https://api.github.com/repos/{owner}/{repo}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        logger.debug("GitHubClient initialized for %s/%s", owner, repo)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_error:
            logger.error(
                "GitHub API error: %s %s -> %s: %s",
                response.request.method, response.request.url,
                response.status_code, response.text[:200],
            )
            raise GitHubAPIError(response.status_code, response.text[:200])

    async def get_issue(self, issue_iid: int) -> dict:
        logger.debug("GitHub GET issue #%s", issue_iid)
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self._base}/issues/{issue_iid}", headers=self._headers)
        self._raise_for_status(r)
        data = r.json()
        result = {
            "iid": data["number"],
            "title": data["title"],
            "description": data.get("body") or "",
            "labels": [lbl["name"] for lbl in data.get("labels", [])],
        }
        logger.debug(
            "GitHub issue #%s fetched: title=%r, labels=%s",
            issue_iid, result["title"], result["labels"],
        )
        return result

    async def get_issue_comments(self, issue_iid: int) -> list[dict]:
        logger.debug("GitHub GET comments for issue #%s", issue_iid)
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/issues/{issue_iid}/comments",
                headers=self._headers,
                params={"per_page": 100},
            )
        self._raise_for_status(r)
        comments = [
            {
                "id": comment["id"],
                "author": comment["user"]["login"],
                "body": comment["body"],
                "created_at": comment["created_at"],
            }
            for comment in r.json()
        ]
        logger.debug("GitHub issue #%s: %d comment(s)", issue_iid, len(comments))
        return comments

    async def update_issue_description(self, issue_iid: int, description: str) -> None:
        logger.info(
            "GitHub update description on issue #%s (%d chars)", issue_iid, len(description)
        )
        async with httpx.AsyncClient() as c:
            r = await c.patch(
                f"{self._base}/issues/{issue_iid}",
                headers=self._headers,
                json={"body": description},
            )
        self._raise_for_status(r)

    async def set_labels(self, issue_iid: int, labels: list[str]) -> None:
        logger.info("GitHub set labels on issue #%s: %s", issue_iid, labels)
        async with httpx.AsyncClient() as c:
            r = await c.put(
                f"{self._base}/issues/{issue_iid}/labels",
                headers=self._headers,
                json={"labels": labels},
            )
        self._raise_for_status(r)

    async def post_comment(self, issue_iid: int, body: str) -> dict:
        logger.info(
            "GitHub post comment on issue #%s (%d chars)", issue_iid, len(body)
        )
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{self._base}/issues/{issue_iid}/comments",
                headers=self._headers,
                json={"body": body},
            )
        self._raise_for_status(r)
        note = r.json()
        logger.debug("GitHub comment posted on issue #%s: id=%s", issue_iid, note.get("id"))
        return note

    async def get_file_content(self, path: str, ref: str = "main") -> str:
        logger.debug("GitHub GET file %r @ %s", path, ref)
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/contents/{urllib.parse.quote(path, safe='/')}",
                headers=self._headers,
                params={"ref": ref},
            )
        if r.status_code == 404:
            logger.debug("GitHub file %r not found @ %s", path, ref)
            return ""
        self._raise_for_status(r)
        data = r.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    async def list_repository_tree(self, ref: str = "main") -> list[dict]:
        logger.debug("GitHub GET repository tree @ %s", ref)
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/git/trees/{ref}",
                headers=self._headers,
                params={"recursive": "1"},
            )
        if r.status_code == 404:
            logger.debug("GitHub repository tree not found @ %s", ref)
            return []
        self._raise_for_status(r)
        data = r.json()
        if data.get("truncated"):
            logger.warning("GitHub tree for %s is truncated; some files may be missing", ref)
        blobs = [{"path": item["path"]} for item in data.get("tree", []) if item["type"] == "blob"]
        logger.debug("GitHub repository tree @ %s: %d blob(s)", ref, len(blobs))
        return blobs

    async def branch_exists(self, branch_name: str) -> bool:
        encoded = urllib.parse.quote(branch_name, safe="")
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/branches/{encoded}",
                headers=self._headers,
            )
        exists = r.status_code == 200
        logger.debug("GitHub branch %r exists=%s", branch_name, exists)
        return exists

    async def create_branch(self, branch_name: str, ref: str = "main") -> None:
        logger.info("GitHub create branch %r from %s", branch_name, ref)
        async with httpx.AsyncClient() as c:
            sha_resp = await c.get(
                f"{self._base}/git/refs/heads/{ref}",
                headers=self._headers,
            )
            self._raise_for_status(sha_resp)
            sha = sha_resp.json()["object"]["sha"]
            r = await c.post(
                f"{self._base}/git/refs",
                headers=self._headers,
                json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            )
        if r.status_code == 422 and "already exists" in r.text.lower():
            logger.info("GitHub branch %r already exists", branch_name)
            return
        self._raise_for_status(r)

    async def create_or_update_file(
            self, path: str, content: str, branch: str, commit_message: str
    ) -> None:
        encoded_content = base64.b64encode(content.encode()).decode()
        url = f"{self._base}/contents/{urllib.parse.quote(path, safe='/')}"
        logger.info(
            "GitHub write file %r on branch %r (%d bytes): %s",
            path, branch, len(content), commit_message,
        )
        payload: dict = {
            "message": commit_message,
            "content": encoded_content,
            "branch": branch,
        }
        async with httpx.AsyncClient() as c:
            existing = await c.get(url, headers=self._headers, params={"ref": branch})
            if existing.status_code == 200:
                payload["sha"] = existing.json()["sha"]
            r = await c.put(url, headers=self._headers, json=payload)
        self._raise_for_status(r)
