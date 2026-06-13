import logging

logger = logging.getLogger(__name__)

ANALYSIS_TODO = "analysis_todo"
ANALYSIS_PROCESSED = "analysis_processed"
ANALYSIS_FAILED = "analysis_failed"
ANALYSIS_DONE = "analysis_done"

ALL_PIPELINE_LABELS = {ANALYSIS_TODO, ANALYSIS_PROCESSED, ANALYSIS_FAILED}


def transition_labels(
    current: list[str], add: list[str], remove: list[str]
) -> list[str]:
    result = set(current) - set(remove)
    result |= set(add)
    return sorted(result)


async def apply_transition(
    client,  # GitLabClient
    issue_iid: int,
    add: list[str],
    remove: list[str],
) -> None:
    issue = await client.get_issue(issue_iid)
    new_labels = transition_labels(issue["labels"], add=add, remove=remove)
    logger.info(
        "Label transition on issue #%s: +%s -%s (was %s, now %s)",
        issue_iid, add, remove, issue["labels"], new_labels,
    )
    await client.set_labels(issue_iid, new_labels)
