from __future__ import annotations

from repo_analyser.analysis.linking import analyze_pull_request, correlate_issues_and_prs
from repo_analyser.github_api import GitHubClient
from repo_analyser.models import GitHubIssue, GitHubPullRequest, RepoData


class RepoTools:
    def __init__(self, github: GitHubClient) -> None:
        self.github = github

    async def get_repo_data(self, repo_url: str) -> RepoData:
        return await self.github.get_repo_data(repo_url)

    async def get_pr_diff(self, repo_full_name: str, pr_id: int) -> str:
        return await self.github.get_pr_diff(repo_full_name, pr_id)

    async def get_issue_details(self, repo_full_name: str, issue_id: int) -> GitHubIssue:
        return await self.github.get_issue_details(repo_full_name, issue_id)

    async def link_issue_pr(self, issues: list[GitHubIssue], prs: list[GitHubPullRequest]):
        pr_analyses = [analyze_pull_request(pr) for pr in prs]
        return correlate_issues_and_prs(issues, pr_analyses)
