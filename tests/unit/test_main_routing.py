from unittest.mock import MagicMock, patch

from src.config import Settings
from src.pipeline import main as main_module


def test_select_graph_routes_to_plan_graph():
    settings = Settings(trigger_type="plan", issue_id=1, platform="github")
    mock_graph = MagicMock()
    with patch.object(main_module, "build_plan_graph", return_value=mock_graph) as build_plan:
        graph, state = main_module._select_graph_and_state(settings, 1)
    build_plan.assert_called_once()
    assert graph is mock_graph
    assert state["status"] == "planning"
    assert state["max_iterations"] == settings.plan_max_iterations


def test_select_graph_routes_to_dev_graph():
    settings = Settings(trigger_type="develop", issue_id=1, platform="github")
    mock_graph = MagicMock()
    with patch.object(main_module, "build_dev_graph", return_value=mock_graph) as build_dev:
        graph, state = main_module._select_graph_and_state(settings, 1)
    build_dev.assert_called_once()
    assert graph is mock_graph
    assert state["status"] == "developing"
    assert state["max_iterations"] == settings.develop_max_iterations


def test_failure_labels_for_new_triggers():
    assert main_module._failure_labels("plan") == ("plan_todo", "plan_failed")
    assert main_module._failure_labels("develop") == ("develop_todo", "develop_failed")
