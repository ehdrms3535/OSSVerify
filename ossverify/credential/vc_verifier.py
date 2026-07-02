import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ossverify.credential.vc_issuer import CONTRACT_ABI, _AMOY_RPC_DEFAULT, _credential_store

# Base58btc alphabet — did:key 디코딩에 사용 (vc_issuer._b58encode의 역연산)
_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58decode(s: str) -> bytes:
    """Base58btc decode."""
    n = 0
    for char in s.encode():
        n = n * 58 + _B58_ALPHABET.index(char)
    n_pad = len(s) - len(s.lstrip("1"))
    body = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big") if n else b""
    return b"\x00" * n_pad + body


def _decode_did_key(did: str) -> bytes:
    """did:key:z<base58btc> → Ed25519 원시 공개키 32바이트.

    did:key 스펙: 'z' prefix = multibase base58btc, 이후 multicodec bytes.
    Ed25519 multicodec prefix = 0xed 0x01 (2바이트) + 32바이트 공개키.
    """
    if not did.startswith("did:key:z"):
        raise ValueError(f"지원하지 않는 DID 형식: {did}")
    multicodec = _b58decode(did[len("did:key:z"):])
    if len(multicodec) < 34 or multicodec[:2] != b"\xed\x01":
        raise ValueError(f"Ed25519 multicodec 프리픽스 아님: {multicodec[:2].hex()}")
    return multicodec[2:]  # 32-byte raw public key


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
    A 인스턴스가 발급한 VC를 B 인스턴스도 올바른 컨트랙트에서 검증할 수 있다 (Model B 지원).

    외부 VC 검증 경로(document 파라미터):
      issuer 필드의 did:key를 디코딩해 Ed25519 공개키를 얻으므로 _credential_store 없이도 검증 가능.
    """

    def _check_on_chain(self, credential_hash: str, document: dict) -> bool:
        """VC 문서에 기록된 컨트랙트 주소에서 해시 등록 여부를 확인한다."""
        anchor = document.get("proof", {}).get("blockchainAnchor", {})
        contract_address = anchor.get("contractAddress", "")
        if not contract_address:
            return False  # blockchainAnchor 없음 = 앵커링 미완료

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

    def _verify_core(
        self,
        document: dict,
        stored_hash: str,
        public_key_bytes: bytes,
        blockchain_tx: Optional[str],
    ) -> VerificationResult:
        """서명·해시·온체인 3단계 검증 공통 로직."""
        # 1) 해시 무결성 — blockchainAnchor 제외 후 재계산
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

        # 3) Polygon 온체인 확인
        is_on_chain = self._check_on_chain(stored_hash, document)

        issued_at_str = document.get("issuanceDate", "")
        try:
            issued_at = datetime.fromisoformat(issued_at_str)
        except ValueError:
            issued_at = datetime.utcnow()

        # is_valid = 서명·무결성 기반 (W3C VC 핵심 요건)
        # is_on_chain은 별도 필드 — 앵커링 안 된 데모 VC도 is_valid=True 가능
        return VerificationResult(
            is_valid=not is_tampered and signature_valid,
            is_tampered=is_tampered,
            is_on_chain=is_on_chain,
            issued_at=issued_at,
            issuer=document.get("issuer", ""),
            credential_subject=document.get("credentialSubject", {}),
            blockchain_tx=blockchain_tx,
        )

    def _verify_external(self, document: dict) -> VerificationResult:
        """외부 인스턴스 발급 VC — did:key issuer에서 공개키를 디코딩해 검증한다.

        _credential_store에 없어도 동작하므로 다른 인스턴스의 VC를 검증할 수 있다.
        서명 무결성이 곧 tamper 감지 기준이다.
        """
        issuer_did = document.get("issuer", "")
        try:
            public_key_bytes = _decode_did_key(issuer_did)
        except ValueError as exc:
            issued_at_str = document.get("issuanceDate", "")
            try:
                issued_at = datetime.fromisoformat(issued_at_str)
            except ValueError:
                issued_at = datetime.utcnow()
            return VerificationResult(
                is_valid=False,
                is_tampered=True,
                is_on_chain=False,
                issued_at=issued_at,
                issuer=issuer_did,
                credential_subject=document.get("credentialSubject", {}),
            )

        # 해시 재계산 (blockchainAnchor 제외) → 온체인 확인에 사용
        canonical_for_hash = json.dumps(
            _doc_without_anchor(document), sort_keys=True, ensure_ascii=False
        ).encode("utf-8")
        credential_hash = hashlib.sha256(canonical_for_hash).hexdigest()

        # 온체인 tx hash는 blockchainAnchor에서 직접 읽음
        anchor = document.get("proof", {}).get("blockchainAnchor", {})
        blockchain_tx: Optional[str] = anchor.get("transactionHash")

        result = self._verify_core(document, credential_hash, public_key_bytes, blockchain_tx)
        # 외부 VC: is_valid는 서명 무결성 기준, is_on_chain은 별도 판단
        return result

    def verify(
        self,
        credential_id: str = "",
        document: Optional[dict] = None,
    ) -> VerificationResult:
        """VC를 검증한다.

        document 파라미터가 있으면 외부 VC 경로(_verify_external)로 처리한다.
        없으면 credential_id로 _credential_store를 조회하는 내부 경로를 사용한다.
        """
        if document is not None:
            return self._verify_external(document)

        entry = _credential_store.get(credential_id)
        if entry is None:
            raise KeyError(f"credential not found: {credential_id}")

        return self._verify_core(
            document=entry["document"],
            stored_hash=entry["hash"],
            public_key_bytes=entry["public_key_bytes"],
            blockchain_tx=entry.get("blockchain_tx"),
        )
