from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from ossverify.profile.profile_builder import ProfessionalProfile


@dataclass
class VerifiableCredential:
    credential_id: str
    document: Dict[str, Any]
    blockchain_tx: str
    issued_at: datetime


class VCIssuer:
    """did:key 방식으로 DID를 생성하고 W3C VC를 발급한 뒤 해시값을 Polygon에 저장한다."""

    def __init__(self, polygon_rpc_url: str = None):
        self.polygon_rpc_url = polygon_rpc_url

    def generate_did(self) -> str:
        raise NotImplementedError

    def build_credential_document(self, profile: ProfessionalProfile, issuer_did: str) -> Dict[str, Any]:
        raise NotImplementedError

    def sign(self, document: Dict[str, Any], private_key: bytes) -> Dict[str, Any]:
        raise NotImplementedError

    def store_hash_on_chain(self, credential_hash: str) -> str:
        raise NotImplementedError

    def issue(self, profile: ProfessionalProfile) -> VerifiableCredential:
        raise NotImplementedError
