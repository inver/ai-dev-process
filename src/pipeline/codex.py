"""Run the reviewer step through the OpenAI Codex CLI in headless mode.

Instead of calling the OpenAI API via langchain-openai, we invoke `codex exec`
as a subprocess. The reviewer gets the combined system + user prompt on stdin and
writes its final message (a JSON ReviewResult) to a temp file via
--output-last-message.

Auth priority (highest first):
  1. CODEX_API_KEY        — passed as OPENAI_API_KEY to the subprocess
  2. CODEX_AUTH_JSON_B64  — base64-encoded auth.json written to a temp dir under
                            HOME; CLI picks it up via CODEX_HOME (preserves
                            auth_mode so ChatGPT OAuth tokens work correctly)
  3. (neither)            — CLI reads the real ~/.codex/auth.json from disk
"""
import base64
import logging
import os
import shutil
import subprocess
import tempfile
import time

from src.config import get_settings
from src.models.review import ReviewResult

logger = logging.getLogger(__name__)


class CodexError(RuntimeError):
    """Raised when the Codex CLI fails or returns unusable output."""


def _format_process_output(stdout: str | None, stderr: str | None) -> str:
    """Format captured process output without truncating diagnostics."""
    stdout = stdout or ""
    stderr = stderr or ""
    if stdout and stderr:
        return f"stdout:\n{stdout}\nstderr:\n{stderr}"
    return stdout or stderr


def _extract_json(text: str) -> str:
    """Pull a JSON object out of the model's text, tolerating ``` fences or prose."""
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


def _build_command(cli: str, settings, output_path: str) -> list[str]:
    return [
        cli, "exec",
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--model", settings.reviewer_model,
        "--output-last-message", output_path,
        "-",  # read prompt from stdin
    ]


def run_codex_review(system_prompt: str, user_prompt: str, settings=None) -> ReviewResult:
    """Invoke the Codex CLI headless and parse its result into a ReviewResult.

    The system and user prompts are concatenated and passed on stdin to avoid
    command-line length limits.
    """
    s = settings or get_settings()
    cli = shutil.which("codex") or "codex"

    env = dict(os.environ)
    api_key = s.codex_api_key.get_secret_value()
    auth_json_b64 = s.codex_auth_json_b64.get_secret_value()

    tmp_codex_home: str | None = None
    if api_key:
        env["OPENAI_API_KEY"] = api_key
        auth_mode = "api-key"
    elif auth_json_b64:
        # Write auth.json to a temp dir under HOME and point CODEX_HOME at it.
        # The full file is needed so the CLI picks up auth_mode (e.g. "chatgpt")
        # and authenticates correctly — extracting only the access_token and
        # passing it as OPENAI_API_KEY fails for ChatGPT OAuth tokens.
        try:
            auth_json_bytes = base64.b64decode(auth_json_b64)
        except Exception as exc:
            raise CodexError(f"CODEX_AUTH_JSON_B64 is not valid base64: {exc}") from exc
        tmp_codex_home = tempfile.mkdtemp(
            dir=os.path.expanduser("~"), prefix=".codex-review-"
        )
        with open(os.path.join(tmp_codex_home, "auth.json"), "wb") as f:
            f.write(auth_json_bytes)
        env["CODEX_HOME"] = tmp_codex_home
        auth_mode = "auth-json-b64"
    else:
        auth_mode = "auth-json"  # CLI reads the real ~/.codex/auth.json from disk

    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    os.close(tmp_fd)
    try:
        cmd = _build_command(cli, s, tmp_path)
        logger.info(
            "Invoking Codex reviewer: cli=%s model=%s auth=%s timeout=%ss "
            "(system_prompt=%d chars, user_prompt=%d chars)",
            cli, s.reviewer_model, auth_mode, s.iteration_timeout_seconds,
            len(system_prompt), len(user_prompt),
        )
        logger.debug("Codex command: %s", cmd)

        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                env=env,
                timeout=s.iteration_timeout_seconds,
            )
        except FileNotFoundError as exc:
            logger.error("Codex CLI ('codex') not found on PATH")
            raise CodexError(
                "Codex CLI ('codex') not found on PATH. Install @openai/codex in the analysis image."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            logger.error("Codex timed out after %ss", s.iteration_timeout_seconds)
            raise CodexError(
                f"Codex timed out after {s.iteration_timeout_seconds}s"
            ) from exc

        elapsed = time.monotonic() - started
        logger.info(
            "Codex returned exit=%s in %.1fs (stdout=%d bytes, stderr=%d bytes)",
            proc.returncode, elapsed, len(proc.stdout or ""), len(proc.stderr or ""),
        )

        if proc.returncode != 0:
            detail = _format_process_output(proc.stdout, proc.stderr)
            logger.error(
                "Codex exited %s; stdout: %s; stderr: %s",
                proc.returncode,
                proc.stdout or "",
                proc.stderr or "",
            )
            raise CodexError(f"Codex exited {proc.returncode}: {detail}")

        try:
            with open(tmp_path) as f:
                result_text = f.read()
        except OSError as exc:
            raise CodexError(f"Could not read Codex output: {exc}") from exc

        json_text = _extract_json(result_text)
        try:
            review = ReviewResult.model_validate_json(json_text)
        except Exception as exc:
            logger.error(
                "Codex output did not match ReviewResult schema: %s", json_text,
            )
            raise CodexError(
                f"Codex output did not match ReviewResult schema: {json_text}"
            ) from exc

        logger.info(
            "Codex review parsed OK: approved=%s quality_score=%s "
            "(%d concern(s), %d missing section(s))",
            review.approved, review.quality_score,
            len(review.concerns or []), len(review.missing_sections or []),
        )
        return review
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        if tmp_codex_home:
            shutil.rmtree(tmp_codex_home, ignore_errors=True)
