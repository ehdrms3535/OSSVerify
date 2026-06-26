# OSSVerify Detailed Design Specification (DDS)

> Version 1.0 | 2026.06.26

---

## 1. 개요

본 문서는 OSSVerify의 각 모듈별 상세 설계를 정의한다. SRS에서 정의된 요구사항을 기반으로 구체적인 구현 방향을 기술한다.

---

## 2. 전체 모듈 구조

```
ossverify/
├── collector/
│   └── github_collector.py       # GitHub 데이터 수집
├── analyzer/
│   ├── influence_analyzer.py     # 기여 영향력 분석
│   ├── domain_analyzer.py        # 전문 분야 추론 (BERT)
│   ├── graph_analyzer.py         # 관계 구조 분석 (PageRank + GNN)
│   ├── explanation_generator.py  # 근거 생성 (LLM)
│   └── score_calculator.py       # 최종 점수 산출 (XGBoost)
├── profile/
│   └── profile_builder.py        # Professional Profile 생성
├── credential/
│   ├── vc_issuer.py              # VC 발급 (did:key)
│   └── vc_verifier.py            # VC 검증 (Polygon)
├── api/
│   └── main.py                   # FastAPI REST API
├── sdk/
│   ├── python/                   # Python SDK 래퍼
│   └── nodejs/                   # Node.js SDK 래퍼
└── config/
    └── weights.yaml              # 가중치 설정 파일
```

---

## 3. 모듈별 상세 설계

### 3.1 GitHub 데이터 수집 모듈 (github_collector.py)

#### 역할
GitHub API를 통해 특정 사용자의 오픈소스 기여 데이터를 수집하고, 타인 프로젝트 기여와 본인 프로젝트 활동을 구분한다.

#### 수집 데이터

```python
class GitHubData:
    username: str

    # 타인 프로젝트 기여 (Contributor)
    contributed_prs: List[PullRequest]       # PR 목록
    contributed_reviews: List[CodeReview]    # 코드리뷰 목록
    contributed_issues: List[Issue]          # 이슈 목록
    contributed_commits: List[Commit]        # 커밋 목록

    # 본인 프로젝트 (Maintainer)
    owned_repos: List[Repository]            # 본인 Repository 목록
    received_prs: List[PullRequest]          # 받은 PR 목록
    received_issues: List[Issue]             # 받은 이슈 목록

    # 공통
    languages: Dict[str, int]               # 사용 언어 및 비율
    activity_ratio: ActivityRatio           # 기여자/Maintainer 활동 비율
```

#### 활동 비율 계산

```python
class ActivityRatio:
    contributor_ratio: float    # 타인 프로젝트 기여 비율
    maintainer_ratio: float     # 본인 프로젝트 활동 비율

# 계산 방식
total = contributor_activities + maintainer_activities
contributor_ratio = contributor_activities / total
maintainer_ratio = maintainer_activities / total
```

#### GitHub API Rate Limit 처리
- 요청 간 딜레이 적용
- Rate Limit 초과 시 자동 대기 후 재시도
- 토큰 미제공 시 Public 데이터만 수집

---

### 3.2 기여 영향력 분석 모듈 (influence_analyzer.py)

#### 역할
수집된 데이터를 기반으로 기여자 점수와 Maintainer 점수를 각각 계산한다.

#### 기여자 점수 계산

```python
class ContributorScore:
    pr_merge_rate: float          # PR 머지율 (35%)
    review_quality: float         # 코드리뷰 품질 (25%)
    maintainer_approval: float    # Maintainer 승인 여부 (15%)
    project_scale: float          # 기여 프로젝트 규모 (10%)
    contribution_consistency: float  # 기여 지속성 (10%)
    issue_resolution_rate: float  # 이슈 해결률 (5%)

def calculate(self) -> float:
    return (
        self.pr_merge_rate * 0.35 +
        self.review_quality * 0.25 +
        self.maintainer_approval * 0.15 +
        self.project_scale * 0.10 +
        self.contribution_consistency * 0.10 +
        self.issue_resolution_rate * 0.05
    )
```

#### Maintainer 점수 계산

```python
class MaintainerScore:
    adoption_rate: float          # 프로젝트 채택률 (30%)
    community_activity: float     # 커뮤니티 활성도 (25%)
    review_quality: float         # PR 리뷰 품질 (20%)
    issue_response_speed: float   # 이슈 응답 속도 (10%)
    release_consistency: float    # 릴리즈 지속성 (10%)
    documentation_level: float    # 문서화 수준 (5%)

def calculate(self) -> float:
    return (
        self.adoption_rate * 0.30 +
        self.community_activity * 0.25 +
        self.review_quality * 0.20 +
        self.issue_response_speed * 0.10 +
        self.release_consistency * 0.10 +
        self.documentation_level * 0.05
    )
```

#### 최종 영향력 점수 (동적 가중치)

```python
def calculate_final_influence(
    contributor_score: float,
    maintainer_score: float,
    activity_ratio: ActivityRatio
) -> float:
    return (
        contributor_score * activity_ratio.contributor_ratio +
        maintainer_score * activity_ratio.maintainer_ratio
    )
```

---

### 3.3 전문 분야 추론 모듈 (domain_analyzer.py)

#### 역할
BERT 파인튜닝 모델로 커밋 메시지, PR 내용, 코드리뷰 텍스트를 분석하여 전문 분야를 추론한다.

#### 지원 전문 분야

```python
class Domain(Enum):
    BACKEND = "Backend"
    FRONTEND = "Frontend"
    AI_ML = "AI/ML"
    DEVOPS = "DevOps"
    CLOUD = "Cloud"
    SECURITY = "Security"
    BLOCKCHAIN = "Blockchain"
```

#### 모델 구조

```
입력: 커밋 메시지 + PR 제목/본문 + 코드리뷰 텍스트
    ↓
BERT Tokenizer
    ↓
BERT Encoder (파인튜닝)
    ↓
Multi-label Classifier
    ↓
출력: 각 도메인별 확률값 (0~1)
```

#### 학습 데이터 구축
- GitHub API로 언어/토픽 태그가 명확한 오픈소스 프로젝트 수집
- 프로젝트 토픽 태그를 레이블로 자동 생성
- 별도 라벨링 작업 최소화

#### 출력 형태

```python
class DomainResult:
    domains: Dict[Domain, float]  # 도메인별 점수
    primary_domain: Domain        # 주 전문 분야
    secondary_domain: Domain      # 부 전문 분야 (선택)
```

---

### 3.4 관계 구조 분석 모듈 (graph_analyzer.py)

#### 역할
PageRank와 GNN으로 개발자-프로젝트 관계망에서 영향력을 계산한다.

#### 그래프 구조

```
노드: 개발자, 프로젝트
엣지:
  - 개발자 → 프로젝트: PR 기여
  - 개발자 → 개발자: 코드리뷰
  - 개발자 → 프로젝트: 이슈 제기
  - 프로젝트 → 프로젝트: 의존 관계
```

#### PageRank 적용
- 많이 기여한 프로젝트에서 기여를 받은 개발자일수록 높은 점수
- 영향력 있는 프로젝트에 기여할수록 가중치 증가

#### GNN 적용
- 관계망 내에서 개발자의 중심성(Centrality) 측정
- 직접 연결뿐 아니라 간접 연결도 반영

---

### 3.5 근거 생성 모듈 (explanation_generator.py)

#### 역할
LLM API를 활용하여 분석 결과를 자연어 평가 근거로 변환한다.

#### 입력/출력

```python
# 입력
class ExplanationInput:
    domain: Domain
    score: float
    contributor_data: ContributorScore
    maintainer_data: MaintainerScore
    top_projects: List[str]
    top_skills: List[str]

# 출력
class ExplanationOutput:
    summary: str           # 한 줄 요약
    reasons: List[str]     # 근거 목록
```

#### 출력 예시

```
Backend 91점
요약: Spring Boot 기반 백엔드 개발 전문가로 2년 이상의 지속적 기여 이력 보유

근거:
- Spring Boot 프로젝트 5개에 장기 기여
- REST API 관련 PR 34건 머지 완료
- Backend Code Review 51회 (코드 개선 반영률 78%)
- 2년 이상 지속 기여
```

---

### 3.6 점수 산출 모듈 (score_calculator.py)

#### 역할
XGBoost 앙상블로 각 모듈의 결과를 합산하여 최종 점수를 산출한다.

#### 입력 피처

```python
class ScoreFeatures:
    influence_score: float        # 영향력 점수
    domain_scores: Dict[str, float]  # 도메인별 점수
    graph_centrality: float       # 그래프 중심성
    activity_ratio: ActivityRatio # 활동 비율
```

#### 출력

```python
class FinalScore:
    overall_score: float          # 종합 점수 (0~100)
    domain_scores: Dict[str, float]  # 도메인별 점수
    influence_level: str          # 영향력 등급 (★1~5)
    activity_level: str           # 활동성 (낮음/보통/높음)
```

---

### 3.7 프로필 생성 모듈 (profile_builder.py)

#### 역할
분석 결과를 종합하여 Professional Profile을 생성한다.

#### 출력 형태

```python
class ProfessionalProfile:
    github_username: str
    primary_domain: str           # 주 전문 분야
    secondary_domain: str         # 부 전문 분야
    top_skills: List[str]         # 주요 기술
    influence_level: str          # 기여 영향력 (★1~5)
    activity_level: str           # 활동성
    overall_score: float          # 종합 점수
    domain_scores: Dict[str, float]  # 도메인별 점수
    explanations: Dict[str, ExplanationOutput]  # 도메인별 근거
    analyzed_at: datetime         # 분석 일시
```

---

### 3.8 VC 발급 모듈 (vc_issuer.py)

#### 역할
did:key 방식으로 DID를 생성하고 W3C 표준 Verifiable Credential을 발급한다.

#### VC 발급 흐름

```
분석 결과 입력
    ↓
did:key로 DID 생성 (로컬 키 쌍)
    ↓
VC 데이터 구성 (W3C VC Data Model 1.1)
    ↓
개인키로 VC 서명
    ↓
VC 해시값 계산 (SHA-256)
    ↓
Polygon 테스트넷에 해시값 저장
    ↓
VC JSON 반환
```

#### VC 구조

```json
{
  "@context": ["https://www.w3.org/2018/credentials/v1"],
  "type": ["VerifiableCredential", "DeveloperCredential"],
  "issuer": "did:key:...",
  "issuanceDate": "2026-06-26T00:00:00Z",
  "credentialSubject": {
    "id": "github:username",
    "primaryDomain": "Backend",
    "overallScore": 91,
    "domainScores": {
      "Backend": 91,
      "Security": 74
    },
    "topSkills": ["Spring", "Java", "Docker"],
    "influenceLevel": "★★★★☆",
    "explanations": { ... }
  },
  "proof": { ... }
}
```

---

### 3.9 VC 검증 모듈 (vc_verifier.py)

#### 역할
Polygon 테스트넷의 해시값과 비교하여 VC의 진위 및 위변조 여부를 확인한다.

#### 검증 흐름

```
credential_id 입력
    ↓
Polygon 테스트넷에서 해시값 조회
    ↓
VC 원본 해시값 계산
    ↓
두 해시값 비교
    ↓
서명 유효성 검증
    ↓
검증 결과 반환
```

#### 출력 형태

```python
class VerificationResult:
    is_valid: bool            # 유효 여부
    is_tampered: bool         # 위변조 여부
    issued_at: datetime       # 발급 일시
    issuer: str               # 발급자 DID
    credential_subject: dict  # 자격증명 내용
```

---

## 4. 가중치 설정 파일 (weights.yaml)

```yaml
contributor:
  pr_merge_rate: 0.35
  review_quality: 0.25
  maintainer_approval: 0.15
  project_scale: 0.10
  contribution_consistency: 0.10
  issue_resolution_rate: 0.05

maintainer:
  adoption_rate: 0.30
  community_activity: 0.25
  review_quality: 0.20
  issue_response_speed: 0.10
  release_consistency: 0.10
  documentation_level: 0.05
```

---

## 5. REST API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | /analyze | GitHub 분석 실행 |
| GET | /profile/{username} | 프로필 조회 |
| POST | /credential/issue | VC 발급 |
| GET | /credential/verify/{credential_id} | VC 검증 |

---

## 6. 데이터 흐름 요약

```
github_collector.py
    ↓ GitHubData
influence_analyzer.py + graph_analyzer.py
    ↓ InfluenceScore
domain_analyzer.py
    ↓ DomainResult
score_calculator.py
    ↓ FinalScore
explanation_generator.py
    ↓ ExplanationOutput
profile_builder.py
    ↓ ProfessionalProfile
vc_issuer.py
    ↓ VerifiableCredential
vc_verifier.py
    ↓ VerificationResult
```