import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from ossverify.profile.profile_builder import ProfessionalProfile

# Base58 alphabet (Bitcoin variant — required for did:key multibase encoding)
_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data: bytes) -> str:
    leading_zeros = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    result = []
    while n:
        n, rem = divmod(n, 58)
        result.append(_B58_ALPHABET[rem:rem + 1])
    result.extend([b"1"] * leading_zeros)
    return b"".join(reversed(result)).decode("ascii")


# 발급된 VC를 메모리에 보관한다. VCVerifier가 이 스토어를 참조해 검증한다.
# credential_id → {"document": dict, "hash": str, "public_key_bytes": bytes}
_credential_store: Dict[str, Dict[str, Any]] = {}


@dataclass
class VerifiableCredential:
    credential_id: str
    document: Dict[str, Any]
    blockchain_tx: str
    issued_at: datetime


class VCIssuer:
    """did:key + Ed25519 서명으로 W3C VC를 발급한다.
    블록체인 앵커링은 Polygon Amoy testnet 연동 전까지 로컬 해시 저장으로 대체한다."""

    def __init__(self, polygon_rpc_url: str = None):
        self.polygon_rpc_url = polygon_rpc_url
        self._private_key: Ed25519PrivateKey = Ed25519PrivateKey.generate()
        self._public_key_bytes: bytes = self._private_key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )

    def generate_did(self) -> str:
        # Ed25519 multicodec prefix = 0xed 0x01, multibase prefix 'z' = base58btc
        multicodec = b"\xed\x01" + self._public_key_bytes
        return f"did:key:z{_b58encode(multicodec)}"

    def build_credential_document(
        self, profile: ProfessionalProfile, issuer_did: str
    ) -> Dict[str, Any]:
        return {
            "@context": [
                "https://www.w3.org/2018/credentials/v1",
                "https://ossverify.io/credentials/v1",
            ],
            "type": ["VerifiableCredential", "OSSContributorCredential"],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "issuer": issuer_did,
            "issuanceDate": datetime.now(timezone.utc).isoformat(),
            "credentialSubject": {
                "id": f"did:github:{profile.github_username}",
                "githubUsername": profile.github_username,
                "primaryDomain": profile.primary_domain,
                "secondaryDomain": profile.secondary_domain,
                "overallScore": round(profile.overall_score, 2),
                "influenceLevel": profile.influence_level,
                "activityLevel": profile.activity_level,
                "topSkills": profile.top_skills,
                "domainScores": profile.domain_scores,
            },
        }

    def sign(self, document: Dict[str, Any], private_key: bytes = None) -> Dict[str, Any]:
        # proof 없이 정규화한 document에 서명 → proof 블록 추가
        canonical = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8")
        signature_hex = self._private_key.sign(canonical).hex()
        signed = dict(document)
        signed["proof"] = {
            "type": "Ed25519Signature2020",
            "created": datetime.now(timezone.utc).isoformat(),
            "verificationMethod": document["issuer"] + "#key-1",
            "proofPurpose": "assertionMethod",
            "proofValue": signature_hex,
        }
        return signed

    def store_hash_on_chain(self, credential_hash: str) -> str:
        # TODO: web3.py + Polygon Amoy testnet 컨트랙트 호출로 교체
        # 현재는 해시 앞 64자리를 mock tx hash로 반환한다.
        return "0x" + credential_hash[:64]

    def issue(self, profile: ProfessionalProfile) -> VerifiableCredential:
        issuer_did = self.generate_did()
        document = self.build_credential_document(profile, issuer_did)
        signed = self.sign(document)

        credential_id = signed["id"]
        canonical = json.dumps(signed, sort_keys=True, ensure_ascii=False).encode("utf-8")
        credential_hash = hashlib.sha256(canonical).hexdigest()
        blockchain_tx = self.store_hash_on_chain(credential_hash)

        _credential_store[credential_id] = {
            "document": signed,
            "hash": credential_hash,
            "public_key_bytes": self._public_key_bytes,
        }

        return VerifiableCredential(
            credential_id=credential_id,
            document=signed,
            blockchain_tx=blockchain_tx,
            issued_at=datetime.now(timezone.utc),
        )
