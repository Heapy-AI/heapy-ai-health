"""동결 임베딩 위에서 동작하는 Linear/Softmax intent 분류기.

작성자: 김진우
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.config import EMBED_MODEL, PINECONE_DIMENSION


class Intent(str, Enum):
    """챗봇 최상위 처리 경로."""

    SIMPLE_LOOKUP = "simple_lookup"
    COMPREHENSIVE = "comprehensive"
    GENERAL_CHAT = "general_chat"
    IGNORE = "ignore"


INTENT_LABELS = tuple(intent.value for intent in Intent)


@dataclass(frozen=True)
class IntentPrediction:
    """분류 결과와 검토가 필요한 저신뢰 결과를 함께 표현한다."""

    intent: Intent
    confidence: float
    probabilities: dict[str, float]
    uncertain: bool
    model_version: str


class LinearIntentClassifier:
    """JSON 가중치를 사용하는 768→4 선형 분류기."""

    def __init__(
        self,
        weights: list[list[float]],
        bias: list[float],
        labels: list[str],
        minimum_confidence: float,
        model_version: str,
    ) -> None:
        if labels != list(INTENT_LABELS):
            raise ValueError(
                f"intent 라벨 순서가 올바르지 않습니다: {labels}"
            )
        if len(weights) != len(labels) or len(bias) != len(labels):
            raise ValueError("intent 가중치 또는 bias 개수가 올바르지 않습니다.")
        if any(len(row) != PINECONE_DIMENSION for row in weights):
            raise ValueError(
                f"intent 가중치 차원은 {PINECONE_DIMENSION}이어야 합니다."
            )
        if not 0.0 < minimum_confidence < 1.0:
            raise ValueError("최소 신뢰도는 0과 1 사이여야 합니다.")

        self._weights = weights
        self._bias = bias
        self._labels = labels
        self._minimum_confidence = minimum_confidence
        self.model_version = model_version

    @classmethod
    def from_file(
        cls,
        artifact_path: Path,
        minimum_confidence: float,
    ) -> "LinearIntentClassifier":
        """검증된 JSON 모델 artifact를 불러온다."""
        payload: dict[str, Any] = json.loads(
            artifact_path.read_text(encoding="utf-8")
        )
        if payload.get("schema_version") != 1:
            raise ValueError("지원하지 않는 intent 모델 schema_version입니다.")
        if payload.get("model_type") != "linear_softmax":
            raise ValueError("intent 모델 유형은 linear_softmax여야 합니다.")
        if payload.get("embedding_model") != EMBED_MODEL:
            raise ValueError(
                "intent 모델의 임베딩 모델이 서버 설정과 다릅니다: "
                f"{payload.get('embedding_model')} != {EMBED_MODEL}"
            )
        if int(payload.get("embedding_dimension", 0)) != PINECONE_DIMENSION:
            raise ValueError(
                "intent 모델의 임베딩 차원이 서버 설정과 다릅니다."
            )

        return cls(
            weights=payload["weights"],
            bias=payload["bias"],
            labels=payload["labels"],
            minimum_confidence=minimum_confidence,
            model_version=str(payload.get("model_version", "unknown")),
        )

    def predict(self, embedding: list[float]) -> IntentPrediction:
        """임베딩에 Linear/Softmax를 적용해 intent 확률을 반환한다."""
        if len(embedding) != PINECONE_DIMENSION:
            raise ValueError(
                f"intent 입력 차원은 {PINECONE_DIMENSION}이어야 합니다."
            )

        logits = [
            sum(weight * value for weight, value in zip(row, embedding, strict=True))
            + bias
            for row, bias in zip(self._weights, self._bias, strict=True)
        ]
        max_logit = max(logits)
        exponentials = [math.exp(logit - max_logit) for logit in logits]
        denominator = sum(exponentials)
        probabilities = [value / denominator for value in exponentials]
        best_index = max(range(len(probabilities)), key=probabilities.__getitem__)
        confidence = probabilities[best_index]

        return IntentPrediction(
            intent=Intent(self._labels[best_index]),
            confidence=confidence,
            probabilities=dict(zip(self._labels, probabilities, strict=True)),
            uncertain=confidence < self._minimum_confidence,
            model_version=self.model_version,
        )
