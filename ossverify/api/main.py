import os
from dataclasses import asdict
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ossverify.collector.github_collector import GitHubCollector
from ossverify.credential.vc_verifier import VCVerifier

load_dotenv()

app = FastAPI(title="OSSVerify API", version="1.0")


class AnalyzeRequest(BaseModel):
    github_username: str
    github_token: Optional[str] = None


class IssueCredentialRequest(BaseModel):
    github_username: str


def success_response(data: Any) -> dict:
    return {"success": True, "data": data, "error": None}


def error_response(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "data": None, "error": {"code": code, "message": message}},
    )


@app.post("/api/v1/analyze")
def analyze(request: AnalyzeRequest):
    try:
        # 요청에 토큰이 없으면 서비스 운영자 토큰(.env의 GITHUB_TOKEN)으로 rate limit 완화
        token = request.github_token or os.getenv("GITHUB_TOKEN")
        collector = GitHubCollector(github_token=token)
        data = collector.collect(request.github_username)
        return success_response(asdict(data))
    except NotImplementedError:
        return error_response("ANALYSIS_FAILED", "분석 기능이 아직 구현되지 않았습니다.", status_code=501)


@app.get("/api/v1/profile/{github_username}")
def get_profile(github_username: str):
    return error_response("ANALYSIS_FAILED", "프로필 조회 기능이 아직 구현되지 않았습니다.", status_code=501)


@app.post("/api/v1/credential/issue")
def issue_credential(request: IssueCredentialRequest):
    return error_response("ANALYSIS_FAILED", "VC 발급 기능이 아직 구현되지 않았습니다.", status_code=501)


@app.get("/api/v1/credential/verify/{credential_id}")
def verify_credential(credential_id: str):
    try:
        verifier = VCVerifier()
        result = verifier.verify(credential_id)
        return success_response({"credential_id": credential_id, **vars(result)})
    except NotImplementedError:
        return error_response("VERIFICATION_FAILED", "VC 검증 기능이 아직 구현되지 않았습니다.", status_code=501)
