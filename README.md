# Open Source Repo Analyser

Production-style multi-agent GitHub repository analysis system built with Google ADK concepts, async Python services, MCP-style tools, and a streaming chat UI.

## System Architecture

The system is split into seven agents coordinated by a central workflow:

1. `Repo Ingestion Agent`
   Fetches issues, pull requests, comments, labels, commit metadata, and repository tree data from the GitHub API.
2. `PR Analysis Agent`
   Inspects PR bodies, comments, commit messages, changed files, and diffs to infer issue relationships.
3. `Issue Analysis Agent`
   Extracts the problem statement, affected modules, easy-fix clues, and complexity signals from each issue.
4. `Correlation Agent`
   Maps issues to one or more PRs and decides whether an issue is resolved or still open.
5. `Prioritization Agent`
   Scores unresolved issues with heuristics for labels, discussion volume, recency, and reactions.
6. `Solution Generator Agent`
   Produces markdown issue briefs with root-cause hypotheses, suggested fixes, likely files, and code guidance.
7. `Coordinator Agent`
   Orchestrates the end-to-end flow, emits streaming logs, and assembles the final dashboard payload.

### Data Flow

`Chat UI -> FastAPI stream endpoint -> Coordinator -> GitHub tools -> analysis agents -> markdown generation -> streamed dashboard`

### Why heuristics + LLM

Easy issues are not derived from LLM output alone. The system combines:

- `good first issue` and similar labels
- low discussion volume
- contained label footprint
- likely file scope from repository tree matching
- optional LLM augmentation for explanation quality, not for sole classification

PR to issue linking scans:

- PR descriptions
- PR comments
- commit messages
- plain `#123` references
- close/fix/resolve keywords such as `Fixes #123`

## Codebase Structure

```text
src/repo_analyser/
  agents/workflow.py          ADK graph definition + coordinator orchestration
  analysis/issues.py          issue parsing heuristics
  analysis/linking.py         issue/PR linking logic
  analysis/prioritization.py  scoring and easy-fix classification
  analysis/solution.py        markdown generation + likely file inference
  providers/                  OpenRouter, HuggingFace, auto-fallback abstraction
  tools/mcp.py                MCP-style tool surface
  cache.py                    file-backed TTL cache
  config.py                   environment-driven settings
  github_api.py               async GitHub client with rate-limit handling
  models.py                   shared pydantic models
  web/app.py                  FastAPI app and streaming endpoint
  web/templates/index.html    chat interface
  web/static/                 UI styling and browser logic
main.py                       app entrypoint
tests/                        unit tests for linking and prioritization
```

## Key Implementation Notes

### Google ADK integration

The project includes an ADK workflow definition in [src/repo_analyser/agents/workflow.py](/Users/tamojit/Developer/opensource-repo-analyser/src/repo_analyser/agents/workflow.py:1). When `google-adk` is installed, `build_adk_agent_graph()` constructs a `SequentialAgent` composed of the required specialized agents. The coordinator service provides the production execution path for the web app and keeps the orchestration deterministic.

### MCP tools

The MCP-style tool layer lives in [src/repo_analyser/tools/mcp.py](/Users/tamojit/Developer/opensource-repo-analyser/src/repo_analyser/tools/mcp.py:1) and exposes:

- `get_repo_data`
- `get_pr_diff`
- `get_issue_details`
- `link_issue_pr`

### Provider strategy

[src/repo_analyser/providers/factory.py](/Users/tamojit/Developer/opensource-repo-analyser/src/repo_analyser/providers/factory.py:1) implements the abstraction:

- OpenRouter as primary
- HuggingFace as fallback
- automatic failover when a provider call fails

### Streaming UI

The web app exposes `/api/analyze/stream` and pushes:

- agent lifecycle logs
- final analysis result

The interface shows:

- repository summary dashboard
- issue to PR mappings
- expandable issue recommendations
- links to generated markdown briefs in `generated_issues/`

## Setup

1. Create and activate a Python 3.12 or 3.13 environment. Python 3.14 is available locally here, but a 3.12/3.13 environment is the safer target for current AI ecosystem packages like `google-adk`.
2. Install dependencies:

```bash
uv sync
```

3. Configure environment variables:

```bash
cp .env.example .env
```

Add values for:

- `GITHUB_TOKEN`
- `OPENROUTER_API_KEY`
- `HUGGINGFACE_API_KEY`

4. Run the app:

```bash
uv run python main.py
```

5. Open `http://127.0.0.1:8000`

## Example Run

Example repository input:

```text
https://github.com/pallets/flask
```

Expected output:

- total issue count
- resolved vs unresolved issue split
- issue to PR mappings
- prioritized unresolved issues
- generated markdown files such as `generated_issues/issue-123.md`

## Environment Variables

```text
GITHUB_TOKEN=
OPENROUTER_API_KEY=
HUGGINGFACE_API_KEY=
OPENROUTER_MODEL=deepseek/deepseek-r1-distill-llama-70b
HUGGINGFACE_MODEL=mistralai/Mistral-7B-Instruct-v0.3
GITHUB_CACHE_TTL_SECONDS=600
MAX_MARKDOWN_ISSUES=25
```

## Validation

Current lightweight validation covers:

- PR to issue reference parsing
- resolved issue correlation
- easy-fix classification heuristics

Recommended next step for production hardening:

- add integration tests with recorded GitHub API fixtures
- persist analysis history in a database
- mount generated markdown as an explicit static directory
- add background jobs for large repositories
