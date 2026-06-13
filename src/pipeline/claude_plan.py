"""Run the planner step through the Claude Code CLI in headless mode."""
import json
import logging
import os
import shutil
import subprocess
import time

from src.config import get_settings
from src.models.plan import PlanOutput
from src.pipeline.claude_code import ClaudeCodeError, _extract_json

logger = logging.getLogger(__name__)

PLANNER_ALLOWED_TOOLS = "Read,Grep,Glob"


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
        str(settings.claude_code_max_turns),
        "--allowedTools",
        PLANNER_ALLOWED_TOOLS,
    ]


def run_claude_plan(system_prompt: str, user_prompt: str, settings=None) -> PlanOutput:
    s = settings or get_settings()
    cli = shutil.which("claude") or "claude"

    env = dict(os.environ)
    token = s.claude_code_oauth_token.get_secret_value()
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        env.pop("ANTHROPIC_API_KEY", None)

    logger.info(
        "Invoking Claude Code planner: model=%s max_turns=%s tools=[%s]",
        s.analyst_model,
        s.claude_code_max_turns,
        PLANNER_ALLOWED_TOOLS,
    )
    started = time.monotonic()
    try:
        proc = subprocess.run(
            _build_command(cli, system_prompt, s),
            input=user_prompt,
            capture_output=True,
            text=True,
            env=env,
            timeout=s.iteration_timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise ClaudeCodeError("Claude Code CLI not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCodeError(
            f"Claude Code planner timed out after {s.iteration_timeout_seconds}s"
        ) from exc

    logger.info(
        "Claude Code planner returned exit=%s in %.1fs",
        proc.returncode,
        time.monotonic() - started,
    )
    if proc.returncode != 0:
        detail = (proc.stdout or proc.stderr or "")[:500]
        raise ClaudeCodeError(f"Claude Code planner exited {proc.returncode}: {detail}")

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeCodeError(
            f"Could not parse Claude Code planner output: {proc.stdout[:500]}"
        ) from exc

    logger.info(
        "Claude Code planner metadata: turns=%s cost=%s",
        payload.get("num_turns"),
        payload.get("total_cost_usd"),
    )
    if payload.get("is_error"):
        raise ClaudeCodeError(
            f"Claude Code planner error: {str(payload.get('result', ''))[:500]}"
        )

    json_text = _extract_json(payload.get("result", ""))
    try:
        return PlanOutput.model_validate_json(json_text)
    except Exception as exc:
        raise ClaudeCodeError(
            f"Planner output did not match PlanOutput schema: {json_text[:500]}"
        ) from exc
