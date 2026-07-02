# -*- coding: utf-8 -*-
"""
OSSVerify Model B cross-verification demo
------------------------------------------
Instance A issues a VC; Instance B verifies it.
B does not share A's private key or _credential_store.
Verification path: issuer(did:key) -> decode public key -> Ed25519 verify -> on-chain check

Usage (from project root):
    python demo/two_instance_demo.py
"""

import copy
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

from ossverify.credential.vc_issuer import VCIssuer
from ossverify.credential.vc_verifier import VCVerifier
from ossverify.profile.profile_builder import ProfessionalProfile


DEMO_PROFILE = ProfessionalProfile(
    github_username="alice",
    primary_domain="Backend",
    secondary_domain="DevOps",
    overall_score=82.5,
    influence_level="High",
    activity_level="Very Active",
    top_skills=["Python", "Go", "Docker", "PostgreSQL", "Kubernetes"],
    domain_scores={"Backend": 78.3, "DevOps": 61.2, "Cloud": 45.0},
    explanations={},
    analyzed_at=datetime.utcnow(),
)


def sep(title: str = "") -> None:
    line = "-" * 60
    if title:
        print(f"\n{line}\n  {title}\n{line}")
    else:
        print(line)


def main() -> int:
    sep("OSSVerify Model B Cross-Verification Demo")

    # Step 1. Instance A: issue VC
    sep("Step 1 | Instance A -- Issue VC")

    issuer_a = VCIssuer()
    vc = issuer_a.issue(DEMO_PROFILE)
    did_a = vc.document["issuer"]

    print(f"  credential_id : {vc.credential_id}")
    print(f"  issuer (A)    : {did_a}")
    print(f"  proofType     : {vc.document['proof']['type']}")
    print(f"  proofValue    : {vc.document['proof']['proofValue'][:40]}...")
    print(f"  is_on_chain   : False  (anchor not called -- demo track)")
    subj = vc.document["credentialSubject"]
    print(f"  disclaimer    : {subj['disclaimer'][:60]}...")
    print(f"  evaluationBasis: {subj['evaluationBasis'][:60]}...")

    # Step 2. Transfer VC document (in real use: SDK / HTTP)
    sep("Step 2 | Transfer VC document to Instance B")

    payload_size = len(json.dumps(vc.document, ensure_ascii=False))
    print(f"  payload size  : {payload_size} bytes")
    print("  (in production: delivered via SDK or HTTP response)")

    # Step 3. Instance B: verify external VC
    sep("Step 3 | Instance B -- Verify external VC")
    print("  (B has no access to A's private key or _credential_store)")

    verifier_b = VCVerifier()
    result = verifier_b.verify(document=vc.document)

    print(f"\n  is_valid      : {result.is_valid}")
    print(f"  is_tampered   : {result.is_tampered}")
    print(f"  is_on_chain   : {result.is_on_chain}  (anchor not called)")
    print(f"  issuer        : {result.issuer}")
    print(f"  subject       : {result.credential_subject.get('githubUsername')}")
    print(f"  primaryDomain : {result.credential_subject.get('primaryDomain')}")
    print(f"  overallScore  : {result.credential_subject.get('overallScore')}")

    assert result.is_valid,        "Step 3 FAIL: valid VC rejected"
    assert not result.is_tampered, "Step 3 FAIL: valid VC flagged as tampered"
    print("\n  [PASS] Valid VC accepted by Instance B")

    # Step 4. Tampering detection
    sep("Step 4 | Tampering detection")
    print("  Forging overallScore: 82.5 -> 99.9 ...")

    tampered = copy.deepcopy(vc.document)
    tampered["credentialSubject"]["overallScore"] = 99.9

    result_t = verifier_b.verify(document=tampered)
    print(f"\n  is_valid      : {result_t.is_valid}   (signature verification failed)")
    print(f"  is_tampered   : {result_t.is_tampered}  (tampering detected)")

    assert not result_t.is_valid, "Step 4 FAIL: forged VC accepted"
    assert result_t.is_tampered,  "Step 4 FAIL: tampering not detected"
    print("\n  [PASS] Forged VC rejected")

    # Step 5. Key mismatch detection
    sep("Step 5 | Key mismatch detection")
    print("  VC signed by Instance C, but claims to use A's did:key ...")

    issuer_c = VCIssuer()
    vc_c = issuer_c.issue(DEMO_PROFILE)

    spoofed = copy.deepcopy(vc_c.document)
    spoofed["issuer"] = did_a
    spoofed["proof"]["verificationMethod"] = did_a + "#key-1"

    result_s = verifier_b.verify(document=spoofed)
    print(f"\n  is_valid      : {result_s.is_valid}   (C signature vs A public key)")
    print(f"  is_tampered   : {result_s.is_tampered}")

    assert not result_s.is_valid, "Step 5 FAIL: key-mismatch VC accepted"
    print("\n  [PASS] Key mismatch detected")

    # Summary
    sep()
    print("  All scenarios passed.")
    print()
    print("  Summary")
    print("  " + "-" * 56)
    print("  A issues -> B verifies      : PASS  (did:key decode)")
    print("  Forged score -> B verifies  : PASS  (signature integrity)")
    print("  Key mismatch -> B verifies  : PASS  (wrong key rejected)")
    print("  Blockchain anchor (demo)    : skipped -- call /credential/anchor separately")
    sep()
    return 0


if __name__ == "__main__":
    sys.exit(main())
