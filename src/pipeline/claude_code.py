"""Run the analyst step through the Claude Code CLI in headless mode.

Instead of calling the Anthropic API directly, we invoke `claude -p` as a
subprocess. This lets the analyst optionally explore the checked-out repo with
read-only tools (Read/Grep/Glob) while still returning a structured
AnalysisOutput. Authentication uses an OAuth token (CLAUDE_CODE_OAUTH_TOKEN),
generated via `claude setup-token`.
"""
import json
import logging
import os
import shutil
import subprocess
import time

from src.config import get_settings
from src.models.analysis import AnalysisOutput

logger = logging.getLogger(__name__)

# Read-only tools the analyst may use to inspect the repository. Anything not
# listed is auto-denied in --print mode (no interactive prompt, no hang).
ANALYST_ALLOWED_TOOLS = "Read,Grep,Glob"


class ClaudeCodeError(RuntimeError):
    """Raised when the Claude Code CLI fails or returns unusable output."""


def _format_process_output(stdout: str | None, stderr: str | None) -> str:
    """Format captured process output without truncating diagnostics."""
    stdout = stdout or ""
    stderr = stderr or ""
    if stdout and stderr:
        return f"stdout:\n{stdout}\nstderr:\n{stderr}"
    return stdout or stderr


def _extract_json(text: str) -> str:
    """Pull a JSON object out of the model's final text, tolerating ``` fences
    or surrounding prose."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return text


def _build_command(cli: str, system_prompt: str, settings) -> list[str]:
    return [
        cli,
        "-p",
        "--output-format", "json",
        "--model", settings.analyst_model,
        "--append-system-prompt", system_prompt,
        "--max-turns", str(settings.claude_code_max_turns),
        "--allowedTools", ANALYST_ALLOWED_TOOLS,
    ]


def run_claude_analysis(system_prompt: str, user_prompt: str, settings=None) -> AnalysisOutput:
    """Invoke Claude Code headless and parse its result into an AnalysisOutput.

    The user prompt is passed on stdin to avoid command-line length limits.
    """
    s = settings or get_settings()
    cli = shutil.which("claude") or "claude"

    env = dict(os.environ)
    token = s.claude_code_oauth_token.get_secret_value()
    auth_mode = "api-key"
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
        # Ensure OAuth is used rather than falling back to API-key auth.
        env.pop("ANTHROPIC_API_KEY", None)
        auth_mode = "oauth-token"

    logger.info(
        "Invoking Claude Code: cli=%s model=%s max_turns=%s tools=[%s] auth=%s "
        "timeout=%ss (system_prompt=%d chars, user_prompt=%d chars)",
        cli, s.analyst_model, s.claude_code_max_turns, ANALYST_ALLOWED_TOOLS,
        auth_mode, s.iteration_timeout_seconds, len(system_prompt), len(user_prompt),
    )
    logger.debug("Claude Code command: %s", _build_command(cli, system_prompt, s))

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
        logger.error("Claude Code CLI ('claude') not found on PATH")
        raise ClaudeCodeError(
            "Claude Code CLI ('claude') not found on PATH. Install "
            "@anthropic-ai/claude-code in the analysis image."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        logger.error(
            "Claude Code timed out after %ss", s.iteration_timeout_seconds,
        )
        raise ClaudeCodeError(
            f"Claude Code timed out after {s.iteration_timeout_seconds}s"
        ) from exc

    elapsed = time.monotonic() - started
    logger.info(
        "Claude Code returned exit=%s in %.1fs (stdout=%d bytes, stderr=%d bytes)",
        proc.returncode, elapsed, len(proc.stdout or ""), len(proc.stderr or ""),
    )

    if proc.returncode != 0:
        detail = _format_process_output(proc.stdout, proc.stderr)
        logger.error(
            "Claude Code exited %s; stdout: %s; stderr: %s",
            proc.returncode,
            proc.stdout or "",
            proc.stderr or "",
        )
        raise ClaudeCodeError(f"Claude Code exited {proc.returncode}: {detail}")

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        logger.error(
            "Could not parse Claude Code JSON output: %s", proc.stdout,
        )
        raise ClaudeCodeError(
            f"Could not parse Claude Code JSON output: {proc.stdout}"
        ) from exc

    # The CLI's JSON envelope carries useful run metadata; surface it for cost
    # and turn tracking across iterations.
    logger.info(
        "Claude Code run metadata: session=%s num_turns=%s duration_api_ms=%s "
        "cost_usd=%s is_error=%s",
        payload.get("session_id"), payload.get("num_turns"),
        payload.get("duration_api_ms"), payload.get("total_cost_usd"),
        payload.get("is_error"),
    )

    if payload.get("is_error"):
        logger.error(
            "Claude Code reported an error: %s",
            str(payload.get("result", "")),
        )
        raise ClaudeCodeError(
            f"Claude Code reported an error: {str(payload.get('result', ''))}"
        )

    result_text = payload.get("result", "")
    json_text = _extract_json(result_text)
    try:
        output = AnalysisOutput.model_validate_json(json_text)
    except Exception as exc:
        logger.error(
            "Claude Code output did not match AnalysisOutput schema: %s",
            json_text,
        )
        raise ClaudeCodeError(
            f"Claude Code output did not match AnalysisOutput schema: {json_text}"
        ) from exc

    logger.info(
        "Claude Code analysis parsed OK: complexity=%s, %d acceptance criteria, "
        "%d risks",
        getattr(output, "estimated_complexity", None),
        len(getattr(output, "acceptance_criteria", []) or []),
        len(getattr(output, "risks", []) or []),
    )
    return output
