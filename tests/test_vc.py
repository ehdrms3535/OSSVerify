"""VC 발급·검증·변조 감지·교차 검증 (Model B) 단위 테스트."""
import copy
from datetime import datetime

import pytest

from ossverify.credential.vc_issuer import VCIssuer
from ossverify.credential.vc_verifier import VCVerifier
from ossverify.profile.profile_builder import ProfessionalProfile


PROFILE = ProfessionalProfile(
    github_username="testuser",
    primary_domain="Backend",
    secondary_domain="DevOps",
    overall_score=80.0,
    influence_level="High",
    activity_level="Very Active",
    top_skills=["Python", "Go"],
    domain_scores={"Backend": 80.0, "DevOps": 55.0},
    explanations={},
    analyzed_at=datetime.utcnow(),
)


# ── 발급 ──────────────────────────────────────────────────────────────────

def test_issue_returns_credential():
    vc = VCIssuer().issue(PROFILE)
    assert vc.credential_id.startswith("urn:uuid:")
    assert vc.document["issuer"].startswith("did:key:z")

def test_issue_no_blockchain_tx():
    vc = VCIssuer().issue(PROFILE)
    assert vc.blockchain_tx is None
    assert "blockchainAnchor" not in vc.document.get("proof", {})

def test_issue_payload_has_disclaimer():
    vc = VCIssuer().issue(PROFILE)
    subj = vc.document["credentialSubject"]
    assert "disclaimer" in subj
    assert "algorithmic estimate" in subj["disclaimer"]

def test_issue_payload_has_evaluation_basis():
    vc = VCIssuer().issue(PROFILE)
    subj = vc.document["credentialSubject"]
    assert "evaluationBasis" in subj
    assert "GitHub" in subj["evaluationBasis"]

def test_issue_proof_type():
    vc = VCIssuer().issue(PROFILE)
    assert vc.document["proof"]["type"] == "Ed25519Signature2020"


# ── 내부 검증 (credential_id) ─────────────────────────────────────────────

def test_internal_verify_valid():
    issuer = VCIssuer()
    vc = issuer.issue(PROFILE)
    result = VCVerifier().verify(vc.credential_id)
    assert result.is_valid
    assert not result.is_tampered
    assert not result.is_on_chain  # anchor 미호출

def test_internal_verify_not_found():
    with pytest.raises(KeyError):
        VCVerifier().verify("urn:uuid:nonexistent-id")

def test_internal_verify_credential_subject():
    vc = VCIssuer().issue(PROFILE)
    result = VCVerifier().verify(vc.credential_id)
    assert result.credential_subject["githubUsername"] == "testuser"
    assert result.credential_subject["primaryDomain"] == "Backend"


# ── 외부 검증 (document) ──────────────────────────────────────────────────

def test_external_verify_valid():
    vc = VCIssuer().issue(PROFILE)
    result = VCVerifier().verify(document=vc.document)
    assert result.is_valid
    assert not result.is_tampered

def test_external_verify_cross_instance():
    """A가 발급한 VC를 B 인스턴스가 _credential_store 없이 검증한다."""
    vc = VCIssuer().issue(PROFILE)

    verifier_b = VCVerifier()  # 완전히 독립된 인스턴스
    result = verifier_b.verify(document=vc.document)
    assert result.is_valid
    assert result.issuer == vc.document["issuer"]


# ── 변조 감지 ─────────────────────────────────────────────────────────────

def test_tamper_score_detected():
    vc = VCIssuer().issue(PROFILE)
    tampered = copy.deepcopy(vc.document)
    tampered["credentialSubject"]["overallScore"] = 99.9

    result = VCVerifier().verify(document=tampered)
    assert not result.is_valid
    assert result.is_tampered

def test_tamper_domain_detected():
    vc = VCIssuer().issue(PROFILE)
    tampered = copy.deepcopy(vc.document)
    tampered["credentialSubject"]["primaryDomain"] = "Blockchain"

    result = VCVerifier().verify(document=tampered)
    assert not result.is_valid
    assert result.is_tampered

def test_tamper_issuer_field_detected():
    vc = VCIssuer().issue(PROFILE)
    tampered = copy.deepcopy(vc.document)
    tampered["issuer"] = "did:key:z6MkFakeIssuer"

    result = VCVerifier().verify(document=tampered)
    assert not result.is_valid


# ── 키 불일치 감지 ────────────────────────────────────────────────────────

def test_key_mismatch_detected():
    """다른 키로 서명한 후 원본 issuer DID를 사용하면 검증이 실패해야 한다."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    import json, hashlib

    issuer = VCIssuer()
    vc = issuer.issue(PROFILE)

    # 완전히 다른 임시 키로 proof를 교체
    evil_key = Ed25519PrivateKey.generate()
    spoofed = copy.deepcopy(vc.document)
    doc_without_proof = {k: v for k, v in spoofed.items() if k != "proof"}
    canonical = json.dumps(doc_without_proof, sort_keys=True, ensure_ascii=False).encode("utf-8")
    evil_sig = evil_key.sign(canonical).hex()

    spoofed["proof"]["proofValue"] = evil_sig  # 다른 키의 서명 + 원래 issuer DID 유지

    result = VCVerifier().verify(document=spoofed)
    assert not result.is_valid
