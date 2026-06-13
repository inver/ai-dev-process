# Plan: Необходимо мигрировать на последнюю версию python и langchain

**Issue:** #1 | **Iterations:** 2 | **Est:** 235 min

## Summary
Migrate the project to Python 3.14 and LangGraph >=0.4 by first discovering actual file locations and asyncio.run call sites, then updating version pins, replacing deprecated LangGraph set_entry_point across all confirmed graph files, refactoring asyncio.run wrappers to async def across all confirmed node modules, updating the existing Dockerfile with a correct lock-file install, generating a pinned requirements-lock.txt, and auditing CI workflows at their discovered paths for stale Python version strings.

## Tasks
### T1: Repository discovery: confirm file locations and call-site scope
Before editing any file, establish ground truth for every file the plan will touch. (a) Find the Dockerfile — confirm it exists at repo root or another location; record the path and current FROM line. (b) Find CI workflow files by searching for analyze-issues.yml and docker-publish.yml under all directories (root, .github/workflows/, .gitlab-ci.d/, etc.); record their actual paths. (c) Grep all three graph files for set_entry_point to confirm which ones need the START-edge fix and which entry-point node name each uses. (d) Grep all three node modules for 'asyncio.run' to record exact line numbers and the enclosing function name for each call site. (e) Grep all three node modules for all 'asyncio.' references to determine whether the asyncio import should be retained or removed after refactoring. Tasks T4-T6, T7-T9, T12, and T13 are conditional on the evidence gathered here.

**Files:** 

**Est:** 15 min

### T2: Verify target LangGraph version and Python 3.14 wheel availability
Run 'pip index versions langgraph' on a Python 3.14 interpreter to determine the current stable release; this value becomes the pinned floor in T3. Read the LangGraph changelog or GitHub releases for the migration guide from 0.2 to the target version — specifically confirm whether set_entry_point raises AttributeError (removed) or only emits a DeprecationWarning in the target, and note any ainvoke config-key changes. Verify that python:3.14-slim exists on Docker Hub. Verify that pydantic>=2.7, pydantic-settings>=2.3, python-gitlab>=4.6, and httpx>=0.27 each have Python 3.14 wheels by doing a dry-run install on a Python 3.14 interpreter. Record the resolved LangGraph version for the PR description.

**Files:** 

**Est:** 15 min

### T3: Update pyproject.toml: Python 3.14 and LangGraph version floor
Set requires-python = '>=3.14'. Change langgraph>=0.2 to langgraph>=0.4 (or ~=X.Y.0 if the stable from T2 has a minor version warranting a tighter pin). Add pip-tools to the [project.optional-dependencies] dev section so the lock workflow is self-contained. Do not change floors for pydantic, pydantic-settings, python-gitlab, or httpx unless T2 found a wheel gap.

**Files:** pyproject.toml

**Est:** 10 min

### T4: Fix graph.py: replace set_entry_point with START edge
Skip if T1 confirmed graph.py does not call set_entry_point. Otherwise add START to the 'from langgraph.graph import ...' line (adjust to langgraph.constants if T2 migration docs indicate START moved). Replace builder.set_entry_point('<node>') with builder.add_edge(START, '<node>') using the exact node name found in T1. Verify END is still exported from the same import path on the target version.

**Files:** src/pipeline/graph.py

**Est:** 10 min

### T5: Fix dev_graph.py: replace set_entry_point with START edge
Skip if T1 confirmed dev_graph.py does not call set_entry_point. Otherwise apply the same START-import and builder.add_edge fix. Use the entry-point node name found in T1 for this file, which may differ from graph.py.

**Files:** src/pipeline/dev_graph.py

**Est:** 10 min

### T6: Fix plan_graph.py: replace set_entry_point with START edge
Skip if T1 confirmed plan_graph.py does not call set_entry_point. Otherwise apply the same START-import and builder.add_edge fix using the entry-point node name from T1.

**Files:** src/pipeline/plan_graph.py

**Est:** 10 min

### T7: Refactor nodes.py: convert asyncio.run wrappers to async def
For each asyncio.run() call site found in T1, convert only the enclosing function to async def and replace asyncio.run(expr) with await expr. The inner _write() and _gather() closures become plain await expressions inside the now-async parent. After all call sites are converted, check whether any remaining 'asyncio.' reference (asyncio.gather, asyncio.to_thread, etc.) still requires the import; remove 'import asyncio' if and only if no such reference remains. Do NOT retain the import on the grounds that test files need it — test files have their own import namespace.

**Files:** src/pipeline/nodes.py

**Est:** 30 min

### T8: Refactor dev_nodes.py: convert asyncio.run wrappers to async def
Skip if T1 found no asyncio.run calls in dev_nodes.py. Otherwise, for each call site recorded in T1 (use the exact line numbers and enclosing function names — do not assume), convert the enclosing function to async def and replace asyncio.run(expr) with await expr. Remove the asyncio import if no other asyncio.X reference remains after refactoring.

**Files:** src/pipeline/dev_nodes.py

**Est:** 30 min

### T9: Refactor plan_nodes.py: convert asyncio.run wrappers to async def
Skip if T1 found no asyncio.run calls in plan_nodes.py. Otherwise apply the same refactoring using exact line numbers and enclosing function names from T1. Remove the asyncio import if no other asyncio.X reference remains.

**Files:** src/pipeline/plan_nodes.py

**Est:** 20 min

### T10: Update main.py: switch to asyncio.run(graph.ainvoke(...))
In src/pipeline/main.py replace graph.invoke(initial_state) with asyncio.run(graph.ainvoke(initial_state)). In the except block the bare asyncio.run() cleanup calls remain safe since the event loop exited when ainvoke raised; consolidate them into a single asyncio.run(async_cleanup(...)) call. Confirm 'import asyncio' is present at the top of main.py since asyncio.run is now the sole event-loop entry point.

**Files:** src/pipeline/main.py

**Est:** 15 min

### T11: Generate requirements-lock.txt on Python 3.14
On a Python 3.14 interpreter with the updated pyproject.toml from T3 in place, run: pip install pip-tools && pip-compile --extra pipeline --extra dev -o requirements-lock.txt pyproject.toml. Commit the resulting requirements-lock.txt. This file must include all transitive dependencies so that subsequent pip install --no-deps steps in Docker and CI never need to resolve anything themselves. If the team prefers uv, run uv lock instead and use uv sync --frozen in Docker/CI; choose one tool and apply it consistently through T12 and T13.

**Files:** requirements-lock.txt

**Est:** 15 min

### T12: Update Dockerfile: python:3.14-slim base and no-deps lock install
Edit the Dockerfile at the path confirmed by T1. Change the FROM line to python:3.14-slim. Add a lock-file install step before the editable install: COPY requirements-lock.txt . followed by RUN pip install --no-deps -r requirements-lock.txt. Then install the project with RUN pip install --no-deps -e '.[pipeline]'. The --no-deps flag is required on BOTH install commands: without it on the editable install, pip re-resolves transitive dependencies and can pull in versions not in requirements-lock.txt, defeating reproducibility. Do not omit --no-deps on the editable install step.

**Files:** Dockerfile

**Est:** 20 min

### T13: Update CI workflow files for Python 3.14 and add lock-drift check
Using the actual CI file paths found in T1 (do not assume .github/workflows/), search for and replace all occurrences of python3.12, python3.13, python:3.12, python:3.13 with python3.14 and python:3.14-slim respectively. Skip this task entirely if T1 found no CI files locally and note that the update must be applied when the files become accessible. In the CI pipeline add a lock-drift check step: pip-compile --check --extra pipeline --extra dev -o requirements-lock.txt pyproject.toml (or uv lock --check if uv was chosen in T11) — this step fails the pipeline if pyproject.toml and requirements-lock.txt diverge.

**Files:** 

**Est:** 15 min

### T14: Run full test suite on Python 3.14 with deprecation warnings as errors
Execute the complete test suite under Python 3.14 with -W error::DeprecationWarning. This flag catches stdlib removals (Python 3.14 removes modules deprecated since 3.11-3.13), LangGraph API warnings (which subclass DeprecationWarning), and pydantic v2 deprecations. Fix all failures before merging. Confirm that pytest-asyncio asyncio_mode='auto' (already in pyproject.toml) correctly discovers and runs async test functions in test_nodes.py, test_graph.py, and the dev/plan equivalents without additional markers.

**Files:** 

**Est:** 20 min

## Test Plan
- grep -n 'set_entry_point' src/pipeline/graph.py src/pipeline/dev_graph.py src/pipeline/plan_graph.py && exit 1 || echo OK
- python3 -W error::DeprecationWarning -c "from src.pipeline.graph import build_graph; build_graph()"
- python3 -W error::DeprecationWarning -c "from src.pipeline.dev_graph import build_dev_graph; build_dev_graph()"
- python3 -W error::DeprecationWarning -c "from src.pipeline.plan_graph import build_plan_graph; build_plan_graph()"
- grep -n 'asyncio\.run' src/pipeline/nodes.py src/pipeline/dev_nodes.py src/pipeline/plan_nodes.py && exit 1 || echo OK
- python3.14 -m pytest tests/ -W error::DeprecationWarning -v
- pip-compile --check --extra pipeline --extra dev -o requirements-lock.txt pyproject.toml
- docker build -t analyzer-test . --no-cache
- docker run --rm analyzer-test python3 -c "import sys; assert sys.version_info >= (3,14)"
- find . -name '*.yml' -not -path './.git/*' | xargs grep -ln 'python3\.12\|python3\.13\|python:3\.12\|python:3\.13' && exit 1 || echo OK

## Assumptions
- T1 discovery is mandatory before any edit task begins; T4-T6 are skipped if T1 finds no set_entry_point in the respective file; T8-T9 are skipped if T1 finds no asyncio.run in the respective file
- The Dockerfile exists at repo root (shown in file tree) and is updated in T12, not created — the acceptance criterion says 'update the Dockerfile base image'
- CI workflow file paths are determined by T1; T13 files_to_modify is left empty as a placeholder and filled from T1 discovery before executing
- LangGraph stable at time of work is >=0.4; exact version is determined in T2 before T3 is written
- python:3.14-slim exists on Docker Hub; verified in T2 before T12 is written
- requirements-lock.txt produced in T11 covers all transitive pipeline and dev dependencies so that pip install --no-deps -e '.[pipeline]' in Docker never needs to fetch additional packages
- pytest-asyncio asyncio_mode='auto' already in pyproject.toml handles all async test functions without additional per-test markers
- pydantic>=2.7, pydantic-settings>=2.3, python-gitlab>=4.6, httpx>=0.27 publish Python 3.14 wheels; if any require source builds, gcc and libffi-dev must be added to the Dockerfile build stage
- analyze_node, revise_node, review_node, and other nodes with no asyncio.run() call sites remain synchronous; LangGraph ainvoke supports mixed sync/async node graphs
- Developers on Python 3.12 or 3.13 must upgrade their local interpreter to 3.14 after this PR merges; the Docker image is the recommended fallback for running the pipeline in the interim

---
*Planned by `claude-sonnet-4-6` · Reviewed by `gpt-5.5`*
