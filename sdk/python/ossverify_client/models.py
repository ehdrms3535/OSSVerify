import dataclasses
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _from_dict(cls, data: dict):
    """dataclass 필드에 있는 키만 골라 인스턴스를 생성한다."""
    keys = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in data.items() if k in keys})


@dataclass
class ContributorScore:
    total: float
    pr_merge_rate: float
    review_quality: Optional[float]
    maintainer_approval: float
    project_scale: float
    contribution_consistency: float
    issue_resolution_rate: float

    @classmethod
    def from_dict(cls, data: dict) -> "ContributorScore":
        return _from_dict(cls, data)


@dataclass
class MaintainerScore:
    total: float
    adoption_rate: float
    community_activity: float
    review_quality: Optional[float]
    issue_response_speed: float
    release_consistency: float
    documentation_level: float

    @classmethod
    def from_dict(cls, data: dict) -> "MaintainerScore":
        return _from_dict(cls, data)


@dataclass
class GraphCentrality:
    pagerank_score: float
    gnn_score: float
    combined: float

    @classmethod
    def from_dict(cls, data: dict) -> "GraphCentrality":
        return _from_dict(cls, data)


@dataclass
class AnalysisResult:
    github_username: str
    overall_score: float
    primary_domain: Optional[str]
    secondary_domain: Optional[str]
    top_skills: List[str]
    influence_level: str
    activity_level: str
    domain_scores: Dict[str, float]
    contributor_score: ContributorScore
    maintainer_score: MaintainerScore
    graph_centrality: GraphCentrality
    activity_ratio: Dict[str, float]
    explanation: Dict[str, Any]
    analyzed_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisResult":
        return cls(
            github_username=data["github_username"],
            overall_score=data["overall_score"],
            primary_domain=data.get("primary_domain"),
            secondary_domain=data.get("secondary_domain"),
            top_skills=data.get("top_skills", []),
            influence_level=data.get("influence_level", ""),
            activity_level=data.get("activity_level", ""),
            domain_scores=data.get("domain_scores", {}),
            contributor_score=ContributorScore.from_dict(data.get("contributor_score", {})),
            maintainer_score=MaintainerScore.from_dict(data.get("maintainer_score", {})),
            graph_centrality=GraphCentrality.from_dict(data.get("graph_centrality", {})),
            activity_ratio=data.get("activity_ratio", {}),
            explanation=data.get("explanation", {}),
            analyzed_at=data.get("analyzed_at", ""),
        )


@dataclass
class VerifiableCredential:
    credential_id: str
    issuer: str
    document: Dict[str, Any]
    blockchain_tx: Optional[str]
    issued_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "VerifiableCredential":
        return _from_dict(cls, data)


@dataclass
class VerificationResult:
    credential_id: str
    is_valid: bool
    is_tampered: bool
    is_on_chain: bool
    issuer: str
    issued_at: str
    credential_subject: Dict[str, Any]
    blockchain_tx: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "VerificationResult":
        return _from_dict(cls, data)


@dataclass
class AnchorResult:
    credential_id: str
    blockchain_tx: str
    is_on_chain: bool

    @classmethod
    def from_dict(cls, data: dict) -> "AnchorResult":
        return _from_dict(cls, data)
