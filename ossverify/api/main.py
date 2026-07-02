import logging
import os
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ossverify.analyzer.domain_analyzer import Domain, DomainAnalyzer
from ossverify.analyzer.explanation_generator import ExplanationGenerator, ExplanationInput, ExplanationOutput
from ossverify.analyzer.graph_analyzer import GraphAnalyzer
from ossverify.analyzer.influence_analyzer import InfluenceAnalyzer
from ossverify.analyzer.score_calculator import ScoreCalculator, ScoreFeatures
from ossverify.collector.github_collector import GitHubCollector, GitHubData
from ossverify.credential.vc_issuer import VCIssuer
from ossverify.credential.vc_verifier import VCVerifier
from ossverify.profile.profile_builder import ProfessionalProfile, ProfileBuilder

load_dotenv()

app = FastAPI(title="OSSVerify API", version="1.0")

try:
    _domain_analyzer: Optional[DomainAnalyzer] = DomainAnalyzer()
except FileNotFoundError:
    _domain_analyzer = None

try:
    _explanation_generator: Optional[ExplanationGenerator] = (
        ExplanationGenerator() if os.environ.get("ANTHROPIC_API_KEY") else None
    )
except Exception:
    _explanation_generator = None

_profile_store: Dict[str, ProfessionalProfile] = {}
_vc_issuer = VCIssuer()

# 분석 작업 비동기 처리용
class JobStatus(str, Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"

_job_store: Dict[str, Dict[str, Any]] = {}
_analyze_pool = ThreadPoolExecutor(max_workers=4)


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


def _total_activity_count(data: GitHubData) -> int:
    return (
        len(data.contributed_prs)
        + len(data.contributed_reviews)
        + len(data.contributed_issues)
        + len(data.contributed_commits)
        + len(data.received_prs)
        + len(data.received_issues)
        + len(data.maintainer_reviews)
    )


def _top_skills(languages: dict, limit: int = 5) -> list:
    return [name for name, _ in sorted(languages.items(), key=lambda item: item[1], reverse=True)[:limit]]


def _domain_text_corpus(data: GitHubData) -> str:
    description_text = " ".join(repo.description for repo in data.owned_repos if repo.description)
    commit_text = " ".join(c.message for c in data.contributed_commits)
    pr_text = " ".join(pr.title for pr in data.contributed_prs + data.received_prs)
    review_text = " ".join(r.body for r in data.contributed_reviews + data.maintainer_reviews if r.body)
    return f"{description_text} {commit_text} {pr_text} {review_text}".strip()


def _profile_to_dict(profile: ProfessionalProfile) -> dict:
    return {
        "github_username": profile.github_username,
        "primary_domain": profile.primary_domain,
        "secondary_domain": profile.secondary_domain,
        "top_skills": profile.top_skills,
        "influence_level": profile.influence_level,
        "activity_level": profile.activity_level,
        "overall_score": round(profile.overall_score, 2),
        "domain_scores": profile.domain_scores,
        "explanation": {
            key: {"summary": exp.summary, "reasons": exp.reasons}
            for key, exp in profile.explanations.items()
        },
        "analyzed_at": profile.analyzed_at.isoformat(),
    }


def _do_analyze(request: AnalyzeRequest) -> dict:
    token = request.github_token or os.getenv("GITHUB_TOKEN")
    # 검색 결과 300건, 레포 300개로 제한 — 점수 지표가 전부 비율 기반이므로 통계적으로 동등
    data = GitHubCollector(
        github_token=token, max_search_pages=3, max_repo_pages=3
    ).collect(request.github_username)

    contributor_score, maintainer_score, final_influence = InfluenceAnalyzer().analyze(data)

    graph_analyzer = GraphAnalyzer()
    graph_centrality = graph_analyzer.calculate_centrality(data)

    domain_scores: dict = {}
    primary_domain = None
    secondary_domain = None
    primary_domain_enum: Domain = Domain.BACKEND
    if _domain_analyzer is not None:
        domain_result = _domain_analyzer.infer(_domain_text_corpus(data))
        domain_scores = {d.value: round(score * 100, 1) for d, score in domain_result.domains.items()}
        raw_primary = domain_result.primary_domain
        raw_secondary = domain_result.secondary_domain

        _blockchain_langs = {"Solidity", "Vyper", "Move", "Rust"}
        top_skill_set = set(_top_skills(data.languages, limit=10))
        if (
            raw_primary is not None
            and raw_primary.value == "Blockchain"
            and not (_blockchain_langs & top_skill_set)
            and raw_secondary is not None
        ):
            raw_primary, raw_secondary = raw_secondary, raw_primary

        primary_domain = raw_primary.value if raw_primary else None
        secondary_domain = raw_secondary.value if raw_secondary else None
        if raw_primary:
            primary_domain_enum = raw_primary

    top_skills = _top_skills(data.languages)

    final_score = ScoreCalculator().calculate(
        ScoreFeatures(
            influence_score=final_influence,
            domain_scores=domain_scores,
            graph_centrality=graph_centrality.pagerank_score,
            activity_ratio=data.activity_ratio,
            total_activity_count=_total_activity_count(data),
        )
    )

    exp_output: Optional[ExplanationOutput] = None
    if _explanation_generator is not None:
        try:
            exp_input = ExplanationInput(
                domain=primary_domain_enum,
                score=final_score.overall_score,
                contributor_data=contributor_score,
                maintainer_data=maintainer_score,
                top_projects=[repo.full_name for repo in data.owned_repos[:5]],
                top_skills=top_skills,
            )
            exp_output = _explanation_generator.generate(exp_input)
        except Exception:
            pass

    explanations: Dict[str, ExplanationOutput] = {}
    if exp_output is not None:
        explanations["primary"] = exp_output

    profile = ProfileBuilder().build(
        github_username=data.username,
        final_score=final_score,
        primary_domain=primary_domain or "",
        secondary_domain=secondary_domain or "",
        top_skills=top_skills,
        explanations=explanations,
    )
    _profile_store[data.username.lower()] = profile

    return {
        "github_username": data.username,
        "overall_score": round(final_score.overall_score, 2),
        "activity_ratio": asdict(data.activity_ratio),
        "contributor_score": {"total": round(contributor_score.calculate(), 2), **asdict(contributor_score)},
        "maintainer_score": {"total": round(maintainer_score.calculate(), 2), **asdict(maintainer_score)},
        "domain_scores": final_score.domain_scores,
        "primary_domain": primary_domain,
        "secondary_domain": secondary_domain,
        "top_skills": top_skills,
        "influence_level": final_score.influence_level,
        "activity_level": final_score.activity_level,
        "graph_centrality": graph_centrality.pagerank_score,
        "explanation": {
            "summary": exp_output.summary if exp_output else None,
            "reasons": exp_output.reasons if exp_output else [],
        },
        "analyzed_at": profile.analyzed_at.isoformat(),
    }


def _run_analyze_job(job_id: str, request: AnalyzeRequest) -> None:
    try:
        result = _do_analyze(request)
        _job_store[job_id]["status"] = JobStatus.COMPLETE
        _job_store[job_id]["data"] = result
    except Exception as e:
        logging.error("analyze job %s failed: %s\n%s", job_id, e, traceback.format_exc())
        _job_store[job_id]["status"] = JobStatus.FAILED
        _job_store[job_id]["error"] = str(e)


@app.post("/api/v1/analyze")
def analyze(request: AnalyzeRequest):
    job_id = str(uuid.uuid4())
    _job_store[job_id] = {"status": JobStatus.PENDING, "data": None, "error": None}
    _analyze_pool.submit(_run_analyze_job, job_id, request)
    return success_response({"job_id": job_id, "status": JobStatus.PENDING})


@app.get("/api/v1/analyze/status/{job_id}")
def get_analyze_status(job_id: str):
    job = _job_store.get(job_id)
    if job is None:
        return error_response("NOT_FOUND", f"Job '{job_id}'을 찾을 수 없습니다.", status_code=404)
    return success_response({
        "job_id": job_id,
        "status": job["status"],
        "data": job["data"],
        "error": job["error"],
    })


@app.get("/api/v1/profile/{github_username}")
def get_profile(github_username: str):
    profile = _profile_store.get(github_username.lower())
    if profile is None:
        return error_response(
            "NOT_FOUND",
            f"'{github_username}'의 분석 이력이 없습니다. POST /api/v1/analyze를 먼저 호출하세요.",
            status_code=404,
        )
    return success_response(_profile_to_dict(profile))


@app.post("/api/v1/credential/issue")
def issue_credential(request: IssueCredentialRequest):
    profile = _profile_store.get(request.github_username.lower())
    if profile is None:
        return error_response(
            "NOT_FOUND",
            f"'{request.github_username}'의 분석 이력이 없습니다. POST /api/v1/analyze를 먼저 호출하세요.",
            status_code=404,
        )
    try:
        vc = _vc_issuer.issue(profile)
        return success_response({
            "credential_id": vc.credential_id,
            "issuer": vc.document.get("issuer"),
            "blockchain_tx": vc.blockchain_tx,
            "issued_at": vc.issued_at.isoformat(),
            "document": vc.document,
        })
    except Exception as e:
        return error_response("ISSUE_FAILED", str(e), status_code=500)


@app.get("/api/v1/credential/verify/{credential_id}")
def verify_credential(credential_id: str):
    try:
        result = VCVerifier().verify(credential_id)
        return success_response({
            "credential_id": credential_id,
            "is_valid": result.is_valid,
            "is_tampered": result.is_tampered,
            "issuer": result.issuer,
            "issued_at": result.issued_at.isoformat(),
            "credential_subject": result.credential_subject,
        })
    except KeyError:
        return error_response("NOT_FOUND", f"'{credential_id}' VC를 찾을 수 없습니다.", status_code=404)
    except Exception as e:
        return error_response("VERIFICATION_FAILED", str(e), status_code=500)
