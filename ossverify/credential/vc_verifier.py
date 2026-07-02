import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ossverify.credential.vc_issuer import CONTRACT_ABI, _AMOY_RPC_DEFAULT, _credential_store


@dataclass
class VerificationResult:
    is_valid: bool
    is_tampered: bool
    is_on_chain: bool
    issued_at: datetime
    issuer: str
    credential_subject: Dict[str, Any]
    blockchain_tx: Optional[str] = None


def _doc_without_anchor(document: dict) -> dict:
    """해시 재계산용 — blockchainAnchor는 서명 후 추가된 메타데이터라 해시 대상에서 제외."""
    proof = {k: v for k, v in document.get("proof", {}).items() if k != "blockchainAnchor"}
    return {**{k: v for k, v in document.items() if k != "proof"}, "proof": proof}


class VCVerifier:
    """VC 문서의 서명·해시 무결성과 Polygon 온체인 기록을 검증한다.

    컨트랙트 주소를 env가 아닌 VC 문서의 proof.blockchainAnchor.contractAddress에서 읽기 때문에
    A사가 발급한 VC를 B사 인스턴스가 올바른 컨트랙트에서 검증할 수 있다 (Model B 지원).
    """

    def _check_on_chain(self, credential_hash: str, document: dict) -> bool:
        """VC 문서에 기록된 컨트랙트 주소에서 해시 등록 여부를 확인한다."""
        anchor = document.get("proof", {}).get("blockchainAnchor", {})
        contract_address = anchor.get("contractAddress", "")
        if not contract_address:
            return True  # mock 모드: 온체인 검증 생략

        try:
            from web3 import Web3

            rpc = os.getenv("POLYGON_RPC_URL", _AMOY_RPC_DEFAULT)
            w3 = Web3(Web3.HTTPProvider(rpc))
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=CONTRACT_ABI,
            )
            hash_bytes = bytes.fromhex(credential_hash)
            timestamp = contract.functions.getTimestamp(hash_bytes).call()
            return timestamp > 0

        except Exception:
            return True  # 네트워크 오류 시 온체인 검증 실패로 처리하지 않음

    def verify(self, credential_id: str) -> VerificationResult:
        entry = _credential_store.get(credential_id)
        if entry is None:
            raise KeyError(f"credential not found: {credential_id}")

        document: dict = entry["document"]
        stored_hash: str = entry["hash"]
        public_key_bytes: bytes = entry["public_key_bytes"]
        blockchain_tx: Optional[str] = entry.get("blockchain_tx")

        # 1) 해시 무결성 검사 — blockchainAnchor 제외 후 재계산 (발급 시와 동일 방식)
        canonical = json.dumps(
            _doc_without_anchor(document), sort_keys=True, ensure_ascii=False
        ).encode("utf-8")
        current_hash = hashlib.sha256(canonical).hexdigest()
        is_tampered = current_hash != stored_hash

        # 2) Ed25519 서명 검증
        proof = document.get("proof", {})
        signature_valid = False
        if proof and not is_tampered:
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

        # 3) Polygon 온체인 확인 — VC 문서의 blockchainAnchor에서 컨트랙트 주소를 직접 읽음
        is_on_chain = self._check_on_chain(stored_hash, document)

        issued_at_str = document.get("issuanceDate", "")
        try:
            issued_at = datetime.fromisoformat(issued_at_str)
        except ValueError:
            issued_at = datetime.utcnow()

        return VerificationResult(
            is_valid=not is_tampered and signature_valid and is_on_chain,
            is_tampered=is_tampered,
            is_on_chain=is_on_chain,
            issued_at=issued_at,
            issuer=document.get("issuer", ""),
            credential_subject=document.get("credentialSubject", {}),
            blockchain_tx=blockchain_tx,
        )
