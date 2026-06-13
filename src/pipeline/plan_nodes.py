import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from src.config import get_settings
from src.context.gatherer import ContextGatherer
from src.gitlab.labels import PLAN_FAILED, PLAN_PROCESSED, PLAN_TODO, apply_transition
from src.models.plan import PlanOutput, PlanReviewResult, PlanState
from src.pipeline.claude_plan import run_claude_plan
from src.pipeline.codex_plan import run_codex_plan_review
from src.pipeline.nodes import _build_branch_manager, build_forge_client
from src.pipeline.prompts import (
    PLANNER_INITIAL,
    PLANNER_REVISION,
    PLANNER_SYSTEM,
    PLAN_REVIEWER_PROMPT,
    PLAN_REVIEWER_SYSTEM,
    format_comments,
)

logger = logging.getLogger(__name__)


def _load_analysis_content(state: PlanState) -> str:
    try:
        client = build_forge_client(get_settings())
        path = f"analysis/{state['issue_iid']}/analysis.json"

        async def _read():
            return await client.get_file_content(path, ref=state["branch_name"])

        return asyncio.run(_read())
    except Exception:
        logger.info("No prior analysis artifact found; proceeding without it")
        return ""


def gather_context_node(state: PlanState) -> dict:
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

    analysis_content = _load_analysis_content({**state, "branch_name": branch_name})
    return {
        **ctx,
        "project_id": project_id,
        "project_path": project_path,
        "branch_name": branch_name,
        "analysis_content": analysis_content,
        "status": "planning",
        "approved": False,
        "failure_reason": None,
        "artifact_json_url": None,
        "artifact_md_url": None,
        "gitlab_comment_id": None,
        "plan_history": [],
        "iteration": 0,
    }


def plan_node(state: PlanState) -> dict:
    prompt = PLANNER_INITIAL.format(
        issue_title=state["issue_title"],
        issue_description=state["issue_description"],
        comments_block=format_comments(state["issue_comments"]),
        file_tree=state["file_tree"],
        readme_content=state["readme_content"],
        analysis_content=state["analysis_content"] or "(no prior analysis)",
    )
    logger.info("Planner initial run for issue #%s", state["issue_iid"])
    result: PlanOutput = run_claude_plan(PLANNER_SYSTEM, prompt)
    return {
        "iteration": state["iteration"] + 1,
        "iteration_start_time": datetime.now(timezone.utc).isoformat(),
        "current_plan": result.model_dump_json(),
        "current_plan_structured": result.model_dump(),
        "status": "reviewing_plan",
    }


def revise_node(state: PlanState) -> dict:
    review = PlanReviewResult(**state["review_result"])
    prompt = PLANNER_REVISION.format(
        issue_title=state["issue_title"],
        issue_description=state["issue_description"],
        comments_block=format_comments(state["issue_comments"]),
        file_tree=state["file_tree"],
        readme_content=state["readme_content"],
        analysis_content=state["analysis_content"] or "(no prior analysis)",
        iteration=state["iteration"],
        previous_plan=state["current_plan"],
        feedback=review.feedback,
        concerns="\n".join(f"- {c}" for c in review.concerns),
        missing_sections="\n".join(f"- {m}" for m in review.missing_sections),
    )
    logger.info("Planner revision for issue #%s iteration %s", state["issue_iid"], state["iteration"])
    result: PlanOutput = run_claude_plan(PLANNER_SYSTEM, prompt)
    return {
        "iteration": state["iteration"] + 1,
        "iteration_start_time": datetime.now(timezone.utc).isoformat(),
        "current_plan": result.model_dump_json(),
        "current_plan_structured": result.model_dump(),
        "status": "reviewing_plan",
    }


def review_node(state: PlanState) -> dict:
    settings = get_settings()
    system_prompt = PLAN_REVIEWER_SYSTEM.format(
        min_quality_score=settings.min_review_quality_score
    )
    prompt = PLAN_REVIEWER_PROMPT.format(
        issue_title=state["issue_title"],
        issue_description=state["issue_description"],
        current_plan=state["current_plan"],
    )
    started = time.monotonic()
    result: PlanReviewResult = run_codex_plan_review(system_prompt, prompt, settings)
    approved = result.approved and result.quality_score >= settings.min_review_quality_score
    logger.info(
        "Plan review for issue #%s iteration %s: approved=%s score=%s in %.1fs",
        state["issue_iid"],
        state["iteration"],
        approved,
        result.quality_score,
        time.monotonic() - started,
    )
    return {
        "review_result": result.model_dump(),
        "approved": approved,
        "plan_history": [{
            "iteration": state["iteration"],
            "approved": approved,
            "quality_score": result.quality_score,
            "feedback": result.feedback,
            "concerns": result.concerns,
        }],
    }


def finalize_node(state: PlanState) -> dict:
    settings = get_settings()
    client = build_forge_client(settings)
    branch_manager = _build_branch_manager(client, settings)
    issue_iid = state["issue_iid"]
    branch = state["branch_name"]
    artifact = {
        "task_id": issue_iid,
        "iteration_count": state["iteration"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "plan": state["current_plan_structured"],
        "review_history": state.get("plan_history", []),
    }
    json_content = json.dumps(artifact, indent=2, ensure_ascii=False)
    md_content = _render_plan_markdown(state, artifact)

    async def _write():
        await branch_manager.ensure_feature_branch(issue_iid)
        json_url = await branch_manager.write_artifact(
            branch, f"plans/{issue_iid}/plan.json", json_content,
            f"plan: JSON for #{issue_iid}",
        )
        md_url = await branch_manager.write_artifact(
            branch, f"plans/{issue_iid}/plan.md", md_content,
            f"plan: Markdown for #{issue_iid}",
        )
        await apply_transition(client, issue_iid, add=[PLAN_PROCESSED], remove=[PLAN_TODO])
        await client.update_issue_description(issue_iid, md_content)
        note = await client.post_comment(issue_iid, _build_comment(branch, json_url, md_url, state))
        return json_url, md_url, note["id"]

    json_url, md_url, comment_id = asyncio.run(_write())
    return {
        "status": "approved",
        "artifact_json_url": json_url,
        "artifact_md_url": md_url,
        "gitlab_comment_id": comment_id,
    }


def handle_failure_node(state: PlanState) -> dict:
    client = build_forge_client(get_settings())
    reason = state.get("failure_reason") or "Max iterations reached without plan approval"

    async def _fail():
        await apply_transition(client, state["issue_iid"], add=[PLAN_FAILED], remove=[PLAN_TODO])
        await client.post_comment(
            state["issue_iid"],
            f"## Planning Failed\n\nReason: {reason}\n\nRe-add `plan_todo` to retry.",
        )

    asyncio.run(_fail())
    return {"status": "failed"}


def _render_plan_markdown(state: dict, artifact: dict) -> str:
    plan = artifact["plan"]
    tasks_md = "\n\n".join(
        f"### {t['id']}: {t['title']}\n{t['description']}\n\n"
        f"**Files:** {', '.join(t.get('files_to_modify', []) + t.get('files_to_create', []))}\n\n"
        f"**Est:** {t.get('estimated_minutes', '?')} min"
        for t in plan.get("tasks", [])
    )
    test_plan = "\n".join(f"- {t}" for t in plan.get("test_plan", []))
    assumptions = "\n".join(f"- {a}" for a in plan.get("assumptions", []))
    return f"""# Plan: {state['issue_title']}

**Issue:** #{state['issue_iid']} | **Iterations:** {state['iteration']} | **Est:** {plan.get('total_estimated_minutes', '?')} min

## Summary
{plan.get('summary', '')}

## Tasks
{tasks_md}

## Test Plan
{test_plan}

## Assumptions
{assumptions}

---
*Planned by `{get_settings().analyst_model}` · Reviewed by `{get_settings().reviewer_model}`*
"""


def _build_comment(branch: str, json_url: str, md_url: str, state: dict) -> str:
    last_review = state.get("plan_history", [{}])[-1]
    score = last_review.get("quality_score", "N/A")
    return (
        "## Plan Complete\n\n"
        f"Completed in **{state['iteration']} iteration(s)** with quality score **{score}/10**.\n\n"
        f"**Artifacts (branch `{branch}`):**\n"
        f"- [JSON Plan]({json_url})\n"
        f"- [Markdown Plan]({md_url})\n\n"
        "Add label `develop_todo` to start implementation."
    )
