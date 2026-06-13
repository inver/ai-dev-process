import os
import pytest
from src.config import Settings, get_settings


def test_settings_reads_env_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    monkeypatch.setenv("GITLAB_TOKEN", "test-gitlab")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "123")
    monkeypatch.setenv("ISSUE_ID", "42")
    settings = Settings()
    assert settings.issue_id == 42
    assert settings.anthropic_api_key.get_secret_value() == "test-anthropic"


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("GITLAB_TOKEN", "x")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "1")
    settings = Settings()
    assert settings.gitlab_url == "https://gitlab.com"
    assert settings.max_iterations == 3
    assert settings.iteration_timeout_seconds == 600
    assert settings.analyst_model == "claude-sonnet-4-6"
    assert settings.reviewer_model == "gpt-5.5"


def test_new_settings_defaults():
    settings = Settings()
    assert settings.developer_max_turns == 60
    assert settings.plan_max_iterations == 3
    assert settings.develop_max_iterations == 3
    assert settings.git_user_email == "ai-dev-process@noreply"
    assert settings.git_user_name == "AI Dev Process"
