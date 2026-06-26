from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict


@dataclass
class VerificationResult:
    is_valid: bool
    is_tampered: bool
    issued_at: datetime
    issuer: str
    credential_subject: Dict[str, Any]


class VCVerifier:
    """Polygon 테스트넷의 해시값과 비교해 VC의 진위 및 위변조 여부를 확인한다."""

    def __init__(self, polygon_rpc_url: str = None):
        self.polygon_rpc_url = polygon_rpc_url

    def fetch_hash_from_chain(self, credential_id: str) -> str:
        raise NotImplementedError

    def verify(self, credential_id: str) -> VerificationResult:
        raise NotImplementedError
