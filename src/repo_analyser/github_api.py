from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx

from repo_analyser.cache import FileCache
from repo_analyser.config import Settings
from repo_analyser.logging_utils import get_logger
from repo_analyser.models import GitHubComment, GitHubIssue, GitHubLabel, GitHubPullRequest, RepoData, RepositoryRef

ISSUE_REF_RE = re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
GITHUB_REPO_RE = re.compile(r"^/([^/]+)/([^/]+?)(?:\.git)?/?$")


class GitHubRateLimitError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, settings: Settings) -> None:
        self.logger = get_logger(__name__, "github")
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "opensource-repo-analyser",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.github_api_base,
            headers=headers,
            timeout=settings.request_timeout_seconds,
        )
        self.cache = FileCache(settings.cache_dir / "github", settings.github_cache_ttl_seconds)

    async def close(self) -> None:
        self.logger.debug("Closing GitHub HTTP client.")
        await self.client.aclose()

    def parse_repo_url(self, repo_url: str) -> RepositoryRef:
        parsed = urlparse(repo_url)
        match = GITHUB_REPO_RE.match(parsed.path)
        if not match:
            msg = f"Unsupported GitHub URL: {repo_url}"
            self.logger.error("Failed to parse GitHub repository URL: %s", repo_url)
            raise ValueError(msg)
        owner, name = match.groups()
        self.logger.info("Parsed repository URL for %s/%s.", owner, name)
        return RepositoryRef(owner=owner, name=name, url=repo_url)

    async def _request_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        cache_key = f"{path}?{params or {}}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug("Cache hit for GitHub request %s.", cache_key)
            return cached
        self.logger.info("Requesting GitHub API path=%s params=%s", path, params or {})
        response = await self.client.get(path, params=params)
        if response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0":
            reset_at = response.headers.get("x-ratelimit-reset")
            self.logger.error("GitHub API rate limit exceeded for path=%s reset_at=%s", path, reset_at)
            raise GitHubRateLimitError(f"GitHub API rate limit exceeded. Reset at epoch {reset_at}.")
        response.raise_for_status()
        data = response.json()
        self.logger.debug("GitHub API response received for %s.", cache_key)
        self.cache.set(cache_key, data)
        return data

    async def _paginate(self, path: str, params: dict[str, Any]) -> AsyncIterator[list[dict[str, Any]]]:
        page = 1
        while True:
            page_params = {**params, "per_page": 100, "page": page}
            data = await self._request_json(path, page_params)
            if not data:
                self.logger.debug("Pagination complete for %s after page %s.", path, page)
                break
            self.logger.info("Fetched page %s for %s with %s items.", page, path, len(data))
            yield data
            if len(data) < 100:
                break
            page += 1
            await asyncio.sleep(0)

    async def get_repo_data(self, repo_url: str) -> RepoData:
        repo = self.parse_repo_url(repo_url)
        self.logger.info("Starting repository data fetch for %s.", repo.full_name)
        issues, pulls = await asyncio.gather(
            self._fetch_issues(repo),
            self._fetch_pull_requests(repo),
        )
        self.logger.info(
            "Completed repository data fetch for %s with %s open issues and %s pull requests.",
            repo.full_name,
            len(issues),
            len(pulls),
        )
        return RepoData(repository=repo, issues=issues, pull_requests=pulls)

    async def _fetch_issues(self, repo: RepositoryRef) -> list[GitHubIssue]:
        issues: list[GitHubIssue] = []
        async for page in self._paginate(f"/repos/{repo.full_name}/issues", {"state": "open"}):
            candidates = [item for item in page if "pull_request" not in item]
            self.logger.info("Processing %s open issues from current page for %s.", len(candidates), repo.full_name)
            details = await asyncio.gather(*(self.get_issue_details(repo.full_name, item["number"]) for item in candidates))
            issues.extend(details)
        self.logger.info("Fetched %s open issues for %s.", len(issues), repo.full_name)
        return issues

    async def _fetch_pull_requests(self, repo: RepositoryRef) -> list[GitHubPullRequest]:
        pulls: list[GitHubPullRequest] = []
        async for page in self._paginate(f"/repos/{repo.full_name}/pulls", {"state": "all"}):
            details = await asyncio.gather(*(self.get_pr_details(repo.full_name, item["number"]) for item in page))
            pulls.extend(details)
        self.logger.info("Fetched %s pull requests for %s.", len(pulls), repo.full_name)
        return pulls

    async def get_issue_details(self, repo_full_name: str, issue_number: int) -> GitHubIssue:
        self.logger.debug("Fetching issue details for %s#%s.", repo_full_name, issue_number)
        issue = await self._request_json(f"/repos/{repo_full_name}/issues/{issue_number}")
        comments = await self._fetch_comments(f"/repos/{repo_full_name}/issues/{issue_number}/comments")
        self.logger.debug("Fetched %s comments for issue %s#%s.", len(comments), repo_full_name, issue_number)
        return GitHubIssue(
            id=issue["id"],
            number=issue["number"],
            title=issue["title"],
            state=issue["state"],
            body=issue.get("body") or "",
            author=issue["user"]["login"],
            created_at=_parse_datetime(issue["created_at"]),
            updated_at=_parse_datetime(issue["updated_at"]),
            comments_count=issue["comments"],
            labels=[GitHubLabel(name=label["name"], color=label.get("color"), description=label.get("description")) for label in issue["labels"]],
            reactions_total=_reaction_total(issue),
            html_url=issue["html_url"],
            comments=comments,
        )

    async def get_pr_details(self, repo_full_name: str, pr_number: int) -> GitHubPullRequest:
        self.logger.debug("Fetching PR details for %s#%s.", repo_full_name, pr_number)
        pr = await self._request_json(f"/repos/{repo_full_name}/pulls/{pr_number}")
        comments, files, commits = await asyncio.gather(
            self._fetch_comments(f"/repos/{repo_full_name}/issues/{pr_number}/comments"),
            self._request_json(f"/repos/{repo_full_name}/pulls/{pr_number}/files"),
            self._request_json(f"/repos/{repo_full_name}/pulls/{pr_number}/commits"),
        )
        diff = await self.get_pr_diff(repo_full_name, pr_number)
        self.logger.debug(
            "Fetched PR %s#%s with %s files, %s commits, and %s comments.",
            repo_full_name,
            pr_number,
            len(files),
            len(commits),
            len(comments),
        )
        return GitHubPullRequest(
            id=pr["id"],
            number=pr["number"],
            title=pr["title"],
            state=pr["state"],
            body=pr.get("body") or "",
            author=pr["user"]["login"],
            created_at=_parse_datetime(pr["created_at"]),
            updated_at=_parse_datetime(pr["updated_at"]),
            merged_at=_parse_datetime(pr["merged_at"]) if pr.get("merged_at") else None,
            html_url=pr["html_url"],
            changed_files=pr.get("changed_files", 0),
            additions=pr.get("additions", 0),
            deletions=pr.get("deletions", 0),
            comments=comments,
            diff=diff,
            commits=[item["commit"]["message"] for item in commits],
            files=[item["filename"] for item in files],
        )

    async def get_pr_diff(self, repo_full_name: str, pr_number: int) -> str:
        cache_key = f"diff:{repo_full_name}:{pr_number}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug("Cache hit for PR diff %s.", cache_key)
            return str(cached)
        self.logger.info("Fetching PR diff for %s#%s.", repo_full_name, pr_number)
        response = await self.client.get(
            f"/repos/{repo_full_name}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        response.raise_for_status()
        diff = response.text
        self.cache.set(cache_key, diff)
        return diff

    async def fetch_repo_tree(self, repo_full_name: str) -> list[str]:
        self.logger.info("Fetching repository tree for %s.", repo_full_name)
        repo = await self._request_json(f"/repos/{repo_full_name}")
        branch = repo["default_branch"]
        tree = await self._request_json(f"/repos/{repo_full_name}/git/trees/{branch}", {"recursive": 1})
        paths = [item["path"] for item in tree.get("tree", []) if item.get("type") == "blob"]
        self.logger.info("Fetched %s files from repository tree for %s.", len(paths), repo_full_name)
        return paths

    async def _fetch_comments(self, path: str) -> list[GitHubComment]:
        comments: list[GitHubComment] = []
        async for page in self._paginate(path, {}):
            for comment in page:
                comments.append(
                    GitHubComment(
                        id=comment["id"],
                        body=comment.get("body") or "",
                        author=comment["user"]["login"],
                        created_at=_parse_datetime(comment["created_at"]),
                        reactions_total=_reaction_total(comment),
                    )
                )
        self.logger.debug("Fetched %s comments from %s.", len(comments), path)
        return comments


def _reaction_total(payload: dict[str, Any]) -> int:
    reactions = payload.get("reactions") or {}
    return int(reactions.get("total_count", 0))


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
