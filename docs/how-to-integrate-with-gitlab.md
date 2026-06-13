# How to Integrate with GitLab

This document walks through connecting the AI Dev Process pipeline to a GitLab project so that adding the `analysis_todo` label to any issue automatically triggers an analysis run.

## How it works

```
Issue labeled "analysis_todo"
        │
        ▼
External webhook service detects label event
        │  calls GitLab pipeline trigger API
        ▼
GitLab CI: run-issue-analysis job
        │  runs Docker image from GitLab Container Registry
        ▼
Pipeline fetches issue content, runs Claude Code analyst
        │
        ▼
Codex reviewer scores the analysis
        │
        ├─ approved → writes analysis.json + analysis.md to feature/<N> branch
        │              updates issue description
        │              posts comment with artifact links
        │              removes "analysis_todo", adds "analysis_processed"
        │
        └─ failed  → posts failure comment
                     removes "analysis_todo", adds "analysis_failed"
```

> **Note:** GitLab does not natively trigger pipelines on label events. The trigger step requires a separate webhook service (e.g., a small server or serverless function) that listens for GitLab webhook events and calls the pipeline trigger API when it sees `analysis_todo` applied.

## Prerequisites

- A GitLab project (self-hosted or gitlab.com)
- Maintainer or Owner access to the project
- A Claude Code OAuth token (`claude setup-token`)
- An OpenAI API key (for the Codex reviewer)
- A webhook receiver that can call the GitLab pipeline trigger API (see Step 4)

## Step 1 — Create the required labels

Go to **Issues → Labels → New label** and create:

| Label | Suggested color | Purpose |
|---|---|---|
| `analysis_todo` | `#F0AD4E` (yellow) | Trigger: add this to request analysis |
| `analysis_processed` | `#428BCA` (blue) | Set by pipeline on success |
| `analysis_failed` | `#D9534F` (red) | Set by pipeline on failure |
| `analysis_done` | `#5CB85C` (green) | Optional: manual approval signal |

## Step 2 — Configure CI/CD variables

Go to **Settings → CI/CD → Variables** and add:

| Variable | Value | Masked | Protected |
|---|---|---|---|
| `GITLAB_TOKEN` | A project access token or personal access token with `api` scope and at least Developer role. | ✓ | ✓ |
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth token. Generate with `claude setup-token`. | ✓ | ✓ |
| `CODEX_AUTH_JSON_B64` | Base64-encoded contents of `~/.codex/auth.json` (preferred for CI). Alternatively set `CODEX_API_KEY` with your OpenAI API key. | ✓ | ✓ |

> **Protected variables** are only injected into jobs running on protected branches/tags. If you run analysis on unprotected refs, uncheck "Protected" or add the ref to the protected list.

### Creating a project access token

**Settings → Access Tokens → Add new token**:

- Token name: `analysis-pipeline`
- Expiration: set an appropriate date
- Role: `Developer`
- Scopes: `api`

## Step 3 — Create a pipeline trigger token

**Settings → CI/CD → Pipeline trigger tokens → Add new token**

Copy the token value — the webhook service needs it to start pipelines.

## Step 4 — Set up the webhook receiver

GitLab fires a webhook on label events but cannot directly start a CI pipeline from it. You need a small service in between.

### What the webhook receiver must do

1. Receive a `POST` from GitLab on the Issue label event
2. Verify the payload contains `object_attributes.action == "update"` and the label `analysis_todo` is in `labels`
3. Call the GitLab pipeline trigger API:

```
POST https://<gitlab-host>/api/v4/projects/<PROJECT_ID>/trigger/pipeline
Content-Type: application/x-www-form-urlencoded

token=<PIPELINE_TRIGGER_TOKEN>&ref=main&variables[ISSUE_ID]=<issue_iid>&variables[TRIGGER_TYPE]=analysis
```

### Minimal example (Python / Flask)

```python
import os, hmac, hashlib, requests
from flask import Flask, request, abort

app = Flask(__name__)

GITLAB_URL     = os.environ["GITLAB_URL"]          # e.g. https://gitlab.com
PROJECT_ID     = os.environ["GITLAB_PROJECT_ID"]
TRIGGER_TOKEN  = os.environ["GITLAB_PIPELINE_TRIGGER_TOKEN"]
WEBHOOK_SECRET = os.environ.get("GITLAB_WEBHOOK_SECRET", "")

@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        token = request.headers.get("X-Gitlab-Token", "")
        if not hmac.compare_digest(token, WEBHOOK_SECRET):
            abort(403)

    payload = request.json
    if payload.get("object_kind") != "issue":
        return "ignored", 200

    labels = [l["title"] for l in payload.get("labels", [])]
    if "analysis_todo" not in labels:
        return "ignored", 200

    issue_iid = payload["object_attributes"]["iid"]
    requests.post(
        f"{GITLAB_URL}/api/v4/projects/{PROJECT_ID}/trigger/pipeline",
        data={
            "token": TRIGGER_TOKEN,
            "ref": "main",
            "variables[ISSUE_ID]": str(issue_iid),
            "variables[TRIGGER_TYPE]": "analysis",
        },
    )
    return "triggered", 200
```

### Register the webhook in GitLab

**Settings → Webhooks → Add new webhook**:

- URL: your receiver's public URL (e.g. `https://your-service.example.com/webhook`)
- Secret token: same value as `GITLAB_WEBHOOK_SECRET`
- Trigger: **Issues events**
- SSL verification: enabled (recommended)

## Step 5 — Verify the CI configuration

The repository ships with `.gitlab-ci.yml` containing two jobs:

### `build-analyzer-image`

Runs on every push to the default branch. Builds the Docker image from `Dockerfile` and pushes it to the GitLab Container Registry (`$CI_REGISTRY_IMAGE/analyzer:latest`).

Requires the built-in `CI_REGISTRY_USER` / `CI_REGISTRY_PASSWORD` / `CI_REGISTRY` variables — these are auto-provided by GitLab, no configuration needed.

### `run-issue-analysis`

Runs only when triggered via the pipeline trigger API (i.e. from the webhook receiver). Pulls the image built above and runs `python -m src.pipeline.main`.

The job reads these variables from the environment:

| Variable | Source | Description |
|---|---|---|
| `ISSUE_ID` | trigger payload | Issue IID to analyze |
| `TRIGGER_TYPE` | trigger payload | Always `analysis` |
| `GITLAB_URL` | `$CI_SERVER_URL` | Auto-set to the running GitLab instance |
| `GITLAB_PROJECT_ID` | `$CI_PROJECT_ID` | Auto-set by GitLab CI |
| `GITLAB_PROJECT_PATH` | `$CI_PROJECT_PATH` | Auto-set by GitLab CI |
| `GITLAB_TOKEN` | CI/CD variable | Project access token (Step 2) |
| `CLAUDE_CODE_OAUTH_TOKEN` | CI/CD variable | Claude Code auth (Step 2) |
| `CODEX_AUTH_JSON_B64` | CI/CD variable | Codex auth (Step 2) |

Optional tuning (add as CI/CD variables or to the job's `variables:` block):

| Variable | Default | Description |
|---|---|---|
| `MAX_ITERATIONS` | `3` | Maximum analyst–reviewer cycles |
| `ITERATION_TIMEOUT_SECONDS` | `600` | Per-iteration timeout (seconds) |
| `MIN_REVIEW_QUALITY_SCORE` | `7` | Minimum score (1–10) to approve |
| `ANALYST_MODEL` | `claude-sonnet-4-6` | Claude model for analysis |
| `REVIEWER_MODEL` | `gpt-5.5` | OpenAI model for review |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for verbose logs |

## Step 6 — Trigger a test run

1. Push to `main` to build the Docker image (check **Build → Pipelines** for the `build-analyzer-image` job)
2. Open any issue in the project
3. Add the `analysis_todo` label
4. The webhook receiver calls the trigger API → check **Build → Pipelines** for the `run-issue-analysis` job

A successful run:
- Posts a comment on the issue with links to `analysis.json` and `analysis.md`
- Updates the issue description with the Markdown analysis
- Replaces `analysis_todo` with `analysis_processed`
- Creates a `feature/<issue-number>` branch with the artifacts under `analysis/<issue-number>/`

## Retrying a failed analysis

1. Remove `analysis_failed` from the issue
2. Re-add `analysis_todo`

The pipeline is idempotent — it recreates the feature branch if it already exists and overwrites previous artifacts.

## Self-hosted GitLab

No special configuration is needed. The pipeline reads `GITLAB_URL` from `$CI_SERVER_URL`, which is automatically set to the correct URL of your GitLab instance. Do not hardcode `https://gitlab.com` — it will 401/404 on a self-hosted instance.

## Artifacts

The `run-issue-analysis` job retains analysis artifacts for 90 days:

```
analysis/
  <issue-iid>/
    analysis_iter1.json   ← per-iteration analyst snapshots
    analysis_iter1.md
    review_iter1.json     ← per-iteration reviewer snapshots
    analysis.json         ← final approved output
    analysis.md
```

Artifacts are also committed to the `feature/<issue-iid>` branch and linked in the issue comment.

## Troubleshooting

**Pipeline is not triggered when label is added**
Check your webhook receiver logs. Confirm the GitLab webhook is configured with "Issues events" and the receiver is reachable from GitLab. Test with **Settings → Webhooks → Test → Issues events**.

**`run-issue-analysis` job fails with "image not found"**
The `build-analyzer-image` job has not run yet or failed. Push to `main` and confirm that job succeeds.

**`GITLAB_TOKEN` not found / 401 errors**
Confirm the variable is defined in **Settings → CI/CD → Variables** and is not restricted to protected refs only (or that `main` is a protected branch).

**Analysis fails with "Max iterations reached"**
Increase `MAX_ITERATIONS` or tune `MIN_REVIEW_QUALITY_SCORE`. Check the job log for the reviewer's feedback to understand why it was rejected repeatedly.

**Job timeout**
The job has a 40-minute timeout (`timeout: 40 minutes` in `.gitlab-ci.yml`). Reduce `MAX_ITERATIONS` or increase `ITERATION_TIMEOUT_SECONDS` to balance quality against wall-clock time.
