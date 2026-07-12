# OSSVerify

> **AI 기반 오픈소스 기여 영향력 분석 & DID 검증 자격증명 발급 SDK**

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![Polygon Amoy](https://img.shields.io/badge/Blockchain-Polygon%20Amoy-8247e5?logo=polygon)](https://polygon.technology)
[![W3C VC](https://img.shields.io/badge/Credential-W3C%20VC-0066cc)](https://www.w3.org/TR/vc-data-model/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

AI 도구가 코드 생성을 지원하는 시대, 단순 커밋 수나 GitHub 프로필만으로는 개발자의 실제 전문성을 신뢰하기 어려워지고 있습니다.  
OSSVerify는 오픈소스 기여 데이터를 AI로 분석하여 **실질적인 기여 영향력과 전문 분야를 평가**하고, W3C DID 기반 Verifiable Credential을 발급하는 오픈소스 SDK입니다.

---

## 핵심 차별점

| 기존 GitHub 분석 서비스 | OSSVerify |
|---|---|
| 커밋 수 · 언어 비율 집계 | 실질적 기여 영향력 측정 |
| 점수만 제공 | 점수 + 근거 제시 (Explainable AI) |
| 웹페이지로 끝남 (위조 가능) | VC 발급 → 제3자 검증 가능 |
| SDK 미제공 | SDK로 외부 서비스 바로 연동 |

---

## Quick Start

> 전제조건: Python 3.9+, GitHub Personal Access Token

```bash
# 1. 클론 및 의존성 설치
git clone https://github.com/ehdrms3535/OSSVerify
cd OSSVerify
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 에 GITHUB_TOKEN 입력 (필수)
# ANTHROPIC_API_KEY 입력 (선택 — Explainable AI)
# POLYGON_PRIVATE_KEY 입력 (선택 — 블록체인 앵커링)

# 3. 서버 실행
uvicorn ossverify.api.main:app --host 0.0.0.0 --port 8000

# 4. 데모 포털 열기
open demo/portal.html   # 또는 브라우저에서 파일로 열기
```

**서버 없이 API만 테스트:**
```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"github_username": "torvalds"}'
# → {"success": true, "data": {"job_id": "...", "status": "pending"}}

curl http://localhost:8000/api/v1/analyze/status/{job_id}
# → 분석 완료 시 결과 반환
```

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        OSSVerify System                         │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐  │
│  │  GitHub API  │───▶│           Data Collector             │  │
│  │  (GraphQL +  │    │  - Commits / PRs / Reviews / Issues  │  │
│  │   REST)      │    │  - Repository 메타데이터 + 언어 통계  │  │
│  └──────────────┘    │  - Code Search (파일 패턴 카운팅)    │  │
│                      └──────────────┬───────────────────────┘  │
│                                     │                           │
│                      ┌──────────────▼───────────────────────┐  │
│                      │          AI Analysis Engine           │  │
│                      │  ┌─────────────────────────────────┐ │  │
│                      │  │  Influence Analyzer             │ │  │
│                      │  │  (PageRank + GNN 혼합)          │ │  │
│                      │  ├─────────────────────────────────┤ │  │
│                      │  │  Domain Analyzer                │ │  │
│                      │  │  (BERT 파인튜닝 + 언어 보정)    │ │  │
│                      │  ├─────────────────────────────────┤ │  │
│                      │  │  Skill Evidence Analyzer        │ │  │
│                      │  │  (파일 패턴 + 키워드 카운팅)    │ │  │
│                      │  ├─────────────────────────────────┤ │  │
│                      │  │  Growth Analyzer (연도별)       │ │  │
│                      │  ├─────────────────────────────────┤ │  │
│                      │  │  Repository Trust (4요소)       │ │  │
│                      │  ├─────────────────────────────────┤ │  │
│                      │  │  Explanation Generator (LLM)   │ │  │
│                      │  └─────────────────────────────────┘ │  │
│                      └──────────────┬───────────────────────┘  │
│                                     │                           │
│                      ┌──────────────▼───────────────────────┐  │
│                      │       Credential Layer               │  │
│                      │  did:key → W3C VC 서명               │  │
│                      │  Polygon Amoy 해시 앵커링            │  │
│                      └──────────────┬───────────────────────┘  │
│                                     │                           │
│            ┌────────────────────────▼────────────────────┐     │
│            │          FastAPI REST API                   │     │
│            │  /analyze  /credential/issue  /verify       │     │
│            └────────────────────────┬────────────────────┘     │
│                                     │                           │
│          ┌──────────────────────────▼──────────────────────┐   │
│          │     SDK / 데모 포털 / 외부 서비스 연동           │   │
│          └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 주요 기능

### 기여 영향력 분석 (Influence Score)
단순 수치가 아닌 기여의 질과 영향력을 두 가지 케이스로 측정합니다.

**케이스 1 — 타인 오픈소스 프로젝트 기여자**
- PR 머지율 (35%) · 코드리뷰 품질 (25%) · Maintainer 승인 여부 (15%)
- 기여한 프로젝트 규모 (10%) · 기여 지속성 (10%) · 이슈 해결률 (5%)

**케이스 2 — 본인 오픈소스 프로젝트 Maintainer**
- 프로젝트 채택률 — 스타/포크/다운로드 (30%) · 커뮤니티 활성도 (25%)
- PR 리뷰 품질 (20%) · 이슈 응답 속도 (10%) · 릴리즈 지속성 (10%)

### Skill Evidence — 기술 스택 증거 제시
사용 언어를 선언하는 게 아니라 **실제 코드베이스에서 증거를 수집**합니다.

```
Python  ████████████  72.3%
  ├ Python 주요 저장소 5개
  ├ 커밋 127건 / PR 34건
  ├ requirements.txt 12개  (GitHub code search)
  ├ FastAPI PR 8건          (PR 제목 키워드 카운팅)
  └ AI/ML 커밋 23건
```

### 성장 분석 (연도별)
연도별 커밋 · PR · 코드리뷰 활동량을 그룹형 막대 차트로 시각화합니다.

### Repository 신뢰도 (4요소)
| 요소 | 만점 | 설명 |
|---|---|---|
| 외부 인기 | 25점 | Star + Fork 로그 스케일 |
| 외부 기여 | 25점 | 외부 PR + Issue 수신 |
| 유지보수 | 25점 | 릴리즈 이력 |
| 문서화 | 25점 | README · CONTRIBUTING · 설명 풍부도 |

### Explainable AI — 평가 근거 생성
```
Backend 91점
이유:
- Spring Boot 프로젝트 5개에 장기 기여
- REST API 관련 PR 34건 머지 완료
- Backend Code Review 51회 (코드 개선 반영률 78%)
- 2년 이상 지속 기여
```

### DID 기반 VC 발급 및 검증
- `did:key` 기반 Verifiable Credential 발급 (Ed25519)
- Polygon Amoy 테스트넷에 해시값 저장 (위변조 방지)
- `POST /api/v1/credential/verify` 로 진위 · 위변조 여부 확인

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/v1/analyze` | 분석 작업 시작 (비동기) |
| `GET` | `/api/v1/analyze/status/{job_id}` | 분석 결과 조회 |
| `POST` | `/api/v1/analyze/self` | 본인 인증 후 분석 |
| `POST` | `/api/v1/credential/issue` | VC 발급 |
| `POST` | `/api/v1/credential/anchor` | 블록체인 앵커링 |
| `GET` | `/api/v1/credential/verify/{id}` | VC 검증 |
| `POST` | `/api/v1/credential/verify` | 외부 VC 문서 검증 |

**Python SDK:**
```bash
pip install ./sdk/python
```
```python
from ossverify_client import OSSVerifyClient

client = OSSVerifyClient("http://localhost:8000")

# 분석 (완료까지 자동 폴링)
result = client.analyze("torvalds", github_token="ghp_...")
print(result.primary_domain, result.overall_score)

# VC 발급
vc = client.issue_credential("torvalds")
print(vc.credential_id)

# 블록체인 앵커링 (본인 인증 필요)
client.anchor_credential(vc.credential_id, github_token="ghp_...")

# VC 검증 (다른 시스템에서도 가능)
verify = client.verify_document(vc.document)
print(verify.is_valid, verify.is_on_chain)
```

**JavaScript SDK:**
```html
<script src="./sdk/js/ossverify.js"></script>
<script>
  const client = new OSSVerifyClient('http://localhost:8000');

  // 분석 (완료까지 자동 폴링)
  const result = await client.analyze('torvalds', { githubToken: 'ghp_...' });
  console.log(result.primary_domain, result.overall_score);

  // VC 발급 및 검증
  const vc = await client.issueCredential('torvalds');
  const verify = await client.verifyDocument(vc.document);
  console.log(verify.is_valid, verify.is_on_chain);
</script>
```

```javascript
// Node.js
const OSSVerifyClient = require('./sdk/js/ossverify.js');
const client = new OSSVerifyClient('http://localhost:8000');
const result = await client.analyze('torvalds');
```

---

## 기술 스택

| 구분 | 기술 |
|---|---|
| API 서버 | FastAPI + Uvicorn |
| 데이터 수집 | GitHub GraphQL API + REST API |
| 전문 분야 추론 | BERT 파인튜닝 (sentence-transformers) |
| 영향력 계산 | PageRank + GNN (NetworkX + PyTorch) |
| 근거 생성 | Claude API (Anthropic) |
| 파일 패턴 분석 | GitHub Code Search API |
| 자격증명 | W3C VC Data Model, did:key (Ed25519) |
| 블록체인 | Polygon Amoy 테스트넷 (web3.py) |

---

## Self-hosting

### 요구사항
- Python 3.9+
- GitHub Personal Access Token (`repo`, `read:user` 스코프)
- (선택) Anthropic API Key — Explainable AI 근거 생성
- (선택) Polygon Amoy 지갑 + POL 테스트 토큰 → 블록체인 앵커링

### 도메인 분류 모델 학습 (선택)
사전 학습된 모델 없이 실행하면 도메인 분류가 비활성화됩니다.

```bash
# 학습 데이터 수집
python -m ossverify.analyzer.training.dataset_builder

# BERT 파인튜닝
python -m ossverify.analyzer.training.train
```

### 블록체인 컨트랙트 배포 (선택)
```bash
# 지갑 생성 (없는 경우)
python -c "from web3 import Web3; a=Web3().eth.account.create(); print('주소:', a.address, '\n개인키:', a.key.hex())"

# OSSVerifyRegistry 컨트랙트 배포 (1회)
python -m ossverify.credential.deploy_contract
# 출력된 컨트랙트 주소를 .env의 POLYGON_CONTRACT_ADDRESS에 추가
```

> 각 인스턴스가 발급한 VC는 자체 컨트랙트 주소를 `proof.blockchainAnchor`에 포함하므로,  
> 다른 인스턴스의 검증자도 올바른 컨트랙트에서 해시를 조회할 수 있습니다.

---

## 적용 가능 서비스

- **채용 플랫폼** — 지원자 오픈소스 기여 이력 자동 검증
- **프리랜서 플랫폼** — 기술 스택 증거 기반 신뢰도 제공
- **개발자 커뮤니티** — Maintainer · Contributor 전문성 확인
- **기업 HRM** — 내부 개발자 기여 영향력 추적

---

## 라이선스

MIT License

---

> **팀명: Veritas | 참가자: 김동근 | 2026 공개SW 개발자대회**
