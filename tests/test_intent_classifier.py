"""Intent Linear/Softmax 분류기 단위 테스트.

작성자: 김진우
"""
import unittest

from app.core.config import PINECONE_DIMENSION
from app.core.state import state
from app.routers.intent import classify_intent
from app.schemas.intent import IntentClassifyRequest
from app.services.intent_classifier import INTENT_LABELS, Intent, LinearIntentClassifier


class LinearIntentClassifierTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_state = dict(state)

    def tearDown(self) -> None:
        state.clear()
        state.update(self._original_state)

    def _build_classifier(self, bias: list[float]) -> LinearIntentClassifier:
        weights = [
            [0.0] * PINECONE_DIMENSION
            for _ in INTENT_LABELS
        ]
        return LinearIntentClassifier(
            weights=weights,
            bias=bias,
            labels=list(INTENT_LABELS),
            minimum_confidence=0.55,
            model_version="test-model",
        )

    def test_highest_logit_is_selected(self) -> None:
        classifier = self._build_classifier([4.0, 1.0, 0.0, -1.0])

        prediction = classifier.predict([0.0] * PINECONE_DIMENSION)

        self.assertEqual(prediction.intent, Intent.SIMPLE_LOOKUP)
        self.assertFalse(prediction.uncertain)
        self.assertEqual(prediction.model_version, "test-model")
        self.assertAlmostEqual(sum(prediction.probabilities.values()), 1.0)

    def test_low_confidence_is_marked_uncertain(self) -> None:
        classifier = self._build_classifier([0.0, 0.0, 0.0, 0.0])

        prediction = classifier.predict([0.0] * PINECONE_DIMENSION)

        self.assertTrue(prediction.uncertain)
        self.assertAlmostEqual(prediction.confidence, 0.25)

    def test_invalid_embedding_dimension_is_rejected(self) -> None:
        classifier = self._build_classifier([1.0, 0.0, 0.0, 0.0])

        with self.assertRaises(ValueError):
            classifier.predict([0.0] * (PINECONE_DIMENSION - 1))

    def test_api_reuses_shared_query_embedding(self) -> None:
        class FakeVectorSearch:
            def embed_query(self, question: str) -> list[float]:
                self.question = question
                return [0.0] * PINECONE_DIMENSION

        vector_search = FakeVectorSearch()
        state["vector_search"] = vector_search
        state["intent_classifier"] = self._build_classifier([0.0, 3.0, 0.0, 0.0])

        response = classify_intent(
            IntentClassifyRequest(question="최근 검사 결과가 왜 높지?")
        )

        self.assertEqual(response.intent, Intent.COMPREHENSIVE.value)
        self.assertEqual(vector_search.question, "최근 검사 결과가 왜 높지?")
        self.assertEqual(response.source, "linear_classifier")
        self.assertFalse(response.guard_triggered)

    def test_api_guard_blocks_before_embedding(self) -> None:
        class FailIfCalledVectorSearch:
            def embed_query(self, question: str) -> list[float]:
                raise AssertionError("Guard 작동 시 임베딩을 호출하면 안 됩니다.")

        state["vector_search"] = FailIfCalledVectorSearch()
        state["intent_classifier"] = self._build_classifier([4.0, 0.0, 0.0, 0.0])

        response = classify_intent(
            IntentClassifyRequest(question="오늘 약 두 알 먹어도 돼?")
        )

        self.assertEqual(response.intent, Intent.IGNORE.value)
        self.assertEqual(response.confidence, 1.0)
        self.assertFalse(response.uncertain)
        self.assertEqual(response.source, "safety_guard")
        self.assertTrue(response.guard_triggered)
        self.assertEqual(response.guard_reason, "medication_decision")


if __name__ == "__main__":
    unittest.main()
