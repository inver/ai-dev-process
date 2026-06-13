from src.gitlab.labels import (
    ALL_PIPELINE_LABELS,
    DEVELOP_FAILED,
    DEVELOP_PROCESSED,
    DEVELOP_TODO,
    PLAN_FAILED,
    PLAN_PROCESSED,
    PLAN_TODO,
)


def test_new_label_constants():
    assert PLAN_TODO == "plan_todo"
    assert PLAN_PROCESSED == "plan_processed"
    assert PLAN_FAILED == "plan_failed"
    assert DEVELOP_TODO == "develop_todo"
    assert DEVELOP_PROCESSED == "develop_processed"
    assert DEVELOP_FAILED == "develop_failed"


def test_all_pipeline_labels_includes_new():
    assert PLAN_TODO in ALL_PIPELINE_LABELS
    assert DEVELOP_TODO in ALL_PIPELINE_LABELS
