from dataclasses import dataclass, field
from typing import Dict, Optional

from ossverify.collector.github_collector import ActivityRatio


@dataclass
class ScoreFeatures:
    influence_score: float
    domain_scores: Dict[str, float] = field(default_factory=dict)
    graph_centrality: float = 0.0
    activity_ratio: Optional[ActivityRatio] = None
    total_activity_count: int = 0


@dataclass
class FinalScore:
    overall_score: float
    domain_scores: Dict[str, float] = field(default_factory=dict)
    influence_level: str = ""
    activity_level: str = ""


def _influence_level_stars(overall_score: float) -> str:
    filled = min(max(round(overall_score / 20), 0), 5)
    return "★" * filled + "☆" * (5 - filled)


def _activity_level_label(total_activity_count: int) -> str:
    if total_activity_count >= 50:
        return "높음"
    if total_activity_count >= 10:
        return "보통"
    return "낮음"


class ScoreCalculator:
    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path

    def calculate(self, features: ScoreFeatures) -> FinalScore:
        # 가중치: influence 60%, graph_centrality 10%, domain 30%
        # graph_centrality나 domain_scores가 없으면 남은 가중치를 influence에 흡수한다.
        w_influence = 0.6
        w_graph = 0.1 if features.graph_centrality > 0 else 0.0
        w_domain = 0.3 if features.domain_scores else 0.0
        w_total = w_influence + w_graph + w_domain
        if w_total == 0:
            w_influence = 1.0
            w_total = 1.0

        domain_avg = (
            sum(features.domain_scores.values()) / len(features.domain_scores)
            if features.domain_scores
            else 0.0
        )
        overall_score = (
            features.influence_score * (w_influence / w_total)
            + features.graph_centrality * (w_graph / w_total)
            + domain_avg * (w_domain / w_total)
        )

        return FinalScore(
            overall_score=overall_score,
            domain_scores=features.domain_scores,
            influence_level=_influence_level_stars(overall_score),
            activity_level=_activity_level_label(features.total_activity_count),
        )
