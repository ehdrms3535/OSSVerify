import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from ossverify.collector.github_collector import ActivityRatio, GitHubData


@dataclass
class ContributorScore:
    pr_merge_rate: float
    review_quality: float
    maintainer_approval: float
    project_scale: float
    contribution_consistency: float
    issue_resolution_rate: float

    def calculate(self) -> float:
        return (
            self.pr_merge_rate * 0.35
            + self.review_quality * 0.25
            + self.maintainer_approval * 0.15
            + self.project_scale * 0.10
            + self.contribution_consistency * 0.10
            + self.issue_resolution_rate * 0.05
        )


@dataclass
class MaintainerScore:
    adoption_rate: float
    community_activity: float
    review_quality: float
    issue_response_speed: float
    release_consistency: float
    documentation_level: float

    def calculate(self) -> float:
        return (
            self.adoption_rate * 0.30
            + self.community_activity * 0.25
            + self.review_quality * 0.20
            + self.issue_response_speed * 0.10
            + self.release_consistency * 0.10
            + self.documentation_level * 0.05
        )


def calculate_final_influence(
    contributor_score: float,
    maintainer_score: float,
    activity_ratio: ActivityRatio,
) -> float:
    return (
        contributor_score * activity_ratio.contributor_ratio
        + maintainer_score * activity_ratio.maintainer_ratio
    )


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    # GitHub returns "...Z" (search/issues) and "...000-08:00" (search/commits) for timestamps
    if not value:
        return None
    value = re.sub(r"\.\d+", "", value.strip())
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def _ratio_score(matched: int, total: int) -> float:
    if total == 0:
        return 0.0
    return matched / total * 100


def _log_scale(value: float, cap: float) -> float:
    if value <= 0:
        return 0.0
    return min(math.log10(value + 1) / math.log10(cap + 1) * 100, 100.0)


def _date_spread_score(dates: List[Optional[datetime]], full_score_days: int, full_score_months: int) -> float:
    parsed = [d for d in dates if d is not None]
    if len(parsed) < 2:
        return 0.0
    span_days = (max(parsed) - min(parsed)).days
    distinct_months = len({(d.year, d.month) for d in parsed})
    span_score = min(span_days / full_score_days, 1.0) * 100
    spread_score = min(distinct_months / full_score_months, 1.0) * 100
    return (span_score + spread_score) / 2


class InfluenceAnalyzer:
    def analyze_contributor(self, data: GitHubData) -> ContributorScore:
        prs = data.contributed_prs
        reviews = data.contributed_reviews
        issues = data.contributed_issues
        commits = data.contributed_commits

        avg_stars = sum(pr.repo_stars for pr in prs) / len(prs) if prs else 0
        contribution_dates = [_parse_dt(pr.created_at) for pr in prs] + [_parse_dt(c.date) for c in commits]

        return ContributorScore(
            pr_merge_rate=_ratio_score(sum(1 for pr in prs if pr.merged), len(prs)),
            review_quality=_ratio_score(sum(1 for r in reviews if r.led_to_change), len(reviews)),
            maintainer_approval=_ratio_score(sum(1 for pr in prs if pr.approved), len(prs)),
            project_scale=_log_scale(avg_stars, cap=100_000),
            contribution_consistency=_date_spread_score(contribution_dates, full_score_days=730, full_score_months=24),
            issue_resolution_rate=_ratio_score(sum(1 for i in issues if i.state == "closed"), len(issues)),
        )

    def analyze_maintainer(self, data: GitHubData) -> MaintainerScore:
        repos = data.owned_repos
        received_prs = data.received_prs
        received_issues = data.received_issues
        maintainer_reviews = data.maintainer_reviews
        releases = data.releases

        total_stars = sum(r.stars for r in repos)
        total_forks = sum(r.forks for r in repos)
        external_contributors = {pr.author for pr in received_prs} | {i.author for i in received_issues}

        response_days = []
        for issue in received_issues:
            opened, closed = _parse_dt(issue.created_at), _parse_dt(issue.closed_at)
            if opened and closed:
                response_days.append((closed - opened).total_seconds() / 86400)
        avg_response_days = sum(response_days) / len(response_days) if response_days else None

        if repos:
            documentation_level = (
                sum(1 for r in repos if r.has_readme) / len(repos) * 50
                + sum(1 for r in repos if r.has_contributing_guide) / len(repos) * 50
            )
        else:
            documentation_level = 0.0

        return MaintainerScore(
            adoption_rate=_log_scale(total_stars + total_forks * 0.5, cap=200_000),
            community_activity=_log_scale(len(external_contributors), cap=200),
            review_quality=_ratio_score(sum(1 for r in maintainer_reviews if r.led_to_change), len(maintainer_reviews)),
            issue_response_speed=0.0 if avg_response_days is None else max(0.0, 100 - _log_scale(avg_response_days, cap=90)),
            release_consistency=_date_spread_score(
                [_parse_dt(r.published_at) for r in releases], full_score_days=365, full_score_months=12
            ),
            documentation_level=documentation_level,
        )

    def analyze(self, data: GitHubData) -> Tuple[ContributorScore, MaintainerScore, float]:
        contributor_score = self.analyze_contributor(data)
        maintainer_score = self.analyze_maintainer(data)
        final_influence = calculate_final_influence(
            contributor_score.calculate(), maintainer_score.calculate(), data.activity_ratio
        )
        return contributor_score, maintainer_score, final_influence
