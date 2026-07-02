import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

DEFAULT_MODEL_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "models", "domain_bert"))


class Domain(Enum):
    BACKEND = "Backend"
    FRONTEND = "Frontend"
    AI_ML = "AI/ML"
    DEVOPS = "DevOps"
    CLOUD = "Cloud"
    SECURITY = "Security"
    BLOCKCHAIN = "Blockchain"


@dataclass
class DomainResult:
    domains: Dict[Domain, float] = field(default_factory=dict)
    primary_domain: Optional[Domain] = None
    secondary_domain: Optional[Domain] = None


class DomainAnalyzer:
    """train.py로 파인튜닝한 BERT 다중 레이블 분류기로 커밋/PR/코드리뷰 텍스트의 전문 분야를 추론한다."""

    def __init__(self, model_path: str = DEFAULT_MODEL_DIR):
        if not os.path.isdir(model_path):
            raise FileNotFoundError(
                f"도메인 분류 모델을 찾을 수 없습니다: {model_path}. "
                "ossverify/analyzer/training/dataset_builder.py 와 train.py 를 먼저 실행하세요."
            )
        os.environ.setdefault("USE_TF", "0")  # avoid transformers importing TensorFlow/Keras (not used here)
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        self.model.eval()
        self.domains = list(Domain)

    def infer(self, text_corpus: str) -> DomainResult:
        inputs = self.tokenizer(text_corpus, truncation=True, padding=True, max_length=256, return_tensors="pt")
        with self._torch.no_grad():
            logits = self.model(**inputs).logits
        probabilities = self._torch.sigmoid(logits)[0].tolist()

        domain_scores = {domain: probabilities[i] for i, domain in enumerate(self.domains)}
        ranked = sorted(domain_scores.items(), key=lambda item: item[1], reverse=True)

        return DomainResult(
            domains=domain_scores,
            primary_domain=ranked[0][0] if ranked else None,
            secondary_domain=ranked[1][0] if len(ranked) > 1 else None,
        )
