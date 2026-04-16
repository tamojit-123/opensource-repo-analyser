from __future__ import annotations

import re

from repo_analyser.models import GitHubIssue, GitHubPullRequest, IssuePrLink, PrAnalysis

KEYWORD_RE = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
PLAIN_ISSUE_RE = re.compile(r"#(\d+)")


def analyze_pull_request(pr: GitHubPullRequest) -> PrAnalysis:
    linked = sorted(set(_extract_issue_refs(pr.body) + _extract_issue_refs("\n".join(pr.commits)) + _extract_issue_refs("\n".join(comment.body for comment in pr.comments))))
    summary = (
        f"Touches {pr.changed_files} files with {pr.additions} additions and {pr.deletions} deletions. "
        f"Detected links to issues: {linked or 'none'}."
    )
    return PrAnalysis(
        pr_number=pr.number,
        linked_issue_numbers=linked,
        changed_files=pr.files,
        summary=summary,
    )


def correlate_issues_and_prs(issues: list[GitHubIssue], pr_analyses: list[PrAnalysis]) -> list[IssuePrLink]:
    pr_map = {issue.number: [] for issue in issues}
    evidence_map = {issue.number: [] for issue in issues}
    for pr in pr_analyses:
        for issue_number in pr.linked_issue_numbers:
            if issue_number in pr_map:
                pr_map[issue_number].append(pr.pr_number)
                evidence_map[issue_number].append(f"PR #{pr.pr_number} referenced issue #{issue_number}")
    links: list[IssuePrLink] = []
    for issue in issues:
        prs = sorted(set(pr_map[issue.number]))
        resolved = bool(prs)
        evidence = evidence_map[issue.number] or ["No linked PR reference found."]
        if issue.state == "closed" and not prs:
            evidence.append("Issue is closed in GitHub, but no linked PR was detected.")
        links.append(IssuePrLink(issue_number=issue.number, pr_numbers=prs, resolved=resolved, evidence=evidence))
    return links


def _extract_issue_refs(text: str) -> list[int]:
    keyword_matches = [int(match) for match in KEYWORD_RE.findall(text or "")]
    plain_matches = [int(match) for match in PLAIN_ISSUE_RE.findall(text or "")]
    return keyword_matches or plain_matches
