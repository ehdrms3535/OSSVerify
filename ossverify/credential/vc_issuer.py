import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat, PublicFormat, load_pem_private_key,
)

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

# ── 데이터 디렉토리 ──────────────────────────────────────────────────────────
_DATA_DIR = Path(os.getenv("OSSVERIFY_DATA_DIR", "ossverify_data"))
_KEY_PATH = _DATA_DIR / "issuer.pem"
_DB_PATH  = _DATA_DIR / "credentials.db"


def _ensure_data_dir() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── 키 영속화 ────────────────────────────────────────────────────────────────

def _load_or_create_key() -> Ed25519PrivateKey:
    _ensure_data_dir()
    if _KEY_PATH.exists():
        pem = _KEY_PATH.read_bytes()
        return load_pem_private_key(pem, password=None)
    key = Ed25519PrivateKey.generate()
    _KEY_PATH.write_bytes(
        key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    return key


# ── SQLite credential store ──────────────────────────────────────────────────

def _get_db() -> sqlite3.Connection:
    _ensure_data_dir()
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS credentials (
            credential_id TEXT PRIMARY KEY,
            document      TEXT NOT NULL,
            hash          TEXT NOT NULL,
            public_key    TEXT NOT NULL,
            blockchain_tx TEXT
        )
    """)
    conn.commit()
    return conn


_db: Optional[sqlite3.Connection] = None


def _credential_db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = _get_db()
    return _db


def _store_credential(credential_id: str, document: dict, hash_: str,
                      public_key_bytes: bytes, blockchain_tx: Optional[str]) -> None:
    db = _credential_db()
    db.execute(
        "INSERT OR REPLACE INTO credentials VALUES (?, ?, ?, ?, ?)",
        (credential_id, json.dumps(document, ensure_ascii=False),
         hash_, public_key_bytes.hex(), blockchain_tx),
    )
    db.commit()


def _load_credential(credential_id: str) -> Optional[Dict[str, Any]]:
    row = _credential_db().execute(
        "SELECT document, hash, public_key, blockchain_tx FROM credentials WHERE credential_id=?",
        (credential_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "document": json.loads(row[0]),
        "hash": row[1],
        "public_key_bytes": bytes.fromhex(row[2]),
        "blockchain_tx": row[3],
    }


def _update_blockchain_tx(credential_id: str, blockchain_tx: str, document: Optional[dict] = None) -> None:
    db = _credential_db()
    if document is not None:
        db.execute(
            "UPDATE credentials SET blockchain_tx=?, document=? WHERE credential_id=?",
            (blockchain_tx, json.dumps(document, ensure_ascii=False), credential_id),
        )
    else:
        db.execute(
            "UPDATE credentials SET blockchain_tx=? WHERE credential_id=?",
            (blockchain_tx, credential_id),
    )
    db.commit()


def _list_credential_ids():
    rows = _credential_db().execute("SELECT credential_id FROM credentials").fetchall()
    return [r[0] for r in rows]


# ── 하위 호환을 위한 dict-like 래퍼 (main.py의 _credential_store 참조용) ──────
class _CredentialStore:
    def __getitem__(self, key: str) -> Dict[str, Any]:
        v = _load_credential(key)
        if v is None:
            raise KeyError(key)
        return v

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        _store_credential(
            key,
            value["document"],
            value["hash"],
            value["public_key_bytes"],
            value.get("blockchain_tx"),
        )

    def __contains__(self, key: object) -> bool:
        return _load_credential(str(key)) is not None

    def get(self, key: str, default=None):
        v = _load_credential(key)
        return v if v is not None else default


_credential_store = _CredentialStore()


def _b58encode(data: bytes) -> str:
    leading_zeros = len(data) - len(data.lstrip(b"\x00"))
    n = int.from_bytes(data, "big")
    result = []
    while n:
        n, rem = divmod(n, 58)
        result.append(_B58_ALPHABET[rem:rem + 1])
    result.extend([b"1"] * leading_zeros)
    return b"".join(reversed(result)).decode("ascii")


@dataclass
class VerifiableCredential:
    credential_id: str
    document: Dict[str, Any]
    blockchain_tx: Optional[str]
    issued_at: datetime


class VCIssuer:
    """did:key + Ed25519 서명으로 W3C VC를 발급하고 Polygon Amoy testnet에 해시를 앵커링한다.

    키쌍은 ossverify_data/issuer.pem에 영속화되며, 재시작 후에도 동일한 DID를 유지한다.

    환경변수:
      POLYGON_PRIVATE_KEY      — 트랜잭션 서명용 개인키 (0x 포함 가능)
      POLYGON_CONTRACT_ADDRESS — 배포된 OSSVerifyRegistry 주소
      POLYGON_RPC_URL          — Amoy RPC URL (기본값: public endpoint)
      OSSVERIFY_DATA_DIR       — 키·DB 저장 디렉토리 (기본값: ossverify_data)
    """

    def __init__(self) -> None:
        self._private_key: Ed25519PrivateKey = _load_or_create_key()
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
        """SHA-256 해시를 Polygon Amoy OSSVerifyRegistry에 기록하고 tx hash를 반환한다."""
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
            return "0x" + credential_hash[:64] + f"_err:{type(exc).__name__}"

    def issue(self, profile: ProfessionalProfile) -> VerifiableCredential:
        """VC를 발급한다 (서명 + 해시 + DB 저장).

        온체인 앵커링은 이 메서드에서 수행하지 않는다.
        블록체인 기록이 필요하면 POST /api/v1/credential/anchor 를 별도로 호출한다.
        """
        issuer_did = self.generate_did()
        document = self.build_credential_document(profile, issuer_did)
        signed = self.sign(document)

        credential_id = signed["id"]
        canonical = json.dumps(signed, sort_keys=True, ensure_ascii=False).encode("utf-8")
        credential_hash = hashlib.sha256(canonical).hexdigest()

        _store_credential(credential_id, signed, credential_hash,
                          self._public_key_bytes, None)

        return VerifiableCredential(
            credential_id=credential_id,
            document=signed,
            blockchain_tx=None,
            issued_at=datetime.now(timezone.utc),
        )
