from dataclasses import dataclass, field
from typing import Dict

from ossverify.collector.github_collector import ActivityRatio


@dataclass
class ScoreFeatures:
    influence_score: float
    domain_scores: Dict[str, float] = field(default_factory=dict)
    graph_centrality: float = 0.0
    activity_ratio: ActivityRatio = None


@dataclass
class FinalScore:
    overall_score: float
    domain_scores: Dict[str, float] = field(default_factory=dict)
    influence_level: str = ""
    activity_level: str = ""


class ScoreCalculator:
    """XGBoost 앙상블로 각 모듈의 결과를 합산해 최종 점수를 산출한다."""

    def __init__(self, model_path: str = None):
        self.model_path = model_path

    def calculate(self, features: ScoreFeatures) -> FinalScore:
        raise NotImplementedError
