from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
    analyzed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    contributor_score: Optional[Dict[str, Any]] = None
    maintainer_score: Optional[Dict[str, Any]] = None
    graph_centrality: Optional[Dict[str, Any]] = None
    activity_ratio: Optional[Dict[str, Any]] = None
    skill_evidence: Optional[List[Dict[str, Any]]] = None
    growth_data: Optional[List[Dict[str, Any]]] = None
    repo_trust: Optional[List[Dict[str, Any]]] = None
    percentile_rank: Optional[float] = None
    rank_label: Optional[str] = None


class ProfileBuilder:
    def build(
        self,
        github_username: str,
        final_score: FinalScore,
        primary_domain: str,
        secondary_domain: str,
        top_skills: List[str],
        explanations: Dict[str, ExplanationOutput],
        contributor_score: Optional[Dict[str, Any]] = None,
        maintainer_score: Optional[Dict[str, Any]] = None,
        graph_centrality: Optional[Dict[str, Any]] = None,
        activity_ratio: Optional[Dict[str, Any]] = None,
        skill_evidence: Optional[List[Dict[str, Any]]] = None,
        growth_data: Optional[List[Dict[str, Any]]] = None,
        repo_trust: Optional[List[Dict[str, Any]]] = None,
        percentile_rank: Optional[float] = None,
        rank_label: Optional[str] = None,
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
            contributor_score=contributor_score,
            maintainer_score=maintainer_score,
            graph_centrality=graph_centrality,
            activity_ratio=activity_ratio,
            skill_evidence=skill_evidence,
            growth_data=growth_data,
            repo_trust=repo_trust,
            percentile_rank=percentile_rank,
            rank_label=rank_label,
        )
