"""Run the plan reviewer step through the Codex CLI in headless mode."""
import base64
import logging
import os
import shutil
import subprocess
import tempfile
import time

from src.config import get_settings
from src.models.plan import PlanReviewResult
from src.pipeline.codex import CodexError, _extract_json

logger = logging.getLogger(__name__)


def _build_command(cli: str, settings, output_path: str) -> list[str]:
    return [
        cli,
        "exec",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--model",
        settings.reviewer_model,
        "--output-last-message",
        output_path,
        "-",
    ]


def run_codex_plan_review(
    system_prompt: str, user_prompt: str, settings=None
) -> PlanReviewResult:
    s = settings or get_settings()
    cli = shutil.which("codex") or "codex"
    env = dict(os.environ)
    tmp_codex_home: str | None = None

    api_key = s.codex_api_key.get_secret_value()
    auth_json_b64 = s.codex_auth_json_b64.get_secret_value()
    if api_key:
        env["OPENAI_API_KEY"] = api_key
    elif auth_json_b64:
        try:
            auth_bytes = base64.b64decode(auth_json_b64)
        except Exception as exc:
            raise CodexError(f"CODEX_AUTH_JSON_B64 invalid base64: {exc}") from exc
        tmp_codex_home = tempfile.mkdtemp(
            dir=os.path.expanduser("~"), prefix=".codex-plan-review-"
        )
        with open(os.path.join(tmp_codex_home, "auth.json"), "wb") as f:
            f.write(auth_bytes)
        env["CODEX_HOME"] = tmp_codex_home

    full_prompt = f"{system_prompt}\n\n{user_prompt}"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    os.close(tmp_fd)
    try:
        logger.info(
            "Invoking Codex plan reviewer: model=%s timeout=%ss",
            s.reviewer_model,
            s.iteration_timeout_seconds,
        )
        started = time.monotonic()
        try:
            proc = subprocess.run(
                _build_command(cli, s, tmp_path),
                input=full_prompt,
                capture_output=True,
                text=True,
                env=env,
                timeout=s.iteration_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise CodexError("Codex CLI not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise CodexError(
                f"Codex plan reviewer timed out after {s.iteration_timeout_seconds}s"
            ) from exc

        logger.info(
            "Codex plan reviewer returned exit=%s in %.1fs",
            proc.returncode,
            time.monotonic() - started,
        )
        if proc.returncode != 0:
            detail = (proc.stdout or proc.stderr or "")[:500]
            raise CodexError(f"Codex plan reviewer exited {proc.returncode}: {detail}")

        try:
            with open(tmp_path) as f:
                result_text = f.read()
        except OSError as exc:
            raise CodexError(f"Could not read Codex plan review output: {exc}") from exc

        json_text = _extract_json(result_text)
        try:
            return PlanReviewResult.model_validate_json(json_text)
        except Exception as exc:
            raise CodexError(
                f"Codex plan review did not match PlanReviewResult schema: {json_text[:500]}"
            ) from exc
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        if tmp_codex_home:
            shutil.rmtree(tmp_codex_home, ignore_errors=True)
