import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ossverify.credential.vc_issuer import _credential_store


@dataclass
class VerificationResult:
    is_valid: bool
    is_tampered: bool
    issued_at: datetime
    issuer: str
    credential_subject: Dict[str, Any]


class VCVerifier:
    """_credential_store의 해시·서명과 비교해 VC 진위 및 위변조 여부를 확인한다."""

    def __init__(self, polygon_rpc_url: str = None):
        self.polygon_rpc_url = polygon_rpc_url

    def fetch_hash_from_chain(self, credential_id: str) -> str:
        entry = _credential_store.get(credential_id)
        if entry is None:
            raise KeyError(f"credential not found: {credential_id}")
        return entry["hash"]

    def verify(self, credential_id: str) -> VerificationResult:
        entry = _credential_store.get(credential_id)
        if entry is None:
            raise KeyError(f"credential not found: {credential_id}")

        document: dict = entry["document"]
        stored_hash: str = entry["hash"]
        public_key_bytes: bytes = entry["public_key_bytes"]

        # 1) 해시 무결성 검사
        canonical = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8")
        current_hash = hashlib.sha256(canonical).hexdigest()
        is_tampered = current_hash != stored_hash

        # 2) Ed25519 서명 검증
        proof = document.get("proof", {})
        signature_valid = False
        if proof and not is_tampered:
            # proof 블록을 제외한 document에 대한 서명이므로 proof 없이 정규화
            doc_without_proof = {k: v for k, v in document.items() if k != "proof"}
            original_canonical = json.dumps(
                doc_without_proof, sort_keys=True, ensure_ascii=False
            ).encode("utf-8")
            try:
                pub_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
                pub_key.verify(bytes.fromhex(proof.get("proofValue", "")), original_canonical)
                signature_valid = True
            except (InvalidSignature, ValueError):
                signature_valid = False

        issued_at_str = document.get("issuanceDate", "")
        try:
            issued_at = datetime.fromisoformat(issued_at_str)
        except ValueError:
            issued_at = datetime.utcnow()

        return VerificationResult(
            is_valid=not is_tampered and signature_valid,
            is_tampered=is_tampered,
            issued_at=issued_at,
            issuer=document.get("issuer", ""),
            credential_subject=document.get("credentialSubject", {}),
        )
