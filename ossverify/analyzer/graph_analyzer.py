from dataclasses import dataclass


@dataclass
class GraphCentrality:
    pagerank_score: float
    gnn_score: float


class GraphAnalyzer:
    """개발자-프로젝트 관계망에서 PageRank/GNN으로 영향력을 계산한다."""

    def build_graph(self, data):
        raise NotImplementedError

    def calculate_centrality(self, username: str) -> GraphCentrality:
        raise NotImplementedError
