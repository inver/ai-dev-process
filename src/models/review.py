from pydantic import BaseModel, Field, field_validator


class ReviewResult(BaseModel):
    approved: bool
    feedback: str
    quality_score: int = Field(ge=1, le=10)
    missing_sections: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
