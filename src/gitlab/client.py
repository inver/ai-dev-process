import httpx
import logging

logger = logging.getLogger(__name__)


class GitLabAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"GitLab API {status_code}: {message}")


class GitLabClient:
    def __init__(self, gitlab_url: str, token: str, project_id: str):
        self._base = f"{gitlab_url.rstrip('/')}/api/v4/projects/{project_id}"
        self._headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
        logger.debug("GitLabClient initialized for %s", self._base)

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_error:
            logger.error(
                "GitLab API error: %s %s -> %s: %s",
                response.request.method, response.request.url,
                response.status_code, response.text[:200],
            )
            raise GitLabAPIError(response.status_code, response.text[:200])

    async def get_issue(self, issue_iid: int) -> dict:
        logger.debug("GitLab GET issue #%s", issue_iid)
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self._base}/issues/{issue_iid}", headers=self._headers)
        self._raise_for_status(r)
        data = r.json()
        result = {
            "iid": data["iid"],
            "title": data["title"],
            "description": data.get("description") or "",
            "labels": [lbl["name"] if isinstance(lbl, dict) else lbl
                       for lbl in data.get("labels", [])],
        }
        logger.debug(
            "GitLab issue #%s fetched: title=%r, labels=%s",
            issue_iid, result["title"], result["labels"],
        )
        return result

    async def get_issue_comments(self, issue_iid: int) -> list[dict]:
        logger.debug("GitLab GET comments for issue #%s", issue_iid)
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/issues/{issue_iid}/notes",
                headers=self._headers,
                params={"per_page": 100},
            )
        self._raise_for_status(r)
        comments = [
            {"id": n["id"], "author": n["author"]["username"],
             "body": n["body"], "created_at": n["created_at"]}
            for n in r.json()
            if not n.get("system", False)
        ]
        logger.debug(
            "GitLab issue #%s: %d non-system comment(s)", issue_iid, len(comments),
        )
        return comments

    async def update_issue_description(self, issue_iid: int, description: str) -> None:
        logger.info(
            "GitLab update description on issue #%s (%d chars)", issue_iid, len(description),
        )
        async with httpx.AsyncClient() as c:
            r = await c.put(
                f"{self._base}/issues/{issue_iid}",
                headers=self._headers,
                json={"description": description},
            )
        self._raise_for_status(r)

    async def set_labels(self, issue_iid: int, labels: list[str]) -> None:
        logger.info("GitLab set labels on issue #%s: %s", issue_iid, labels)
        async with httpx.AsyncClient() as c:
            r = await c.put(
                f"{self._base}/issues/{issue_iid}",
                headers=self._headers,
                json={"labels": ",".join(labels)},
            )
        self._raise_for_status(r)

    async def post_comment(self, issue_iid: int, body: str) -> dict:
        logger.info(
            "GitLab post comment on issue #%s (%d chars)", issue_iid, len(body),
        )
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{self._base}/issues/{issue_iid}/notes",
                headers=self._headers,
                json={"body": body},
            )
        self._raise_for_status(r)
        note = r.json()
        logger.debug("GitLab comment posted on issue #%s: note id=%s", issue_iid, note.get("id"))
        return note

    async def get_file_content(self, path: str, ref: str = "main") -> str:
        import urllib.parse
        encoded = urllib.parse.quote(path, safe="")
        logger.debug("GitLab GET file %r @ %s", path, ref)
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/repository/files/{encoded}/raw",
                headers=self._headers,
                params={"ref": ref},
            )
        if r.status_code == 404:
            logger.debug("GitLab file %r not found @ %s", path, ref)
            return ""
        self._raise_for_status(r)
        return r.text

    async def list_repository_tree(self, ref: str = "main") -> list[dict]:
        logger.debug("GitLab GET repository tree @ %s", ref)
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/repository/tree",
                headers=self._headers,
                params={"recursive": "true", "ref": ref, "per_page": 200},
            )
        if r.status_code == 404:
            logger.debug("GitLab repository tree not found @ %s", ref)
            return []
        self._raise_for_status(r)
        blobs = [item for item in r.json() if item["type"] == "blob"]
        logger.debug("GitLab repository tree @ %s: %d blob(s)", ref, len(blobs))
        return blobs

    async def branch_exists(self, branch_name: str) -> bool:
        import urllib.parse
        encoded = urllib.parse.quote(branch_name, safe="")
        async with httpx.AsyncClient() as c:
            r = await c.get(
                f"{self._base}/repository/branches/{encoded}",
                headers=self._headers,
            )
        exists = r.status_code == 200
        logger.debug("GitLab branch %r exists=%s", branch_name, exists)
        return exists

    async def create_branch(self, branch_name: str, ref: str = "main") -> None:
        logger.info("GitLab create branch %r from %s", branch_name, ref)
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"{self._base}/repository/branches",
                headers=self._headers,
                json={"branch": branch_name, "ref": ref},
            )
        if r.status_code == 400 and "already exists" in r.text:
            logger.info("GitLab branch %r already exists", branch_name)
            return
        self._raise_for_status(r)

    async def create_or_update_file(
            self, path: str, content: str, branch: str, commit_message: str
    ) -> None:
        import urllib.parse
        import base64
        encoded_path = urllib.parse.quote(path, safe="")
        encoded_content = base64.b64encode(content.encode()).decode()
        payload = {
            "branch": branch,
            "commit_message": commit_message,
            "encoding": "base64",
            "content": encoded_content,
        }
        logger.info(
            "GitLab write file %r on branch %r (%d bytes): %s",
            path, branch, len(content), commit_message,
        )
        async with httpx.AsyncClient() as c:
            # Try update (PUT) first; if 404, create (POST)
            r = await c.put(
                f"{self._base}/repository/files/{encoded_path}",
                headers=self._headers,
                json=payload,
            )
            if r.status_code == 400 and ("not found" in r.text.lower() or "doesn't exist" in r.text.lower()):
                logger.debug("GitLab file %r absent; creating instead of updating", path)
                r = await c.post(
                    f"{self._base}/repository/files/{encoded_path}",
                    headers=self._headers,
                    json=payload,
                )
        self._raise_for_status(r)
