import json
import threading
import time
from typing import Dict, List, Optional, Tuple

import requests

GITHUB_API_BASE = "https://api.github.com"

# get_repos_batch: repo 조회만 하는 얕은 쿼리 → alias 20개 가능
_GRAPHQL_BATCH_SIZE = 20
# get_pr_reviews_batch: reviews + commits 중첩 쿼리 → complexity 절감을 위해 alias 10개
_GRAPHQL_PR_BATCH_SIZE = 10

# GitHub Search API rate limiter (30 req/min for authenticated users).
# 토큰 버킷: burst=10으로 일반 유저(6-8회 검색)는 대기 없이 통과,
# 대형 계정(18회+)은 초과분만 ~2초씩 대기한다.
class _SearchRateLimiter:
    def __init__(self, rate: float = 0.45, burst: int = 10):
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        # 토큰 계산만 락 안에서, sleep은 락 밖에서 수행 (락 중 sleep 방지)
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(self._burst, self._tokens + (now - self._last) * self._rate)
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            time.sleep(wait)

_SEARCH_LIMITER = _SearchRateLimiter()


class GitHubHTTPClient:
    """공통 GitHub REST/GraphQL 호출 로직: 인증, rate limit 대기, 페이지네이션, 네트워크 재시도."""

    def __init__(self, github_token: Optional[str] = None, per_page: int = 100, max_pages: int = 10):
        self.github_token = github_token
        self.per_page = per_page
        self.max_pages = max_pages
        self.session = requests.Session()

        # 병렬 스레드 수(max_workers=10)에 맞게 커넥션 풀 크기 확장
        adapter = requests.adapters.HTTPAdapter(pool_maxsize=20, pool_connections=20)
        self.session.mount("https://", adapter)

        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"
        self.session.headers.update(headers)
        self.repo_cache: Dict[str, dict] = {}
        self._repo_lock = threading.Lock()

    def request(self, method: str, url: str, max_retries: int = 5, **kwargs) -> requests.Response:
        kwargs.setdefault("timeout", 30)
        attempt = 0
        rate_limit_retries = 0
        while True:
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.exceptions.RequestException:
                attempt += 1
                if attempt > max_retries:
                    raise
                time.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code == 502:
                attempt += 1
                if attempt > max_retries:
                    return response
                time.sleep(min(2 ** attempt, 30))
                continue
            if response.status_code in (403, 429) and response.headers.get("X-RateLimit-Remaining") == "0":
                rate_limit_retries += 1
                if rate_limit_retries > 3:
                    return response
                reset_at = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
                time.sleep(max(reset_at - time.time(), 1))
                continue
            if response.status_code == 403 and "retry-after" in response.headers:
                time.sleep(int(response.headers["retry-after"]))
                continue
            return response

    def paginate(self, url: str, params: dict, items_key: Optional[str] = None, max_pages: Optional[int] = None) -> List[dict]:
        results: List[dict] = []
        params = dict(params, per_page=self.per_page)
        is_search = "/search/" in url
        for page in range(1, (max_pages or self.max_pages) + 1):
            if is_search:
                _SEARCH_LIMITER.acquire()
            response = self.request("GET", url, params=dict(params, page=page))
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

    def search_code_count(self, query: str) -> int:
        """GitHub code search로 매칭 파일 수(total_count)를 반환한다. 실패 시 0."""
        _SEARCH_LIMITER.acquire()
        try:
            resp = self.request("GET", f"{GITHUB_API_BASE}/search/code",
                                params={"q": query, "per_page": 1})
            if resp.status_code == 200:
                return resp.json().get("total_count", 0)
        except Exception:
            pass
        return 0

    def get_repo(self, full_name: str) -> dict:
        if full_name in self.repo_cache:
            return self.repo_cache[full_name]
        with self._repo_lock:
            if full_name not in self.repo_cache:
                response = self.request("GET", f"{GITHUB_API_BASE}/repos/{full_name}")
                if response.status_code == 200:
                    self.repo_cache[full_name] = response.json()
                else:
                    return {}  # 일시적 오류는 캐싱하지 않음
        return self.repo_cache.get(full_name, {})

    def get_repos_batch(self, full_names: List[str]) -> None:
        """GraphQL alias 배치로 여러 repo를 한 번에 조회해 repo_cache를 채웁니다.
        이미 캐시된 항목은 건너뜁니다. REST N회 → GraphQL ceil(N/20)회."""
        uncached = [fn for fn in full_names if fn not in self.repo_cache]
        if not uncached:
            return

        for i in range(0, len(uncached), _GRAPHQL_BATCH_SIZE):
            batch = uncached[i:i + _GRAPHQL_BATCH_SIZE]
            index_map: Dict[str, str] = {}  # alias → full_name
            field_parts: List[str] = []

            for j, full_name in enumerate(batch):
                parts = full_name.split("/", 1)
                if len(parts) != 2:
                    continue
                owner, name = parts
                alias = f"r{j}"
                index_map[alias] = full_name
                field_parts.append(
                    f'{alias}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) '
                    f'{{ nameWithOwner stargazerCount forkCount description }}'
                )

            if not field_parts:
                continue

            query = "query { rateLimit { remaining } " + " ".join(field_parts) + " }"
            try:
                data = self.graphql_raw(query, {})
            except Exception:
                continue

            for alias, full_name in index_map.items():
                repo_data = data.get(alias)
                if repo_data:
                    self.repo_cache[full_name] = {
                        "stargazers_count": repo_data.get("stargazerCount", 0),
                        "forks_count": repo_data.get("forkCount", 0),
                        "description": repo_data.get("description") or "",
                        "full_name": repo_data.get("nameWithOwner", full_name),
                    }

    def get_pr_reviews_batch(
        self,
        pr_items: List[Tuple[str, int]],
    ) -> Dict[Tuple[str, int], dict]:
        """GraphQL alias 배치로 여러 PR의 reviews + commits를 한 번에 조회.

        반환: {(full_name, pr_number): {"reviews": [...nodes...], "commit_dates": [...]}}
        REST (list_reviews + commits) 2N회 → GraphQL ceil(N/20)회.
        """
        results: Dict[Tuple[str, int], dict] = {}

        for i in range(0, len(pr_items), _GRAPHQL_PR_BATCH_SIZE):
            batch = pr_items[i:i + _GRAPHQL_PR_BATCH_SIZE]
            index_map: Dict[str, Tuple[str, int]] = {}
            field_parts: List[str] = []

            for j, (full_name, pr_number) in enumerate(batch):
                parts = full_name.split("/", 1)
                if len(parts) != 2:
                    continue
                owner, name = parts
                alias = f"r{j}"
                index_map[alias] = (full_name, pr_number)
                # reviews(first:20), commits(first:50) — 복잡도 절감
                field_parts.append(
                    f'{alias}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{'
                    f'  pullRequest(number: {pr_number}) {{'
                    f'    author {{ login }}'
                    f'    reviews(first: 20) {{ nodes {{ state author {{ login }} submittedAt body }} }}'
                    f'    commits(first: 50) {{ nodes {{ commit {{ committedDate }} }} }}'
                    f'  }}'
                    f'}}'
                )

            if not field_parts:
                continue

            query = "query { rateLimit { remaining } " + " ".join(field_parts) + " }"
            try:
                data = self.graphql_raw(query, {})
            except Exception:
                continue

            for alias, key in index_map.items():
                repo_data = data.get(alias)
                if not repo_data:
                    continue
                pr_data = repo_data.get("pullRequest")
                if not pr_data:
                    continue
                # nodes 자체가 null로 올 수 있음 (삭제된 리뷰/커밋, 접근 불가 PR)
                # dict.get(key, default)는 key가 없을 때만 default 사용 —
                # key가 있고 값이 null이면 None 반환. `or []` 로 방어.
                commit_nodes = (pr_data.get("commits") or {}).get("nodes") or []
                commit_dates = [
                    node["commit"]["committedDate"]
                    for node in commit_nodes
                    if node and node.get("commit") and node["commit"].get("committedDate")
                ]
                review_nodes = (pr_data.get("reviews") or {}).get("nodes") or []
                pr_author = (pr_data.get("author") or {}).get("login", "")
                results[key] = {
                    "reviews": [r for r in review_nodes if r],
                    "commit_dates": commit_dates,
                    "pr_author": pr_author,
                }

        return results

    def graphql(self, query: str, variables: dict) -> dict:
        """기존 동작 유지 — errors 발생 시 예외."""
        response = self.request("POST", "https://api.github.com/graphql",
                                json={"query": query, "variables": variables})
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data["data"]

    def graphql_raw(self, query: str, variables: dict) -> dict:
        """배치용 — partial errors 허용, null 필드는 호출자가 직접 처리."""
        response = self.request("POST", "https://api.github.com/graphql",
                                json={"query": query, "variables": variables})
        response.raise_for_status()
        return response.json().get("data") or {}

    @staticmethod
    def repo_full_name_from_url(repository_url: str) -> str:
        return repository_url.split("repos/")[-1]

    @staticmethod
    def repo_owner(full_name: str) -> str:
        return full_name.split("/")[0]
