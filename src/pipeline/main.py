import sys
import asyncio
import logging
from src.config import get_settings
from src.gitlab.client import GitLabClient
from src.gitlab.labels import ANALYSIS_FAILED, ANALYSIS_TODO, apply_transition
from src.logging_config import setup_logging
from src.pipeline.graph import build_graph

logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)

    if not settings.issue_id:
        print("ERROR: ISSUE_ID environment variable not set", file=sys.stderr)
        sys.exit(1)

    if not settings.gitlab_token.get_secret_value():
        print(
            "ERROR: GITLAB_TOKEN not set. The GitLab API returns 401 without a "
            "valid token with 'api' scope. Define it as a CI/CD variable exposed "
            "to this pipeline's ref.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not settings.claude_code_oauth_token.get_secret_value():
        print(
            "ERROR: CLAUDE_CODE_OAUTH_TOKEN not set. The analyst runs via the "
            "Claude Code CLI and needs an OAuth token (generate with "
            "`claude setup-token`).",
            file=sys.stderr,
        )
        sys.exit(1)

    issue_iid = settings.issue_id
    initial_state = {
        "issue_iid": issue_iid,
        "project_id": settings.gitlab_project_id,
        "project_path": settings.gitlab_project_path,
        "trigger_type": settings.trigger_type,
        "issue_title": "", "issue_description": "", "issue_labels": [],
        "issue_comments": [], "readme_content": "", "file_tree": "",
        "max_iterations": settings.max_iterations,
        "iteration_timeout_seconds": settings.iteration_timeout_seconds,
        "iteration": 0, "iteration_start_time": "",
        "current_analysis": "", "current_analysis_structured": {},
        "review_result": None, "analysis_history": [],
        "approved": False, "status": "analyzing", "failure_reason": None,
        "branch_name": f"feature/{issue_iid}",
        "artifact_json_url": None, "artifact_md_url": None, "gitlab_comment_id": None,
    }

    logger.info(
        "Starting analysis pipeline for issue #%s (trigger=%s, max_iterations=%s, "
        "analyst=%s, reviewer=%s)",
        issue_iid, settings.trigger_type, settings.max_iterations,
        settings.analyst_model, settings.reviewer_model,
    )

    try:
        graph = build_graph()
        final_state = graph.invoke(initial_state)
        logger.info(
            "Pipeline finished for issue #%s: status=%s after %s iteration(s)",
            issue_iid, final_state["status"], final_state.get("iteration"),
        )
        exit_code = 0 if final_state["status"] in ("approved", "failed") else 1
    except Exception as exc:
        logger.exception("Unhandled pipeline error for issue #%s", issue_iid)
        print(f"Unhandled pipeline error: {exc}", file=sys.stderr)
        client = GitLabClient(
            settings.gitlab_url,
            settings.gitlab_token.get_secret_value(),
            settings.gitlab_project_id,
        )
        asyncio.run(apply_transition(
            client, issue_iid,
            add=[ANALYSIS_FAILED], remove=[ANALYSIS_TODO],
        ))
        asyncio.run(client.post_comment(
            issue_iid,
            f"## Analysis Failed\n\nUnexpected error: `{exc}`\n\nCheck CI job logs for details.",
        ))
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
