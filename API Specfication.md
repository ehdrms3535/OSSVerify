# OSSVerify API Specification

> Version 2.0 | 2026.07.07

---

## 1. 개요

### 1.1 Base URL
```
http://localhost:8000/api/v1
```

### 1.2 공통 응답 형식

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

### 1.3 공통 에러 응답

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "에러 메시지"
  }
}
```

### 1.4 에러 코드

| 코드 | HTTP | 설명 |
|------|------|------|
| `NOT_FOUND` | 404 | 리소스(Job, VC, Profile)를 찾을 수 없음 |
| `GITHUB_RATE_LIMIT` | 429 | GitHub API Rate Limit 초과 |
| `ANALYSIS_FAILED` | 500 | 분석 실패 |
| `ISSUE_FAILED` | 500 | VC 발급 실패 |
| `VERIFICATION_FAILED` | 500 | VC 검증 중 오류 |
| `ALREADY_ANCHORED` | 409 | 이미 온체인에 앵커링된 VC |
| `INVALID_REQUEST` | 400 | 잘못된 요청 |

### 1.5 인증

일부 엔드포인트는 GitHub Personal Access Token을 Bearer 토큰으로 요구한다.  
토큰의 GitHub 인증 사용자와 요청 대상 사용자명이 일치해야 한다 (self-match).

```
Authorization: Bearer <github_personal_access_token>
```

| HTTP 상태 | 의미 |
|-----------|------|
| 401 | 토큰 없음 또는 인증 실패 |
| 403 | 인증 사용자 ≠ 요청 대상 사용자 |

---

## 2. 엔드포인트

---

### 2.1 개발자 분석 (비인증)

#### `POST /analyze`

GitHub 사용자의 오픈소스 기여 데이터를 수집하고 AI로 분석한다.  
분석은 비동기로 실행되며 `job_id`를 즉시 반환한다.  
결과는 `GET /analyze/status/{job_id}`로 폴링한다.

**Request**

```json
{
  "github_username": "string",
  "github_token": "string (optional)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `github_username` | string | ✅ | GitHub 사용자명 |
| `github_token` | string | ❌ | GitHub PAT (없으면 서버 토큰 사용) |

**Response `200`**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending"
  },
  "error": null
}
```

---

### 2.2 분석 결과 폴링

#### `GET /analyze/status/{job_id}`

비동기 분석 작업의 상태와 결과를 반환한다.

**Path Parameter**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `job_id` | string (UUID) | `/analyze` 응답의 `job_id` |

**Response `200` — 진행 중**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "pending",
    "data": null,
    "error": null
  },
  "error": null
}
```

**Response `200` — 완료**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "complete",
    "data": {
      "github_username": "octocat",
      "overall_score": 87.4,
      "activity_ratio": {
        "contributor_ratio": 0.7,
        "maintainer_ratio": 0.3
      },
      "contributor_score": {
        "total": 91.2,
        "pr_merge_rate": 88.0,
        "review_quality": 92.0,
        "maintainer_approval": 95.0,
        "project_scale": 87.0,
        "contribution_consistency": 90.0,
        "issue_resolution_rate": 82.0
      },
      "maintainer_score": {
        "total": 76.3,
        "adoption_rate": 82.0,
        "community_activity": 74.0,
        "review_quality": null,
        "issue_response_speed": 71.0,
        "release_consistency": 69.0,
        "documentation_level": 65.0
      },
      "domain_scores": {
        "Backend": 91.0,
        "Security": 74.0,
        "DevOps": 61.0
      },
      "primary_domain": "Backend",
      "secondary_domain": "Security",
      "top_skills": ["Python", "Java", "Docker", "MySQL"],
      "influence_level": "High",
      "activity_level": "Very Active",
      "graph_centrality": {
        "pagerank_score": 82.3,
        "gnn_score": 91.0,
        "combined": 86.65
      },
      "explanation": {
        "summary": "Spring Boot 기반 백엔드 개발 전문가로 2년 이상의 지속적 기여 이력 보유",
        "reasons": [
          "Spring Boot 프로젝트 5개에 장기 기여",
          "REST API 관련 PR 34건 머지 완료",
          "Backend Code Review 51회 (코드 개선 반영률 78%)",
          "2년 이상 지속 기여"
        ]
      },
      "analyzed_at": "2026-07-07T00:00:00Z"
    },
    "error": null
  },
  "error": null
}
```

> `review_quality` 는 리뷰 데이터가 없는 경우 `null` 을 반환한다.

**Response `200` — 실패**

```json
{
  "success": true,
  "data": {
    "job_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "failed",
    "data": null,
    "error": "GitHub user not found"
  },
  "error": null
}
```

**에러 응답 (job 없음)**

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "NOT_FOUND",
    "message": "Job '550e8400...'을 찾을 수 없습니다."
  }
}
```

---

### 2.3 개발자 분석 (본인 인증)

#### `POST /analyze/self`

GitHub 토큰으로 인증된 본인의 프로필만 분석할 수 있다.  
`Authorization` 헤더의 토큰이 GitHub 수집에도 재사용된다.

**Headers**

```
Authorization: Bearer <github_personal_access_token>
```

**Request**

```json
{
  "github_username": "string"
}
```

**Response** — `/analyze` 와 동일 (비동기 `job_id` 반환)

**에러 응답**

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "FORBIDDEN",
    "message": "인증된 사용자(alice)와 요청 대상(octocat)이 일치하지 않습니다."
  }
}
```

---

### 2.4 프로필 조회

#### `GET /profile/{github_username}`

분석 완료된 Professional Profile을 조회한다.  
분석 이력이 없으면 `404`를 반환한다 (`POST /analyze`를 먼저 호출해야 함).

**Path Parameter**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `github_username` | string | GitHub 사용자명 |

**Response `200`**

```json
{
  "success": true,
  "data": {
    "github_username": "octocat",
    "primary_domain": "Backend",
    "secondary_domain": "Security",
    "top_skills": ["Python", "Java", "Docker", "MySQL"],
    "overall_score": 87.4,
    "influence_level": "High",
    "activity_level": "Very Active",
    "domain_scores": {
      "Backend": 91.0,
      "Security": 74.0,
      "DevOps": 61.0
    },
    "explanation": {
      "primary": {
        "summary": "Spring Boot 기반 백엔드 개발 전문가",
        "reasons": [
          "REST API 관련 PR 34건 머지 완료",
          "Backend Code Review 51회"
        ]
      }
    },
    "analyzed_at": "2026-07-07T00:00:00Z"
  },
  "error": null
}
```

---

### 2.5 VC 발급

#### `POST /credential/issue`

분석 결과를 기반으로 W3C DID 기반 Verifiable Credential을 발급한다.  
서명만 수행하며 블록체인 앵커링은 하지 않는다.  
온체인 기록이 필요하면 `POST /credential/anchor`를 별도로 호출한다.

**Request**

```json
{
  "github_username": "string"
}
```

**Response `200`**

```json
{
  "success": true,
  "data": {
    "credential_id": "urn:uuid:4c865028-f439-4377-94f6-ad5a38dea84d",
    "issuer": "did:key:z6MkfwKGSfQUdTJG4Wjz4TR9QZGUysfqMwxesEwAPQgEthWv",
    "blockchain_tx": null,
    "issued_at": "2026-07-07T00:00:00Z",
    "document": {
      "@context": [
        "https://www.w3.org/2018/credentials/v1",
        "https://ossverify.io/credentials/v1"
      ],
      "type": ["VerifiableCredential", "OSSContributorCredential"],
      "id": "urn:uuid:4c865028-f439-4377-94f6-ad5a38dea84d",
      "issuer": "did:key:z6MkfwKGSfQUdTJG4Wjz4TR9QZGUysfqMwxesEwAPQgEthWv",
      "issuanceDate": "2026-07-07T00:00:00Z",
      "credentialSubject": {
        "id": "did:github:octocat",
        "githubUsername": "octocat",
        "primaryDomain": "Backend",
        "secondaryDomain": "Security",
        "overallScore": 87.4,
        "influenceLevel": "High",
        "activityLevel": "Very Active",
        "topSkills": ["Python", "Java", "Docker", "MySQL"],
        "domainScores": { "Backend": 91.0, "Security": 74.0 },
        "evaluationBasis": "Algorithmic analysis of public GitHub activity data (commits, pull requests, issues, code reviews). Scores reflect open-source contribution influence as estimated by OSSVerify's AI model.",
        "disclaimer": "This credential is an algorithmic estimate, not a formal professional certification. No liability is assumed for hiring or evaluation decisions made on the basis of this credential."
      },
      "proof": {
        "type": "Ed25519Signature2020",
        "created": "2026-07-07T00:00:00Z",
        "verificationMethod": "did:key:z6MkfwKGSfQUdTJG4Wjz4TR9QZGUysfqMwxesEwAPQgEthWv#key-1",
        "proofPurpose": "assertionMethod",
        "proofValue": "bc97f126cb9881dc7ae6462042103b6a0d64e5c6..."
      }
    }
  },
  "error": null
}
```

> `blockchain_tx` 는 앵커링 전 `null` 이다.  
> `document` 를 그대로 보관하면 나중에 `POST /credential/verify` 로 검증할 수 있다.

---

### 2.6 VC 온체인 앵커링

#### `POST /credential/anchor`

발급된 VC를 Polygon Amoy 테스트넷에 앵커링한다.  
`credentialSubject.githubUsername` 과 인증 사용자가 일치해야 한다.  
이미 앵커링된 VC에 재호출하면 `409`를 반환한다.

**Headers**

```
Authorization: Bearer <github_personal_access_token>
```

**Request**

```json
{
  "credential_id": "urn:uuid:4c865028-f439-4377-94f6-ad5a38dea84d"
}
```

**Response `200`**

```json
{
  "success": true,
  "data": {
    "credential_id": "urn:uuid:4c865028-f439-4377-94f6-ad5a38dea84d",
    "blockchain_tx": "0xabc123def456...",
    "is_on_chain": true
  },
  "error": null
}
```

**에러 응답 — 이미 앵커링됨 `409`**

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ALREADY_ANCHORED",
    "message": "이미 앵커링된 VC입니다 (tx: 0xabc123...)."
  }
}
```

---

### 2.7 VC 검증 (credential_id)

#### `GET /credential/verify/{credential_id}`

서버 내부 스토어에서 credential_id로 VC를 조회해 검증한다.  
같은 인스턴스에서 발급된 VC에 사용한다.

**Path Parameter**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `credential_id` | string | 발급된 VC ID (`urn:uuid:...`) |

**Response `200`**

```json
{
  "success": true,
  "data": {
    "credential_id": "urn:uuid:4c865028-f439-4377-94f6-ad5a38dea84d",
    "is_valid": true,
    "is_tampered": false,
    "is_on_chain": true,
    "blockchain_tx": "0xabc123def456...",
    "issuer": "did:key:z6MkfwKGSfQUdTJG4Wjz4TR9QZGUysfqMwxesEwAPQgEthWv",
    "issued_at": "2026-07-07T00:00:00Z",
    "credential_subject": {
      "githubUsername": "octocat",
      "primaryDomain": "Backend",
      "overallScore": 87.4
    }
  },
  "error": null
}
```

> `is_valid` = 서명 무결성 기준.  
> `is_on_chain` = Polygon Amoy 등록 여부 (앵커링 전이면 `false`).

---

### 2.8 VC 검증 (외부 문서)

#### `POST /credential/verify`

VC 문서를 직접 받아 검증한다.  
`issuer` 필드의 `did:key`에서 공개키를 디코딩하므로  
**다른 인스턴스가 발급한 VC도 검증 가능하다** (Model B 교차 검증).

**Request**

```json
{
  "document": { "...VC 문서 전체..." }
}
```

**Response `200`**

```json
{
  "success": true,
  "data": {
    "credential_id": "urn:uuid:4c865028-f439-4377-94f6-ad5a38dea84d",
    "is_valid": true,
    "is_tampered": false,
    "is_on_chain": false,
    "blockchain_tx": null,
    "issuer": "did:key:z6MkfwKGSfQUdTJG4Wjz4TR9QZGUysfqMwxesEwAPQgEthWv",
    "issued_at": "2026-07-07T00:00:00Z",
    "credential_subject": {
      "githubUsername": "octocat",
      "primaryDomain": "Backend",
      "overallScore": 87.4
    }
  },
  "error": null
}
```

> `is_tampered: true` 이면 문서 내용이 서명 이후 변경된 것이다.

---

## 3. 엔드포인트 요약

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `POST` | `/analyze` | ❌ | 비동기 분석 시작 |
| `GET` | `/analyze/status/{job_id}` | ❌ | 분석 결과 폴링 |
| `POST` | `/analyze/self` | ✅ Bearer | 본인 인증 분석 |
| `GET` | `/profile/{github_username}` | ❌ | 프로필 조회 |
| `POST` | `/credential/issue` | ❌ | VC 발급 (서명만) |
| `POST` | `/credential/anchor` | ✅ Bearer | 온체인 앵커링 |
| `GET` | `/credential/verify/{credential_id}` | ❌ | 내부 VC 검증 |
| `POST` | `/credential/verify` | ❌ | 외부 VC 문서 검증 |

---

## 4. 흐름 예시

### 4.1 표준 흐름 (데모 트랙 — 블록체인 없음)

```
POST /analyze  →  { job_id }
         ↓ 폴링
GET  /analyze/status/{job_id}  →  { status: "complete", data: { ... } }
         ↓
POST /credential/issue  →  { credential_id, document, blockchain_tx: null }
         ↓
GET  /credential/verify/{credential_id}  →  { is_valid: true, is_on_chain: false }
```

### 4.2 프로덕션 흐름 (블록체인 앵커링 포함)

```
POST /analyze/self  [Bearer token]  →  { job_id }
         ↓ 폴링
GET  /analyze/status/{job_id}  →  { status: "complete", data: { ... } }
         ↓
POST /credential/issue  →  { credential_id, document }
         ↓
POST /credential/anchor  [Bearer token]  →  { blockchain_tx, is_on_chain: true }
         ↓
GET  /credential/verify/{credential_id}  →  { is_valid: true, is_on_chain: true }
```

### 4.3 Model B 교차 검증 흐름

```
[인스턴스 A]  POST /credential/issue  →  VC document
         ↓ document 전달 (SDK / HTTP)
[인스턴스 B]  POST /credential/verify  { document: <A의 VC> }
         →  { is_valid: true }   ← A의 did:key 공개키 디코딩으로 검증
```

---

## 5. SDK 사용 예시

### 5.1 Python

```python
import httpx
import time

BASE = "http://localhost:8000/api/v1"

# 1. 분석 시작
resp = httpx.post(f"{BASE}/analyze", json={"github_username": "octocat"})
job_id = resp.json()["data"]["job_id"]

# 2. 결과 폴링
while True:
    resp = httpx.get(f"{BASE}/analyze/status/{job_id}")
    status = resp.json()["data"]["status"]
    if status == "complete":
        result = resp.json()["data"]["data"]
        break
    elif status == "failed":
        raise RuntimeError(resp.json()["data"]["error"])
    time.sleep(3)

print(result["overall_score"])    # 87.4
print(result["primary_domain"])   # "Backend"

# 3. VC 발급
resp = httpx.post(f"{BASE}/credential/issue", json={"github_username": "octocat"})
vc = resp.json()["data"]
credential_id = vc["credential_id"]
document = vc["document"]

# 4. 온체인 앵커링 (본인 인증 필요)
token = "github_pat_..."
resp = httpx.post(
    f"{BASE}/credential/anchor",
    json={"credential_id": credential_id},
    headers={"Authorization": f"Bearer {token}"},
)
print(resp.json()["data"]["blockchain_tx"])   # "0xabc123..."

# 5. 외부 VC 검증 (다른 인스턴스에서도 동작)
resp = httpx.post(f"{BASE}/credential/verify", json={"document": document})
print(resp.json()["data"]["is_valid"])        # True
```

### 5.2 Node.js

```javascript
const BASE = 'http://localhost:8000/api/v1';

// 1. 분석 시작
const { data: { job_id } } = await fetch(`${BASE}/analyze`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ github_username: 'octocat' }),
}).then(r => r.json());

// 2. 결과 폴링
let result;
while (true) {
  const { data: job } = await fetch(`${BASE}/analyze/status/${job_id}`).then(r => r.json());
  if (job.status === 'complete') { result = job.data; break; }
  if (job.status === 'failed') throw new Error(job.error);
  await new Promise(r => setTimeout(r, 3000));
}

console.log(result.overallScore);     // 87.4
console.log(result.primaryDomain);    // "Backend"

// 3. VC 발급
const { data: vc } = await fetch(`${BASE}/credential/issue`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ github_username: 'octocat' }),
}).then(r => r.json());

// 4. 온체인 앵커링
const token = 'github_pat_...';
await fetch(`${BASE}/credential/anchor`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
  body: JSON.stringify({ credential_id: vc.credential_id }),
});

// 5. 외부 VC 검증
const { data: verification } = await fetch(`${BASE}/credential/verify`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ document: vc.document }),
}).then(r => r.json());

console.log(verification.isValid);    // true
```

---

## 6. 성능 기준

| 엔드포인트 | 목표 응답 시간 |
|------------|---------------|
| `POST /analyze` | 1초 이내 (job 큐잉) |
| `GET /analyze/status/{job_id}` | 1초 이내 |
| 분석 완료까지 | 30~120초 (계정 규모에 따라 상이) |
| `GET /profile/{github_username}` | 1초 이내 (메모리 조회) |
| `POST /credential/issue` | 3초 이내 |
| `POST /credential/anchor` | 30~60초 (Polygon Amoy 트랜잭션 확인) |
| `GET /credential/verify/{credential_id}` | 3초 이내 |
| `POST /credential/verify` | 3초 이내 |
