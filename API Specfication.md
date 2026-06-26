# OSSVerify API Specification

> Version 1.0 | 2026.06.26

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

| 코드 | 설명 |
|------|------|
| GITHUB_USER_NOT_FOUND | GitHub 사용자를 찾을 수 없음 |
| GITHUB_RATE_LIMIT | GitHub API Rate Limit 초과 |
| ANALYSIS_FAILED | 분석 실패 |
| CREDENTIAL_NOT_FOUND | VC를 찾을 수 없음 |
| VERIFICATION_FAILED | VC 검증 실패 |
| INVALID_REQUEST | 잘못된 요청 |

---

## 2. 엔드포인트

---

### 2.1 개발자 분석

#### `POST /analyze`

GitHub 사용자의 오픈소스 기여 데이터를 수집하고 AI로 분석한다.

**Request**

```json
{
  "github_username": "string",
  "github_token": "string (optional)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| github_username | string | ✅ | GitHub 사용자명 |
| github_token | string | ❌ | GitHub Personal Access Token (Private 레포 포함 시 필요) |

**Response**

```json
{
  "success": true,
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
      "review_quality": 78.0,
      "issue_response_speed": 71.0,
      "release_consistency": 69.0,
      "documentation_level": 65.0
    },
    "domain_scores": {
      "Backend": 91,
      "Security": 74,
      "DevOps": 61
    },
    "primary_domain": "Backend",
    "secondary_domain": "Security",
    "top_skills": ["Spring", "Java", "Docker", "MySQL"],
    "influence_level": "★★★★☆",
    "activity_level": "높음",
    "analyzed_at": "2026-06-26T00:00:00Z"
  }
}
```

**에러 응답 예시**

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "GITHUB_USER_NOT_FOUND",
    "message": "GitHub 사용자 'octocat'을 찾을 수 없습니다."
  }
}
```

---

### 2.2 프로필 조회

#### `GET /profile/{github_username}`

분석된 Professional Profile을 조회한다. 분석 이력이 없으면 자동으로 분석을 실행한다.

**Path Parameter**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| github_username | string | GitHub 사용자명 |

**Response**

```json
{
  "success": true,
  "data": {
    "github_username": "octocat",
    "primary_domain": "Backend",
    "secondary_domain": "Security",
    "top_skills": ["Spring", "Java", "Docker", "MySQL"],
    "overall_score": 87.4,
    "influence_level": "★★★★☆",
    "activity_level": "높음",
    "domain_scores": {
      "Backend": 91,
      "Security": 74,
      "DevOps": 61
    },
    "explanations": {
      "Backend": {
        "summary": "Spring Boot 기반 백엔드 개발 전문가로 2년 이상의 지속적 기여 이력 보유",
        "reasons": [
          "Spring Boot 프로젝트 5개에 장기 기여",
          "REST API 관련 PR 34건 머지 완료",
          "Backend Code Review 51회 (코드 개선 반영률 78%)",
          "2년 이상 지속 기여"
        ]
      },
      "Security": {
        "summary": "보안 취약점 분석 및 패치 기여 경험 보유",
        "reasons": [
          "보안 관련 이슈 12건 해결",
          "CVE 관련 PR 3건 머지 완료"
        ]
      }
    },
    "analyzed_at": "2026-06-26T00:00:00Z"
  }
}
```

---

### 2.3 VC 발급

#### `POST /credential/issue`

분석 결과를 기반으로 W3C DID 기반 Verifiable Credential을 발급한다.

**Request**

```json
{
  "github_username": "string"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| github_username | string | ✅ | GitHub 사용자명 |

**Response**

```json
{
  "success": true,
  "data": {
    "credential_id": "vc_abc123def456",
    "credential": {
      "@context": ["https://www.w3.org/2018/credentials/v1"],
      "type": ["VerifiableCredential", "DeveloperCredential"],
      "issuer": "did:key:z6Mk...",
      "issuanceDate": "2026-06-26T00:00:00Z",
      "credentialSubject": {
        "id": "github:octocat",
        "primaryDomain": "Backend",
        "overallScore": 87.4,
        "domainScores": {
          "Backend": 91,
          "Security": 74
        },
        "topSkills": ["Spring", "Java", "Docker", "MySQL"],
        "influenceLevel": "★★★★☆"
      },
      "proof": {
        "type": "Ed25519Signature2020",
        "created": "2026-06-26T00:00:00Z",
        "verificationMethod": "did:key:z6Mk...#key-1",
        "proofPurpose": "assertionMethod",
        "proofValue": "z..."
      }
    },
    "blockchain_tx": "0xabc123...",
    "issued_at": "2026-06-26T00:00:00Z"
  }
}
```

---

### 2.4 VC 검증

#### `GET /credential/verify/{credential_id}`

발급된 VC의 진위 여부 및 위변조 여부를 확인한다.

**Path Parameter**

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| credential_id | string | 발급된 VC ID |

**Response**

```json
{
  "success": true,
  "data": {
    "credential_id": "vc_abc123def456",
    "is_valid": true,
    "is_tampered": false,
    "issued_at": "2026-06-26T00:00:00Z",
    "issuer": "did:key:z6Mk...",
    "credential_subject": {
      "id": "github:octocat",
      "primaryDomain": "Backend",
      "overallScore": 87.4,
      "domainScores": {
        "Backend": 91,
        "Security": 74
      },
      "topSkills": ["Spring", "Java", "Docker", "MySQL"],
      "influenceLevel": "★★★★☆"
    }
  }
}
```

**검증 실패 응답**

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "VERIFICATION_FAILED",
    "message": "VC가 위변조되었거나 유효하지 않습니다."
  }
}
```

---

## 3. SDK 사용 예시

### 3.1 Python SDK

```python
from ossverify import OSSVerify

client = OSSVerify()

# 개발자 분석
result = client.analyzeDeveloper("octocat")
print(result.overall_score)       # 87.4
print(result.primary_domain)      # "Backend"

# 프로필 조회
profile = client.getProfessionalProfile("octocat")
print(profile.top_skills)         # ["Spring", "Java", "Docker", "MySQL"]
print(profile.explanations)       # 도메인별 평가 근거

# VC 발급
credential = client.issueCredential("octocat")
print(credential.credential_id)   # "vc_abc123def456"

# VC 검증
result = client.verifyCredential("vc_abc123def456")
print(result.is_valid)            # True
print(result.is_tampered)         # False
```

### 3.2 Node.js SDK

```javascript
const { OSSVerify } = require('ossverify');

const client = new OSSVerify();

// 개발자 분석
const result = await client.analyzeDeveloper('octocat');
console.log(result.overallScore);      // 87.4
console.log(result.primaryDomain);     // "Backend"

// 프로필 조회
const profile = await client.getProfessionalProfile('octocat');
console.log(profile.topSkills);        // ["Spring", "Java", "Docker", "MySQL"]
console.log(profile.explanations);     // 도메인별 평가 근거

// VC 발급
const credential = await client.issueCredential('octocat');
console.log(credential.credentialId);  // "vc_abc123def456"

// VC 검증
const verify = await client.verifyCredential('vc_abc123def456');
console.log(verify.isValid);           // true
console.log(verify.isTampered);        // false
```

---

## 4. 성능 기준

| 엔드포인트 | 목표 응답 시간 |
|------------|---------------|
| POST /analyze | 30초 이내 |
| GET /profile/{username} | 3초 이내 (캐시 히트 시 1초 이내) |
| POST /credential/issue | 10초 이내 |
| GET /credential/verify/{credential_id} | 3초 이내 |