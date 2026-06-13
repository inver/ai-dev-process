from typing import Literal
from pydantic import BaseModel, Field


class RiskItem(BaseModel):
    description: str
    mitigation: str
    severity: Literal["low", "medium", "high"]


class AnalysisOutput(BaseModel):
    problem_statement: str
    acceptance_criteria: list[str]
    technical_approach: list[str]
    dependencies: list[str]
    risks: list[RiskItem] = Field(default_factory=list)
    estimated_complexity: Literal["low", "medium", "high", "very_high"]
    open_questions: list[str] = Field(default_factory=list)
