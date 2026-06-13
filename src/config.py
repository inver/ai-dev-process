from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM keys
    # Analyst now runs via the Claude Code CLI (OAuth), so the Anthropic API
    # key is optional and kept only for backwards compatibility.
    anthropic_api_key: SecretStr = SecretStr("")
    # Codex CLI auth — three options, highest priority first:
    #   1. codex_api_key       — explicit OpenAI API key (OPENAI_API_KEY)
    #   2. codex_auth_json_b64 — base64-encoded ~/.codex/auth.json (for CI)
    #   3. (neither)           — Codex CLI reads ~/.codex/auth.json from disk
    codex_api_key: SecretStr = SecretStr("")
    codex_auth_json_b64: SecretStr = SecretStr("")

    # Claude Code (analyst) — headless CLI authenticated via OAuth token.
    claude_code_oauth_token: SecretStr = SecretStr("")
    claude_code_max_turns: int = 12

    # GitLab (both services)
    gitlab_url: str = "https://gitlab.com"
    gitlab_token: SecretStr
    gitlab_project_id: str
    gitlab_project_path: str = ""

    # Pipeline trigger (webhook service only)
    gitlab_pipeline_trigger_token: SecretStr = SecretStr("")

    # Analysis job (injected by CI trigger)
    issue_id: int = 0
    trigger_type: str = "analysis"

    # Loop tuning
    max_iterations: int = 3
    iteration_timeout_seconds: int = 600

    # Logging
    log_level: str = "INFO"

    # Model selection
    analyst_model: str = "claude-sonnet-4-6"
    reviewer_model: str = "gpt-5.5"

    # Review quality gate — analysis is approved only when quality_score >= this value
    min_review_quality_score: int = 7


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
