"""Retrieval 평가 지표와 골든 ID 정규화 단위 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest

from evaluation.retrieval_evaluator import (
    calculate_retrieval_metrics,
    normalize_document_id,
)


class RetrievalEvaluatorTest(unittest.TestCase):
    def test_health_screening_id_is_normalized_to_pinecone_record_id(self) -> None:
        self.assertEqual(
            normalize_document_id(
                "health_screening",
                "screening:fasting_glucose:001",
            ),
            "FASTING_GLUCOSE",
        )

    def test_hit_recall_and_mrr_are_calculated_separately(self) -> None:
        metrics = calculate_retrieval_metrics(
            retrieved_ids=["noise", "acceptable-extra", "gold-1"],
            gold_ids=["gold-1", "gold-2"],
            acceptable_ids=["gold-1", "gold-2", "acceptable-extra"],
        )

        self.assertEqual(metrics.hit_at_1, 0.0)
        self.assertEqual(metrics.hit_at_3, 1.0)
        self.assertEqual(metrics.hit_at_5, 1.0)
        self.assertEqual(metrics.recall_at_1, 0.0)
        self.assertEqual(metrics.recall_at_3, 0.5)
        self.assertEqual(metrics.recall_at_5, 0.5)
        self.assertEqual(metrics.mrr_at_10, 0.5)

    def test_duplicate_retrieved_ids_do_not_inflate_recall(self) -> None:
        metrics = calculate_retrieval_metrics(
            retrieved_ids=["gold-1", "gold-1", "gold-2"],
            gold_ids=["gold-1", "gold-2"],
            acceptable_ids=["gold-1", "gold-2"],
        )

        self.assertEqual(metrics.recall_at_1, 0.5)
        self.assertEqual(metrics.recall_at_3, 1.0)
        self.assertEqual(metrics.mrr_at_10, 1.0)

    def test_answerable_question_requires_gold_and_acceptable_ids(self) -> None:
        with self.assertRaises(ValueError):
            calculate_retrieval_metrics(["record"], [], ["record"])
        with self.assertRaises(ValueError):
            calculate_retrieval_metrics(["record"], ["record"], [])


if __name__ == "__main__":
    unittest.main()
