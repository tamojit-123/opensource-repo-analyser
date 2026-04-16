from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class IssuePriority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class IssueComplexity(str, Enum):
    easy = "easy"
    moderate = "moderate"
    complex = "complex"


class RepositoryRef(BaseModel):
    owner: str
    name: str
    url: HttpUrl

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class GitHubLabel(BaseModel):
    name: str
    color: str | None = None
    description: str | None = None


class GitHubComment(BaseModel):
    id: int
    body: str
    author: str
    created_at: datetime
    reactions_total: int = 0


class GitHubIssue(BaseModel):
    id: int
    number: int
    title: str
    state: str
    body: str
    author: str
    created_at: datetime
    updated_at: datetime
    comments_count: int
    labels: list[GitHubLabel] = Field(default_factory=list)
    reactions_total: int = 0
    html_url: str
    comments: list[GitHubComment] = Field(default_factory=list)


class GitHubPullRequest(BaseModel):
    id: int
    number: int
    title: str
    state: str
    body: str
    author: str
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    html_url: str
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0
    commits: list[str] = Field(default_factory=list)
    comments: list[GitHubComment] = Field(default_factory=list)
    diff: str | None = None
    files: list[str] = Field(default_factory=list)


class RepoData(BaseModel):
    repository: RepositoryRef
    issues: list[GitHubIssue]
    pull_requests: list[GitHubPullRequest]


class IssueAnalysis(BaseModel):
    issue_number: int
    problem_summary: str
    affected_modules: list[str] = Field(default_factory=list)
    complexity_signals: list[str] = Field(default_factory=list)
    easy_fix_signals: list[str] = Field(default_factory=list)
    root_cause_hypothesis: str


class PrAnalysis(BaseModel):
    pr_number: int
    linked_issue_numbers: list[int] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    summary: str


class IssuePrLink(BaseModel):
    issue_number: int
    pr_numbers: list[int] = Field(default_factory=list)
    resolved: bool
    evidence: list[str] = Field(default_factory=list)


class IssueScore(BaseModel):
    issue_number: int
    score: float
    priority: IssuePriority
    complexity: IssueComplexity
    confidence: float
    rationale: list[str] = Field(default_factory=list)


class IssueSuggestion(BaseModel):
    issue_number: int
    issue_title: str
    markdown_path: str
    problem: str
    root_cause: str
    suggested_fix: str
    files_to_modify: list[str] = Field(default_factory=list)
    code_guidance: list[str] = Field(default_factory=list)
    additional_notes: list[str] = Field(default_factory=list)
    confidence_score: float


class DashboardSummary(BaseModel):
    total_issues: int
    resolved_issues: int
    unresolved_issues: int
    easy_fix_issues: int


class AnalysisResult(BaseModel):
    repository: RepositoryRef
    summary: DashboardSummary
    links: list[IssuePrLink]
    issue_analyses: list[IssueAnalysis]
    pr_analyses: list[PrAnalysis]
    prioritization: list[IssueScore]
    suggestions: list[IssueSuggestion]


class AgentLogEvent(BaseModel):
    agent: str
    status: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    repo_url: HttpUrl


class ChatResponse(BaseModel):
    result: AnalysisResult
    logs: list[AgentLogEvent]
