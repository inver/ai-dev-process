import operator
from typing import Annotated, Optional, TypedDict


class AnalysisState(TypedDict):
    # Populated by gather_context node
    issue_iid: int
    project_id: str
    project_path: str
    trigger_type: str          # "analysis" or "reanalysis"
    issue_title: str
    issue_description: str
    issue_comments: list[dict]
    issue_labels: list[str]
    readme_content: str
    file_tree: str

    # Loop control (set in initial state)
    max_iterations: int
    iteration_timeout_seconds: int

    # Updated by analyze/revise nodes
    iteration: int
    iteration_start_time: str  # ISO 8601 string (JSON-serializable)
    current_analysis: str      # JSON string of AnalysisOutput
    current_analysis_structured: dict

    # Updated by review node
    review_result: Optional[dict]
    # Reducer: each review appends one entry without overwriting prior history
    analysis_history: Annotated[list[dict], operator.add]

    # Terminal state
    approved: bool
    status: str                # "analyzing" | "reviewing" | "approved" | "failed"
    failure_reason: Optional[str]

    # Set by finalize node
    branch_name: str
    artifact_json_url: Optional[str]
    artifact_md_url: Optional[str]
    gitlab_comment_id: Optional[int]
