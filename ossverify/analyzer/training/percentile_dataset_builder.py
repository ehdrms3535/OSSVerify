"""
GitHub 유저 데이터 수집 스크립트 — 백분위 테이블 구축용

사용법:
    python -m ossverify.analyzer.training.percentile_dataset_builder
    python -m ossverify.analyzer.training.percentile_dataset_builder --max-per-domain 100
"""

import argparse
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

OUTPUT_PATH = Path("ossverify_data/percentile_dataset.json")
OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# 도메인별 검색 쿼리 — 언어 + 최소 활동 기준
# followers:10..1000 → 너무 유명하거나 비활성 유저 제외
_DOMAIN_QUERIES: Dict[str, List[str]] = {
    "Backend": [
        "language:java followers:10..500 repos:5..100",
        "language:python followers:10..500 repos:5..100",
        "language:go followers:10..500 repos:5..100",
        "language:kotlin followers:10..500 repos:5..100",
    ],
    "Frontend": [
        "language:javascript followers:10..500 repos:5..100",
        "language:typescript followers:10..500 repos:5..100",
    ],
    "AI/ML": [
        "language:python followers:20..500 repos:3..80",
    ],
    "DevOps": [
        "language:shell followers:10..300 repos:5..80",
        "language:go followers:10..300 repos:5..80",
    ],
    "Blockchain": [
        "language:solidity followers:5..300 repos:3..60",
        "language:rust followers:10..300 repos:5..80",
    ],
    "Cloud": [
        "language:go followers:10..300 repos:5..80",
        "language:python followers:10..300 repos:5..80",
    ],
    "Security": [
        "language:python followers:10..300 repos:5..80",
        "language:c followers:10..300 repos:5..80",
    ],
    "Mobile": [
        "language:swift followers:10..300 repos:5..80",
        "language:kotlin followers:10..300 repos:5..80",
        "language:dart followers:10..300 repos:5..80",
    ],
}


def _search_users(token: str, query: str, per_page: int = 30, max_pages: int = 3) -> List[str]:
    """GitHub user search API로 사용자명 목록 반환."""
    import requests as _req

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    logins: List[str] = []
    for page in range(1, max_pages + 1):
        try:
            resp = _req.get(
                "https://api.github.com/search/users",
                headers=headers,
                params={"q": query, "per_page": per_page, "page": page, "sort": "repositories"},
                timeout=20,
            )
            if resp.status_code == 422:
                log.warning("검색 쿼리 오류 (422): %s", query)
                break
            if resp.status_code in (403, 429):
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset - time.time(), 1)
                log.info("Rate limit — %.0f초 대기", wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                break
            items = resp.json().get("items", [])
            logins.extend(item["login"] for item in items)
            if len(items) < per_page:
                break
            time.sleep(2)  # search API 부하 방지
        except Exception as e:
            log.warning("검색 오류: %s", e)
            break
    return logins


def _analyze_user(username: str, token: str) -> Optional[dict]:
    """OSSVerify 분석 실행 후 핵심 지표만 추출."""
    from ossverify.analyzer.domain_analyzer import DomainAnalyzer
    from ossverify.analyzer.graph_analyzer import GraphAnalyzer
    from ossverify.analyzer.influence_analyzer import InfluenceAnalyzer
    from ossverify.analyzer.score_calculator import ScoreCalculator, ScoreFeatures
    from ossverify.collector.github_collector import GitHubCollector

    try:
        data = GitHubCollector(
            github_token=token, max_search_pages=2, max_repo_pages=2
        ).collect(username)

        if not data.languages:
            return None

        contributor_score, maintainer_score, final_influence = InfluenceAnalyzer().analyze(data)
        graph_centrality = GraphAnalyzer().calculate_centrality(data)
        combined_centrality = (graph_centrality.pagerank_score + graph_centrality.gnn_score) / 2

        total_activity = (
            len(data.contributed_prs) + len(data.contributed_reviews)
            + len(data.contributed_issues) + len(data.contributed_commits)
            + len(data.received_prs) + len(data.received_issues)
            + len(data.maintainer_reviews)
        )

        # 도메인 분류
        domain_scores: dict = {}
        primary_domain = "Backend"
        try:
            domain_analyzer = DomainAnalyzer()
            text = " ".join([
                r.description for r in data.owned_repos if r.description
            ] + [c.message for c in data.contributed_commits[:50]])
            result = domain_analyzer.infer(text)
            ranked = sorted(result.domains.items(), key=lambda x: x[1], reverse=True)
            domain_scores = {d.value: round(s * 100, 1) for d, s in result.domains.items()}
            if ranked:
                primary_domain = ranked[0][0].value
        except Exception:
            pass

        final_score = ScoreCalculator().calculate(ScoreFeatures(
            influence_score=final_influence,
            domain_scores=domain_scores,
            graph_centrality=combined_centrality,
            activity_ratio=data.activity_ratio,
            total_activity_count=total_activity,
        ))

        top_lang = max(data.languages, key=data.languages.get) if data.languages else ""

        return {
            "username": username,
            "primary_domain": primary_domain,
            "top_language": top_lang,
            "overall_score": round(final_score.overall_score, 2),
            "influence_score": round(final_influence, 2),
            "contributor_total": round(contributor_score.calculate(), 2),
            "maintainer_total": round(maintainer_score.calculate(), 2),
            "graph_centrality": round(combined_centrality, 4),
            "total_activity": total_activity,
            "repo_count": len(data.owned_repos),
            "pr_count": len(data.contributed_prs),
            "commit_count": len(data.contributed_commits),
            "domain_scores": domain_scores,
            "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    except Exception as e:
        log.debug("분석 실패 (%s): %s", username, e)
        return None


def build_dataset(max_per_domain: int = 80, token: Optional[str] = None) -> None:
    token = token or os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN이 없습니다.")

    # 기존 데이터 로드 (재시작 가능)
    existing: List[dict] = []
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    done_users = {r["username"].lower() for r in existing}
    log.info("기존 수집 데이터: %d명", len(existing))

    results = list(existing)
    domain_counts: Dict[str, int] = {}
    for r in existing:
        d = r.get("primary_domain", "Backend")
        domain_counts[d] = domain_counts.get(d, 0) + 1

    for domain, queries in _DOMAIN_QUERIES.items():
        current = domain_counts.get(domain, 0)
        if current >= max_per_domain:
            log.info("[%s] 이미 %d명 수집 완료, 건너뜀", domain, current)
            continue

        need = max_per_domain - current
        log.info("[%s] %d명 추가 수집 시작", domain, need)

        candidates: List[str] = []
        for query in queries:
            logins = _search_users(token, query, per_page=30, max_pages=3)
            candidates.extend(l for l in logins if l.lower() not in done_users)
            if len(candidates) >= need * 3:
                break
            time.sleep(3)

        added = 0
        for username in candidates:
            if added >= need:
                break
            if username.lower() in done_users:
                continue

            log.info("[%s] 분석 중: %s (%d/%d)", domain, username, added + 1, need)
            record = _analyze_user(username, token)
            done_users.add(username.lower())

            if record:
                results.append(record)
                added += 1
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

            # 중간 저장 (5명마다)
            if len(results) % 5 == 0:
                _save(results)

            time.sleep(1)

        log.info("[%s] 완료: %d명 추가", domain, added)

    _save(results)
    log.info("전체 수집 완료: %d명", len(results))
    _print_summary(results)


def _save(results: List[dict]) -> None:
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def _print_summary(results: List[dict]) -> None:
    from collections import Counter
    counts = Counter(r.get("primary_domain", "?") for r in results)
    print("\n=== 수집 요약 ===")
    for domain, count in sorted(counts.items()):
        scores = [r["overall_score"] for r in results if r.get("primary_domain") == domain]
        avg = sum(scores) / len(scores) if scores else 0
        print(f"  {domain:12s}: {count:4d}명  평균 점수 {avg:.1f}")
    print(f"  {'합계':12s}: {len(results):4d}명")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OSSVerify 백분위 데이터셋 수집")
    parser.add_argument("--max-per-domain", type=int, default=80, help="도메인별 최대 수집 인원 (기본: 80)")
    parser.add_argument("--token", type=str, default=None, help="GitHub PAT")
    args = parser.parse_args()
    build_dataset(max_per_domain=args.max_per_domain, token=args.token)
