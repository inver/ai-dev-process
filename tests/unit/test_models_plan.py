from src.models.plan import PlanOutput, PlanReviewResult, PlanState, PlanTask


def test_plan_task_model():
    task = PlanTask(
        id="T1",
        title="Add login endpoint",
        description="Implement POST /login",
        files_to_modify=["src/auth.py"],
        files_to_create=["tests/test_auth.py"],
        test_steps=["pytest tests/test_auth.py"],
        estimated_minutes=30,
    )
    assert task.id == "T1"
    assert task.estimated_minutes == 30


def test_plan_output_model():
    plan = PlanOutput(
        summary="Implement login",
        tasks=[],
        total_estimated_minutes=0,
        test_plan=["pytest"],
        assumptions=[],
    )
    assert plan.summary == "Implement login"
    assert plan.model_dump_json()


def test_plan_review_result():
    review = PlanReviewResult(
        approved=True,
        quality_score=8,
        feedback="Good plan",
        concerns=[],
        missing_sections=[],
        suggestions=[],
    )
    assert review.approved
    assert 1 <= review.quality_score <= 10


def test_plan_state_keys():
    keys = PlanState.__annotations__.keys()
    assert "issue_iid" in keys
    assert "current_plan" in keys
    assert "plan_history" in keys
