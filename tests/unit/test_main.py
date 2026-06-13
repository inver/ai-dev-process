import pytest
from src import config


def _set_required(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "1")
    monkeypatch.setenv("ISSUE_ID", "42")


def test_main_exits_when_token_missing(monkeypatch, capsys):
    _set_required(monkeypatch)
    monkeypatch.setenv("GITLAB_TOKEN", "")
    config.get_settings.cache_clear()

    from src.pipeline import main as main_mod
    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 1
    assert "GITLAB_TOKEN" in capsys.readouterr().err


def test_main_exits_when_oauth_token_missing(monkeypatch, capsys):
    _set_required(monkeypatch)
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")
    config.get_settings.cache_clear()

    from src.pipeline import main as main_mod
    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 1
    assert "CLAUDE_CODE_OAUTH_TOKEN" in capsys.readouterr().err


def test_main_exits_when_issue_id_missing(monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "1")
    monkeypatch.setenv("ISSUE_ID", "0")
    config.get_settings.cache_clear()

    from src.pipeline import main as main_mod
    with pytest.raises(SystemExit) as exc:
        main_mod.main()

    assert exc.value.code == 1
    assert "ISSUE_ID" in capsys.readouterr().err
