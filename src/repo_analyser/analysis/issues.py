from __future__ import annotations

import re

from repo_analyser.models import GitHubIssue, IssueAnalysis

CODE_PATH_RE = re.compile(r"`([^`]+\.[a-zA-Z0-9]+)`|([A-Za-z0-9_./-]+\.[a-zA-Z0-9]+)")


def analyze_issue(issue: GitHubIssue) -> IssueAnalysis:
    text = " ".join([issue.title, issue.body] + [comment.body for comment in issue.comments])
    matched_paths = sorted({match[0] or match[1] for match in CODE_PATH_RE.findall(text) if match[0] or match[1]})
    labels = {label.name.lower() for label in issue.labels}
    complexity_signals: list[str] = []
    easy_fix_signals: list[str] = []

    if "bug" in labels:
        complexity_signals.append("Bug label suggests a concrete defect.")
    if issue.comments_count >= 6:
        complexity_signals.append("High comment count hints at nuance or unresolved scope.")
    if "good first issue" in labels:
        easy_fix_signals.append("Marked as good first issue.")
    if issue.comments_count <= 2:
        easy_fix_signals.append("Limited discussion suggests contained scope.")
    if matched_paths:
        easy_fix_signals.append("Issue references explicit files or modules.")

    root_cause = (
        "The issue likely stems from a missing guard, outdated conditional path, or incomplete data handling "
        "around the modules mentioned in the issue discussion."
    )
    summary = (issue.body or issue.title).strip().splitlines()[0][:280]
    return IssueAnalysis(
        issue_number=issue.number,
        problem_summary=summary,
        affected_modules=matched_paths[:8],
        complexity_signals=complexity_signals,
        easy_fix_signals=easy_fix_signals,
        root_cause_hypothesis=root_cause,
    )
