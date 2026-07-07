"""FastAPI 엔드포인트 smoke test — TestClient (외부 네트워크 호출 없음)."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from ossverify.api.main import _job_store, _profile_store, app
from ossverify.credential.vc_issuer import VCIssuer
from ossverify.profile.profile_builder import ProfessionalProfile

client = TestClient(app)


def _make_profile(username: str = "testuser") -> ProfessionalProfile:
    return ProfessionalProfile(
        github_username=username,
        primary_domain="Backend",
        secondary_domain="DevOps",
        overall_score=75.0,
        influence_level="High",
        activity_level="Active",
        top_skills=["Python"],
        domain_scores={"Backend": 75.0},
        explanations={},
        analyzed_at=datetime.utcnow(),
    )


# ── /analyze ──────────────────────────────────────────────────────────────

def test_analyze_returns_job_id():
    resp = client.post("/api/v1/analyze", json={"github_username": "octocat"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert "job_id" in body["data"]
    assert body["data"]["status"] == "pending"

def test_analyze_status_pending():
    resp = client.post("/api/v1/analyze", json={"github_username": "octocat"})
    job_id = resp.json()["data"]["job_id"]

    resp2 = client.get(f"/api/v1/analyze/status/{job_id}")
    assert resp2.status_code == 200
    assert resp2.json()["data"]["job_id"] == job_id

def test_analyze_status_not_found():
    resp = client.get("/api/v1/analyze/status/nonexistent-job-id-xyz")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


# ── /profile ──────────────────────────────────────────────────────────────

def test_profile_not_found():
    resp = client.get("/api/v1/profile/nobody_xyz_99999")
    assert resp.status_code == 404

def test_profile_found_after_injection():
    _profile_store["api_test_user"] = _make_profile("api_test_user")
    resp = client.get("/api/v1/profile/api_test_user")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["primary_domain"] == "Backend"
    assert data["overall_score"] == 75.0


# ── /credential/issue ─────────────────────────────────────────────────────

def test_credential_issue_no_profile():
    resp = client.post("/api/v1/credential/issue", json={"github_username": "nobody_xyz_99999"})
    assert resp.status_code == 404

def test_credential_issue_success():
    _profile_store["issue_test"] = _make_profile("issue_test")
    resp = client.post("/api/v1/credential/issue", json={"github_username": "issue_test"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["credential_id"].startswith("urn:uuid:")
    assert data["blockchain_tx"] is None  # 앵커링 미완료
    assert "document" in data
    subj = data["document"]["credentialSubject"]
    assert "disclaimer" in subj
    assert "evaluationBasis" in subj


# ── /credential/verify (GET) ──────────────────────────────────────────────

def test_credential_verify_not_found():
    resp = client.get("/api/v1/credential/verify/urn:uuid:nonexistent-xyz")
    assert resp.status_code == 404

def test_credential_verify_by_id():
    _profile_store["verify_test"] = _make_profile("verify_test")
    issue_resp = client.post("/api/v1/credential/issue", json={"github_username": "verify_test"})
    credential_id = issue_resp.json()["data"]["credential_id"]

    resp = client.get(f"/api/v1/credential/verify/{credential_id}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_valid"] is True
    assert data["is_tampered"] is False
    assert data["is_on_chain"] is False


# ── /credential/verify (POST — 외부 문서) ────────────────────────────────

def test_credential_verify_external_document():
    _profile_store["ext_verify_test"] = _make_profile("ext_verify_test")
    issue_resp = client.post("/api/v1/credential/issue", json={"github_username": "ext_verify_test"})
    document = issue_resp.json()["data"]["document"]

    resp = client.post("/api/v1/credential/verify", json={"document": document})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_valid"] is True
    assert data["is_tampered"] is False

def test_credential_verify_external_tampered():
    import copy
    _profile_store["tamper_test"] = _make_profile("tamper_test")
    issue_resp = client.post("/api/v1/credential/issue", json={"github_username": "tamper_test"})
    document = copy.deepcopy(issue_resp.json()["data"]["document"])
    document["credentialSubject"]["overallScore"] = 99.9

    resp = client.post("/api/v1/credential/verify", json={"document": document})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["is_valid"] is False
    assert data["is_tampered"] is True


# ── 전체 흐름: issue → verify by ID → verify by document ─────────────────

def test_full_flow():
    username = "full_flow_test"
    _profile_store[username] = _make_profile(username)

    # 발급
    issue_resp = client.post("/api/v1/credential/issue", json={"github_username": username})
    assert issue_resp.status_code == 200
    vc_data = issue_resp.json()["data"]
    cred_id = vc_data["credential_id"]
    document = vc_data["document"]

    # ID로 검증
    id_verify = client.get(f"/api/v1/credential/verify/{cred_id}")
    assert id_verify.json()["data"]["is_valid"] is True

    # 문서로 검증
    doc_verify = client.post("/api/v1/credential/verify", json={"document": document})
    assert doc_verify.json()["data"]["is_valid"] is True
