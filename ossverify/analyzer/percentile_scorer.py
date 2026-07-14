"""
백분위 스코어러 — 수집된 데이터셋 기반 도메인별 백분위 계산

사용법:
    # 테이블 빌드 (데이터셋 수집 후 1회 실행)
    python -m ossverify.analyzer.percentile_scorer

    # 코드에서 사용
    scorer = PercentileScorer.load()
    pct = scorer.percentile(domain="Backend", overall_score=72.5)
    # → 83.2  (상위 16.8%)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

_DATASET_PATH  = Path("ossverify_data/percentile_dataset.json")
_TABLE_PATH    = Path("ossverify_data/percentile_table.json")
_TABLE_BUNDLE  = Path("ossverify/analyzer/percentile_table.json")  # 코드와 함께 배포되는 기본 테이블

# 테이블에 포함할 지표
_METRICS = ["overall_score", "influence_score", "contributor_total",
            "maintainer_total", "graph_centrality", "total_activity"]


def build_table() -> None:
    """데이터셋에서 백분위 테이블을 계산해 JSON으로 저장한다."""
    if not _DATASET_PATH.exists():
        raise FileNotFoundError(f"데이터셋 파일이 없습니다: {_DATASET_PATH}\n"
                                "먼저 percentile_dataset_builder.py를 실행하세요.")

    with open(_DATASET_PATH, encoding="utf-8") as f:
        dataset: List[dict] = json.load(f)

    log.info("데이터셋 로드: %d명", len(dataset))

    table: Dict[str, dict] = {"_global": {}, "_meta": {}}

    # 전체 분포
    for metric in _METRICS:
        values = sorted(r[metric] for r in dataset if metric in r and r[metric] is not None)
        if values:
            table["_global"][metric] = _quantiles(values)

    table["_meta"] = {
        "total_users": len(dataset),
        "built_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
    }

    # 도메인별 분포
    domains = set(r.get("primary_domain", "") for r in dataset)
    for domain in domains:
        if not domain:
            continue
        subset = [r for r in dataset if r.get("primary_domain") == domain]
        if len(subset) < 10:
            log.warning("[%s] 데이터 부족 (%d명) — 건너뜀", domain, len(subset))
            continue
        table[domain] = {}
        for metric in _METRICS:
            values = sorted(r[metric] for r in subset if metric in r and r[metric] is not None)
            if values:
                table[domain][metric] = _quantiles(values)
        table[domain]["_count"] = len(subset)
        log.info("[%s] %d명 처리 완료", domain, len(subset))

    # 두 경로에 저장 (ossverify_data/ + 소스 번들)
    for path in (_TABLE_PATH, _TABLE_BUNDLE):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=2)
    log.info("백분위 테이블 저장 완료: %s", _TABLE_PATH)

    # 요약 출력
    _print_summary(table)


def _quantiles(sorted_values: List[float], steps: int = 100) -> List[float]:
    """백분위 0~100을 steps+1개 구간으로 나눈 분위수 리스트."""
    n = len(sorted_values)
    result = []
    for p in range(steps + 1):
        idx = min(int(p / 100 * (n - 1)), n - 1)
        result.append(round(sorted_values[idx], 4))
    return result


def _print_summary(table: dict) -> None:
    meta = table.get("_meta", {})
    print(f"\n=== 백분위 테이블 ===  (총 {meta.get('total_users', '?')}명)")
    for key, val in table.items():
        if key.startswith("_"):
            continue
        count = val.get("_count", "?")
        qs = val.get("overall_score", [])
        if qs:
            p25 = qs[25]; p50 = qs[50]; p75 = qs[75]
            print(f"  {key:12s}: {count:4}명  P25={p25:.1f}  P50={p50:.1f}  P75={p75:.1f}")


class PercentileScorer:
    """로드된 테이블로 즉시 백분위를 계산하는 클라이언트."""

    def __init__(self, table: dict) -> None:
        self._table = table

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "PercentileScorer":
        """테이블 파일 로드. 없으면 빈 테이블로 초기화 (백분위 비활성)."""
        candidates = [path, _TABLE_PATH, _TABLE_BUNDLE] if path else [_TABLE_PATH, _TABLE_BUNDLE]
        for p in candidates:
            if p and Path(p).exists():
                with open(p, encoding="utf-8") as f:
                    table = json.load(f)
                log.info("백분위 테이블 로드: %s (%d명)", p, table.get("_meta", {}).get("total_users", "?"))
                return cls(table)
        log.warning("백분위 테이블 없음 — 백분위 비활성화")
        return cls({})

    def percentile(
        self,
        domain: Optional[str],
        metric: str = "overall_score",
        value: float = 0.0,
    ) -> Optional[float]:
        """value가 해당 도메인 분포에서 몇 번째 백분위인지 반환 (0~100).

        Returns None if table is unavailable.
        """
        dist = self._table.get(domain or "", self._table.get("_global", {}))
        if not dist:
            dist = self._table.get("_global", {})
        quantiles: List[float] = dist.get(metric, [])
        if not quantiles:
            return None

        # bisect로 백분위 추정
        lo, hi = 0, len(quantiles) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if quantiles[mid] < value:
                lo = mid + 1
            else:
                hi = mid
        return round(lo, 1)

    def rank_label(self, percentile: float) -> str:
        """백분위 → 표시용 레이블."""
        if percentile >= 95:   return "상위 5%"
        if percentile >= 90:   return "상위 10%"
        if percentile >= 80:   return "상위 20%"
        if percentile >= 70:   return "상위 30%"
        if percentile >= 50:   return "상위 50%"
        return f"상위 {100 - int(percentile)}%"

    def is_available(self) -> bool:
        return bool(self._table)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build_table()
