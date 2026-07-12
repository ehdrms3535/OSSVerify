from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List

from ossverify.collector.github_collector import GitHubData


@dataclass
class YearlyActivity:
    year: int
    commit_count: int
    pr_count: int
    review_count: int
    total: int


def analyze_growth(data: GitHubData) -> List[YearlyActivity]:
    """연도별 GitHub 활동량을 집계한다."""
    by_year: Dict[int, Dict[str, int]] = defaultdict(
        lambda: {"commit": 0, "pr": 0, "review": 0}
    )

    for commit in data.contributed_commits:
        if commit.date and len(commit.date) >= 4:
            try:
                year = int(commit.date[:4])
                if 2010 <= year <= 2030:
                    by_year[year]["commit"] += 1
            except ValueError:
                pass

    for pr in data.contributed_prs:
        if pr.created_at and len(pr.created_at) >= 4:
            try:
                year = int(pr.created_at[:4])
                if 2010 <= year <= 2030:
                    by_year[year]["pr"] += 1
            except ValueError:
                pass

    return [
        YearlyActivity(
            year=year,
            commit_count=counts["commit"],
            pr_count=counts["pr"],
            review_count=counts["review"],
            total=counts["commit"] + counts["pr"] + counts["review"],
        )
        for year, counts in sorted(by_year.items())
    ]
