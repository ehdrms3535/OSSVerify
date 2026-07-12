from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ossverify.collector.github_collector import GitHubData

# 언어 → 관련 프레임워크 (커밋/PR 텍스트 감지용)
_FRAMEWORK_MAP: Dict[str, List[str]] = {
    "Python":     ["Django", "Flask", "FastAPI", "Celery", "SQLAlchemy",
                   "NumPy", "Pandas", "TensorFlow", "PyTorch", "Scikit-learn", "Pytest"],
    "JavaScript": ["React", "Vue", "Angular", "Express", "Next.js", "Node.js", "Webpack", "Jest"],
    "TypeScript": ["React", "Next.js", "NestJS", "Angular", "Prisma"],
    "Java":       ["Spring Boot", "Spring", "Maven", "Gradle", "Hibernate", "JPA", "JUnit", "Kafka"],
    "Kotlin":     ["Spring Boot", "Ktor", "Coroutines", "Android", "Jetpack"],
    "Go":         ["Gin", "Echo", "gRPC", "Fiber"],
    "Rust":       ["Tokio", "Actix", "Axum", "WebAssembly"],
    "C++":        ["CMake", "Boost", "OpenCV", "CUDA", "Qt"],
    "C":          ["GCC", "Linux Kernel", "OpenSSL"],
    "Ruby":       ["Rails", "Sinatra", "RSpec", "Sidekiq"],
    "PHP":        ["Laravel", "Symfony", "WordPress", "Composer"],
    "Swift":      ["SwiftUI", "UIKit", "Combine", "Vapor"],
    "Scala":      ["Akka", "Spark", "Play", "ZIO"],
    "Shell":      ["Bash", "GitHub Actions", "Docker", "Kubernetes"],
    "Solidity":   ["Hardhat", "Truffle", "OpenZeppelin", "Foundry"],
    "CUDA":       ["cuDNN", "TensorRT", "PyTorch"],
    "R":          ["ggplot2", "dplyr", "Shiny", "tidyverse"],
}

# 언어별 PR/커밋 키워드 카운팅 규칙
# 각 항목: (레이블, [검색 키워드 소문자])
_TECH_KEYWORD_RULES: Dict[str, List[Tuple[str, List[str]]]] = {
    "Java": [
        ("Spring Boot PR",  ["spring boot", "springboot", "spring-boot"]),
        ("REST API PR",     ["rest api", "restapi", "@restcontroller", "requestmapping", "rest endpoint"]),
        ("JPA 커밋",         ["jpa", "hibernate", "@entity", "entitymanager"]),
        ("Kafka 커밋",       ["kafka", "consumer", "producer", "topic"]),
        ("Maven 빌드",       ["maven", "pom.xml", "mvn"]),
        ("Gradle 빌드",      ["gradle", "build.gradle"]),
    ],
    "Kotlin": [
        ("Spring Boot PR",  ["spring boot", "springboot"]),
        ("Coroutine 커밋",  ["coroutine", "suspend", "flow", "async"]),
        ("Android PR",      ["android", "activity", "fragment", "jetpack"]),
    ],
    "Python": [
        ("Django PR",       ["django"]),
        ("FastAPI PR",      ["fastapi", "fast api"]),
        ("Flask PR",        ["flask"]),
        ("AI/ML 커밋",      ["pandas", "numpy", "dataframe", "tensor", "model.fit", "train"]),
        ("pytest 커밋",     ["pytest", "test_", "assert ", "fixture"]),
        ("API 커밋",        ["api", "endpoint", "router", "schema"]),
    ],
    "JavaScript": [
        ("React PR",        ["react", "component", "jsx", "hook", "usestate"]),
        ("Next.js PR",      ["next.js", "nextjs", "app router", "pages/"]),
        ("Node.js PR",      ["node", "express", "middleware"]),
        ("테스트 커밋",      ["jest", "test(", "describe(", "expect("]),
    ],
    "TypeScript": [
        ("NestJS PR",       ["nestjs", "@controller", "@injectable", "@module"]),
        ("React PR",        ["react", "tsx", "component", "hook"]),
        ("타입 정의",        ["interface ", "type ", "generic", "enum "]),
    ],
    "Go": [
        ("API PR",          ["gin", "echo", "fiber", "router", "handler"]),
        ("gRPC PR",         ["grpc", "protobuf", "proto"]),
        ("동시성 커밋",      ["goroutine", "channel", "mutex", "sync"]),
    ],
    "Rust": [
        ("비동기 PR",        ["tokio", "async fn", "await", "future"]),
        ("웹 PR",            ["actix", "axum", "warp", "rocket"]),
    ],
    "C++": [
        ("CUDA 커밋",        ["cuda", "gpu", "kernel<<<", "__global__"]),
        ("OpenCV 커밋",      ["opencv", "cv::", "mat ", "imshow"]),
        ("CMake 빌드",       ["cmake", "cmakelists", "add_executable"]),
    ],
    "Solidity": [
        ("스마트 컨트랙트", ["contract ", "solidity", "pragma"]),
        ("DeFi 커밋",       ["defi", "erc20", "erc721", "swap"]),
        ("테스트 커밋",     ["hardhat", "truffle", "ethers", "waffle"]),
    ],
    "Shell": [
        ("CI/CD 커밋",      ["ci", "cd", "pipeline", "deploy", "workflow"]),
        ("Docker 커밋",     ["docker", "container", "image", "compose"]),
        ("k8s 커밋",        ["kubectl", "kubernetes", "k8s", "helm"]),
    ],
}


@dataclass
class SkillEvidence:
    skill: str
    confidence: float                       # 0–100 (바이트 비중)
    repo_count: int
    commit_count: int
    pr_count: int
    file_pattern_counts: List[Tuple[str, int]] = field(default_factory=list)  # ("Dockerfile", 3)
    keyword_counts: List[Tuple[str, int]] = field(default_factory=list)       # ("Spring Boot PR", 12)
    detected_frameworks: List[str] = field(default_factory=list)
    evidence_items: List[str] = field(default_factory=list)                   # UI 표시용 문자열


class SkillEvidenceAnalyzer:
    def analyze(
        self,
        data: GitHubData,
        top_skills: List[str],
        file_patterns: Dict[str, List[Tuple[str, int]]] = None,
    ) -> List[SkillEvidence]:
        if file_patterns is None:
            file_patterns = {}

        total_bytes = sum(data.languages.values()) or 1

        # 모든 커밋·PR 텍스트를 소문자로 미리 준비
        all_commit_texts = [c.message.lower() for c in data.contributed_commits]
        all_pr_texts = [pr.title.lower() for pr in data.contributed_prs]

        results: List[SkillEvidence] = []

        for skill in top_skills[:6]:
            byte_count = data.languages.get(skill, 0)
            confidence = round(min(byte_count / total_bytes * 100, 100.0), 1)

            # ── 언어별 repo / commit / PR 집계 ──────────────────────────────
            matching_repos = {
                fn for fn, lang in data.repo_languages.items() if lang == skill
            }
            commit_count = sum(1 for c in data.contributed_commits
                               if c.repo_full_name in matching_repos)
            pr_count = sum(1 for pr in data.contributed_prs
                           if pr.repo_full_name in matching_repos)

            # ── 프레임워크 감지 (커밋+PR 텍스트) ────────────────────────────
            skill_commit_texts = [c.message.lower() for c in data.contributed_commits
                                  if c.repo_full_name in matching_repos]
            skill_pr_texts = [pr.title.lower() for pr in data.contributed_prs
                              if pr.repo_full_name in matching_repos]
            combined_text = " ".join(skill_commit_texts + skill_pr_texts)
            detected = [fw for fw in _FRAMEWORK_MAP.get(skill, [])
                        if fw.lower() in combined_text][:4]

            # ── 기술 키워드별 PR/커밋 카운팅 ─────────────────────────────────
            keyword_counts: List[Tuple[str, int]] = []
            for label, kws in _TECH_KEYWORD_RULES.get(skill, []):
                # PR 제목 + 커밋 메시지 전체에서 키워드 검색 (repo 무관)
                count = sum(
                    1 for text in all_commit_texts + all_pr_texts
                    if any(kw in text for kw in kws)
                )
                if count > 0:
                    keyword_counts.append((label, count))

            # ── 파일 패턴 카운팅 (GitHub code search 결과) ──────────────────
            lang_files = file_patterns.get(skill, [])
            infra_files = file_patterns.get("_infra", []) if skill == top_skills[0] else []
            file_pattern_counts = lang_files + infra_files

            # ── UI 표시용 evidence_items 생성 ────────────────────────────────
            evidence: List[str] = []
            if matching_repos:
                evidence.append(f"{skill} 주요 저장소 {len(matching_repos)}개")
            if commit_count:
                evidence.append(f"커밋 {commit_count}건")
            if pr_count:
                evidence.append(f"PR {pr_count}건")
            # 파일 패턴 ("Dockerfile 3개")
            for fp_label, fp_count in file_pattern_counts:
                evidence.append(f"{fp_label} {fp_count}개")
            # 기술 키워드 ("Spring Boot PR 12건")
            for kw_label, kw_count in keyword_counts[:3]:
                evidence.append(f"{kw_label} {kw_count}건")
            # 감지된 프레임워크 (파일·키워드 없을 때 보조)
            if not file_pattern_counts and not keyword_counts:
                evidence.extend(detected[:3])

            results.append(SkillEvidence(
                skill=skill,
                confidence=confidence,
                repo_count=len(matching_repos),
                commit_count=commit_count,
                pr_count=pr_count,
                file_pattern_counts=file_pattern_counts,
                keyword_counts=keyword_counts,
                detected_frameworks=detected,
                evidence_items=evidence,
            ))

        return results
