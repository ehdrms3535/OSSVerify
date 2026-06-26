import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import requests

GITHUB_API_BASE = "https://api.github.com"


@dataclass
class PullRequest:
    number: int
    title: str
    merged: bool
    repo_full_name: str
    repo_stars: int
    author: str = ""
    created_at: str = ""
    approved: bool = False


@dataclass
class CodeReview:
    pr_number: int
    repo_full_name: str
    body: str
    led_to_change: bool


@dataclass
class Issue:
    number: int
    repo_full_name: str
    state: str
    author: str = ""
    created_at: str = ""
    closed_at: Optional[str] = None


@dataclass
class Commit:
    sha: str
    repo_full_name: str
    message: str
    date: str = ""


@dataclass
class Release:
    repo_full_name: str
    tag_name: str
    published_at: str


@dataclass
class Repository:
    full_name: str
    stars: int
    forks: int
    has_readme: bool
    has_contributing_guide: bool


@dataclass
class ActivityRatio:
    contributor_ratio: float
    maintainer_ratio: float

    @staticmethod
    def from_counts(contributor_activities: int, maintainer_activities: int) -> "ActivityRatio":
        total = contributor_activities + maintainer_activities
        if total == 0:
            return ActivityRatio(contributor_ratio=0.0, maintainer_ratio=0.0)
        return ActivityRatio(
            contributor_ratio=contributor_activities / total,
            maintainer_ratio=maintainer_activities / total,
        )


@dataclass
class GitHubData:
    username: str

    contributed_prs: List[PullRequest] = field(default_factory=list)
    contributed_reviews: List[CodeReview] = field(default_factory=list)
    contributed_issues: List[Issue] = field(default_factory=list)
    contributed_commits: List[Commit] = field(default_factory=list)

    owned_repos: List[Repository] = field(default_factory=list)
    received_prs: List[PullRequest] = field(default_factory=list)
    received_issues: List[Issue] = field(default_factory=list)
    maintainer_reviews: List[CodeReview] = field(default_factory=list)
    releases: List[Release] = field(default_factory=list)

    languages: Dict[str, int] = field(default_factory=dict)
    activity_ratio: Optional[ActivityRatio] = None


class GitHubCollector:
    def __init__(self, github_token: Optional[str] = None, per_page: int = 100, max_search_pages: int = 10):
        self.github_token = github_token
        self.per_page = per_page
        self.max_search_pages = max_search_pages  # GitHub search API caps results at 1000 (10 * 100) anyway
        self.session = requests.Session()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        self.session.headers.update(headers)
        self._repo_cache: Dict[str, dict] = {}

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        while True:
            response = self.session.request(method, url, **kwargs)
            if response.status_code in (403, 429) and response.headers.get("X-RateLimit-Remaining") == "0":
                reset_at = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                time.sleep(max(reset_at - time.time(), 1))
                continue
            if response.status_code == 403 and "retry-after" in response.headers:
                time.sleep(int(response.headers["retry-after"]))
                continue
            return response

    def _paginate(self, url: str, params: dict, items_key: Optional[str] = None) -> List[dict]:
        results: List[dict] = []
        params = dict(params, per_page=self.per_page)
        for page in range(1, self.max_search_pages + 1):
            response = self._request("GET", url, params=dict(params, page=page))
            if response.status_code != 200:
                break
            payload = response.json()
            items = payload[items_key] if items_key else payload
            if not items:
                break
            results.extend(items)
            if len(items) < self.per_page:
                break
        return results

    def _get_repo(self, full_name: str) -> dict:
        if full_name not in self._repo_cache:
            response = self._request("GET", f"{GITHUB_API_BASE}/repos/{full_name}")
            self._repo_cache[full_name] = response.json() if response.status_code == 200 else {}
        return self._repo_cache[full_name]

    @staticmethod
    def _repo_full_name_from_url(repository_url: str) -> str:
        return repository_url.split("repos/")[-1]

    @staticmethod
    def _repo_owner(full_name: str) -> str:
        return full_name.split("/")[0]

    def _search_issues(self, query: str) -> List[dict]:
        return self._paginate(f"{GITHUB_API_BASE}/search/issues", {"q": query}, items_key="items")

    def _list_reviews(self, repo_full_name: str, pr_number: int) -> List[dict]:
        response = self._request("GET", f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/reviews")
        return response.json() if response.status_code == 200 else []

    def _collect_owned_repos(self, username: str) -> List[Repository]:
        raw_repos = self._paginate(f"{GITHUB_API_BASE}/users/{username}/repos", {"type": "owner", "sort": "updated"})
        repos = []
        for raw in raw_repos:
            full_name = raw["full_name"]
            # community/profile gives readme + contributing presence in a single call
            community = self._request("GET", f"{GITHUB_API_BASE}/repos/{full_name}/community/profile")
            files = community.json().get("files", {}) if community.status_code == 200 else {}
            repos.append(
                Repository(
                    full_name=full_name,
                    stars=raw.get("stargazers_count", 0),
                    forks=raw.get("forks_count", 0),
                    has_readme=bool(files.get("readme")),
                    has_contributing_guide=bool(files.get("contributing")),
                )
            )
        return repos

    def _collect_languages(self, owned_repos: List[Repository]) -> Dict[str, int]:
        totals: Dict[str, int] = {}
        for repo in owned_repos:
            response = self._request("GET", f"{GITHUB_API_BASE}/repos/{repo.full_name}/languages")
            if response.status_code != 200:
                continue
            for language, byte_count in response.json().items():
                totals[language] = totals.get(language, 0) + byte_count
        return totals

    def _collect_prs(self, username: str) -> Tuple[List[PullRequest], List[PullRequest]]:
        contributed, received = [], []
        for raw in self._search_issues(f"type:pr author:{username}"):
            repo_full_name = self._repo_full_name_from_url(raw["repository_url"])
            if self._repo_owner(repo_full_name) == username:
                continue
            repo = self._get_repo(repo_full_name)
            reviews = self._list_reviews(repo_full_name, raw["number"])
            approved = any(
                r.get("state") == "APPROVED" and r.get("user", {}).get("login") != username for r in reviews
            )
            contributed.append(
                PullRequest(
                    number=raw["number"],
                    title=raw["title"],
                    merged=bool(raw.get("pull_request", {}).get("merged_at")),
                    repo_full_name=repo_full_name,
                    repo_stars=repo.get("stargazers_count", 0),
                    author=username,
                    created_at=raw.get("created_at", ""),
                    approved=approved,
                )
            )
        for raw in self._search_issues(f"type:pr user:{username}"):
            if raw["user"]["login"] == username:
                continue
            repo_full_name = self._repo_full_name_from_url(raw["repository_url"])
            repo = self._get_repo(repo_full_name)
            received.append(
                PullRequest(
                    number=raw["number"],
                    title=raw["title"],
                    merged=bool(raw.get("pull_request", {}).get("merged_at")),
                    repo_full_name=repo_full_name,
                    repo_stars=repo.get("stargazers_count", 0),
                    author=raw["user"]["login"],
                    created_at=raw.get("created_at", ""),
                )
            )
        return contributed, received

    def _collect_issues(self, username: str) -> Tuple[List[Issue], List[Issue]]:
        contributed, received = [], []
        for raw in self._search_issues(f"type:issue author:{username}"):
            repo_full_name = self._repo_full_name_from_url(raw["repository_url"])
            if self._repo_owner(repo_full_name) == username:
                continue
            contributed.append(
                Issue(
                    number=raw["number"],
                    repo_full_name=repo_full_name,
                    state=raw["state"],
                    author=username,
                    created_at=raw.get("created_at", ""),
                    closed_at=raw.get("closed_at"),
                )
            )
        for raw in self._search_issues(f"type:issue user:{username}"):
            if raw["user"]["login"] == username:
                continue
            repo_full_name = self._repo_full_name_from_url(raw["repository_url"])
            received.append(
                Issue(
                    number=raw["number"],
                    repo_full_name=repo_full_name,
                    state=raw["state"],
                    author=raw["user"]["login"],
                    created_at=raw.get("created_at", ""),
                    closed_at=raw.get("closed_at"),
                )
            )
        return contributed, received

    def _collect_commits(self, username: str) -> List[Commit]:
        commits = []
        for raw in self._paginate(f"{GITHUB_API_BASE}/search/commits", {"q": f"author:{username}"}, items_key="items"):
            commits.append(
                Commit(
                    sha=raw["sha"],
                    repo_full_name=raw["repository"]["full_name"],
                    message=raw["commit"]["message"],
                    date=raw["commit"]["author"]["date"],
                )
            )
        return commits

    def _review_led_to_change(self, repo_full_name: str, pr_number: int, review_submitted_at: str) -> bool:
        # heuristic: a commit pushed to the PR after the review was submitted counts as a change
        response = self._request("GET", f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/commits")
        if response.status_code != 200:
            return False
        return any(commit["commit"]["committer"]["date"] > review_submitted_at for commit in response.json())

    def _collect_reviews(self, username: str) -> List[CodeReview]:
        reviews = []
        for raw in self._search_issues(f"type:pr reviewed-by:{username}"):
            repo_full_name = self._repo_full_name_from_url(raw["repository_url"])
            pr_number = raw["number"]
            for review in self._list_reviews(repo_full_name, pr_number):
                if review.get("user", {}).get("login") != username:
                    continue
                reviews.append(
                    CodeReview(
                        pr_number=pr_number,
                        repo_full_name=repo_full_name,
                        body=review.get("body") or "",
                        led_to_change=self._review_led_to_change(repo_full_name, pr_number, review["submitted_at"]),
                    )
                )
        return reviews

    def _collect_maintainer_reviews(self, username: str, received_prs: List[PullRequest]) -> List[CodeReview]:
        reviews = []
        for pr in received_prs:
            for review in self._list_reviews(pr.repo_full_name, pr.number):
                if review.get("user", {}).get("login") != username:
                    continue
                reviews.append(
                    CodeReview(
                        pr_number=pr.number,
                        repo_full_name=pr.repo_full_name,
                        body=review.get("body") or "",
                        led_to_change=self._review_led_to_change(pr.repo_full_name, pr.number, review["submitted_at"]),
                    )
                )
        return reviews

    def _collect_releases(self, owned_repos: List[Repository]) -> List[Release]:
        releases = []
        for repo in owned_repos:
            for raw in self._paginate(f"{GITHUB_API_BASE}/repos/{repo.full_name}/releases", {}):
                releases.append(
                    Release(
                        repo_full_name=repo.full_name,
                        tag_name=raw.get("tag_name", ""),
                        published_at=raw.get("published_at") or raw.get("created_at", ""),
                    )
                )
        return releases

    def collect(self, username: str) -> GitHubData:
        owned_repos = self._collect_owned_repos(username)
        languages = self._collect_languages(owned_repos)
        releases = self._collect_releases(owned_repos)
        contributed_prs, received_prs = self._collect_prs(username)
        contributed_issues, received_issues = self._collect_issues(username)
        contributed_commits = self._collect_commits(username)
        contributed_reviews = self._collect_reviews(username)
        maintainer_reviews = self._collect_maintainer_reviews(username, received_prs)

        contributor_activities = (
            len(contributed_prs) + len(contributed_reviews) + len(contributed_issues) + len(contributed_commits)
        )
        maintainer_activities = len(received_prs) + len(received_issues) + len(maintainer_reviews)

        return GitHubData(
            username=username,
            contributed_prs=contributed_prs,
            contributed_reviews=contributed_reviews,
            contributed_issues=contributed_issues,
            contributed_commits=contributed_commits,
            owned_repos=owned_repos,
            received_prs=received_prs,
            received_issues=received_issues,
            maintainer_reviews=maintainer_reviews,
            releases=releases,
            languages=languages,
            activity_ratio=ActivityRatio.from_counts(contributor_activities, maintainer_activities),
        )
