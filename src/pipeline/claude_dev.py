"""Run the developer step through the Claude Code CLI with write tools."""
import json
import logging
import os
import shutil
import subprocess
import time

from src.config import get_settings
from src.models.mr_review import DeveloperOutput
from src.pipeline.claude_code import (
    ClaudeCodeError,
    _extract_json,
    _format_process_output,
)

logger = logging.getLogger(__name__)

DEVELOPER_ALLOWED_TOOLS = "Edit,Write,Bash,Read,Grep,Glob"


def _build_command(cli: str, system_prompt: str, settings) -> list[str]:
    return [
        cli,
        "-p",
        "--output-format",
        "json",
        "--model",
        settings.analyst_model,
        "--append-system-prompt",
        system_prompt,
        "--max-turns",
        str(settings.developer_max_turns),
        "--allowedTools",
        DEVELOPER_ALLOWED_TOOLS,
    ]


def run_claude_dev(
    system_prompt: str, user_prompt: str, repo_dir: str, settings=None
) -> DeveloperOutput:
    s = settings or get_settings()
    cli = shutil.which("claude") or "claude"

    env = dict(os.environ)
    token = s.claude_code_oauth_token.get_secret_value()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        env.pop("ANTHROPIC_API_KEY", None)

    logger.info(
        "Invoking Claude Code developer: model=%s max_turns=%s timeout=%ss tools=[%s] cwd=%s",
        s.analyst_model,
        s.developer_max_turns,
        s.developer_timeout_seconds,
        DEVELOPER_ALLOWED_TOOLS,
        repo_dir,
    )
    started = time.monotonic()
    try:
        proc = subprocess.run(
            _build_command(cli, system_prompt, s),
            input=user_prompt,
            capture_output=True,
            text=True,
            env=env,
            cwd=repo_dir,
            timeout=s.developer_timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise ClaudeCodeError("Claude Code CLI not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCodeError(
            f"Claude Code developer timed out after {s.developer_timeout_seconds}s"
        ) from exc

    logger.info(
        "Claude Code developer returned exit=%s in %.1fs",
        proc.returncode,
        time.monotonic() - started,
    )
    if proc.returncode != 0:
        detail = _format_process_output(proc.stdout, proc.stderr)
        raise ClaudeCodeError(f"Claude Code developer exited {proc.returncode}: {detail}")

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeCodeError(f"Could not parse developer output: {proc.stdout}") from exc

    logger.info(
        "Claude Code developer metadata: turns=%s cost=%s",
        payload.get("num_turns"),
        payload.get("total_cost_usd"),
    )
    if payload.get("is_error"):
        raise ClaudeCodeError(
            f"Claude Code developer error: {str(payload.get('result', ''))}"
        )

    json_text = _extract_json(payload.get("result", ""))
    try:
        return DeveloperOutput.model_validate_json(json_text)
    except Exception as exc:
        raise ClaudeCodeError(
            f"Developer output did not match DeveloperOutput schema: {json_text}"
        ) from exc
