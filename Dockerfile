# Dockerfile — analysis pipeline (analyst runs via the Claude Code CLI)
FROM python:3.14-slim

WORKDIR /app

# Node.js + the Claude Code CLI (the analyst shells out to `claude -p`).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg git \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && npm install -g @openai/codex \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements-lock.txt ./
RUN pip install --no-cache-dir --no-deps -r requirements-lock.txt
RUN pip install --no-cache-dir --no-deps -e ".[pipeline]"

COPY src/ ./src/
COPY prompts/ ./prompts/

ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "src.pipeline.main"]
