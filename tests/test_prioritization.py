from datetime import datetime, timedelta, timezone

from repo_analyser.analysis.prioritization import score_issue
from repo_analyser.models import GitHubIssue, GitHubLabel


def test_good_first_issue_is_classified_as_easy():
    now = datetime.now(timezone.utc)
    issue = GitHubIssue(
        id=1,
        number=101,
        title="Update typo in docs",
        state="open",
        body="A typo exists in the install guide.",
        author="octocat",
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(days=1),
        comments_count=1,
        labels=[GitHubLabel(name="good first issue")],
        reactions_total=0,
        html_url="https://example.com",
    )
    score = score_issue(issue)
    assert score.complexity.value == "easy"
    assert score.priority.value in {"low", "medium"}
