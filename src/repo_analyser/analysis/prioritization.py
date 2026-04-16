from __future__ import annotations

from datetime import datetime, timezone

from repo_analyser.models import GitHubIssue, IssueComplexity, IssuePriority, IssueScore

HIGH_PRIORITY_LABELS = {"bug", "critical", "p0", "priority:high", "security"}
EASY_FIX_LABELS = {"good first issue", "easy", "starter", "beginner"}
COMPLEX_LABELS = {"epic", "refactor", "architecture", "breaking-change"}


def score_issue(issue: GitHubIssue) -> IssueScore:
    labels = {label.name.lower() for label in issue.labels}
    now = datetime.now(timezone.utc)
    age_days = max((now - issue.updated_at).days, 0)

    score = 0.0
    rationale: list[str] = []

    if labels & HIGH_PRIORITY_LABELS:
        score += 45
        rationale.append("High-priority label detected.")
    if issue.comments_count >= 5:
        score += 15
        rationale.append("Discussion volume suggests active impact.")
    if issue.reactions_total >= 3:
        score += 10
        rationale.append("Community reactions indicate interest.")
    if age_days <= 14:
        score += 12
        rationale.append("Recently updated issue.")
    if age_days > 120:
        score -= 8
        rationale.append("Issue is stale.")
    if labels & EASY_FIX_LABELS:
        score += 8
        rationale.append("Easy-fix label detected.")
    if labels & COMPLEX_LABELS:
        score -= 5
        rationale.append("Complexity-oriented label detected.")

    easy_signals = int(bool(labels & EASY_FIX_LABELS)) + int(issue.comments_count <= 2) + int(len(labels) <= 2)
    complex_signals = int(bool(labels & COMPLEX_LABELS)) + int(issue.comments_count >= 8)

    if easy_signals >= 2:
        complexity = IssueComplexity.easy
    elif complex_signals >= 2:
        complexity = IssueComplexity.complex
    else:
        complexity = IssueComplexity.moderate

    if score >= 45:
        priority = IssuePriority.high
    elif score >= 20:
        priority = IssuePriority.medium
    else:
        priority = IssuePriority.low

    confidence = min(0.95, 0.45 + (len(rationale) * 0.1))
    return IssueScore(
        issue_number=issue.number,
        score=round(score, 2),
        priority=priority,
        complexity=complexity,
        confidence=round(confidence, 2),
        rationale=rationale or ["No strong prioritization signals found."],
    )
