from src.models.mr_review import DeveloperOutput, DevelopmentState, MRReviewResult


def test_developer_output():
    output = DeveloperOutput(
        implementation_summary="Added login endpoint",
        files_modified=["src/auth.py"],
        files_created=["tests/test_auth.py"],
        tests_run=True,
        test_summary="All tests pass",
        open_questions=[],
    )
    assert output.tests_run
    assert output.model_dump_json()


def test_mr_review_result():
    review = MRReviewResult(
        approved=False,
        quality_score=5,
        feedback="Missing error handling",
        concerns=["No 404 response"],
        blocking_issues=["Unhandled exception on line 42"],
        suggestions=[],
    )
    assert not review.approved
    assert review.blocking_issues


def test_development_state_keys():
    keys = DevelopmentState.__annotations__.keys()
    assert "issue_iid" in keys
    assert "mr_id" in keys
    assert "dev_branch_name" in keys
    assert "dev_history" in keys
