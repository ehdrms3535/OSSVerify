from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

from ossverify.analyzer.explanation_generator import ExplanationOutput
from ossverify.analyzer.score_calculator import FinalScore


@dataclass
class ProfessionalProfile:
    github_username: str
    primary_domain: str
    secondary_domain: str
    top_skills: List[str]
    influence_level: str
    activity_level: str
    overall_score: float
    domain_scores: Dict[str, float] = field(default_factory=dict)
    explanations: Dict[str, ExplanationOutput] = field(default_factory=dict)
    analyzed_at: datetime = field(default_factory=datetime.utcnow)


class ProfileBuilder:
    def build(
        self,
        github_username: str,
        final_score: FinalScore,
        primary_domain: str,
        secondary_domain: str,
        top_skills: List[str],
        explanations: Dict[str, ExplanationOutput],
    ) -> ProfessionalProfile:
        return ProfessionalProfile(
            github_username=github_username,
            primary_domain=primary_domain,
            secondary_domain=secondary_domain,
            top_skills=top_skills,
            influence_level=final_score.influence_level,
            activity_level=final_score.activity_level,
            overall_score=final_score.overall_score,
            domain_scores=final_score.domain_scores,
            explanations=explanations,
        )
