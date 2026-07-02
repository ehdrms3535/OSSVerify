import json
import os
from dataclasses import dataclass, field
from typing import List

import anthropic

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


def _build_prompt(inp: ExplanationInput) -> str:
    c = inp.contributor_data
    m = inp.maintainer_data
    projects = ", ".join(inp.top_projects) if inp.top_projects else "없음"
    skills = ", ".join(inp.top_skills) if inp.top_skills else "없음"

    return f"""당신은 오픈소스 개발자 분석 시스템입니다. 아래의 GitHub 활동 분석 데이터를 바탕으로 개발자에 대한 자연어 평가를 작성하세요.

## 분석 데이터

- 주요 도메인: {inp.domain.value}
- 종합 점수: {inp.score:.1f} / 100
- 주요 프로젝트: {projects}
- 주요 기술 스택: {skills}

### 기여자(Contributor) 점수
- PR 병합률: {c.pr_merge_rate:.2f}
- 코드 리뷰 품질: {"데이터 없음" if c.review_quality is None else f"{c.review_quality:.2f}"}
- 메인테이너 승인률: {c.maintainer_approval:.2f}
- 프로젝트 규모: {c.project_scale:.2f}
- 기여 일관성: {c.contribution_consistency:.2f}
- 이슈 해결률: {c.issue_resolution_rate:.2f}

### 메인테이너(Maintainer) 점수
- PR 채택률: {m.adoption_rate:.2f}
- 커뮤니티 활동: {m.community_activity:.2f}
- 리뷰 품질: {"데이터 없음" if m.review_quality is None else f"{m.review_quality:.2f}"}
- 이슈 응답 속도: {m.issue_response_speed:.2f}
- 릴리즈 일관성: {m.release_consistency:.2f}
- 문서화 수준: {m.documentation_level:.2f}

## 출력 형식

반드시 다음 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요:

{{
  "summary": "개발자에 대한 2-3문장 종합 평가",
  "reasons": [
    "평가 근거 1",
    "평가 근거 2",
    "평가 근거 3"
  ]
}}

summary는 개발자의 전체적인 역량과 특징을 간결하게 설명하세요.
reasons는 점수 산정 근거가 되는 구체적인 항목들을 3-5개 제시하세요."""


class ExplanationGenerator:
    """LLM API를 활용해 분석 결과를 자연어 평가 근거로 변환한다."""

    def __init__(self, llm_client=None):
        self.llm_client = llm_client or anthropic.Anthropic(
            api_key=os.environ.get("ANTHROPIC_API_KEY")
        )

    def generate(self, explanation_input: ExplanationInput) -> ExplanationOutput:
        prompt = _build_prompt(explanation_input)

        with self.llm_client.messages.stream(
            model="claude-opus-4-8",
            max_tokens=1024,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()

        raw_text = ""
        for block in message.content:
            if block.type == "text":
                raw_text = block.text
                break

        # Claude가 ```json ... ``` 코드블록으로 감싸는 경우 벗겨낸다
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()

        try:
            parsed = json.loads(text)
            return ExplanationOutput(
                summary=parsed.get("summary", ""),
                reasons=parsed.get("reasons", []),
            )
        except (json.JSONDecodeError, KeyError):
            return ExplanationOutput(summary=raw_text, reasons=[])
