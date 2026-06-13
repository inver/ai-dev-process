import pytest


@pytest.fixture(autouse=True)
def _default_env(monkeypatch):
    """Provide dummy required settings so get_settings() works in tests that
    exercise real code paths (graph nodes, webhook routes). Individual tests
    may override these via their own monkeypatch.setenv calls."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    # CODEX_API_KEY is optional — Codex CLI falls back to ~/.codex/auth.json
    monkeypatch.setenv("GITLAB_TOKEN", "test-gitlab")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "123")

    from src.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
