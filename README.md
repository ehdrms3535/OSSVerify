# OSSVerify

> AI Professional Intelligence Engine — 오픈소스 기여 영향력 분석 및 DID 검증 자격증명 발급 SDK

AI 도구가 코드 생성을 지원하는 시대, 단순 커밋 수나 GitHub 프로필만으로는 개발자의 실제 전문성을 신뢰하기 어려워지고 있습니다. OSSVerify는 오픈소스 기여 데이터를 AI로 분석하여 **실질적인 기여 영향력과 전문 분야를 평가**하고, W3C DID 기반 Verifiable Credential을 발급하는 오픈소스 SDK입니다.

---

## 핵심 차별점

| 기존 GitHub 분석 서비스 | OSSVerify |
|------------------------|-----------|
| 커밋 수 · 언어 비율 집계 | 실질적 기여 영향력 측정 |
| 점수만 제공 | 점수 + 근거 제시 (Explainable AI) |
| 웹페이지로 끝남 (위조 가능) | VC 발급 → 제3자 검증 가능 |
| SDK 미제공 | SDK로 외부 서비스 바로 연동 |

---

## 동작 흐름

```
GitHub API
    ↓
기여 데이터 수집
(Commit / PR / Issue / Code Review / 기술 스택)
    ↓
실질적 기여 영향력 분석
(기여자 역량 + Maintainer 역량 — 활동 비율 기반 동적 가중치)
    ↓
BERT 파인튜닝으로 전문 분야 추론
    ↓
Explainable AI — 평가 근거 생성
    ↓
Professional Profile 생성
    ↓
did:key 기반 Verifiable Credential 발급
    ↓
Polygon 테스트넷에 해시값 저장 (위변조 방지)
    ↓
SDK → 채용 플랫폼 / 프리랜서 플랫폼 / 인재 관리 시스템
```

---

## 주요 기능

### 기여 영향력 분석
단순 수치가 아닌 기여의 질과 영향력을 두 가지 케이스로 측정합니다.

**케이스 1 — 타인 오픈소스 프로젝트 기여자**
- PR 머지율 (35%)
- 코드리뷰 품질 (25%)
- Maintainer 승인 여부 (15%)
- 기여한 프로젝트 규모 (10%)
- 기여 지속성 (10%)
- 이슈 해결률 (5%)

**케이스 2 — 본인 오픈소스 프로젝트 Maintainer**
- 프로젝트 채택률 — 스타 수, 포크 수, 다운로드 수 (30%)
- 커뮤니티 활성도 (25%)
- PR 리뷰 품질 (20%)
- 이슈 응답 속도 (10%)
- 릴리즈 지속성 (10%)
- 문서화 수준 (5%)

### Explainable AI
점수만 주는 게 아니라 평가 근거를 함께 제시합니다.

```
Backend 91점
이유:
- Spring Boot 프로젝트 5개에 장기 기여
- REST API 관련 PR 34건 머지 완료
- Backend Code Review 51회 (코드 개선 반영률 78%)
- 2년 이상 지속 기여
```

### Professional Profile 자동 생성

```
김동근

전문 분야     Backend / Security
주요 기술     Spring · Java · Docker · MySQL
기여 영향력   ★★★★☆
활동성        높음
```

### DID 기반 VC 발급 및 검증
- did:key 기반 Verifiable Credential 발급
- Polygon 테스트넷에 해시값 저장 (위변조 방지)
- `verifyCredential()` 로 진위 · 위변조 여부 확인

---

## SDK API

```python
# 개발자 분석
result = ossverify.analyzeDeveloper("github_username")

# 프로필 조회
profile = ossverify.getProfessionalProfile("github_username")

# VC 발급
credential = ossverify.issueCredential("github_username")

# VC 검증
is_valid = ossverify.verifyCredential(credential_id)
```

---

## 기술 스택

| 구분 | 기술 |
|------|------|
| AI 분석 엔진 | Python |
| API 서버 | FastAPI |
| 전문 분야 추론 | BERT 파인튜닝 |
| 영향력 계산 | PageRank + GNN |
| 근거 생성 | LLM (API) |
| 최종 점수 산출 | XGBoost 앙상블 |
| 자격증명 | W3C DID (did:key), Verifiable Credential |
| 블록체인 | Polygon 테스트넷 |
| SDK | Node.js / Python 래퍼 |
| 데이터 수집 | GitHub API |

---

## 아키텍처

```
AI 분석 엔진 (Python)
├── GitHub 데이터 수집
├── 영향력 계산 (PageRank + GNN)
├── 전문 분야 추론 (BERT)
├── 근거 생성 (LLM)
├── Profile 생성
├── VC 발급 (did:key)
└── VC 검증 (Polygon)
        ↓
FastAPI REST API
        ↓
SDK (Node.js / Python)
        ↓
데모앱
```

---

## 적용 가능 서비스

- 채용 플랫폼
- 프리랜서 플랫폼
- 개발자 커뮤니티
- 기업 인재 관리 시스템 (HRM)

---

## 기대 효과

| 대상 | 효과 |
|------|------|
| 개발자 | 실질적 기여 이력으로 전문성을 객관적으로 증명 |
| 기업 | 근거 기반 채용 의사결정 및 검증 비용 절감 |
| 오픈소스 프로젝트 | Maintainer · Contributor 전문성 확인으로 운영 신뢰성 강화 |
| 생태계 | 오픈소스 기여 문화 활성화 및 개발자 커리어 성장 지원 |

---

## 라이선스

이 프로젝트는 오픈소스로 공개됩니다.

---

> 팀명: Veritas | 참가자: 김동근 | 2026 공개SW 개발자대회