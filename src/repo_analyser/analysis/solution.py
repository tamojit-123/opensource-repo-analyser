from __future__ import annotations

import shutil
from pathlib import Path

from repo_analyser.logging_utils import get_logger
from repo_analyser.models import GitHubIssue, IssueAnalysis, IssueScore, IssueSuggestion, RepositoryRef
from repo_analyser.providers.base import LlmRequest, ModelProvider

logger = get_logger(__name__, "solution-generator")


def clear_generated_issue_artifacts(output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    removed_count = 0
    for path in output_dir.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
            removed_count += 1
        else:
            path.unlink(missing_ok=True)
            removed_count += 1
    logger.info("Cleared %s generated issue artifact(s) from %s.", removed_count, output_dir)
    return removed_count


async def build_issue_suggestion(
    repository: RepositoryRef,
    issue: GitHubIssue,
    analysis: IssueAnalysis,
    score: IssueScore,
    provider: ModelProvider | None,
    repo_tree: list[str],
    output_dir: Path,
) -> IssueSuggestion:
    logger.info("Building suggestion for issue #%s in %s.", issue.number, repository.full_name)
    likely_files = infer_likely_files(issue, analysis, repo_tree)
    suggested_fix = (
        "Start with a targeted reproduction, add a regression test, and patch the smallest branch that explains "
        "the observed failure before broadening scope."
    )
    additional_notes = [
        f"Priority: {score.priority.value}",
        f"Complexity: {score.complexity.value}",
        "Confidence blends heuristics with repository context.",
    ]

    if provider is not None:
        prompt = LlmRequest(
            system_prompt=(
                "You generate concise engineering fix plans for open source GitHub issues. "
                "Use cautious language, avoid certainty when evidence is thin, and return plain markdown-ready text."
            ),
            user_prompt=(
                f"Repository: {repository.full_name}\n"
                f"Issue #{issue.number}: {issue.title}\n"
                f"Body:\n{issue.body}\n\n"
                f"Analysis:\n- Summary: {analysis.problem_summary}\n"
                f"- Affected modules: {', '.join(analysis.affected_modules) or 'unknown'}\n"
                f"- Likely files: {', '.join(likely_files) or 'unknown'}\n"
                f"- Priority: {score.priority.value}\n"
                f"- Complexity: {score.complexity.value}\n"
                "Return:\n1. Root cause hypothesis\n2. Suggested fix\n3. Code guidance as 3 bullets"
            ),
        )
        try:
            logger.info("Calling LLM provider for issue #%s suggestion.", issue.number)
            response = await provider.generate(prompt)
            llm_text = response.text.strip()
            if llm_text:
                additional_notes.append(f"Generated with {response.provider}:{response.model}")
                suggested_fix = llm_text
                logger.info("LLM suggestion generated for issue #%s using %s.", issue.number, response.provider)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM generation failed for issue #%s: %s", issue.number, exc)
            additional_notes.append(f"LLM generation unavailable, used heuristic plan. Reason: {exc}")

    suggestion = IssueSuggestion(
        issue_number=issue.number,
        issue_title=issue.title,
        markdown_path="",
        problem=analysis.problem_summary,
        root_cause=analysis.root_cause_hypothesis,
        suggested_fix=suggested_fix,
        files_to_modify=likely_files,
        code_guidance=[
            "Look for validation and guard conditions on the failing path.",
            "Add or extend a regression test that captures the current issue report.",
            "Keep the initial patch narrow, then revisit adjacent cleanup in a follow-up.",
        ],
        additional_notes=additional_notes,
        confidence_score=score.confidence,
    )
    markdown_path = write_issue_markdown(output_dir, suggestion)
    suggestion.markdown_path = markdown_path
    logger.info("Suggestion markdown written for issue #%s at %s.", issue.number, markdown_path)
    return suggestion


def infer_likely_files(issue: GitHubIssue, analysis: IssueAnalysis, repo_tree: list[str]) -> list[str]:
    tokens = {
        token.lower()
        for token in " ".join([issue.title, issue.body] + analysis.affected_modules).replace("/", " ").replace("_", " ").split()
        if len(token) > 3
    }
    matches: list[tuple[int, str]] = []
    for path in repo_tree:
        score = sum(1 for token in tokens if token in path.lower())
        if score:
            matches.append((score, path))
    matches.sort(key=lambda item: (-item[0], len(item[1])))
    inferred = [path for _, path in matches[:5]]
    return inferred or analysis.affected_modules[:5]


def write_issue_markdown(output_dir: Path, suggestion: IssueSuggestion) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"issue-{suggestion.issue_number}.md"
    body = "\n".join(
        [
            f"# {suggestion.issue_title}",
            "",
            "## Problem",
            suggestion.problem,
            "",
            "## Root Cause (Hypothesis)",
            suggestion.root_cause,
            "",
            "## Suggested Fix",
            suggestion.suggested_fix,
            "",
            "## Files to Modify",
            *(f"- {item}" for item in (suggestion.files_to_modify or ["Needs codebase scan"])),
            "",
            "## Code Guidance",
            *(f"- {item}" for item in suggestion.code_guidance),
            "",
            "## Additional Notes",
            *(f"- {item}" for item in suggestion.additional_notes),
            "",
            f"## Confidence Score\n{suggestion.confidence_score}",
        ]
    )
    path.write_text(body, encoding="utf-8")
    return str(path)
