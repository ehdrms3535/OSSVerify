import concurrent.futures
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ossverify.collector.github_http import GITHUB_API_BASE, GitHubHTTPClient

# GitHub 자동화 봇 — 리뷰어/기여자/이슈 작성자 통계에서 제외
_BOT_LOGINS = frozenset({
    "dependabot", "dependabot[bot]",
    "renovate", "renovate[bot]",
    "github-actions[bot]",
    "codecov[bot]",
    "snyk-bot",
    "pre-commit-ci[bot]",
    "allcontributors[bot]",
    "imgbot[bot]",
    "semantic-release-bot",
    "stale[bot]",
    "greenkeeper[bot]",
    "pyup-bot",
})


def _is_bot(login: str) -> bool:
    return login in _BOT_LOGINS or login.endswith("[bot]")

# 사용자 레포지터리 메타데이터, 언어, 릴리즈를 한 번의 GraphQL 페이지네이션으로 수집.
# community/profile REST 엔드포인트(N호출) + languages(N호출) + releases(N호출)를 대체.
_REPOS_GRAPHQL = """
query UserRepos($login: String!, $after: String) {
  user(login: $login) {
    repositories(
      first: 100
      ownerAffiliations: [OWNER]
      orderBy: {field: UPDATED_AT, direction: DESC}
      after: $after
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        nameWithOwner
        stargazerCount
        forkCount
        description
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
        releases(first: 10, orderBy: {field: CREATED_AT, direction: DESC}) {
          nodes { tagName publishedAt createdAt }
        }
      }
    }
  }
}
"""


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
    description: str = ""


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
    def __init__(
        self,
        github_token: Optional[str] = None,
        per_page: int = 100,
        max_search_pages: int = 10,
        max_repo_pages: int = 10,
    ):
        self.client = GitHubHTTPClient(github_token, per_page=per_page, max_pages=max_search_pages)
        self.max_repo_pages = max_repo_pages

    # -------------------------------------------------------------------------
    # 내부 헬퍼
    # -------------------------------------------------------------------------

    def _search_issues(self, query: str) -> List[dict]:
        return self.client.paginate(f"{GITHUB_API_BASE}/search/issues", {"q": query}, items_key="items")

    def _list_reviews(self, repo_full_name: str, pr_number: int) -> List[dict]:
        response = self.client.request("GET", f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/reviews")
        return response.json() if response.status_code == 200 else []

    def _review_led_to_change(self, repo_full_name: str, pr_number: int, review_submitted_at: str) -> bool:
        response = self.client.request("GET", f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/commits")
        if response.status_code != 200:
            return False
        return any(commit["commit"]["committer"]["date"] > review_submitted_at for commit in response.json())

    # -------------------------------------------------------------------------
    # GraphQL — 레포 메타데이터 + 언어 + 릴리즈 한 번에
    # -------------------------------------------------------------------------

    def _collect_repos_graphql(self, username: str) -> Tuple[List[Repository], Dict[str, int], List[Release]]:
        repos: List[Repository] = []
        languages: Dict[str, int] = {}
        releases: List[Release] = []
        cursor = None
        page = 0

        while page < self.max_repo_pages:
            try:
                data = self.client.graphql(_REPOS_GRAPHQL, {"login": username, "after": cursor})
            except Exception:
                # 502/타임아웃 등 일시적 오류 — 지금까지 수집한 부분 결과로 계속 진행
                break
            connection = data["user"]["repositories"]

            for node in (connection.get("nodes") or []):
                full_name = node["nameWithOwner"]
                # git object 조회 제거 (502 유발) — description·stars 기반 휴리스틱
                has_readme = bool(node.get("description") or node.get("stargazerCount", 0) > 5)
                has_contributing = node.get("stargazerCount", 0) > 100

                repo = Repository(
                    full_name=full_name,
                    stars=node["stargazerCount"],
                    forks=node["forkCount"],
                    description=node.get("description") or "",
                    has_readme=has_readme,
                    has_contributing_guide=has_contributing,
                )
                repos.append(repo)

                # PR 수집 시 get_repo() REST 재호출 방지용 캐시 선채움
                self.client.repo_cache[full_name] = {
                    "stargazers_count": repo.stars,
                    "forks_count": repo.forks,
                    "description": repo.description,
                    "full_name": full_name,
                }

                for edge in (node.get("languages") or {}).get("edges") or []:
                    if not edge or not edge.get("node"):
                        continue
                    lang = edge["node"]["name"]
                    languages[lang] = languages.get(lang, 0) + edge["size"]

                for rel in (node.get("releases") or {}).get("nodes") or []:
                    releases.append(Release(
                        repo_full_name=full_name,
                        tag_name=rel.get("tagName", ""),
                        published_at=rel.get("publishedAt") or rel.get("createdAt", ""),
                    ))

            page += 1
            page_info = connection["pageInfo"]
            if not page_info["hasNextPage"]:
                break
            cursor = page_info["endCursor"]

        return repos, languages, releases

    # -------------------------------------------------------------------------
    # PR 수집 — 내부 per-PR 병렬 (리뷰 확인 N호출)
    # -------------------------------------------------------------------------

    def _collect_prs(self, username: str) -> Tuple[List[PullRequest], List[PullRequest]]:
        contrib_raws = [
            raw for raw in self._search_issues(f"type:pr author:{username}")
            if self.client.repo_owner(self.client.repo_full_name_from_url(raw["repository_url"])) != username
        ]
        received_raws = [
            raw for raw in self._search_issues(f"type:pr user:{username}")
            if raw["user"]["login"] != username
        ]

        # 외부 레포 stars: GraphQL 배치로 선캐싱 (REST 최대 300회 → GraphQL ~15회)
        contrib_repo_names = list({
            self.client.repo_full_name_from_url(raw["repository_url"])
            for raw in contrib_raws
        })
        self.client.get_repos_batch(contrib_repo_names)

        # contributed PR의 reviews: GraphQL 배치 (REST 300회 → GraphQL ~15회)
        contrib_pr_items = [
            (self.client.repo_full_name_from_url(raw["repository_url"]), raw["number"])
            for raw in contrib_raws
        ]
        contrib_pr_data = self.client.get_pr_reviews_batch(contrib_pr_items)

        contributed = []
        for raw in contrib_raws:
            repo_full_name = self.client.repo_full_name_from_url(raw["repository_url"])
            pr_number = raw["number"]
            repo = self.client.get_repo(repo_full_name)
            pr_info = contrib_pr_data.get((repo_full_name, pr_number), {})
            reviews = pr_info.get("reviews", [])
            approved = any(
                r.get("state") == "APPROVED"
                and (r.get("author") or {}).get("login") != username
                and not _is_bot((r.get("author") or {}).get("login") or "")
                for r in reviews
            )
            contributed.append(PullRequest(
                number=pr_number,
                title=raw["title"],
                merged=bool(raw.get("pull_request", {}).get("merged_at")),
                repo_full_name=repo_full_name,
                repo_stars=repo.get("stargazers_count", 0),
                author=username,
                created_at=raw.get("created_at", ""),
                approved=approved,
            ))

        # received PR의 레포는 GraphQL 캐시 히트 (자신의 레포)
        received = []
        for raw in received_raws:
            author_login = raw["user"]["login"]
            if _is_bot(author_login):
                continue
            repo_full_name = self.client.repo_full_name_from_url(raw["repository_url"])
            repo = self.client.get_repo(repo_full_name)
            received.append(PullRequest(
                number=raw["number"],
                title=raw["title"],
                merged=bool(raw.get("pull_request", {}).get("merged_at")),
                repo_full_name=repo_full_name,
                repo_stars=repo.get("stargazers_count", 0),
                author=author_login,
                created_at=raw.get("created_at", ""),
            ))

        return contributed, received

    # -------------------------------------------------------------------------
    # 이슈 수집 (per-issue 추가 호출 없음 — 병렬화는 최상위에서)
    # -------------------------------------------------------------------------

    def _collect_issues(self, username: str) -> Tuple[List[Issue], List[Issue]]:
        contributed, received = [], []
        for raw in self._search_issues(f"type:issue author:{username}"):
            repo_full_name = self.client.repo_full_name_from_url(raw["repository_url"])
            if self.client.repo_owner(repo_full_name) == username:
                continue
            contributed.append(Issue(
                number=raw["number"],
                repo_full_name=repo_full_name,
                state=raw["state"],
                author=username,
                created_at=raw.get("created_at", ""),
                closed_at=raw.get("closed_at"),
            ))
        for raw in self._search_issues(f"type:issue user:{username}"):
            author_login = raw["user"]["login"]
            if author_login == username or _is_bot(author_login):
                continue
            repo_full_name = self.client.repo_full_name_from_url(raw["repository_url"])
            received.append(Issue(
                number=raw["number"],
                repo_full_name=repo_full_name,
                state=raw["state"],
                author=raw["user"]["login"],
                created_at=raw.get("created_at", ""),
                closed_at=raw.get("closed_at"),
            ))
        return contributed, received

    # -------------------------------------------------------------------------
    # 커밋 수집 (per-commit 추가 호출 없음)
    # -------------------------------------------------------------------------

    def _collect_commits(self, username: str) -> List[Commit]:
        commits = []
        for raw in self.client.paginate(
            f"{GITHUB_API_BASE}/search/commits", {"q": f"author:{username}"}, items_key="items"
        ):
            commits.append(Commit(
                sha=raw["sha"],
                repo_full_name=raw["repository"]["full_name"],
                message=raw["commit"]["message"],
                date=raw["commit"]["author"]["date"],
            ))
        return commits

    # -------------------------------------------------------------------------
    # 리뷰 수집 — 내부 per-PR 병렬 (list_reviews + led_to_change 2N호출)
    # -------------------------------------------------------------------------

    def _collect_reviews(self, username: str) -> List[CodeReview]:
        pr_raws = self._search_issues(f"type:pr reviewed-by:{username}")

        # GraphQL 배치로 reviews + commits 한 번에 조회 (REST 2N회 → GraphQL ~N/20회)
        pr_items = [
            (self.client.repo_full_name_from_url(raw["repository_url"]), raw["number"])
            for raw in pr_raws
        ]
        pr_data = self.client.get_pr_reviews_batch(pr_items)

        reviews = []
        for (full_name, pr_number), info in pr_data.items():
            # 자기 PR에 자기가 리뷰한 경우 제외 (self-review)
            if info.get("pr_author") == username:
                continue
            commit_dates = info.get("commit_dates", [])
            for review in info.get("reviews", []):
                if not review:
                    continue
                if (review.get("author") or {}).get("login") != username:
                    continue
                submitted_at = review.get("submittedAt", "")
                led = any(d > submitted_at for d in commit_dates)
                reviews.append(CodeReview(
                    pr_number=pr_number,
                    repo_full_name=full_name,
                    body=review.get("body") or "",
                    led_to_change=led,
                ))
        return reviews

    def _collect_maintainer_reviews(self, username: str, received_prs: List[PullRequest]) -> List[CodeReview]:
        # GraphQL 배치로 reviews + commits 한 번에 조회 (REST 2N회 → GraphQL ~N/10회)
        pr_items = [(pr.repo_full_name, pr.number) for pr in received_prs]
        pr_data = self.client.get_pr_reviews_batch(pr_items)

        reviews = []
        for (full_name, pr_number), info in pr_data.items():
            # 자기 repo에 자기가 올린 PR은 received_prs 필터에서 이미 제외되지만
            # GraphQL 응답에 pr_author가 있으면 한 번 더 검사
            if info.get("pr_author") == username:
                continue
            commit_dates = info.get("commit_dates", [])
            for review in info.get("reviews", []):
                if not review:
                    continue
                if (review.get("author") or {}).get("login") != username:
                    continue
                submitted_at = review.get("submittedAt", "")
                led = any(d > submitted_at for d in commit_dates)
                reviews.append(CodeReview(
                    pr_number=pr_number,
                    repo_full_name=full_name,
                    body=review.get("body") or "",
                    led_to_change=led,
                ))
        return reviews

    # -------------------------------------------------------------------------
    # 최상위 수집 — Phase 1: 5개 독립 수집기 동시 실행
    #                Phase 2: received_prs 필요한 maintainer_reviews
    # -------------------------------------------------------------------------

    def collect(self, username: str) -> GitHubData:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            f_repos = pool.submit(self._collect_repos_graphql, username)
            f_prs = pool.submit(self._collect_prs, username)
            f_issues = pool.submit(self._collect_issues, username)
            f_commits = pool.submit(self._collect_commits, username)
            f_reviews = pool.submit(self._collect_reviews, username)

            owned_repos, languages, releases = f_repos.result()
            contributed_prs, received_prs = f_prs.result()
            contributed_issues, received_issues = f_issues.result()
            contributed_commits = f_commits.result()
            contributed_reviews = f_reviews.result()

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
