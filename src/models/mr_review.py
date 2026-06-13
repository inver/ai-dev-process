import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class DeveloperOutput(BaseModel):
    implementation_summary: str
    files_modified: list[str] = Field(default_factory=list)
    files_created: list[str] = Field(default_factory=list)
    tests_run: bool = False
    test_summary: str = ""
    open_questions: list[str] = Field(default_factory=list)


class MRReviewResult(BaseModel):
    approved: bool
    quality_score: int
    feedback: str
    concerns: list[str] = Field(default_factory=list)
    blocking_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class DevelopmentState(TypedDict):
    issue_iid: int
    project_id: str
    project_path: str
    trigger_type: str
    issue_title: str
    issue_description: str
    issue_comments: list[dict]
    issue_labels: list[str]
    readme_content: str
    file_tree: str
    analysis_content: str
    plan_content: str

    max_iterations: int
    iteration_timeout_seconds: int

    iteration: int
    iteration_start_time: str
    dev_branch_name: str
    implementation_summary: str
    review_result: dict | None
    dev_history: Annotated[list[dict], operator.add]

    mr_id: int | None
    mr_url: str | None
    mr_diff: str

    approved: bool
    status: str
    failure_reason: str | None
    branch_name: str
    gitlab_comment_id: int | None
