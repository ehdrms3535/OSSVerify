import hashlib
import json
import os
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

_AMOY_RPC_DEFAULT = "https://rpc-amoy.polygon.technology/"
_AMOY_CHAIN_ID = 80002

# OSSVerifyRegistry ABI — storeHash / getTimestamp
CONTRACT_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "_hash", "type": "bytes32"}],
        "name": "storeHash",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "_hash", "type": "bytes32"}],
        "name": "getTimestamp",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "credentialHash", "type": "bytes32"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
        ],
        "name": "HashStored",
        "type": "event",
    },
]


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
# credential_id → {"document": dict, "hash": str, "public_key_bytes": bytes, "blockchain_tx": str}
_credential_store: Dict[str, Dict[str, Any]] = {}


@dataclass
class VerifiableCredential:
    credential_id: str
    document: Dict[str, Any]
    blockchain_tx: str
    issued_at: datetime


class VCIssuer:
    """did:key + Ed25519 서명으로 W3C VC를 발급하고 Polygon Amoy testnet에 해시를 앵커링한다.

    환경변수:
      POLYGON_PRIVATE_KEY      — 트랜잭션 서명용 개인키 (0x 포함 가능)
      POLYGON_CONTRACT_ADDRESS — 배포된 OSSVerifyRegistry 주소
      POLYGON_RPC_URL          — Amoy RPC URL (기본값: public endpoint)

    두 변수가 없으면 mock tx hash를 반환해 정상 발급은 유지한다.
    """

    def __init__(self) -> None:
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
                "evaluationBasis": (
                    "Algorithmic analysis of public GitHub activity data "
                    "(commits, pull requests, issues, code reviews). "
                    "Scores reflect open-source contribution influence "
                    "as estimated by OSSVerify's AI model."
                ),
                "disclaimer": (
                    "This credential is an algorithmic estimate, "
                    "not a formal professional certification. "
                    "No liability is assumed for hiring or evaluation decisions "
                    "made on the basis of this credential."
                ),
            },
        }

    def sign(self, document: Dict[str, Any]) -> Dict[str, Any]:
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
        """SHA-256 해시를 Polygon Amoy OSSVerifyRegistry에 기록하고 tx hash를 반환한다.

        POLYGON_PRIVATE_KEY 또는 POLYGON_CONTRACT_ADDRESS 가 없으면 mock을 반환한다.
        """
        private_key = os.getenv("POLYGON_PRIVATE_KEY", "")
        contract_address = os.getenv("POLYGON_CONTRACT_ADDRESS", "")
        if not private_key or not contract_address:
            return "0x" + credential_hash[:64]

        try:
            from web3 import Web3

            rpc = os.getenv("POLYGON_RPC_URL", _AMOY_RPC_DEFAULT)
            w3 = Web3(Web3.HTTPProvider(rpc))

            if not private_key.startswith("0x"):
                private_key = "0x" + private_key
            account = w3.eth.account.from_key(private_key)

            contract = w3.eth.contract(
                address=Web3.to_checksum_address(contract_address),
                abi=CONTRACT_ABI,
            )

            hash_bytes = bytes.fromhex(credential_hash)
            tx = contract.functions.storeHash(hash_bytes).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 100_000,
                "gasPrice": w3.eth.gas_price,
                "chainId": _AMOY_CHAIN_ID,
            })
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            return receipt.transactionHash.hex()

        except Exception as exc:
            # 블록체인 오류 시 mock으로 폴백 — VC 발급 자체는 중단하지 않음
            return "0x" + credential_hash[:64] + f"_err:{type(exc).__name__}"

    def issue(self, profile: ProfessionalProfile) -> VerifiableCredential:
        """VC를 발급한다 (서명 + 해시 + 메모리 저장).

        온체인 앵커링은 이 메서드에서 수행하지 않는다.
        블록체인 기록이 필요하면 POST /api/v1/credential/anchor 를 별도로 호출한다.
        이 분리 덕분에 공개 엔드포인트(/credential/issue)가 실제 체인 트랜잭션을 유발하지 않는다.
        """
        issuer_did = self.generate_did()
        document = self.build_credential_document(profile, issuer_did)
        signed = self.sign(document)

        credential_id = signed["id"]

        # 서명 직후 해시 계산 — anchor() 호출 시 온체인에 기록되는 값과 일치해야 함
        canonical = json.dumps(signed, sort_keys=True, ensure_ascii=False).encode("utf-8")
        credential_hash = hashlib.sha256(canonical).hexdigest()

        _credential_store[credential_id] = {
            "document": signed,
            "hash": credential_hash,
            "public_key_bytes": self._public_key_bytes,
            "blockchain_tx": None,  # anchor() 호출 전까지 None
        }

        return VerifiableCredential(
            credential_id=credential_id,
            document=signed,
            blockchain_tx=None,
            issued_at=datetime.now(timezone.utc),
        )
