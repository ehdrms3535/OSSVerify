"""영향력 점수 계산 — _weighted_sum, review_quality null 처리."""
import pytest

from ossverify.analyzer.influence_analyzer import (
    ContributorScore,
    MaintainerScore,
    _weighted_sum,
    calculate_final_influence,
)
from ossverify.collector.github_collector import ActivityRatio


# ── _weighted_sum ─────────────────────────────────────────────────────────

def test_weighted_sum_equal_weights():
    assert _weighted_sum([(100.0, 0.5), (0.0, 0.5)]) == 50.0

def test_weighted_sum_normalizes_over_1():
    # 가중치 합이 1이 아니어도 정규화
    result = _weighted_sum([(80.0, 2.0), (60.0, 2.0)])
    assert result == 70.0

def test_weighted_sum_single_term():
    assert _weighted_sum([(75.0, 0.35)]) == 75.0

def test_weighted_sum_empty():
    assert _weighted_sum([]) == 0.0

def test_weighted_sum_zero_weight():
    assert _weighted_sum([(100.0, 0.0)]) == 0.0


# ── ContributorScore ──────────────────────────────────────────────────────

def test_contributor_score_with_review():
    score = ContributorScore(
        pr_merge_rate=80.0, review_quality=90.0, maintainer_approval=70.0,
        project_scale=60.0, contribution_consistency=50.0, issue_resolution_rate=40.0,
    )
    result = score.calculate()
    assert 0 < result < 100

def test_contributor_score_null_review_uniform_equal():
    """모든 항목이 동점이면 review_quality 유무에 관계없이 결과가 동일하다."""
    with_review = ContributorScore(
        pr_merge_rate=80.0, review_quality=80.0, maintainer_approval=80.0,
        project_scale=80.0, contribution_consistency=80.0, issue_resolution_rate=80.0,
    )
    no_review = ContributorScore(
        pr_merge_rate=80.0, review_quality=None, maintainer_approval=80.0,
        project_scale=80.0, contribution_consistency=80.0, issue_resolution_rate=80.0,
    )
    assert abs(with_review.calculate() - no_review.calculate()) < 0.001

def test_contributor_score_null_review_raises_low_review():
    """리뷰 점수가 낮을 때 null이면 가중치 재분배로 점수가 더 높아야 한다."""
    low = ContributorScore(
        pr_merge_rate=90.0, review_quality=10.0, maintainer_approval=90.0,
        project_scale=90.0, contribution_consistency=90.0, issue_resolution_rate=90.0,
    )
    no_review = ContributorScore(
        pr_merge_rate=90.0, review_quality=None, maintainer_approval=90.0,
        project_scale=90.0, contribution_consistency=90.0, issue_resolution_rate=90.0,
    )
    assert no_review.calculate() > low.calculate()

def test_contributor_score_perfect():
    score = ContributorScore(
        pr_merge_rate=100.0, review_quality=100.0, maintainer_approval=100.0,
        project_scale=100.0, contribution_consistency=100.0, issue_resolution_rate=100.0,
    )
    assert score.calculate() == pytest.approx(100.0)

def test_contributor_score_zero():
    score = ContributorScore(
        pr_merge_rate=0.0, review_quality=0.0, maintainer_approval=0.0,
        project_scale=0.0, contribution_consistency=0.0, issue_resolution_rate=0.0,
    )
    assert score.calculate() == pytest.approx(0.0)


# ── MaintainerScore ───────────────────────────────────────────────────────

def test_maintainer_score_with_review():
    score = MaintainerScore(
        adoption_rate=80.0, community_activity=70.0, review_quality=60.0,
        issue_response_speed=50.0, release_consistency=40.0, documentation_level=30.0,
    )
    result = score.calculate()
    assert 0 < result < 100

def test_maintainer_score_null_review():
    score = MaintainerScore(
        adoption_rate=70.0, community_activity=60.0, review_quality=None,
        issue_response_speed=50.0, release_consistency=40.0, documentation_level=30.0,
    )
    result = score.calculate()
    assert 0 < result < 100

def test_maintainer_score_null_review_uniform_equal():
    with_review = MaintainerScore(
        adoption_rate=70.0, community_activity=70.0, review_quality=70.0,
        issue_response_speed=70.0, release_consistency=70.0, documentation_level=70.0,
    )
    no_review = MaintainerScore(
        adoption_rate=70.0, community_activity=70.0, review_quality=None,
        issue_response_speed=70.0, release_consistency=70.0, documentation_level=70.0,
    )
    assert abs(with_review.calculate() - no_review.calculate()) < 0.001


# ── calculate_final_influence ─────────────────────────────────────────────

def test_final_influence_contributor_only():
    ratio = ActivityRatio(contributor_ratio=1.0, maintainer_ratio=0.0)
    assert calculate_final_influence(80.0, 60.0, ratio) == pytest.approx(80.0)

def test_final_influence_maintainer_only():
    ratio = ActivityRatio(contributor_ratio=0.0, maintainer_ratio=1.0)
    assert calculate_final_influence(80.0, 60.0, ratio) == pytest.approx(60.0)

def test_final_influence_mixed():
    ratio = ActivityRatio(contributor_ratio=0.7, maintainer_ratio=0.3)
    expected = 80.0 * 0.7 + 60.0 * 0.3
    assert calculate_final_influence(80.0, 60.0, ratio) == pytest.approx(expected)
