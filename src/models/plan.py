import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field


class PlanTask(BaseModel):
    id: str
    title: str
    description: str
    files_to_modify: list[str] = Field(default_factory=list)
    files_to_create: list[str] = Field(default_factory=list)
    test_steps: list[str] = Field(default_factory=list)
    estimated_minutes: int = 0


class PlanOutput(BaseModel):
    summary: str
    tasks: list[PlanTask] = Field(default_factory=list)
    total_estimated_minutes: int = 0
    test_plan: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class PlanReviewResult(BaseModel):
    approved: bool
    quality_score: int
    feedback: str
    concerns: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PlanState(TypedDict):
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

    max_iterations: int
    iteration_timeout_seconds: int

    iteration: int
    iteration_start_time: str
    current_plan: str
    current_plan_structured: dict
    review_result: dict | None
    plan_history: Annotated[list[dict], operator.add]

    approved: bool
    status: str
    failure_reason: str | None
    branch_name: str
    artifact_json_url: str | None
    artifact_md_url: str | None
    gitlab_comment_id: int | None
