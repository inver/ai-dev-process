from pathlib import Path

_PROMPTS_DIR = Path(__file__).parents[2] / "prompts"


def _load(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


ANALYST_SYSTEM = _load("analyst_system.md")
ANALYST_INITIAL = _load("analyst_initial.md")
ANALYST_REVISION = _load("analyst_revision.md")
REVIEWER_SYSTEM = _load("reviewer_system.md")
REVIEWER_PROMPT = _load("reviewer_prompt.md")


def format_comments(comments: list[dict]) -> str:
    if not comments:
        return "(no comments)"
    return "\n".join(
        f"[{c['author']} at {c['created_at']}]: {c['body']}"
        for c in comments
    )
