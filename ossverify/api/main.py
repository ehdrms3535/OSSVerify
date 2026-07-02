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


# 언어 → 도메인 사전 신호 (바이트 비중 기반 혼합에 사용)
# 학습 데이터가 CI/Docker 키워드에 편향될 수 있어 언어 비중으로 보정
_LANGUAGE_DOMAIN_SIGNAL: Dict[str, Dict[str, float]] = {
    "Python":           {"Backend": 0.35, "AI/ML": 0.40, "DevOps": 0.15, "Cloud": 0.10},
    "JavaScript":       {"Frontend": 0.50, "Backend": 0.30, "DevOps": 0.10, "Cloud": 0.10},
    "TypeScript":       {"Frontend": 0.50, "Backend": 0.30, "DevOps": 0.10, "Cloud": 0.10},
    "Java":             {"Backend": 0.60, "Cloud": 0.20, "DevOps": 0.10, "AI/ML": 0.10},
    "Kotlin":           {"Backend": 0.50, "Frontend": 0.30, "Cloud": 0.15, "AI/ML": 0.05},
    "Go":               {"Backend": 0.40, "DevOps": 0.30, "Cloud": 0.20, "Security": 0.10},
    "Rust":             {"Backend": 0.35, "Blockchain": 0.25, "Security": 0.25, "DevOps": 0.15},
    "C#":               {"Backend": 0.50, "Frontend": 0.20, "Cloud": 0.20, "AI/ML": 0.10},
    "C++":              {"Backend": 0.30, "AI/ML": 0.35, "Security": 0.20, "Blockchain": 0.15},
    "C":                {"Backend": 0.40, "Security": 0.25, "DevOps": 0.20, "AI/ML": 0.15},
    "Ruby":             {"Backend": 0.65, "Frontend": 0.15, "DevOps": 0.20},
    "PHP":              {"Backend": 0.65, "Frontend": 0.25, "DevOps": 0.10},
    "Swift":            {"Frontend": 0.60, "Backend": 0.25, "AI/ML": 0.15},
    "Dart":             {"Frontend": 0.90, "Backend": 0.10},
    "Shell":            {"DevOps": 0.55, "Cloud": 0.25, "Backend": 0.20},
    "HCL":              {"Cloud": 0.70, "DevOps": 0.30},
    "Dockerfile":       {"DevOps": 0.65, "Cloud": 0.35},
    "Vue":              {"Frontend": 0.90, "Backend": 0.10},
    "HTML":             {"Frontend": 0.75, "Backend": 0.15, "DevOps": 0.10},
    "CSS":              {"Frontend": 0.90, "Backend": 0.10},
    "SCSS":             {"Frontend": 0.90, "Backend": 0.10},
    "Solidity":         {"Blockchain": 0.90, "Backend": 0.10},
    "Vyper":            {"Blockchain": 0.95, "Backend": 0.05},
    "R":                {"AI/ML": 0.90, "Backend": 0.10},
    "CUDA":             {"AI/ML": 0.85, "Backend": 0.15},
    "Jupyter Notebook": {"AI/ML": 0.80, "Backend": 0.15, "Cloud": 0.05},
}


def _blend_language_signal(
    bert_scores: Dict[Domain, float],
    languages: Dict[str, int],
    lang_weight: float = 0.35,
) -> Dict[Domain, float]:
    """BERT 점수에 언어 바이트 비중 신호를 혼합해 CI/Docker 키워드 편향을 보정."""
    total_bytes = sum(languages.values())
    if total_bytes == 0:
        return bert_scores

    lang_signal: Dict[Domain, float] = {d: 0.0 for d in Domain}
    for lang, byte_count in languages.items():
        proportion = byte_count / total_bytes
        domain_map = _LANGUAGE_DOMAIN_SIGNAL.get(lang)
        if domain_map:
            for domain_val, weight in domain_map.items():
                try:
                    lang_signal[Domain(domain_val)] += proportion * weight
                except ValueError:
                    pass

    return {
        d: (1 - lang_weight) * bert_scores.get(d, 0.0) + lang_weight * lang_signal[d]
        for d in Domain
    }


def _domain_text_corpus(data: GitHubData) -> str:
    # 스타 순 정렬 후 상위 3개 description 3회 반복
    # — 학습 데이터(dataset_builder.py)와 동일 방식, CI/Docker 커밋 노이즈 희석
    top_repos = sorted(data.owned_repos, key=lambda r: r.stars, reverse=True)
    top_desc = " ".join(
        " ".join([r.description] * 3) for r in top_repos[:3] if r.description
    )
    rest_desc = " ".join(r.description for r in top_repos[3:] if r.description)
    commit_text = " ".join(c.message for c in data.contributed_commits)
    pr_text = " ".join(pr.title for pr in data.contributed_prs + data.received_prs)
    review_text = " ".join(r.body for r in data.contributed_reviews + data.maintainer_reviews if r.body)
    return f"{top_desc} {rest_desc} {commit_text} {pr_text} {review_text}".strip()


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
        # 언어 바이트 비중 35% 혼합 — CI/Docker 커밋 키워드로 인한 DevOps 편향 보정
        blended = _blend_language_signal(domain_result.domains, data.languages)
        ranked = sorted(blended.items(), key=lambda x: x[1], reverse=True)
        domain_scores = {d.value: round(score * 100, 1) for d, score in blended.items()}
        raw_primary = ranked[0][0] if ranked else None
        raw_secondary = ranked[1][0] if len(ranked) > 1 else None

        _blockchain_langs = {"Solidity", "Vyper", "Move"}
        _devops_langs = {"Shell", "HCL", "Dockerfile", "Makefile", "PowerShell", "Jsonnet"}
        top_skill_set = set(_top_skills(data.languages, limit=10))
        total_lang_bytes = sum(data.languages.values()) or 1

        # Blockchain 보정: 블록체인 전용 언어 없이 Blockchain 1위 → 2위로 스왑
        if (
            raw_primary is not None
            and raw_primary.value == "Blockchain"
            and not (_blockchain_langs & top_skill_set)
            and raw_secondary is not None
        ):
            raw_primary, raw_secondary = raw_secondary, raw_primary

        # DevOps 보정: DevOps 전용 언어(Shell/HCL/Dockerfile 등) 바이트 비중 20% 미만 → 2위로 스왑
        # BERT가 CI/Docker 커밋 텍스트를 DevOps로 과도하게 분류하는 편향 보정
        if (
            raw_primary is not None
            and raw_primary.value == "DevOps"
            and raw_secondary is not None
        ):
            devops_bytes = sum(data.languages.get(l, 0) for l in _devops_langs)
            if devops_bytes / total_lang_bytes < 0.20:
                raw_primary, raw_secondary = raw_secondary, raw_primary

        primary_domain = raw_primary.value if raw_primary else None
        secondary_domain = raw_secondary.value if raw_secondary else None
        if raw_primary:
            primary_domain_enum = raw_primary

    top_skills = _top_skills(data.languages)

    # PageRank 50% + GNN 50% 혼합 — 구조적 중심성과 학습된 임베딩을 동등 반영
    combined_centrality = (graph_centrality.pagerank_score + graph_centrality.gnn_score) / 2

    final_score = ScoreCalculator().calculate(
        ScoreFeatures(
            influence_score=final_influence,
            domain_scores=domain_scores,
            graph_centrality=combined_centrality,
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
        "graph_centrality": {
            "pagerank_score": graph_centrality.pagerank_score,
            "gnn_score": graph_centrality.gnn_score,
            "combined": round(combined_centrality, 2),
        },
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
            "is_on_chain": result.is_on_chain,
            "blockchain_tx": result.blockchain_tx,
            "issuer": result.issuer,
            "issued_at": result.issued_at.isoformat(),
            "credential_subject": result.credential_subject,
        })
    except KeyError:
        return error_response("NOT_FOUND", f"'{credential_id}' VC를 찾을 수 없습니다.", status_code=404)
    except Exception as e:
        return error_response("VERIFICATION_FAILED", str(e), status_code=500)
