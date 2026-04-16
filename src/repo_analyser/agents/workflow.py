from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from repo_analyser.analysis.issues import analyze_issue
from repo_analyser.analysis.linking import analyze_pull_request, correlate_issues_and_prs
from repo_analyser.analysis.prioritization import score_issue
from repo_analyser.analysis.solution import build_issue_suggestion, clear_generated_issue_artifacts
from repo_analyser.config import Settings
from repo_analyser.github_api import GitHubClient
from repo_analyser.logging_utils import get_logger
from repo_analyser.models import AgentLogEvent, AnalysisResult, DashboardSummary
from repo_analyser.providers.factory import AutoFallbackProvider

LogHandler = Callable[[AgentLogEvent], Awaitable[None]]

try:
    from google.adk.agents import LlmAgent, SequentialAgent
    from google.adk.tools import FunctionTool

    ADK_AVAILABLE = True
except ImportError:  # pragma: no cover
    LlmAgent = SequentialAgent = FunctionTool = object
    ADK_AVAILABLE = False


def build_adk_agent_graph(settings: Settings, github: GitHubClient) -> Any:
    if not ADK_AVAILABLE:
        return None

    async def get_repo_data(repo_url: str) -> dict[str, Any]:
        return (await github.get_repo_data(repo_url)).model_dump(mode="json")

    async def get_pr_diff(repo_full_name: str, pr_id: int) -> str:
        return await github.get_pr_diff(repo_full_name, pr_id)

    async def get_issue_details(repo_full_name: str, issue_id: int) -> dict[str, Any]:
        return (await github.get_issue_details(repo_full_name, issue_id)).model_dump(mode="json")

    repo_agent = LlmAgent(
        name="repo_ingestion_agent",
        model="gemini-2.5-flash",
        instruction="Use the tools to fetch open repository issues, pull requests, comments, labels, and references.",
        tools=[FunctionTool(get_repo_data), FunctionTool(get_issue_details)],
    )
    pr_agent = LlmAgent(
        name="pr_analysis_agent",
        model="gemini-2.5-flash",
        instruction="Analyze PRs, changed files, diffs, and explicit issue references.",
        tools=[FunctionTool(get_pr_diff)],
    )
    issue_agent = LlmAgent(
        name="issue_analysis_agent",
        model="gemini-2.5-flash",
        instruction="Summarize issue problem statements, affected modules, and complexity signals.",
    )
    correlation_agent = LlmAgent(
        name="correlation_agent",
        model="gemini-2.5-flash",
        instruction="Map issues to PRs, identify resolved and unresolved issues, and explain edge cases.",
    )
    prioritization_agent = LlmAgent(
        name="prioritization_agent",
        model="gemini-2.5-flash",
        instruction="Prioritize unresolved issues using labels, comments, reactions, recency, and ease-of-fix heuristics.",
    )
    solution_agent = LlmAgent(
        name="solution_generator_agent",
        model="gemini-2.5-pro",
        instruction="Generate markdown fix briefs with cautious root-cause hypotheses and code guidance.",
    )
    return SequentialAgent(
        name="coordinator_agent",
        sub_agents=[repo_agent, pr_agent, issue_agent, correlation_agent, prioritization_agent, solution_agent],
    )


class CoordinatorService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = AutoFallbackProvider(settings)
        self.logger = get_logger(__name__, "coordinator")

    async def analyze(self, repo_url: str, emit_log: LogHandler) -> AnalysisResult:
        github = GitHubClient(self.settings)
        try:
            self.logger.info("Starting analysis for %s.", repo_url)
            await self._emit(emit_log, "coordinator", "running", "Starting open-issue repository analysis.")
            cleared_artifacts = clear_generated_issue_artifacts(self.settings.output_dir)
            await self._emit(
                emit_log,
                "coordinator",
                "running",
                "Cleared generated issue briefs from the previous repository run.",
                {"cleared_artifacts": cleared_artifacts},
            )
            await self._emit(emit_log, "repo_ingestion_agent", "running", "Fetching open issues and pull requests from GitHub.")
            repo_data = await github.get_repo_data(repo_url)
            await self._emit(
                emit_log,
                "repo_ingestion_agent",
                "completed",
                "Open-issue repository ingestion complete.",
                {"open_issues": len(repo_data.issues), "prs": len(repo_data.pull_requests)},
            )

            await self._emit(emit_log, "pr_analysis_agent", "running", "Analyzing pull requests, diffs, and issue references.")
            pr_analyses = [analyze_pull_request(pr) for pr in repo_data.pull_requests]
            await self._emit(emit_log, "pr_analysis_agent", "completed", "Pull request analysis complete.", {"analyzed_prs": len(pr_analyses)})

            await self._emit(emit_log, "issue_analysis_agent", "running", "Extracting issue summaries and complexity signals.")
            issue_analyses = [analyze_issue(issue) for issue in repo_data.issues]
            await self._emit(emit_log, "issue_analysis_agent", "completed", "Issue analysis complete.", {"analyzed_issues": len(issue_analyses)})

            await self._emit(emit_log, "correlation_agent", "running", "Linking issues and PRs across descriptions, comments, and commit messages.")
            links = correlate_issues_and_prs(repo_data.issues, pr_analyses)
            unresolved_numbers = {link.issue_number for link in links if not link.resolved}
            await self._emit(
                emit_log,
                "correlation_agent",
                "completed",
                "Issue/PR correlation complete.",
                {"linked_issues": len(links), "unresolved": len(unresolved_numbers)},
            )

            await self._emit(emit_log, "prioritization_agent", "running", "Scoring unresolved issues with heuristic prioritization.")
            issue_by_number = {issue.number: issue for issue in repo_data.issues}
            analysis_by_number = {analysis.issue_number: analysis for analysis in issue_analyses}
            prioritization = [score_issue(issue_by_number[number]) for number in unresolved_numbers]
            prioritization.sort(key=lambda item: item.score, reverse=True)
            await self._emit(
                emit_log,
                "prioritization_agent",
                "completed",
                "Prioritization complete.",
                {"prioritized_issues": len(prioritization)},
            )

            await self._emit(emit_log, "solution_generator_agent", "running", "Generating markdown fix briefs for unresolved open issues.")
            repo_tree = await github.fetch_repo_tree(repo_data.repository.full_name)
            suggestions = []
            for score in prioritization[: self.settings.max_markdown_issues]:
                self.logger.info("Generating suggestion for issue #%s.", score.issue_number)
                suggestion = await build_issue_suggestion(
                    repository=repo_data.repository,
                    issue=issue_by_number[score.issue_number],
                    analysis=analysis_by_number[score.issue_number],
                    score=score,
                    provider=self.provider,
                    repo_tree=repo_tree,
                    output_dir=self.settings.output_dir,
                )
                suggestions.append(suggestion)
            await self._emit(
                emit_log,
                "solution_generator_agent",
                "completed",
                "Markdown brief generation complete.",
                {"files": len(suggestions)},
            )

            summary = DashboardSummary(
                total_issues=len(repo_data.issues),
                resolved_issues=sum(1 for link in links if link.resolved),
                unresolved_issues=sum(1 for link in links if not link.resolved),
                easy_fix_issues=sum(1 for item in prioritization if item.complexity.value == "easy"),
            )
            self.logger.info("Analysis complete for %s. Summary=%s", repo_url, summary.model_dump(mode="json"))
            await self._emit(emit_log, "coordinator", "completed", "Open-issue analysis pipeline completed successfully.", summary.model_dump(mode="json"))
            return AnalysisResult(
                repository=repo_data.repository,
                summary=summary,
                links=links,
                issue_analyses=issue_analyses,
                pr_analyses=pr_analyses,
                prioritization=prioritization,
                suggestions=suggestions,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.exception("Analysis failed for %s: %s", repo_url, exc)
            await self._emit(emit_log, "coordinator", "failed", f"Analysis failed: {exc}")
            raise
        finally:
            await github.close()

    async def _emit(
        self,
        emit_log: LogHandler,
        agent: str,
        status: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        self.logger.info("%s | %s | %s | %s", agent, status, message, data or {}, extra={"agent": agent})
        await emit_log(AgentLogEvent(agent=agent, status=status, message=message, data=data or {}))
