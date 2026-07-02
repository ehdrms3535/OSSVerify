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
    """개발자-프로젝트 이분 그래프를 구성하고 PageRank + GCN Autoencoder로 영향력 중심성을 계산한다.

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

    # ──────────────────────────────────────────────────────────────────────────
    # GNN (Graph Autoencoder)
    # ──────────────────────────────────────────────────────────────────────────

    def _gnn_score(self, data: GitHubData) -> float:
        """2-layer GCN Graph Autoencoder 학습 후 임베딩 L2 norm 기반 점수 (0–100).

        비지도 학습: 링크 예측 BCE 손실로 노드 임베딩을 학습한다.
        허브 노드(많은 연결·높은 가중치)는 더 큰 임베딩 norm을 가지는 경향이 있어
        target 개발자의 norm을 developer 노드 내 최대값으로 정규화해 점수를 산출한다.
        """
        try:
            import torch
            import torch.nn as nn
            import torch.nn.functional as F
        except ImportError:
            return 0.0

        G = self._graph
        nodes = list(G.nodes())
        n = len(nodes)
        if n < 3:
            return 0.0

        node_idx = {node: i for i, node in enumerate(nodes)}
        target_idx = node_idx.get(data.username)
        if target_idx is None:
            return 0.0

        # ── 노드 피처 행렬 (5개 피처) ────────────────────────────────────────
        out_weights = [
            sum(d["weight"] for _, _, d in G.out_edges(nd, data=True)) for nd in nodes
        ]
        in_weights = [
            sum(d["weight"] for _, _, d in G.in_edges(nd, data=True)) for nd in nodes
        ]
        max_out   = max(out_weights) or 1.0
        max_in    = max(in_weights)  or 1.0
        max_stars = max((G.nodes[nd].get("stars", 0) for nd in nodes), default=0) or 1.0

        rows = []
        for i, nd in enumerate(nodes):
            attr = G.nodes[nd]
            rows.append([
                1.0 if nd == data.username else 0.0,
                1.0 if attr.get("node_type") == "developer" else 0.0,
                math.log1p(out_weights[i]) / math.log1p(max_out),
                math.log1p(in_weights[i])  / math.log1p(max_in),
                math.log1p(attr.get("stars", 0)) / math.log1p(max_stars),
            ])
        X = torch.tensor(rows, dtype=torch.float32)

        # ── 정규화 인접 행렬 (대칭화 + self-loop) ────────────────────────────
        A = torch.zeros(n, n, dtype=torch.float32)
        for src, dst, d in G.edges(data=True):
            si, di = node_idx[src], node_idx[dst]
            w = float(d.get("weight", 1.0))
            A[si, di] += w
            A[di, si] += w  # 대칭화
        A.fill_diagonal_(1.0)  # self-loop

        deg = A.sum(1)
        d_inv_sqrt = deg.pow(-0.5).clamp(max=1e4)
        # D^(-1/2) A D^(-1/2)
        A_norm = d_inv_sqrt.unsqueeze(1) * A * d_inv_sqrt.unsqueeze(0)

        # ── GCN 인코더 ────────────────────────────────────────────────────────
        IN_DIM, HIDDEN, EMBED = X.shape[1], 32, 16

        class _GCNEncoder(nn.Module):
            def __init__(self, in_dim: int, hidden: int, embed: int) -> None:
                super().__init__()
                self.W1 = nn.Linear(in_dim, hidden, bias=False)
                self.W2 = nn.Linear(hidden, embed, bias=False)

            def forward(
                self,
                x: "torch.Tensor",
                adj: "torch.Tensor",
            ) -> "torch.Tensor":
                h = F.relu(adj @ self.W1(x))
                return adj @ self.W2(h)

        model = _GCNEncoder(IN_DIM, HIDDEN, EMBED)
        optimizer = torch.optim.Adam(model.parameters(), lr=0.01)

        # 재구성 타겟: self-loop 제거 후 이진화
        A_target = (A.clone().fill_diagonal_(0) > 0).float()

        # 노드 수에 따라 에폭 조정 — CPU 학습 시간 제한
        epochs = 150 if n < 100 else 100 if n < 500 else 50

        model.train()
        for _ in range(epochs):
            optimizer.zero_grad()
            z = model(X, A_norm)
            recon = torch.sigmoid(z @ z.t())
            loss = F.binary_cross_entropy(recon, A_target)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            z = model(X, A_norm)

        # developer 노드 내 최대 norm으로 정규화
        norms = z.norm(dim=1)
        dev_indices = [
            i for i, nd in enumerate(nodes)
            if G.nodes[nd].get("node_type") == "developer"
        ]
        if not dev_indices:
            return 0.0
        max_dev_norm = norms[dev_indices].max().item()
        if max_dev_norm == 0:
            return 0.0

        score = norms[target_idx].item() / max_dev_norm * 100
        return round(min(score, 100.0), 2)

    # ──────────────────────────────────────────────────────────────────────────

    def calculate_centrality(self, data: GitHubData) -> GraphCentrality:
        if self._graph is None:
            self.build_graph(data)

        G = self._graph
        if len(G.nodes) < 2:
            return GraphCentrality(pagerank_score=0.0, gnn_score=0.0)

        pagerank = nx.pagerank(G, weight="weight", alpha=0.85, max_iter=200)
        user_pr = pagerank.get(data.username, 0.0)
        max_pr = max(pagerank.values()) if pagerank else 1.0
        normalized = min(user_pr / max_pr * 100, 100.0) if max_pr > 0 else 0.0

        gnn = self._gnn_score(data)

        return GraphCentrality(pagerank_score=round(normalized, 2), gnn_score=gnn)
