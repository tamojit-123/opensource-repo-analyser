from datetime import datetime, timezone

from repo_analyser.analysis.linking import analyze_pull_request, correlate_issues_and_prs
from repo_analyser.models import GitHubIssue, GitHubLabel, GitHubPullRequest


def _issue(number: int) -> GitHubIssue:
    now = datetime.now(timezone.utc)
    return GitHubIssue(
        id=number,
        number=number,
        title=f"Issue {number}",
        state="open",
        body="Something is broken",
        author="octocat",
        created_at=now,
        updated_at=now,
        comments_count=0,
        labels=[GitHubLabel(name="bug")],
        reactions_total=0,
        html_url="https://example.com",
    )


def test_link_detection_uses_pr_body_and_commit_messages():
    now = datetime.now(timezone.utc)
    pr = GitHubPullRequest(
        id=1,
        number=9,
        title="Fix bug",
        state="closed",
        body="Fixes #12",
        author="octocat",
        created_at=now,
        updated_at=now,
        merged_at=now,
        html_url="https://example.com",
        commits=["cleanup and closes #13"],
        files=["src/app.py"],
    )
    analysis = analyze_pull_request(pr)
    assert analysis.linked_issue_numbers == [12, 13]


def test_correlation_marks_issue_resolved_when_linked_pr_exists():
    issue = _issue(12)
    pr_analysis = analyze_pull_request(
        GitHubPullRequest(
            id=1,
            number=99,
            title="Patch",
            state="closed",
            body="Resolves #12",
            author="octocat",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            html_url="https://example.com",
        )
    )
    links = correlate_issues_and_prs([issue], [pr_analysis])
    assert links[0].resolved is True
    assert links[0].pr_numbers == [99]
