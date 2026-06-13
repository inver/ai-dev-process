import re

from src.forge.client import ForgeClient

EXCLUDED_PATHS = re.compile(r"(^\.git/|__pycache__|\.pyc$|\.egg-info)")


def build_file_tree_string(blobs: list[dict]) -> str:
    paths = [b["path"] for b in blobs if not EXCLUDED_PATHS.search(b["path"])]
    paths.sort()
    lines = []
    for path in paths[:150]:  # cap to avoid huge prompts
        depth = path.count("/")
        indent = "  " * depth
        name = path.rsplit("/", 1)[-1]
        lines.append(f"{indent}{name}")
    return "\n".join(lines) if lines else "(empty repository)"


class ContextGatherer:
    def __init__(self, client: ForgeClient):
        self._client = client

    async def gather(self, issue_iid: int) -> dict:
        issue, comments, blobs, readme = await _gather_all(
            self._client, issue_iid
        )
        return {
            "issue_iid": issue_iid,
            "issue_title": issue["title"],
            "issue_description": issue["description"],
            "issue_labels": issue["labels"],
            "issue_comments": comments,
            "readme_content": readme[:6000],  # token budget guard
            "file_tree": build_file_tree_string(blobs),
        }


async def _gather_all(client: ForgeClient, issue_iid: int):
    import asyncio
    issue_coro = client.get_issue(issue_iid)
    comments_coro = client.get_issue_comments(issue_iid)
    tree_coro = client.list_repository_tree()
    readme_coro = client.get_file_content("README.md")
    return await asyncio.gather(issue_coro, comments_coro, tree_coro, readme_coro)
