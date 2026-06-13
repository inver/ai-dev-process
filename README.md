# AI Dev Process — Issue Analyzer

Automatically analyzes GitLab issues using Claude Code (analyst) and OpenAI Codex (reviewer). When you add the `analysis_todo` label to an issue the pipeline reads the issue, generates a structured analysis, has it reviewed by GPT, and writes the approved result back to the issue description along with JSON/Markdown artifacts on a feature branch.

## How it works

1. A webhook (separate service) detects the `analysis_todo` label on an issue and triggers a CI pipeline with `ISSUE_ID`.
2. The `run-issue-analysis` job runs inside the pre-built analyzer Docker image.
3. The analyst (Claude Code CLI) produces a structured `AnalysisOutput`.
4. The reviewer (OpenAI Codex CLI) scores it; if the score is below `MIN_REVIEW_QUALITY_SCORE` the analyst revises.
5. On approval the pipeline writes artifacts to `analysis/<issue_id>/` on the feature branch and updates the issue description.

## Using the analyzer image in another project

### 1. Build or pull the image

The image is built automatically from this repo's `main` branch and pushed to its GitLab Container Registry. Reference it directly:

```
registry.gitlab.com/<this-project-path>/analyzer:latest
```

Or build it yourself:

```bash
docker build -t my-analyzer .
```

### 2. Add CI/CD variables to the target project

Go to **Settings → CI/CD → Variables** and add the following (all masked):

| Variable | Required | Description |
|---|---|---|
| `GITLAB_TOKEN` | yes | GitLab personal/project access token with `api` scope and Developer role |
| `CLAUDE_CODE_OAUTH_TOKEN` | yes | Claude Code OAuth token — generate with `claude setup-token` |
| `CODEX_AUTH_JSON_B64` | yes* | Base64-encoded `~/.codex/auth.json` (ChatGPT Plus / OAuth account) |
| `CODEX_API_KEY` | yes* | OpenAI API key — use instead of `CODEX_AUTH_JSON_B64` for API accounts |
| `MIN_REVIEW_QUALITY_SCORE` | no | Minimum reviewer score to approve (default: `7`, range 1–10) |
| `MAX_ITERATIONS` | no | Max analyst/reviewer cycles before failing (default: `3`) |

*One of `CODEX_AUTH_JSON_B64` or `CODEX_API_KEY` is required.

To get `CODEX_AUTH_JSON_B64`:

```bash
base64 -w0 ~/.codex/auth.json
```

### 3. Add `.gitlab-ci.yml` to the target project

```yaml
variables:
  ANALYZER_IMAGE: "registry.gitlab.com/<this-project-path>/analyzer:latest"
  ISSUE_ID: ""
  TRIGGER_TYPE: "analysis"

run-issue-analysis:
  stage: analyze
  image: "$ANALYZER_IMAGE"
  rules:
    - if: '$CI_PIPELINE_SOURCE == "trigger" && $ISSUE_ID != ""'
  timeout: 40 minutes
  variables:
    ISSUE_ID: "$ISSUE_ID"
    TRIGGER_TYPE: "$TRIGGER_TYPE"
    GITLAB_URL: "$CI_SERVER_URL"
    GITLAB_PROJECT_ID: "$CI_PROJECT_ID"
    GITLAB_PROJECT_PATH: "$CI_PROJECT_PATH"
    # GITLAB_TOKEN, CLAUDE_CODE_OAUTH_TOKEN, CODEX_AUTH_JSON_B64 — from CI/CD variables above
  script:
    - python -m src.pipeline.main
  artifacts:
    when: always
    paths:
      - analysis/
    expire_in: 90 days
```

### 4. Create a pipeline trigger token

In the target project go to **Settings → CI/CD → Pipeline trigger tokens** and create a token. The webhook service uses this to fire the `run-issue-analysis` job when a label is added.

### 5. Set up the webhook service

The webhook listens for GitLab issue events and calls the pipeline trigger API. Configure it with:

- `GITLAB_URL` — your GitLab instance URL
- `GITLAB_TOKEN` — token with `api` scope
- `GITLAB_PIPELINE_TRIGGER_TOKEN` — from step 4
- `GITLAB_PROJECT_ID` — numeric ID of the target project

Point a GitLab webhook at the service URL for **Issues events**.

## Labels

| Label | Meaning |
|---|---|
| `analysis_todo` | Triggers analysis |
| `analysis_processed` | Added on success, removes `analysis_todo` |
| `analysis_failed` | Added on failure |

## Tuning the analyzer

Override these environment variables in the CI job or as CI/CD variables:

| Variable | Default | Description |
|---|---|---|
| `ANALYST_MODEL` | `claude-sonnet-4-6` | Claude model used by the analyst |
| `REVIEWER_MODEL` | `gpt-5.5` | Codex model used by the reviewer |
| `MIN_REVIEW_QUALITY_SCORE` | `7` | Minimum score (1–10) to approve without revision |
| `MAX_ITERATIONS` | `3` | Maximum analyst revision cycles |
| `ITERATION_TIMEOUT_SECONDS` | `600` | Per-iteration timeout in seconds |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`) |

## Artifacts

After a successful run the following files are committed to `feature/<issue_id>` and also written to the issue description:

```
analysis/<issue_id>/
  analysis.json          # final approved artifact
  analysis.md            # rendered Markdown report (written to issue description)
  analysis_iter1.json    # per-iteration analyst snapshots
  analysis_iter1.md
  review_iter1.json      # per-iteration reviewer snapshots
  ...
```

## Running locally

```bash
cp .env.example .env   # fill in required values
pip install -e ".[pipeline]"
ISSUE_ID=42 python -m src.pipeline.main
```

Required `.env` fields: `GITLAB_TOKEN`, `GITLAB_PROJECT_ID`, `CLAUDE_CODE_OAUTH_TOKEN`, and one of `CODEX_AUTH_JSON_B64` / `CODEX_API_KEY`.
