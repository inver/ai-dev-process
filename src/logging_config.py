"""Central logging configuration for the analysis pipeline.

Logs go to stderr so they don't pollute stdout (the Claude Code CLI and the
pipeline both reserve stdout for structured output). Call ``setup_logging``
once at process start; module loggers obtained via ``logging.getLogger`` then
inherit the configured level and format.
"""
import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, idempotently.

    Quiets noisy third-party loggers (httpx, urllib3) to WARNING so the
    Claude Code / Codex interaction logs we add stay readable.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
        stream=sys.stderr,
    )

    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
