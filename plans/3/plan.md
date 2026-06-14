# Plan: Добавить ожидание, когда восстановится лимит токенов в claude и codex + процессы plan и develop должны идти также в ветке feature/<issue_id>

**Issue:** #3 | **Iterations:** 1 | **Est:** 350 min

## Summary
Add sleep-and-retry on token/rate-limit errors to all six Claude/Codex CLI wrappers via a new retry.py module, and fix the develop pipeline to target feature/<issue_id> instead of develop/<issue_id>.

## Tasks
### T1: Create src/pipeline/retry.py
New module with four exports: (1) RATE_LIMIT_PATTERNS list = ['rate limit', 'rate_limit', 'ratelimit', 'too many requests', 'token limit', 'quota exceeded', 'overloaded', 'capacity', 'insufficient_quota', '429']. (2) is_rate_limit_error(msg: str) -> bool using any(p in msg.lower() for p in RATE_LIMIT_PATTERNS). (3) run_with_rate_limit_retry(fn, cfg, logger, exc_types, sleep_fn=time.sleep): while-loop calling fn(); on exc_types exception, if is_rate_limit_error(str(exc)) and attempt < cfg.max_rate_limit_retries: log warning with fn.__name__, attempt (1-based), cfg.max_rate_limit_retries, cfg.rate_limit_retry_wait_seconds, and str(exc)[:200]; call sleep_fn(cfg.rate_limit_retry_wait_seconds); increment attempt; continue; else raise immediately; after exhaustion log error and re-raise original exception; return fn() result on success. (4) check_retry_timeout_config(cfg, logger): emit log.warning when cfg.max_rate_limit_retries * cfg.rate_limit_retry_wait_seconds > 0.4 * cfg.iteration_timeout_seconds.

**Files:** src/pipeline/retry.py

**Est:** 30 min

### T2: Add rate-limit config fields to src/config.py
In the Settings class in src/config.py, insert two new plain int fields after developer_timeout_seconds: rate_limit_retry_wait_seconds: int = 60 and max_rate_limit_retries: int = 10. No Field() alias needed — pydantic-settings maps field names to env vars RATE_LIMIT_RETRY_WAIT_SECONDS and MAX_RATE_LIMIT_RETRIES automatically.

**Files:** src/config.py

**Est:** 10 min

### T3: Write tests/unit/test_retry.py
Create tests/unit/test_retry.py. Test is_rate_limit_error truth table: assert True for 'rate limit exceeded', '429 Too Many Requests', 'quota exceeded', 'overloaded', 'token limit reached', 'ratelimit hit', 'capacity error', 'insufficient_quota'; assert False for 'syntax error', 'file not found', 'permission denied'. Test run_with_rate_limit_retry with injectable sleep_fn=MagicMock(): (a) success on first call — fn called once, sleep not called, result returned; (b) one rate-limit failure then success — sleep called once with cfg.rate_limit_retry_wait_seconds; (c) exhaustion — fn always raises matching exc, sleep called exactly max_rate_limit_retries times, original exc is re-raised; (d) non-rate-limit error — exc propagated immediately without sleeping. Use a simple namespace object for cfg with rate_limit_retry_wait_seconds=1 and max_rate_limit_retries=3 to keep tests fast.

**Files:** tests/unit/test_retry.py

**Est:** 30 min

### T4: Add retry to run_claude_analysis (claude_code.py)
In src/pipeline/claude_code.py, refactor run_claude_analysis: extract the full function body (from cli/env setup through 'return output') into a nested function _attempt(). Add 'from src.pipeline.retry import run_with_rate_limit_retry' at the top of the file and replace the body with 'return run_with_rate_limit_retry(_attempt, s, logger, (ClaudeCodeError,))'. Both ClaudeCodeError raise sites are automatically covered: the non-zero exit path (raise ClaudeCodeError(f'Claude Code exited {proc.returncode}: {detail}')) and the is_error=True path (raise ClaudeCodeError(f'Claude Code reported an error: ...')). External signature of run_claude_analysis is unchanged.

**Files:** src/pipeline/claude_code.py

**Est:** 20 min

### T5: Add retry to run_claude_plan (claude_plan.py)
In src/pipeline/claude_plan.py, apply the same _attempt() extraction pattern as T4 to run_claude_plan. Both ClaudeCodeError raise sites are covered: non-zero exit path and is_error=True path. Add 'from src.pipeline.retry import run_with_rate_limit_retry' and wrap with run_with_rate_limit_retry(_attempt, s, logger, (ClaudeCodeError,)). Signature unchanged.

**Files:** src/pipeline/claude_plan.py

**Est:** 20 min

### T6: Add retry to run_claude_dev (claude_dev.py)
In src/pipeline/claude_dev.py, apply the same _attempt() extraction pattern as T4 to run_claude_dev. repo_dir is passed as a parameter so _attempt's closure captures it correctly. Both ClaudeCodeError raise sites are covered. Wrap with run_with_rate_limit_retry(_attempt, s, logger, (ClaudeCodeError,)). Signature unchanged.

**Files:** src/pipeline/claude_dev.py

**Est:** 20 min

### T7: Add retry to run_codex_review (codex.py)
In src/pipeline/codex.py, refactor run_codex_review with a Codex-specific pattern: move temp-file creation (mkstemp for tmp_path; optional mkdtemp for tmp_codex_home) AND the finally cleanup block (os.unlink + shutil.rmtree) INSIDE a nested _attempt() function so each retry creates and cleans up its own isolated temp files. Keep env setup and auth detection outside _attempt (idempotent). Add 'from src.pipeline.retry import run_with_rate_limit_retry' and wrap with run_with_rate_limit_retry(_attempt, s, logger, (CodexError,)). Only the non-zero exit path raises CodexError; is_error does not apply to Codex. Signature unchanged.

**Files:** src/pipeline/codex.py

**Est:** 25 min

### T8: Add retry to run_codex_plan_review (codex_plan.py)
In src/pipeline/codex_plan.py, apply the same Codex _attempt() pattern as T7: move temp-file creation (mkstemp; optional mkdtemp) and finally cleanup inside _attempt(); keep env/auth setup outside. Add 'from src.pipeline.retry import run_with_rate_limit_retry' and wrap with run_with_rate_limit_retry(_attempt, s, logger, (CodexError,)). Signature unchanged.

**Files:** src/pipeline/codex_plan.py

**Est:** 25 min

### T9: Add retry to run_codex_mr_review (codex_mr.py)
In src/pipeline/codex_mr.py, apply the same Codex _attempt() pattern as T7: move temp-file creation and finally cleanup inside _attempt(); keep env/auth setup outside. Add 'from src.pipeline.retry import run_with_rate_limit_retry' and wrap with run_with_rate_limit_retry(_attempt, s, logger, (CodexError,)). Signature unchanged.

**Files:** src/pipeline/codex_mr.py

**Est:** 25 min

### T10: Fix develop pipeline branch name to feature/<issue_id>
Two changes in src/pipeline/dev_nodes.py: (1) In gather_context_node, change the returned dict key 'dev_branch_name' from f'develop/{state["issue_iid"]}' to f'feature/{state["issue_iid"]}'. (2) In develop_node, change _clone_repo(settings, dev_branch) to _clone_repo(settings, dev_branch, existing_branch=True) because feature/<issue_id> is guaranteed to exist (ensure_feature_branch called at line 120 of gather_context_node). revise_node already passes existing_branch=True and needs no change. Also fix src/pipeline/main.py initial develop state: change 'dev_branch_name': f'develop/{issue_iid}' to 'dev_branch_name': f'feature/{issue_iid}' for consistency (gather_context_node overwrites this, but it must not be wrong in the initial state).

**Files:** src/pipeline/dev_nodes.py, src/pipeline/main.py

**Est:** 15 min

### T11: Update CI timeout and add startup misconfiguration warning
Two changes: (1) In .github/workflows/analyze-issues.yml, raise 'timeout: 40 minutes' to 'timeout: 120 minutes'. Worst-case wall-clock with default settings: 3 iterations * 600s + 10 retries * 60s = 2400s (~40 min) just for the pipeline, leaving no headroom for rate-limit sleeps. (2) In src/pipeline/main.py, add 'from src.pipeline.retry import check_retry_timeout_config' and call check_retry_timeout_config(settings, logger) immediately after setup_logging(settings.log_level). This emits a WARNING when max_rate_limit_retries * rate_limit_retry_wait_seconds > 0.4 * iteration_timeout_seconds.

**Files:** .github/workflows/analyze-issues.yml, src/pipeline/main.py

**Est:** 15 min

### T12: Add rate-limit retry tests to Claude wrapper test files
Add one integration-style unit test per Claude wrapper. In tests/unit/test_claude_code.py add test_run_claude_analysis_retries_on_rate_limit: use unittest.mock.patch('subprocess.run', side_effect=[...]) to return returncode=1 with stdout='rate limit exceeded' twice, then returncode=0 with valid AnalysisOutput JSON; patch 'src.pipeline.retry.time.sleep' with MagicMock(); create a mock settings with rate_limit_retry_wait_seconds=1 and max_rate_limit_retries=3; assert result is AnalysisOutput and sleep mock was called exactly twice with 1. Mirror the same pattern in tests/unit/test_claude_plan.py for run_claude_plan returning PlanOutput JSON, and in tests/unit/test_claude_dev.py for run_claude_dev returning DeveloperOutput JSON (also pass a tmp repo_dir via tmp_path fixture).

**Files:** tests/unit/test_claude_code.py, tests/unit/test_claude_plan.py, tests/unit/test_claude_dev.py

**Est:** 40 min

### T13: Add rate-limit retry tests to Codex wrapper test files
Create tests/unit/test_codex.py with test_run_codex_review_retries_on_rate_limit: patch subprocess.run to return returncode=1 with stderr='429 Too Many Requests' twice then returncode=0; patch tempfile.mkstemp to return a real temp file pre-populated with valid ReviewResult JSON; patch 'src.pipeline.retry.time.sleep' with MagicMock(); assert sleep called twice and result is ReviewResult; assert mkstemp called 3 times (once per attempt) confirming fresh temp files per retry. Add mirror tests in tests/unit/test_codex_plan.py for run_codex_plan_review/PlanReviewResult and in tests/unit/test_codex_mr.py for run_codex_mr_review/MRReviewResult.

**Files:** tests/unit/test_codex_plan.py, tests/unit/test_codex_mr.py, tests/unit/test_codex.py

**Est:** 40 min

### T14: Add feature-branch assertion to tests/unit/test_dev_nodes.py
In tests/unit/test_dev_nodes.py add test_gather_context_sets_feature_branch: mock ContextGatherer.gather to return a minimal context dict; mock BranchManager.ensure_feature_branch as an async no-op; mock build_forge_client to return a mock client with async get_file_content returning ''; mock get_settings returning a Settings with required fields. Call asyncio.run(gather_context_node({'issue_iid': 99, 'branch_name': '', ...})) supplying all required DevelopmentState keys as empty defaults. Assert result['dev_branch_name'] == 'feature/99' and result['branch_name'] == 'feature/99'. Also assert result['dev_branch_name'] != 'develop/99' as a regression guard.

**Files:** tests/unit/test_dev_nodes.py

**Est:** 20 min

### T15: Run full test suite and verify no regressions
Run the complete tests/unit/ test suite to confirm all existing tests still pass alongside the new tests. Fix any import or signature breakage introduced by the _attempt() refactors. Ensure no test calls time.sleep for real (all retry tests must use sleep_fn injection or patch 'src.pipeline.retry.time.sleep').

**Files:** 

**Est:** 15 min

## Test Plan
- python -m py_compile src/pipeline/retry.py src/config.py src/pipeline/claude_code.py src/pipeline/claude_plan.py src/pipeline/claude_dev.py src/pipeline/codex.py src/pipeline/codex_plan.py src/pipeline/codex_mr.py src/pipeline/dev_nodes.py src/pipeline/main.py
- python -c "from src.config import Settings; s = Settings(); assert s.rate_limit_retry_wait_seconds == 60; assert s.max_rate_limit_retries == 10"
- pytest tests/unit/test_retry.py -v
- pytest tests/unit/test_claude_code.py tests/unit/test_claude_plan.py tests/unit/test_claude_dev.py -v
- pytest tests/unit/test_codex.py tests/unit/test_codex_plan.py tests/unit/test_codex_mr.py -v
- pytest tests/unit/test_dev_nodes.py -v -k feature_branch
- pytest tests/unit/ -v

## Assumptions
- Python 3.12+; pydantic-settings BaseSettings already in use — no new packages required
- CI workflow file is .github/workflows/analyze-issues.yml (GitHub Actions); adjust path if a separate GitLab CI YAML is the active one
- tests/unit/__init__.py and tests/__init__.py already exist per the repository file tree; create only if absent
- tests/unit/test_codex.py does not exist and must be created; tests/unit/test_codex_plan.py and test_codex_mr.py already exist and are extended
- sleep_fn injection for test isolation is achieved by patching 'src.pipeline.retry.time.sleep' in tests (run_with_rate_limit_retry defaults to the module-level time.sleep reference)
- src/pipeline/main.py initial develop state contains 'dev_branch_name': f'develop/{issue_iid}' that must be fixed alongside dev_nodes.py:136
- _clone_repo accepts an existing_branch keyword argument as implied by its use in revise_node at line 215; no changes to _clone_repo's signature are needed
- The 'capacity' substring in RATE_LIMIT_PATTERNS is accepted with known false-positive risk; no runtime env-var extension mechanism is added in this iteration
- DevelopmentState.dev_branch_name is a plain str field — changing its value from 'develop/<id>' to 'feature/<id>' requires no model schema change
- plan_nodes.py already targets feature/<issue_id> correctly and requires no changes

---
*Planned by `claude-sonnet-4-6` · Reviewed by `gpt-5.5`*
