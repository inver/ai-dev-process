import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from src.config import get_settings
from src.context.gatherer import ContextGatherer
from src.gitlab.branches import BranchManager
from src.gitlab.client import GitLabClient
from src.gitlab.labels import ANALYSIS_PROCESSED, ANALYSIS_FAILED, ANALYSIS_TODO, apply_transition
from src.models.analysis import AnalysisOutput
from src.models.review import ReviewResult
from src.pipeline.claude_code import run_claude_analysis
from src.pipeline.codex import run_codex_review
from src.models.state import AnalysisState
from src.pipeline.prompts import (
    ANALYST_SYSTEM, ANALYST_INITIAL, ANALYST_REVISION,
    REVIEWER_SYSTEM, REVIEWER_PROMPT, format_comments,
)

logger = logging.getLogger(__name__)


def build_gitlab_client(settings=None) -> GitLabClient:
    s = settings or get_settings()
    return GitLabClient(s.gitlab_url, s.gitlab_token.get_secret_value(), s.gitlab_project_id)


def _build_branch_manager(settings) -> BranchManager:
    client = build_gitlab_client(settings)
    web_url = f"{settings.gitlab_url.rstrip('/')}/{settings.gitlab_project_path}"
    return BranchManager(client, web_url)


def _persist_analysis_snapshot(state: AnalysisState, result: AnalysisOutput, iteration: int) -> None:
    """Best-effort commit of an analyst snapshot for iteration ``iteration``.

    Failures are logged and swallowed: intermediate snapshots are for an audit
    trail, not correctness, so a GitLab hiccup must not abort the analysis loop.
    """
    issue_iid = state["issue_iid"]
    branch = state["branch_name"]
    try:
        bm = _build_branch_manager(get_settings())
        json_content = result.model_dump_json(indent=2)
        # Render against an iteration-corrected view of state without mutating it.
        md_content = _render_markdown({**state, "iteration": iteration}, {"analysis": result.model_dump()})
        msg = f"analysis: iteration {iteration} snapshot for #{issue_iid}"
        json_path = f"analysis/{issue_iid}/analysis_iter{iteration}.json"
        md_path = f"analysis/{issue_iid}/analysis_iter{iteration}.md"

        async def _write():
            await bm.write_artifact(branch, json_path, json_content, msg)
            await bm.write_artifact(branch, md_path, md_content, msg)

        asyncio.run(_write())
        logger.info("Persisted analysis snapshot for issue #%s iteration %s", issue_iid, iteration)
    except Exception:
        logger.warning(
            "Failed to persist analysis snapshot for issue #%s iteration %s; continuing",
            issue_iid, iteration, exc_info=True,
        )


def _persist_review_snapshot(state: AnalysisState, review: ReviewResult, iteration: int) -> None:
    """Best-effort commit of a reviewer snapshot for iteration ``iteration``."""
    issue_iid = state["issue_iid"]
    branch = state["branch_name"]
    try:
        bm = _build_branch_manager(get_settings())
        json_content = review.model_dump_json(indent=2)
        msg = f"analysis: iteration {iteration} review for #{issue_iid}"
        json_path = f"analysis/{issue_iid}/review_iter{iteration}.json"

        async def _write():
            await bm.write_artifact(branch, json_path, json_content, msg)

        asyncio.run(_write())
        logger.info("Persisted review snapshot for issue #%s iteration %s", issue_iid, iteration)
    except Exception:
        logger.warning(
            "Failed to persist review snapshot for issue #%s iteration %s; continuing",
            issue_iid, iteration, exc_info=True,
        )


def gather_context_node(state: AnalysisState) -> dict:
    settings = get_settings()
    client = build_gitlab_client(settings)
    gatherer = ContextGatherer(client)
    web_url = f"{settings.gitlab_url.rstrip('/')}/{settings.gitlab_project_path}"
    branch_manager = BranchManager(client, web_url)

    async def _gather():
        context = await gatherer.gather(state["issue_iid"])
        # Create the feature branch up front so per-iteration snapshots have a
        # target; ensure_feature_branch is idempotent.
        await branch_manager.ensure_feature_branch(state["issue_iid"])
        return context

    ctx = asyncio.run(_gather())
    return {
        **ctx,
        "project_id": settings.gitlab_project_id,
        "project_path": settings.gitlab_project_path,
        "branch_name": f"feature/{state['issue_iid']}",
        "status": "analyzing",
        "approved": False,
        "failure_reason": None,
        "artifact_json_url": None,
        "artifact_md_url": None,
        "gitlab_comment_id": None,
        "analysis_history": [],
        "iteration": 0,
    }


def analyze_node(state: AnalysisState) -> dict:
    comments_block = format_comments(state["issue_comments"])
    prompt = ANALYST_INITIAL.format(
        issue_title=state["issue_title"],
        issue_description=state["issue_description"],
        comments_block=comments_block,
        file_tree=state["file_tree"],
        readme_content=state["readme_content"],
    )
    logger.info(
        "Analyst (initial) for issue #%s, iteration %s",
        state["issue_iid"], state["iteration"],
    )
    result: AnalysisOutput = run_claude_analysis(ANALYST_SYSTEM, prompt)
    _persist_analysis_snapshot(state, result, state["iteration"] + 1)
    return {
        "iteration": state["iteration"] + 1,
        "iteration_start_time": datetime.now(timezone.utc).isoformat(),
        "current_analysis": result.model_dump_json(),
        "current_analysis_structured": result.model_dump(),
        "status": "reviewing",
    }


def revise_node(state: AnalysisState) -> dict:
    review = ReviewResult(**state["review_result"])
    comments_block = format_comments(state["issue_comments"])
    prompt = ANALYST_REVISION.format(
        issue_title=state["issue_title"],
        issue_description=state["issue_description"],
        comments_block=comments_block,
        file_tree=state["file_tree"],
        readme_content=state["readme_content"],
        iteration=state["iteration"],
        previous_analysis=state["current_analysis"],
        feedback=review.feedback,
        concerns="\n".join(f"- {c}" for c in review.concerns),
        missing_sections="\n".join(f"- {m}" for m in review.missing_sections),
    )
    logger.info(
        "Analyst (revision) for issue #%s, iteration %s; addressing %d concern(s)",
        state["issue_iid"], state["iteration"], len(review.concerns or []),
    )
    result: AnalysisOutput = run_claude_analysis(ANALYST_SYSTEM, prompt)
    _persist_analysis_snapshot(state, result, state["iteration"] + 1)
    return {
        "iteration": state["iteration"] + 1,
        "iteration_start_time": datetime.now(timezone.utc).isoformat(),
        "current_analysis": result.model_dump_json(),
        "current_analysis_structured": result.model_dump(),
        "status": "reviewing",
    }


def review_node(state: AnalysisState) -> dict:
    settings = get_settings()
    system_prompt = REVIEWER_SYSTEM.format(min_quality_score=settings.min_review_quality_score)
    prompt = REVIEWER_PROMPT.format(
        issue_title=state["issue_title"],
        issue_description=state["issue_description"],
        current_analysis=state["current_analysis"],
    )
    logger.info(
        "Invoking Codex reviewer (model=%s, min_score=%s) for issue #%s iteration %s "
        "(system=%d chars, prompt=%d chars)",
        settings.reviewer_model, settings.min_review_quality_score,
        state["issue_iid"], state["iteration"],
        len(system_prompt), len(prompt),
    )
    started = time.monotonic()
    try:
        result: ReviewResult = run_codex_review(system_prompt, prompt, settings)
    except Exception:
        logger.exception(
            "Codex reviewer invocation failed for issue #%s iteration %s",
            state["issue_iid"], state["iteration"],
        )
        raise
    elapsed = time.monotonic() - started
    # Enforce quality gate regardless of what the LLM decided.
    approved = result.approved and result.quality_score >= settings.min_review_quality_score
    logger.info(
        "Codex reviewer returned in %.1fs: approved=%s (llm=%s, score=%s/%s) "
        "(%d concern(s), %d missing section(s))",
        elapsed, approved, result.approved, result.quality_score,
        settings.min_review_quality_score,
        len(result.concerns or []), len(result.missing_sections or []),
    )
    _persist_review_snapshot(state, result, state["iteration"])
    history_entry = {
        "iteration": state["iteration"],
        "approved": approved,
        "quality_score": result.quality_score,
        "feedback": result.feedback,
        "concerns": result.concerns,
    }
    return {
        "review_result": result.model_dump(),
        "approved": approved,
        "analysis_history": [history_entry],  # reducer appends this
    }


def finalize_node(state: AnalysisState) -> dict:
    settings = get_settings()
    client = build_gitlab_client(settings)
    web_url = f"{settings.gitlab_url.rstrip('/')}/{settings.gitlab_project_path}"
    branch_manager = BranchManager(client, web_url)

    analysis = state["current_analysis_structured"]
    issue_iid = state["issue_iid"]
    branch = state["branch_name"]

    artifact = {
        "task_id": issue_iid,
        "iteration_count": state["iteration"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analysis": analysis,
        "review_history": state.get("analysis_history", []),
    }
    json_content = json.dumps(artifact, indent=2, ensure_ascii=False)
    md_content = _render_markdown(state, artifact)

    json_path = f"analysis/{issue_iid}/analysis.json"
    md_path = f"analysis/{issue_iid}/analysis.md"

    async def _write():
        await branch_manager.ensure_feature_branch(issue_iid)
        json_url = await branch_manager.write_artifact(branch, json_path, json_content, f"analysis: JSON for #{issue_iid}")
        md_url = await branch_manager.write_artifact(branch, md_path, md_content, f"analysis: Markdown for #{issue_iid}")
        await apply_transition(client, issue_iid, add=[ANALYSIS_PROCESSED], remove=[ANALYSIS_TODO])
        await client.update_issue_description(issue_iid, md_content)
        comment_body = _build_comment(branch, json_url, md_url, state)
        note = await client.post_comment(issue_iid, comment_body)
        return json_url, md_url, note["id"]

    json_url, md_url, comment_id = asyncio.run(_write())
    return {
        "status": "approved",
        "artifact_json_url": json_url,
        "artifact_md_url": md_url,
        "gitlab_comment_id": comment_id,
    }


def handle_failure_node(state: AnalysisState) -> dict:
    settings = get_settings()
    client = build_gitlab_client(settings)
    reason = state.get("failure_reason") or "Max iterations reached without reviewer approval"

    async def _fail():
        await apply_transition(client, state["issue_iid"], add=[ANALYSIS_FAILED], remove=[ANALYSIS_TODO])
        await client.post_comment(
            state["issue_iid"],
            f"## Analysis Failed\n\nReason: {reason}\n\n"
            "Re-add the `analysis_todo` label to retry.",
        )

    asyncio.run(_fail())
    return {"status": "failed"}


def _render_markdown(state: dict, artifact: dict) -> str:
    a = artifact["analysis"]
    criteria = "\n".join(f"- [ ] {c}" for c in a.get("acceptance_criteria", []))
    approach = "\n".join(f"{i+1}. {s}" for i, s in enumerate(a.get("technical_approach", [])))
    risks = "\n".join(
        f"- **{r['severity'].upper()}**: {r['description']} — *{r['mitigation']}*"
        for r in a.get("risks", [])
    )
    return f"""# Analysis: {state['issue_title']}

**Issue:** #{state['issue_iid']} | **Complexity:** {a.get('estimated_complexity', 'N/A')} | **Iterations:** {state['iteration']}

## Problem Statement
{a.get('problem_statement', '')}

## Acceptance Criteria
{criteria}

## Technical Approach
{approach}

## Dependencies
{chr(10).join('- ' + d for d in a.get('dependencies', []))}

## Risks
{risks}

## Open Questions
{chr(10).join('- ' + q for q in a.get('open_questions', []))}

---
*Analyzed by `{get_settings().analyst_model}` · Reviewed by `{get_settings().reviewer_model}`*
"""


def _build_comment(branch: str, json_url: str, md_url: str, state: dict) -> str:
    last_review = state.get("analysis_history", [{}])[-1]
    score = last_review.get("quality_score", "N/A")
    return (
        f"## ✅ Analysis Complete\n\n"
        f"Completed in **{state['iteration']} iteration(s)** with quality score **{score}/10**.\n\n"
        f"**Artifacts (branch `{branch}`):**\n"
        f"- [JSON Analysis]({json_url})\n"
        f"- [Markdown Report]({md_url})\n\n"
        f"**Summary:** {state['current_analysis_structured'].get('problem_statement', '')}\n\n"
        "To approve, add label `analysis_done`.\n"
        "Add a comment to trigger re-analysis."
    )
