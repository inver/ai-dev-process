import asyncio
import logging
import sys

from src.config import get_settings
from src.gitlab.labels import (
    ANALYSIS_FAILED,
    ANALYSIS_TODO,
    DEVELOP_FAILED,
    DEVELOP_TODO,
    PLAN_FAILED,
    PLAN_TODO,
    apply_transition,
)
from src.logging_config import setup_logging
from src.pipeline.dev_graph import build_dev_graph
from src.pipeline.graph import build_graph
from src.pipeline.nodes import build_forge_client
from src.pipeline.plan_graph import build_plan_graph

logger = logging.getLogger(__name__)


def _project_identity(settings) -> tuple[str, str]:
    if settings.platform == "github":
        project = f"{settings.github_owner}/{settings.github_repo}"
        return project, project
    return settings.gitlab_project_id, settings.gitlab_project_path


def _base_initial_state(settings, issue_iid: int) -> dict:
    project_id, project_path = _project_identity(settings)
    return {
        "issue_iid": issue_iid,
        "project_id": project_id,
        "project_path": project_path,
        "trigger_type": settings.trigger_type,
        "issue_title": "",
        "issue_description": "",
        "issue_labels": [],
        "issue_comments": [],
        "readme_content": "",
        "file_tree": "",
        "iteration_timeout_seconds": settings.iteration_timeout_seconds,
        "iteration": 0,
        "iteration_start_time": "",
        "review_result": None,
        "approved": False,
        "failure_reason": None,
        "branch_name": f"feature/{issue_iid}",
        "gitlab_comment_id": None,
    }


def _select_graph_and_state(settings, issue_iid: int):
    if settings.trigger_type == "plan":
        return build_plan_graph(), {
            **_base_initial_state(settings, issue_iid),
            "analysis_content": "",
            "max_iterations": settings.plan_max_iterations,
            "current_plan": "",
            "current_plan_structured": {},
            "plan_history": [],
            "status": "planning",
            "artifact_json_url": None,
            "artifact_md_url": None,
        }
    if settings.trigger_type == "develop":
        return build_dev_graph(), {
            **_base_initial_state(settings, issue_iid),
            "analysis_content": "",
            "plan_content": "",
            "max_iterations": settings.develop_max_iterations,
            "dev_branch_name": f"develop/{issue_iid}",
            "implementation_summary": "",
            "dev_history": [],
            "mr_id": None,
            "mr_url": None,
            "mr_diff": "",
            "status": "developing",
        }
    return build_graph(), {
        **_base_initial_state(settings, issue_iid),
        "max_iterations": settings.max_iterations,
        "current_analysis": "",
        "current_analysis_structured": {},
        "analysis_history": [],
        "status": "analyzing",
        "artifact_json_url": None,
        "artifact_md_url": None,
    }


def _failure_labels(trigger_type: str) -> tuple[str, str]:
    label_map = {
        "analysis": (ANALYSIS_TODO, ANALYSIS_FAILED),
        "plan": (PLAN_TODO, PLAN_FAILED),
        "develop": (DEVELOP_TODO, DEVELOP_FAILED),
    }
    return label_map.get(trigger_type, (ANALYSIS_TODO, ANALYSIS_FAILED))


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    if not settings.issue_id:
        print("ERROR: ISSUE_ID environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not settings.claude_code_oauth_token.get_secret_value():
        print(
            "ERROR: CLAUDE_CODE_OAUTH_TOKEN not set. The analyst runs via the "
            "Claude Code CLI and needs an OAuth token (generate with "
            "`claude setup-token`).",
            file=sys.stderr,
        )
        sys.exit(1)

    if settings.platform == "github":
        if not settings.github_token.get_secret_value():
            print("ERROR: GITHUB_TOKEN not set for platform=github", file=sys.stderr)
            sys.exit(1)
        if not settings.github_owner or not settings.github_repo:
            print("ERROR: GITHUB_OWNER and GITHUB_REPO must be set for platform=github", file=sys.stderr)
            sys.exit(1)
    else:
        if not settings.gitlab_token.get_secret_value():
            print("ERROR: GITLAB_TOKEN not set for platform=gitlab", file=sys.stderr)
            sys.exit(1)

    issue_iid = settings.issue_id
    graph, initial_state = _select_graph_and_state(settings, issue_iid)

    logger.info(
        "Starting pipeline for issue #%s (platform=%s, trigger=%s, max_iterations=%s, "
        "analyst=%s, reviewer=%s)",
        issue_iid, settings.platform, settings.trigger_type, initial_state["max_iterations"],
        settings.analyst_model, settings.reviewer_model,
    )

    try:
        final_state = asyncio.run(graph.ainvoke(initial_state))
        logger.info(
            "Pipeline finished for issue #%s: status=%s after %s iteration(s)",
            issue_iid, final_state["status"], final_state.get("iteration"),
        )
        exit_code = 0 if final_state["status"] in ("approved", "failed") else 1
    except Exception as exc:
        logger.exception("Unhandled pipeline error for issue #%s", issue_iid)
        print(f"Unhandled pipeline error: {exc}", file=sys.stderr)
        client = build_forge_client(settings)
        todo_label, failed_label = _failure_labels(settings.trigger_type)

        async def _cleanup():
            await apply_transition(client, issue_iid, add=[failed_label], remove=[todo_label])
            await client.post_comment(
                issue_iid,
                f"## Pipeline Failed\n\nUnexpected error: `{exc}`\n\nCheck CI job logs for details.",
            )

        asyncio.run(_cleanup())
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
