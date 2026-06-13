# How It Works

AI Dev Process is a label-triggered CI pipeline that uses Claude Code (analyst/developer) and Codex (reviewer) to work
through GitHub or GitLab issues in three sequential stages: **Analyze → Plan → Develop**.

Each stage is triggered by adding a label to an issue and produces structured artifacts committed to a feature branch.

---

## Overview

```
Issue labeled "analysis_todo"
        │
        ▼
  ┌─────────────┐
  │   Analyze   │  Claude Code reads the issue + repo context and produces
  │   Pipeline  │  a structured analysis (problem statement, acceptance
  └─────────────┘  criteria, technical approach, risks, open questions).
        │
        │  artifacts committed to feature/<N> branch:
        │    analysis/<N>/analysis.json
        │    analysis/<N>/analysis.md
        │
        ▼
Issue labeled "plan_todo"
        │
        ▼
  ┌─────────────┐
  │    Plan     │  Claude Code reads the issue + prior analysis and writes
  │   Pipeline  │  a task-by-task implementation plan with file lists,
  └─────────────┘  test steps, and time estimates.
        │
        │  artifacts committed to feature/<N> branch:
        │    plans/<N>/plan.json
        │    plans/<N>/plan.md
        │
        ▼
Issue labeled "develop_todo"
        │
        ▼
  ┌─────────────┐
  │   Develop   │  Claude Code clones the repo, implements the plan on a
  │   Pipeline  │  develop/<N> branch, commits and pushes the code, and
  └─────────────┘  opens a pull/merge request.
        │
        │  a PR/MR is created: develop/<N> → main
```

Each pipeline loops internally: the AI produces output, an independent Codex reviewer scores it (1–10), and if the score
is below the threshold (default 7) the AI revises and the reviewer scores again. After `MAX_ITERATIONS` failed attempts
the job posts a failure comment and exits.

---

## Stage 1: Analysis

**Trigger:** add label `analysis_todo`

**What happens:**

1. The pipeline fetches the issue title, description, and comments.
2. It also reads the repository README and file tree for context.
3. Claude Code (headless `claude -p`) receives a system prompt describing the analyst role, then the issue content as a
   user prompt.
4. Claude Code returns a JSON `AnalysisOutput`:
    - `problem_statement`
    - `acceptance_criteria` (list)
    - `technical_approach` (ordered steps)
    - `dependencies`
    - `risks` (each with `severity` and `mitigation`)
    - `open_questions`
    - `estimated_complexity`
5. Codex reviews the analysis and returns a score and structured feedback.
6. If approved (score ≥ `MIN_REVIEW_QUALITY_SCORE`):
    - `analysis.json` and `analysis.md` are committed to `feature/<N>`
    - The issue description is updated with the Markdown report
    - A comment is posted with links to both artifacts
    - Label changes: `analysis_todo` → `analysis_processed`
7. If rejected, Claude Code revises and the review loop repeats.
8. After `MAX_ITERATIONS` rejections: label changes to `analysis_failed`; a failure comment is posted.

**Retry:** remove `analysis_failed`, re-add `analysis_todo`.

---

## Stage 2: Planning

**Trigger:** add label `plan_todo`

**Prerequisite:** run Analysis first. The plan pipeline loads `analysis/<N>/analysis.json` from the `feature/<N>` branch
as additional context (gracefully skipped if absent).

**What happens:**

1. Same context gathering as analysis (issue + README + file tree).
2. Prior analysis artifact is loaded from the feature branch.
3. Claude Code (read-only tools: `Read`, `Grep`, `Glob`) receives the issue and analysis, and produces a JSON
   `PlanOutput`:
    - `summary`
    - `tasks` — ordered list, each with:
        - `id`, `title`, `description`
        - `files_to_modify`, `files_to_create`
        - `test_steps`
        - `estimated_minutes`
    - `total_estimated_minutes`
    - `test_plan`
    - `assumptions`
4. Codex reviews the plan and scores it.
5. If approved:
    - `plan.json` and `plan.md` are committed to `feature/<N>` under `plans/<N>/`
    - Issue description is updated, comment posted with artifact links
    - Label: `plan_todo` → `plan_processed`
6. On failure: `plan_todo` → `plan_failed`; failure comment with retry instructions.

**Retry:** remove `plan_failed`, re-add `plan_todo`.

---

## Stage 3: Development

**Trigger:** add label `develop_todo`

**Prerequisites:** Analysis and Planning are strongly recommended. The develop pipeline loads both
`analysis/<N>/analysis.json` and `plans/<N>/plan.json` from the feature branch as context.

**What happens:**

1. Context gathering: issue + README + file tree + prior analysis + prior plan.
2. The pipeline **clones the target repository** into a temporary directory and checks out a new branch `develop/<N>`.
3. Claude Code (write tools: `Edit`, `Write`, `Bash`, `Read`, `Grep`, `Glob`) runs inside the cloned repo and implements
   the plan:
    - Reads existing code
    - Writes/edits files
    - Runs tests via `Bash`
    - Returns a JSON `DeveloperOutput` summarising what was built and test results
4. The pipeline commits all changes and pushes `develop/<N>` to the remote.
5. A pull request (GitHub) or merge request (GitLab) is opened: `develop/<N>` → `main`.
6. Codex fetches the diff and reviews it as an MR reviewer, scoring for correctness, test coverage, security, and plan
   adherence.
7. If approved:
    - Label: `develop_todo` → `develop_processed`
    - A comment is posted with the MR/PR link and quality score
8. If rejected, Claude Code re-runs on the same branch (fixing the blocking issues), pushes again, and the review loop
   repeats.
9. On failure: `develop_todo` → `develop_failed`; failure comment posted.

**Retry:** remove `develop_failed`, re-add `develop_todo`.

---

## Labels Reference

| Label                | Trigger / Meaning                                       |
|----------------------|---------------------------------------------------------|
| `analysis_todo`      | Start analysis pipeline                                 |
| `analysis_processed` | Analysis completed and approved                         |
| `analysis_failed`    | Analysis failed — re-add `analysis_todo` to retry       |
| `analysis_done`      | Optional: manual signal that analysis has been reviewed |
| `plan_todo`          | Start planning pipeline                                 |
| `plan_processed`     | Plan completed and approved                             |
| `plan_failed`        | Planning failed — re-add `plan_todo` to retry           |
| `develop_todo`       | Start development pipeline                              |
| `develop_processed`  | Development completed and MR/PR approved                |
| `develop_failed`     | Development failed — re-add `develop_todo` to retry     |

---

## Artifacts

All artifacts are committed to the `feature/<issue-number>` branch of the repository.

```
feature/<N>/
  analysis/<N>/
    analysis_iter1.json   ← analyst output per iteration
    analysis_iter1.md
    review_iter1.json     ← reviewer score per iteration
    analysis.json         ← final approved analysis
    analysis.md

  plans/<N>/
    plan.json             ← final approved implementation plan
    plan.md

develop/<N>/              ← separate branch with the actual code changes
  (normal code files)
```

Links to all artifacts are posted as a comment on the issue when each pipeline stage completes.

---

## Internal Loop Logic

Each pipeline stage runs the same `gather_context → agent → review ⟷ revise → finalize` state machine built with
LangGraph.

```
gather_context
      │
      ▼
   agent (analyze / plan / develop)
      │
      ▼
   review
      │
      ├─ score ≥ threshold → finalize → END
      │
      ├─ iteration < max AND time < timeout → revise → (back to review)
      │
      └─ iteration == max OR timeout → handle_failure → END
```

**Configurable thresholds** (set as environment variables or CI variables):

| Variable                    | Default             | Description                                      |
|-----------------------------|---------------------|--------------------------------------------------|
| `MAX_ITERATIONS`            | `3`                 | Maximum analyst–reviewer cycles per stage        |
| `ITERATION_TIMEOUT_SECONDS` | `600`               | Per-iteration wall-clock timeout                 |
| `MIN_REVIEW_QUALITY_SCORE`  | `7`                 | Minimum score (1–10) to approve and move forward |
| `ANALYST_MODEL`             | `claude-sonnet-4-6` | Claude model for analysis/planning/development   |
| `REVIEWER_MODEL`            | `gpt-5.5`           | OpenAI model for reviewing                       |
| `LOG_LEVEL`                 | `INFO`              | Set to `DEBUG` for verbose pipeline logs         |

---

## Technology Stack

- **Python 3.12+** with Pydantic for structured outputs and settings
- **LangGraph** for the state-machine pipeline
- **Claude Code CLI** (`claude -p --output-format json`) for analysis, planning, and development
- **Codex CLI** (`codex exec`) for independent review
- **Docker** — the entire pipeline runs in a container pulled from GHCR (GitHub) or the GitLab Container Registry
- **GitHub Actions** or **GitLab CI** as the job runner; triggered by issue label events

---

## Platform Differences

| Aspect             | GitHub                                 | GitLab                                                           |
|--------------------|----------------------------------------|------------------------------------------------------------------|
| Trigger mechanism  | Native Actions `issues: labeled` event | Requires a webhook receiver service (see integration guide)      |
| Image registry     | GHCR (`ghcr.io/<owner>/<repo>:main`)   | GitLab Container Registry (`$CI_REGISTRY_IMAGE/analyzer:latest`) |
| Auth token env var | `GITHUB_TOKEN` (auto-provided)         | `GITLAB_TOKEN` (configured manually)                             |
| MR/PR creation     | GitHub Pull Request                    | GitLab Merge Request                                             |
| Integration guide  | `docs/how-to-integrate-with-github.md` | `docs/how-to-integrate-with-gitlab.md`                           |

---

## Running Locally

You can invoke the pipeline directly without CI for testing or debugging:

```bash
# 1. Set required environment variables
export PLATFORM=github
export GITHUB_TOKEN=<your-token>
export GITHUB_OWNER=<owner>
export GITHUB_REPO=<repo>
export ISSUE_ID=42
export TRIGGER_TYPE=analysis        # or: plan, develop
export CLAUDE_CODE_OAUTH_TOKEN=<token>   # from: claude setup-token
export CODEX_AUTH_JSON_B64=$(base64 -w0 ~/.codex/auth.json)

# 2. Install Python dependencies
pip install -e ".[pipeline]"

# 3. Run
python -m src.pipeline.main
```

Or via Docker (same as CI):

```bash
docker run --rm \
  -e PLATFORM=github \
  -e GITHUB_TOKEN=<token> \
  -e GITHUB_OWNER=<owner> \
  -e GITHUB_REPO=<repo> \
  -e ISSUE_ID=42 \
  -e TRIGGER_TYPE=analysis \
  -e CLAUDE_CODE_OAUTH_TOKEN=<token> \
  -e CODEX_AUTH_JSON_B64=$(base64 -w0 ~/.codex/auth.json) \
  ghcr.io/<owner>/<repo>:main
```

Set `LOG_LEVEL=DEBUG` to see the full prompt and response traffic.

---

## Error Handling

- **Secret missing:** the pre-flight validation step in the workflow fails immediately with a clear error message
  pointing to the exact setting to fix.
- **Claude Code exits non-zero:** the pipeline raises `ClaudeCodeError` and falls through to `handle_failure`, which
  posts a comment and applies the `*_failed` label.
- **Codex exits non-zero or returns malformed JSON:** same `handle_failure` path.
- **Unhandled exception:** `main.py` catches it, posts a failure comment with the exception text, and exits with code 1.
- **Development: no files changed:** the `develop` node detects an empty git diff and skips the commit/push step (no
  empty commits).
- **Idempotency:** all pipelines are idempotent — re-running on the same issue recreates/overwrites the feature branch
  and artifacts safely.
