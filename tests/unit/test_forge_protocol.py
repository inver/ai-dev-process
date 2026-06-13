from src.forge.client import ForgeClient
from src.gitlab.client import GitLabClient

def test_gitlab_client_satisfies_forge_protocol():
    # Protocol is structural — GitLabClient already has all required methods
    assert issubclass(GitLabClient, ForgeClient)

def test_github_client_satisfies_forge_protocol():
    from src.github.client import GitHubClient
    assert issubclass(GitHubClient, ForgeClient)
