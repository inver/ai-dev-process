def test_github_settings_defaults(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "123")
    from src.config import Settings
    s = Settings()
    assert s.platform == "gitlab"
    assert s.github_token.get_secret_value() == ""
    assert s.github_owner == ""
    assert s.github_repo == ""


def test_github_platform_settings(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "tok")
    monkeypatch.setenv("GITLAB_PROJECT_ID", "123")
    monkeypatch.setenv("PLATFORM", "github")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_abc")
    monkeypatch.setenv("GITHUB_OWNER", "myorg")
    monkeypatch.setenv("GITHUB_REPO", "myrepo")
    from src.config import Settings
    s = Settings()
    assert s.platform == "github"
    assert s.github_token.get_secret_value() == "ghp_abc"
    assert s.github_owner == "myorg"
    assert s.github_repo == "myrepo"
