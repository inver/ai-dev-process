import logging

from src.forge.client import ForgeClient

logger = logging.getLogger(__name__)


class BranchManager:
    def __init__(self, client: ForgeClient, project_web_url: str, blob_prefix: str = "/-/blob"):
        self._client = client
        self._web_url = project_web_url.rstrip("/")
        self._blob_prefix = blob_prefix

    async def ensure_feature_branch(self, issue_iid: int, ref: str = "main") -> str:
        branch = f"feature/{issue_iid}"
        if not await self._client.branch_exists(branch):
            logger.info("Creating feature branch %r for issue #%s", branch, issue_iid)
            await self._client.create_branch(branch, ref=ref)
        else:
            logger.debug("Feature branch %r already exists", branch)
        return branch

    async def write_artifact(
            self, branch: str, file_path: str, content: str, commit_message: str
    ) -> str:
        await self._client.create_or_update_file(
            path=file_path, content=content,
            branch=branch, commit_message=commit_message,
        )
        url = f"{self._web_url}{self._blob_prefix}/{branch}/{file_path}"
        logger.info("Artifact written: %s", url)
        return url
