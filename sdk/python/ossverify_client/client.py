import time
from typing import Optional

import requests

from .exceptions import (
    OSSVerifyAnalysisError,
    OSSVerifyAPIError,
    OSSVerifyTimeoutError,
)
from .models import (
    AnchorResult,
    AnalysisResult,
    VerifiableCredential,
    VerificationResult,
)

_DEFAULT_POLL_INTERVAL = 5   # seconds
_DEFAULT_TIMEOUT = 300       # seconds (5 minutes)


class OSSVerifyClient:
    """OSSVerify REST API 클라이언트.

    Args:
        base_url: OSSVerify 서버 URL (기본값: http://localhost:8000)
        timeout:  분석 폴링 최대 대기 시간 (초, 기본값: 300)

    Example::

        client = OSSVerifyClient("http://localhost:8000")
        result = client.analyze("torvalds")
        print(result.primary_domain, result.overall_score)

        vc = client.issue_credential("torvalds")
        client.anchor_credential(vc.credential_id, github_token="ghp_...")
        verify = client.verify_credential(vc.credential_id)
        print(verify.is_valid, verify.is_on_chain)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ── 분석 ──────────────────────────────────────────────────────────────

    def analyze(
        self,
        github_username: str,
        github_token: Optional[str] = None,
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
    ) -> AnalysisResult:
        """GitHub 사용자를 분석한다. 완료될 때까지 자동 폴링.

        Args:
            github_username: GitHub 사용자명
            github_token:    GitHub PAT (없으면 서버 토큰 사용)
            poll_interval:   폴링 간격 (초)
        """
        payload: dict = {"github_username": github_username}
        if github_token:
            payload["github_token"] = github_token

        resp = self._post("/api/v1/analyze", json=payload)
        job_id: str = resp["data"]["job_id"]
        return self._poll(job_id, poll_interval)

    def analyze_self(
        self,
        github_username: str,
        github_token: str,
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
    ) -> AnalysisResult:
        """본인 인증 분석. 토큰의 GitHub 사용자 == github_username 이어야 한다."""
        resp = self._post(
            "/api/v1/analyze/self",
            json={"github_username": github_username},
            auth_token=github_token,
        )
        job_id: str = resp["data"]["job_id"]
        return self._poll(job_id, poll_interval)

    def get_profile(self, github_username: str) -> AnalysisResult:
        """이미 분석된 프로필을 조회한다."""
        resp = self._get(f"/api/v1/profile/{github_username}")
        return AnalysisResult.from_dict(resp["data"])

    # ── VC 발급·앵커링·검증 ───────────────────────────────────────────────

    def issue_credential(self, github_username: str) -> VerifiableCredential:
        """분석 결과를 기반으로 VC를 발급한다 (서명만, 블록체인 기록 없음)."""
        resp = self._post(
            "/api/v1/credential/issue",
            json={"github_username": github_username},
        )
        return VerifiableCredential.from_dict(resp["data"])

    def anchor_credential(
        self, credential_id: str, github_token: str
    ) -> AnchorResult:
        """발급된 VC를 Polygon Amoy 온체인에 앵커링한다. 본인 인증 필요."""
        resp = self._post(
            "/api/v1/credential/anchor",
            json={"credential_id": credential_id},
            auth_token=github_token,
        )
        return AnchorResult.from_dict(resp["data"])

    def verify_credential(self, credential_id: str) -> VerificationResult:
        """credential_id로 같은 인스턴스의 VC를 검증한다."""
        resp = self._get(f"/api/v1/credential/verify/{credential_id}")
        return VerificationResult.from_dict(resp["data"])

    def verify_document(self, document: dict) -> VerificationResult:
        """VC 문서를 직접 검증한다. 다른 인스턴스 발급 VC도 검증 가능."""
        resp = self._post("/api/v1/credential/verify", json={"document": document})
        return VerificationResult.from_dict(resp["data"])

    # ── 내부 헬퍼 ────────────────────────────────────────────────────────

    def _poll(self, job_id: str, poll_interval: int) -> AnalysisResult:
        deadline = time.monotonic() + self.timeout
        while True:
            resp = self._get(f"/api/v1/analyze/status/{job_id}")
            job = resp["data"]
            status = job["status"]

            if status == "complete":
                return AnalysisResult.from_dict(job["data"])
            if status == "failed":
                raise OSSVerifyAnalysisError(job.get("error", "analysis failed"))
            if time.monotonic() > deadline:
                raise OSSVerifyTimeoutError(
                    f"Analysis timed out after {self.timeout}s (job_id={job_id})"
                )
            time.sleep(poll_interval)

    def _get(self, path: str) -> dict:
        resp = self._session.get(f"{self.base_url}{path}", timeout=30)
        return self._handle(resp)

    def _post(
        self,
        path: str,
        json: dict,
        auth_token: Optional[str] = None,
    ) -> dict:
        headers = {}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        resp = self._session.post(
            f"{self.base_url}{path}", json=json, headers=headers, timeout=30
        )
        return self._handle(resp)

    @staticmethod
    def _handle(resp: requests.Response) -> dict:
        try:
            body = resp.json()
        except Exception:
            resp.raise_for_status()
            raise

        if not body.get("success"):
            err = body.get("error") or {}
            raise OSSVerifyAPIError(
                code=err.get("code", "UNKNOWN"),
                message=err.get("message", resp.text),
                status_code=resp.status_code,
            )
        return body
