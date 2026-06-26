from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class Domain(Enum):
    BACKEND = "Backend"
    FRONTEND = "Frontend"
    AI_ML = "AI/ML"
    DEVOPS = "DevOps"
    CLOUD = "Cloud"
    SECURITY = "Security"
    BLOCKCHAIN = "Blockchain"


@dataclass
class DomainResult:
    domains: Dict[Domain, float] = field(default_factory=dict)
    primary_domain: Optional[Domain] = None
    secondary_domain: Optional[Domain] = None


class DomainAnalyzer:
    """BERT 파인튜닝 모델로 커밋 메시지/PR/코드리뷰 텍스트를 분석해 전문 분야를 추론한다."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path

    def infer(self, text_corpus: str) -> DomainResult:
        raise NotImplementedError
