from dataclasses import dataclass, field
from typing import List

from ossverify.analyzer.domain_analyzer import Domain
from ossverify.analyzer.influence_analyzer import ContributorScore, MaintainerScore


@dataclass
class ExplanationInput:
    domain: Domain
    score: float
    contributor_data: ContributorScore
    maintainer_data: MaintainerScore
    top_projects: List[str] = field(default_factory=list)
    top_skills: List[str] = field(default_factory=list)


@dataclass
class ExplanationOutput:
    summary: str
    reasons: List[str] = field(default_factory=list)


class ExplanationGenerator:
    """LLM API를 활용해 분석 결과를 자연어 평가 근거로 변환한다."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def generate(self, explanation_input: ExplanationInput) -> ExplanationOutput:
        raise NotImplementedError
