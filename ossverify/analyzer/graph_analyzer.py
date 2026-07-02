import math
from dataclasses import dataclass
from typing import Optional

import networkx as nx

from ossverify.collector.github_collector import GitHubData


@dataclass
class GraphCentrality:
    pagerank_score: float
    gnn_score: float


class GraphAnalyzer:
    """개발자-프로젝트 이분 그래프를 구성하고 PageRank로 영향력 중심성을 계산한다.

    노드 종류:
      - developer: GitHub 사용자 (분석 대상 + 외부 기여자)
      - repo:      GitHub 저장소

    엣지 방향 및 가중치:
      developer → repo  기여 행위 (PR 병합=3, PR=1, 리뷰→변경=2, 리뷰=1, 커밋=0.5)
      repo → developer  저장소가 기여자를 역방향으로 endorses (기여 가중치 × 0.5)
      repo → 소유자     인기(star) 기반 보너스 (log10(stars+1))
    """

    def __init__(self) -> None:
        self._graph: Optional[nx.DiGraph] = None

    def build_graph(self, data: GitHubData) -> nx.DiGraph:
        G = nx.DiGraph()
        username = data.username
        G.add_node(username, node_type="developer")

        def _add_contrib_edge(src: str, dst: str, w: float) -> None:
            if G.has_edge(src, dst):
                G[src][dst]["weight"] += w
            else:
                G.add_edge(src, dst, weight=w)

        # 기여 PR (user → 외부 repo)
        for pr in data.contributed_prs:
            w = 3.0 if pr.merged else 1.0
            if pr.approved:
                w += 1.0
            G.add_node(pr.repo_full_name, node_type="repo", stars=pr.repo_stars)
            _add_contrib_edge(username, pr.repo_full_name, w)
            _add_contrib_edge(pr.repo_full_name, username, w * 0.5)

        # 기여 리뷰 (user → 외부 repo)
        for review in data.contributed_reviews:
            w = 2.0 if review.led_to_change else 1.0
            G.add_node(review.repo_full_name, node_type="repo")
            _add_contrib_edge(username, review.repo_full_name, w)

        # 기여 커밋 (user → 외부 repo)
        for commit in data.contributed_commits:
            G.add_node(commit.repo_full_name, node_type="repo")
            _add_contrib_edge(username, commit.repo_full_name, 0.5)

        # 받은 PR (외부 contributor → user의 repo → user)
        for pr in data.received_prs:
            contributor = pr.author
            if not contributor or contributor == username:
                continue
            G.add_node(contributor, node_type="developer")
            G.add_node(pr.repo_full_name, node_type="repo")
            w = 2.0 if pr.merged else 1.0
            _add_contrib_edge(contributor, pr.repo_full_name, w)
            # 소유 repo가 user를 역방향 endorses
            _add_contrib_edge(pr.repo_full_name, username, w * 0.3)

        # 소유 저장소 star 보너스 (popular repo → user)
        for repo in data.owned_repos:
            G.add_node(repo.full_name, node_type="repo", stars=repo.stars)
            if repo.stars > 0:
                star_w = math.log10(repo.stars + 1)
                _add_contrib_edge(repo.full_name, username, star_w)

        self._graph = G
        return G

    def calculate_centrality(self, data: GitHubData) -> GraphCentrality:
        if self._graph is None:
            self.build_graph(data)

        G = self._graph
        if len(G.nodes) < 2:
            return GraphCentrality(pagerank_score=0.0, gnn_score=0.0)

        pagerank = nx.pagerank(G, weight="weight", alpha=0.85, max_iter=200)
        user_pr = pagerank.get(data.username, 0.0)

        # 그래프 내 최대 PageRank 대비 비율로 0-100 정규화
        max_pr = max(pagerank.values()) if pagerank else 1.0
        normalized = min(user_pr / max_pr * 100, 100.0) if max_pr > 0 else 0.0

        return GraphCentrality(pagerank_score=round(normalized, 2), gnn_score=0.0)
