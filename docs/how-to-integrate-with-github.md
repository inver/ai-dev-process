# How to Integrate with GitHub

This document walks through connecting the AI Dev Process pipeline to a GitHub repository so that adding the
`analysis_todo` label to any issue automatically triggers an analysis run.

## How it works

```
Issue labeled "analysis_todo"
        │
        ▼
GitHub Actions: analyze-issues.yml
        │  pulls image from GHCR
        ▼
Docker container (ghcr.io/<owner>/<repo>:main)
        │  runs python -m src.pipeline.main
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

## Prerequisites

- The repository is hosted on GitHub
- You have admin access (to configure secrets and Actions)
- A Claude Code OAuth token (`claude setup-token`)
- An OpenAI API key (for the Codex reviewer)

## Step 1 — Create the required labels

Create these labels in **Issues → Labels → New label**:

| Label                | Suggested color    | Purpose                               |
|----------------------|--------------------|---------------------------------------|
| `analysis_todo`      | `#e4e669` (yellow) | Trigger: add this to request analysis |
| `analysis_processed` | `#0075ca` (blue)   | Set by pipeline on success            |
| `analysis_failed`    | `#d73a4a` (red)    | Set by pipeline on failure            |
| `analysis_done`      | `#0e8a16` (green)  | Optional: manual approval signal      |

Or via the GitHub CLI:

```bash
gh label create analysis_todo      --color e4e669 --description "Trigger issue analysis"
gh label create analysis_processed --color 0075ca --description "Analysis completed successfully"
gh label create analysis_failed    --color d73a4a --description "Analysis failed — re-add analysis_todo to retry"
gh label create analysis_done      --color 0e8a16 --description "Analysis approved"
```

## Step 2 — Configure repository secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**:

| Secret name               | Value                                                        |
|---------------------------|--------------------------------------------------------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code OAuth token. Generate with `claude setup-token`. |
| `CODEX_API_KEY`           | OpenAI API key for the Codex reviewer.                       |

The built-in `GITHUB_TOKEN` (auto-provided by Actions) handles all GitHub API calls — no extra token needed.

## Step 3 — Enable the workflows

The repository ships with two workflow files under `.github/workflows/`:

### `docker-publish.yml` — builds and publishes the Docker image

Triggers on every push to `main`. Builds the image from `Dockerfile` and pushes it to `ghcr.io/<owner>/<repo>:main`.

No configuration needed — uses the built-in `GITHUB_TOKEN` with `packages: write`.

**Verify:** Go to **Actions → Build and Push Docker Image** and confirm the run succeeded, then check **Packages** on
your profile or org page.

### `analyze-issues.yml` — runs the analysis pipeline

Triggers when an issue receives a label, filters to `analysis_todo`, and pulls the image built above.

No configuration needed beyond the secrets from Step 2.

## Step 4 — Grant Actions write permissions (organizations only)

For **personal accounts**, package permissions are automatic.

For **organizations**, go to **Settings → Actions → General → Workflow permissions** and select **Read and write
permissions**.

Or link the package to the repository directly:

1. Navigate to `https://github.com/orgs/<org>/packages/container/<repo>/settings`
2. Under "Manage Actions access", add your repository with **Write** role

## Step 5 — Trigger a test run

1. Open any issue in the repository
2. Add the `analysis_todo` label
3. Go to **Actions → Issue Analysis** and watch the run

A successful run:

- Posts a comment with links to `analysis.json` and `analysis.md`
- Updates the issue description with the Markdown analysis
- Replaces `analysis_todo` with `analysis_processed`
- Creates a `feature/<issue-number>` branch with the artifacts

## Environment variables reference

All variables are passed to the Docker container by `analyze-issues.yml`. Override any of them by editing the workflow's
`env:` block.

| Variable                  | Source                         | Description                                             |
|---------------------------|--------------------------------|---------------------------------------------------------|
| `PLATFORM`                | hardcoded `github`             | Selects the GitHub client                               |
| `GITHUB_TOKEN`            | `github.token`                 | Built-in token with `issues: write` + `contents: write` |
| `GITHUB_OWNER`            | `github.repository_owner`      | Repository owner (user or org)                          |
| `GITHUB_REPO`             | `github.event.repository.name` | Repository name                                         |
| `ISSUE_ID`                | `github.event.issue.number`    | Issue number being analyzed                             |
| `CLAUDE_CODE_OAUTH_TOKEN` | secret                         | Claude Code CLI authentication                          |
| `CODEX_API_KEY`           | secret                         | OpenAI API key for the reviewer                         |
| `ANALYST_MODEL`           | `claude-sonnet-4-6`            | Claude model for analysis                               |
| `REVIEWER_MODEL`          | `gpt-5.5`                      | OpenAI model for review                                 |

Optional tuning (add to the `env:` block):

| Variable                    | Default | Description                     |
|-----------------------------|---------|---------------------------------|
| `MAX_ITERATIONS`            | `3`     | Maximum analyst–reviewer cycles |
| `ITERATION_TIMEOUT_SECONDS` | `600`   | Per-iteration timeout (seconds) |
| `MIN_REVIEW_QUALITY_SCORE`  | `7`     | Minimum score (1–10) to approve |
| `LOG_LEVEL`                 | `INFO`  | Set to `DEBUG` for verbose logs |

## Retrying a failed analysis

1. Remove `analysis_failed` from the issue
2. Re-add `analysis_todo`

The pipeline is idempotent — it recreates the feature branch if it already exists and overwrites previous artifacts.

## Pinning to a specific image version

By default the workflow pulls `:main`. To pin to a specific commit:

```yaml
# in analyze-issues.yml, last line of the docker run command:
ghcr.io/${{ github.repository }}:sha-abc1234
```

Find the `sha-` tag in the `docker-publish.yml` run logs or on the **Packages** page.

## Troubleshooting

**"manifest unknown" / image not found**
`docker-publish.yml` has not run yet or failed. Check **Actions → Build and Push Docker Image**.

**Permission denied pulling image**
For org repositories, the package may not be linked. See Step 4.

**Analysis job times out**
The job has a 45-minute hard cap. Reduce `MAX_ITERATIONS` or increase `ITERATION_TIMEOUT_SECONDS`.

**Issue description not updated / comment not posted**
Verify **Settings → Actions → General → Workflow permissions** is set to "Read and write permissions".
