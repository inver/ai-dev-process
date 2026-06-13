import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone

from src.config import get_settings
from src.context.gatherer import ContextGatherer
from src.gitlab.labels import DEVELOP_FAILED, DEVELOP_PROCESSED, DEVELOP_TODO, apply_transition
from src.models.mr_review import DeveloperOutput, DevelopmentState, MRReviewResult
from src.pipeline.claude_dev import run_claude_dev
from src.pipeline.codex_mr import run_codex_mr_review
from src.pipeline.nodes import _build_branch_manager, build_forge_client
from src.pipeline.prompts import (
    DEVELOPER_INITIAL,
    DEVELOPER_REVISION,
    DEVELOPER_SYSTEM,
    MR_REVIEWER_PROMPT,
    MR_REVIEWER_SYSTEM,
    format_comments,
)

logger = logging.getLogger(__name__)


class GitCommandError(RuntimeError):
    """Raised when a git subprocess fails with captured output."""


def _run_git(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        **kwargs,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        command = " ".join(args)
        if detail:
            raise GitCommandError(f"Git command failed ({result.returncode}): {command}\n{detail}")
        raise GitCommandError(f"Git command failed ({result.returncode}): {command}")
    return result


def _clone_url(settings) -> str:
    if settings.platform == "github":
        token = settings.github_token.get_secret_value()
        return f"https://x-access-token:{token}@github.com/{settings.github_owner}/{settings.github_repo}.git"
    token = settings.gitlab_token.get_secret_value()
    host = settings.gitlab_url.rstrip("/").replace("https://", "")
    return f"https://oauth2:{token}@{host}/{settings.gitlab_project_path}.git"


def _clone_repo(settings, dev_branch: str, existing_branch: bool = False) -> str:
    tmp_dir = tempfile.mkdtemp(prefix="ai-dev-")
    clone_cmd = ["git", "clone"]
    if existing_branch:
        clone_cmd.extend(["-b", dev_branch])
    clone_cmd.extend([_clone_url(settings), tmp_dir])
    _run_git(clone_cmd)
    _run_git(["git", "-C", tmp_dir, "config", "user.email", settings.git_user_email])
    _run_git(["git", "-C", tmp_dir, "config", "user.name", settings.git_user_name])
    if not existing_branch:
        remote_branch = subprocess.run(
            ["git", "-C", tmp_dir, "ls-remote", "--exit-code", "--heads", "origin", dev_branch],
            capture_output=True,
            text=True,
        )
        if remote_branch.returncode == 0:
            _run_git(["git", "-C", tmp_dir, "fetch", "origin", dev_branch])
            _run_git(["git", "-C", tmp_dir, "checkout", "-B", dev_branch, f"origin/{dev_branch}"])
            logger.info("Reusing existing remote branch %s", dev_branch)
        elif remote_branch.returncode == 2:
            _run_git(["git", "-C", tmp_dir, "checkout", "-b", dev_branch])
        else:
            detail = (remote_branch.stderr or remote_branch.stdout or "").strip()
            raise GitCommandError(
                f"Could not inspect remote branch {dev_branch}: {detail}"
            )
    logger.info("Cloned repo to %s on branch %s", tmp_dir, dev_branch)
    return tmp_dir


def _commit_and_push(repo_dir: str, dev_branch: str, issue_iid: int) -> None:
    _run_git(["git", "-C", repo_dir, "add", "-A"])
    result = _run_git(
        ["git", "-C", repo_dir, "diff", "--cached", "--name-only"],
    )
    if not result.stdout.strip():
        logger.warning("No changes to commit for issue #%s", issue_iid)
        return
    _run_git(
        ["git", "-C", repo_dir, "commit", "-m", f"develop: implement #{issue_iid}"],
    )
    _run_git(
        ["git", "-C", repo_dir, "push", "-u", "origin", dev_branch],
    )
    logger.info("Committed and pushed branch %s for issue #%s", dev_branch, issue_iid)


def _load_artifact(state: DevelopmentState, path: str) -> str:
    try:
        client = build_forge_client(get_settings())

        async def _read():
            return await client.get_file_content(path, ref=state["branch_name"])

        return asyncio.run(_read())
    except Exception:
        logger.info("Artifact %s not found on %s", path, state["branch_name"])
        return ""


def gather_context_node(state: DevelopmentState) -> dict:
    settings = get_settings()
    client = build_forge_client(settings)
    gatherer = ContextGatherer(client)
    branch_manager = _build_branch_manager(client, settings)

    async def _gather():
        context = await gatherer.gather(state["issue_iid"])
        await branch_manager.ensure_feature_branch(state["issue_iid"])
        return context

    ctx = asyncio.run(_gather())
    branch_name = f"feature/{state['issue_iid']}"

    if settings.platform == "github":
        project_id = f"{settings.github_owner}/{settings.github_repo}"
        project_path = project_id
    else:
        project_id = settings.gitlab_project_id
        project_path = settings.gitlab_project_path

    state_with_branch = {**state, "branch_name": branch_name}
    return {
        **ctx,
        "project_id": project_id,
        "project_path": project_path,
        "branch_name": branch_name,
        "dev_branch_name": f"develop/{state['issue_iid']}",
        "analysis_content": _load_artifact(
            state_with_branch, f"analysis/{state['issue_iid']}/analysis.json"
        ),
        "plan_content": _load_artifact(
            state_with_branch, f"plans/{state['issue_iid']}/plan.json"
        ),
        "status": "developing",
        "approved": False,
        "failure_reason": None,
        "gitlab_comment_id": None,
        "dev_history": [],
        "iteration": 0,
        "mr_id": None,
        "mr_url": None,
        "mr_diff": "",
        "implementation_summary": "",
    }


def develop_node(state: DevelopmentState) -> dict:
    settings = get_settings()
    prompt = DEVELOPER_INITIAL.format(
        issue_title=state["issue_title"],
        issue_description=state["issue_description"],
        comments_block=format_comments(state["issue_comments"]),
        file_tree=state["file_tree"],
        readme_content=state["readme_content"],
        plan_content=state["plan_content"] or "(no plan available; use your best judgment)",
        analysis_content=state["analysis_content"] or "(no prior analysis)",
    )
    dev_branch = state["dev_branch_name"]
    issue_iid = state["issue_iid"]
    repo_dir = None
    try:
        repo_dir = _clone_repo(settings, dev_branch)
        result: DeveloperOutput = run_claude_dev(
            DEVELOPER_SYSTEM, prompt, repo_dir=repo_dir, settings=settings
        )
        _commit_and_push(repo_dir, dev_branch, issue_iid)
    finally:
        if repo_dir and os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)

    client = build_forge_client(settings)

    async def _create_mr():
        return await client.create_merge_request(
            source_branch=dev_branch,
            target_branch="main",
            title=f"develop: implement #{issue_iid} - {state['issue_title']}",
            description=(
                f"Closes #{issue_iid}\n\n"
                f"## Implementation Summary\n{result.implementation_summary}\n\n"
                "*Implemented by Claude Code; reviewed by Codex*"
            ),
        )

    mr = asyncio.run(_create_mr())
    return {
        "iteration": state["iteration"] + 1,
        "iteration_start_time": datetime.now(timezone.utc).isoformat(),
        "implementation_summary": result.model_dump_json(),
        "mr_id": mr["id"],
        "mr_url": mr["url"],
        "status": "reviewing_mr",
    }


def revise_node(state: DevelopmentState) -> dict:
    settings = get_settings()
    review = MRReviewResult(**state["review_result"])
    prompt = DEVELOPER_REVISION.format(
        issue_title=state["issue_title"],
        previous_summary=state["implementation_summary"],
        feedback=review.feedback,
        blocking_issues="\n".join(f"- {b}" for b in review.blocking_issues),
        concerns="\n".join(f"- {c}" for c in review.concerns),
    )
    dev_branch = state["dev_branch_name"]
    issue_iid = state["issue_iid"]
    repo_dir = None
    try:
        repo_dir = _clone_repo(settings, dev_branch, existing_branch=True)
        result: DeveloperOutput = run_claude_dev(
            DEVELOPER_SYSTEM, prompt, repo_dir=repo_dir, settings=settings
        )
        _commit_and_push(repo_dir, dev_branch, issue_iid)
    finally:
        if repo_dir and os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)

    return {
        "iteration": state["iteration"] + 1,
        "iteration_start_time": datetime.now(timezone.utc).isoformat(),
        "implementation_summary": result.model_dump_json(),
        "status": "reviewing_mr",
    }


def review_mr_node(state: DevelopmentState) -> dict:
    settings = get_settings()
    client = build_forge_client(settings)

    async def _get_diff():
        return await client.get_merge_request_diff(state["mr_id"])

    mr_diff = asyncio.run(_get_diff())
    system_prompt = MR_REVIEWER_SYSTEM.format(
        min_quality_score=settings.min_review_quality_score
    )
    prompt = MR_REVIEWER_PROMPT.format(
        issue_title=state["issue_title"],
        plan_content=state["plan_content"] or "(no plan)",
        mr_diff=mr_diff[:10000],
    )
    started = time.monotonic()
    result: MRReviewResult = run_codex_mr_review(system_prompt, prompt, settings)
    approved = (
        result.approved
        and result.quality_score >= settings.min_review_quality_score
        and not result.blocking_issues
    )
    logger.info(
        "MR review for issue #%s MR #%s: approved=%s score=%s in %.1fs",
        state["issue_iid"],
        state["mr_id"],
        approved,
        result.quality_score,
        time.monotonic() - started,
    )
    return {
        "review_result": result.model_dump(),
        "approved": approved,
        "mr_diff": mr_diff,
        "dev_history": [{
            "iteration": state["iteration"],
            "approved": approved,
            "quality_score": result.quality_score,
            "feedback": result.feedback,
            "blocking_issues": result.blocking_issues,
        }],
    }


def finalize_node(state: DevelopmentState) -> dict:
    client = build_forge_client(get_settings())

    async def _finish():
        await apply_transition(client, state["issue_iid"], add=[DEVELOP_PROCESSED], remove=[DEVELOP_TODO])
        last_review = state.get("dev_history", [{}])[-1]
        score = last_review.get("quality_score", "N/A")
        note = await client.post_comment(
            state["issue_iid"],
            "## Development Complete\n\n"
            f"MR [#{state['mr_id']}]({state['mr_url']}) created after "
            f"**{state['iteration']} iteration(s)** with review score **{score}/10**.\n\n"
            f"**Implementation summary:** {state['implementation_summary'][:500]}",
        )
        return note["id"]

    return {"status": "approved", "gitlab_comment_id": asyncio.run(_finish())}


def handle_failure_node(state: DevelopmentState) -> dict:
    client = build_forge_client(get_settings())
    reason = state.get("failure_reason") or "Max iterations reached without MR approval"

    async def _fail():
        await apply_transition(client, state["issue_iid"], add=[DEVELOP_FAILED], remove=[DEVELOP_TODO])
        await client.post_comment(
            state["issue_iid"],
            f"## Development Failed\n\nReason: {reason}\n\nRe-add `develop_todo` to retry.",
        )

    asyncio.run(_fail())
    return {"status": "failed"}
