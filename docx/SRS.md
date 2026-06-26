# OSSVerify Software Requirements Specification (SRS)

> Version 1.0 | 2026.06.26

---

## 1. 개요

### 1.1 목적
본 문서는 OSSVerify의 기능 요구사항 및 비기능 요구사항을 정의한다.

### 1.2 범위
OSSVerify는 GitHub 오픈소스 기여 데이터를 AI로 분석하여 개발자의 실질적 기여 영향력과 전문 분야를 평가하고, W3C DID 기반 Verifiable Credential을 발급하는 오픈소스 SDK이다.

### 1.3 용어 정의

| 용어 | 정의 |
|------|------|
| VC | Verifiable Credential — W3C 표준 기반 검증 가능한 자격증명 |
| DID | Decentralized Identifier — 탈중앙화 식별자 |
| did:key | 로컬 키 쌍 기반 DID 메서드 |
| Maintainer | 오픈소스 프로젝트를 직접 운영하는 개발자 |
| Contributor | 타인의 오픈소스 프로젝트에 기여하는 개발자 |
| Explainable AI | 분석 결과와 함께 평가 근거를 제시하는 AI |
| PR | Pull Request |

---

## 2. 전체 시스템 개요

### 2.1 시스템 구성

```
GitHub API
    ↓
OSSVerify Core (Python)
├── 데이터 수집 모듈
├── 영향력 분석 모듈 (PageRank + GNN)
├── 전문 분야 추론 모듈 (BERT)
├── 근거 생성 모듈 (LLM)
├── 점수 산출 모듈 (XGBoost)
├── 프로필 생성 모듈
└── VC 발급/검증 모듈 (did:key + Polygon)
    ↓
FastAPI REST API
    ↓
SDK (Node.js / Python)
    ↓
데모앱
```

### 2.2 사용자 유형

| 사용자 | 설명 |
|--------|------|
| 개발자 | GitHub 계정을 분석하여 VC를 발급받는 주체 |
| 기업/서비스 | SDK를 통해 개발자 VC를 검증하는 주체 |
| SDK 사용자 | OSSVerify SDK를 자신의 서비스에 통합하는 개발자 |

---

## 3. 기능 요구사항

### 3.1 GitHub 데이터 수집

| ID | 요구사항 |
|----|----------|
| FR-01 | GitHub API를 통해 특정 사용자의 Commit 이력을 수집할 수 있어야 한다 |
| FR-02 | GitHub API를 통해 특정 사용자의 Pull Request 이력을 수집할 수 있어야 한다 |
| FR-03 | GitHub API를 통해 특정 사용자의 Issue 이력을 수집할 수 있어야 한다 |
| FR-04 | GitHub API를 통해 특정 사용자의 Code Review 이력을 수집할 수 있어야 한다 |
| FR-05 | GitHub API를 통해 특정 사용자의 Repository 정보를 수집할 수 있어야 한다 |
| FR-06 | GitHub API를 통해 특정 사용자의 사용 언어 및 기술 스택을 수집할 수 있어야 한다 |
| FR-07 | 타인 프로젝트 기여 활동과 본인 프로젝트 활동을 구분하여 수집할 수 있어야 한다 |

### 3.2 기여 영향력 분석

| ID | 요구사항 |
|----|----------|
| FR-08 | PR 머지율을 계산할 수 있어야 한다 |
| FR-09 | 코드리뷰 품질을 평가할 수 있어야 한다 |
| FR-10 | Maintainer 승인 여부를 확인할 수 있어야 한다 |
| FR-11 | 기여한 프로젝트의 규모(스타 수, 포크 수)를 반영할 수 있어야 한다 |
| FR-12 | 기여 지속성(단발성 vs 장기 기여)을 측정할 수 있어야 한다 |
| FR-13 | 이슈 해결률을 계산할 수 있어야 한다 |
| FR-14 | 본인 프로젝트의 채택률(스타 수, 포크 수, 다운로드 수)을 측정할 수 있어야 한다 |
| FR-15 | 본인 프로젝트의 커뮤니티 활성도를 측정할 수 있어야 한다 |
| FR-16 | 본인 프로젝트의 이슈 응답 속도를 측정할 수 있어야 한다 |
| FR-17 | 본인 프로젝트의 릴리즈 지속성을 측정할 수 있어야 한다 |
| FR-18 | 본인 프로젝트의 문서화 수준을 평가할 수 있어야 한다 |
| FR-19 | 기여자 활동 비율과 Maintainer 활동 비율을 자동 계산하여 동적 가중치를 적용할 수 있어야 한다 |

### 3.3 전문 분야 추론

| ID | 요구사항 |
|----|----------|
| FR-20 | BERT 파인튜닝 모델로 커밋 메시지, PR 내용, 코드리뷰 텍스트를 분석할 수 있어야 한다 |
| FR-21 | Backend, Frontend, AI/ML, DevOps, Cloud, Security, Blockchain 중 전문 분야를 추론할 수 있어야 한다 |
| FR-22 | 단순 언어 사용량이 아닌 기여 맥락으로 전문 분야를 판단해야 한다 |
| FR-23 | 복수의 전문 분야를 동시에 추론할 수 있어야 한다 |

### 3.4 Explainable AI

| ID | 요구사항 |
|----|----------|
| FR-24 | 전문 분야별 점수를 0~100 사이로 산출할 수 있어야 한다 |
| FR-25 | 점수와 함께 평가 근거를 자연어로 생성할 수 있어야 한다 |
| FR-26 | 평가 근거는 구체적인 기여 활동(PR 수, 리뷰 수 등)을 포함해야 한다 |

### 3.5 Professional Profile 생성

| ID | 요구사항 |
|----|----------|
| FR-27 | 전문 분야, 주요 기술, 기여 영향력, 활동성을 포함한 프로필을 생성할 수 있어야 한다 |
| FR-28 | 프로필은 JSON 형태로 반환되어야 한다 |

### 3.6 VC 발급

| ID | 요구사항 |
|----|----------|
| FR-29 | did:key 방식으로 DID를 생성할 수 있어야 한다 |
| FR-30 | W3C DID 표준 기반 Verifiable Credential을 발급할 수 있어야 한다 |
| FR-31 | 발급된 VC의 해시값을 Polygon 테스트넷에 저장할 수 있어야 한다 |
| FR-32 | VC에는 전문 분야, 점수, 평가 근거, 발급 일시가 포함되어야 한다 |

### 3.7 VC 검증

| ID | 요구사항 |
|----|----------|
| FR-33 | credential ID로 VC의 진위 여부를 확인할 수 있어야 한다 |
| FR-34 | Polygon 테스트넷의 해시값과 비교하여 위변조 여부를 확인할 수 있어야 한다 |
| FR-35 | 검증 결과를 JSON 형태로 반환해야 한다 |

### 3.8 SDK 제공

| ID | 요구사항 |
|----|----------|
| FR-36 | Python SDK를 제공해야 한다 |
| FR-37 | Node.js SDK를 제공해야 한다 |
| FR-38 | SDK는 analyzeDeveloper(), getProfessionalProfile(), issueCredential(), verifyCredential() API를 제공해야 한다 |
| FR-39 | SDK는 패키지 매니저(pip, npm)를 통해 설치할 수 있어야 한다 |

---

## 4. 비기능 요구사항

### 4.1 성능

| ID | 요구사항 |
|----|----------|
| NFR-01 | analyzeDeveloper() 응답 시간은 30초 이내여야 한다 |
| NFR-02 | verifyCredential() 응답 시간은 3초 이내여야 한다 |
| NFR-03 | GitHub API Rate Limit을 초과하지 않도록 요청을 제어해야 한다 |

### 4.2 신뢰성

| ID | 요구사항 |
|----|----------|
| NFR-04 | VC 해시값은 Polygon 테스트넷에 영구 저장되어야 한다 |
| NFR-05 | 블록체인 저장 실패 시 재시도 로직이 있어야 한다 |

### 4.3 보안

| ID | 요구사항 |
|----|----------|
| NFR-06 | GitHub API 토큰은 외부에 노출되지 않아야 한다 |
| NFR-07 | did:key 개인키는 서버에 저장하지 않아야 한다 |
| NFR-08 | VC에는 개인정보가 최소한으로 포함되어야 한다 |

### 4.4 호환성

| ID | 요구사항 |
|----|----------|
| NFR-09 | W3C DID Core 1.0 표준을 준수해야 한다 |
| NFR-10 | W3C Verifiable Credentials Data Model 1.1 표준을 준수해야 한다 |
| NFR-11 | Python 3.10 이상에서 동작해야 한다 |
| NFR-12 | Node.js 18 이상에서 동작해야 한다 |

### 4.5 유지보수성

| ID | 요구사항 |
|----|----------|
| NFR-13 | 가중치는 설정 파일로 분리되어 코드 수정 없이 변경 가능해야 한다 |
| NFR-14 | 각 모듈은 독립적으로 테스트 가능해야 한다 |
| NFR-15 | API 문서는 자동 생성(FastAPI Swagger)으로 제공되어야 한다 |

---

## 5. 시스템 제약사항

| 항목 | 내용 |
|------|------|
| GitHub API | Public Repository만 분석 가능 (Private은 토큰 필요) |
| 블록체인 | Polygon 테스트넷 사용 (메인넷 아님) |
| 분석 대상 | GitHub 계정만 지원 (GitLab, Bitbucket 미지원) |
| 언어 | SDK는 Python / Node.js만 제공 |

---

## 6. 향후 확장 가능성

- GitLab, Bitbucket 지원
- did:ethr 마이그레이션 (Polygon 메인넷)
- 실시간 모니터링 및 VC 자동 갱신
- 기업용 대시보드 제공