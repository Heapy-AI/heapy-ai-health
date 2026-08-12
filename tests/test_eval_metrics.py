"""골든셋 평가 지표 계산 단위 테스트."""
from __future__ import annotations

import math
import unittest

from evaluation.eval import metrics as M


def _document(record_id: str, source: str = "https://example.com") -> dict:
    return {
        "rank": 0,
        "record_id": record_id,
        "collection": "disease_info",
        "score": 0.5,
        "source_label": "질병관리청",
        "source": source,
        "section": "개요",
        "title": "t",
        "text": "본문",
    }


def _record(**overrides) -> dict:
    record = {
        "question_id": "q1",
        "question": "질문",
        "status": "ok",
        "gold": {
            "answerable": True,
            "reference_answer": "토혈은 상부위장관 출혈로 피를 토하는 것입니다.",
            "gold_document_ids": ["kdca-6256-0"],
            "acceptable_document_ids": ["kdca-6256-0"],
            "source_uri": "https://example.com",
        },
        "retrieved_documents": [_document("kdca-6256-0"), _document("kdca-9999-3")],
        "candidate_documents": [_document("kdca-6256-0"), _document("kdca-9999-3")],
        "cited_chunk_ids": ["C1"],
        "answer": "토혈은 상부위장관에서 출혈이 생겨 피를 토하는 것입니다.",
        "grounded": True,
    }
    record.update(overrides)
    return record


class DocumentIdNormalizationTest(unittest.TestCase):
    def test_screening_id_maps_to_canonical_key(self) -> None:
        self.assertEqual(M.normalize_document_id("screening:chest_xray:001"), "CHEST_XRAY")
        self.assertEqual(
            M.normalize_document_id("screening:reference_range_limits:001"),
            "REFERENCE_RANGE_LIMITS",
        )

    def test_other_ids_are_unchanged(self) -> None:
        self.assertEqual(M.normalize_document_id("kdca-6256-0"), "kdca-6256-0")
        self.assertEqual(
            M.normalize_document_id("eyak:200004060:interactions:001"),
            "eyak:200004060:interactions:001",
        )

    def test_document_group_collapses_sections(self) -> None:
        self.assertEqual(M.document_group("kdca-6256-17"), "kdca-6256")
        self.assertEqual(M.document_group("kdca-6256-0"), "kdca-6256")
        self.assertEqual(
            M.document_group("eyak:200004060:interactions:001"), "eyak:200004060"
        )
        self.assertEqual(M.document_group("screening:alt:001"), "ALT")


class RetrievalMetricTest(unittest.TestCase):
    def test_hit_and_rank_metrics(self) -> None:
        retrieved = ["a", "b", "c", "d"]
        relevant = {"c"}
        self.assertEqual(M.hit_at_k(retrieved, relevant, 1), 0.0)
        self.assertEqual(M.hit_at_k(retrieved, relevant, 3), 1.0)
        self.assertAlmostEqual(M.reciprocal_rank(retrieved, relevant), 1 / 3)

    def test_recall_and_precision(self) -> None:
        self.assertAlmostEqual(M.context_recall_ids(["a", "b"], {"a", "c"}), 0.5)
        self.assertAlmostEqual(M.context_precision_ids(["a", "b"], {"a"}), 0.5)

    def test_no_relevant_documents_yields_nan(self) -> None:
        self.assertTrue(math.isnan(M.hit_at_k(["a"], set(), 3)))
        self.assertTrue(math.isnan(M.context_recall_ids(["a"], set())))

    def test_ndcg_rewards_higher_rank(self) -> None:
        early = M.ndcg_at_k(["a", "x", "y"], {"a"}, 10)
        late = M.ndcg_at_k(["x", "y", "a"], {"a"}, 10)
        self.assertGreater(early, late)
        self.assertAlmostEqual(early, 1.0)


class CitationMetricTest(unittest.TestCase):
    def test_labels_resolve_to_record_ids(self) -> None:
        resolved = M.citation_ids_to_record_ids(["C1", "C3"], ["a", "b", "c"])
        self.assertEqual(resolved, ["a", "c"])

    def test_out_of_range_and_malformed_labels_are_dropped(self) -> None:
        self.assertEqual(M.citation_ids_to_record_ids(["C9", "X1", ""], ["a"]), [])

    def test_citation_accuracy(self) -> None:
        self.assertAlmostEqual(M.citation_accuracy(["a", "b"], {"a"}), 0.5)
        self.assertTrue(math.isnan(M.citation_accuracy([], {"a"})))


class TextMetricTest(unittest.TestCase):
    def test_identical_text_scores_one(self) -> None:
        self.assertAlmostEqual(M.char_ngram_f1("공복혈당 정상", "공복혈당 정상"), 1.0)
        self.assertAlmostEqual(M.token_f1("공복혈당 정상", "공복혈당 정상"), 1.0)

    def test_disjoint_text_scores_zero(self) -> None:
        self.assertEqual(M.char_ngram_f1("가나다", "라마바"), 0.0)

    def test_reference_coverage_ignores_spacing(self) -> None:
        self.assertEqual(M.reference_coverage("답은 급성 부고환염 입니다", "급성부고환염"), 1.0)
        self.assertEqual(M.reference_coverage("답은 감기입니다", "급성부고환염"), 0.0)

    def test_cosine_similarity(self) -> None:
        self.assertAlmostEqual(M.cosine_similarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(M.cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertEqual(M.cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0)


class AggregationTest(unittest.TestCase):
    def test_mean_skips_nan(self) -> None:
        self.assertAlmostEqual(M.mean([1.0, float("nan"), 3.0]), 2.0)
        self.assertTrue(math.isnan(M.mean([float("nan")])))

    def test_percentile_interpolates(self) -> None:
        self.assertAlmostEqual(M.percentile([1.0, 2.0, 3.0, 4.0], 0.5), 2.5)
        self.assertAlmostEqual(M.percentile([5.0], 0.9), 5.0)


class AbstentionTest(unittest.TestCase):
    def test_constants_match_application_responses(self) -> None:
        """앱의 고정 거절 문구가 바뀌면 거절 지표가 조용히 틀어지므로 함께 검사한다."""
        from app.services.chat_orchestrator import GENERAL_IGNORE_ANSWER
        from app.services.grounded_rag import NOT_GROUNDED_ANSWER

        self.assertEqual(
            M.ABSTENTION_ANSWERS,
            {NOT_GROUNDED_ANSWER, GENERAL_IGNORE_ANSWER},
        )

    def test_fixed_refusal_answers_count_as_abstention(self) -> None:
        from app.services.grounded_rag import NOT_GROUNDED_ANSWER

        self.assertTrue(M.is_abstention(NOT_GROUNDED_ANSWER, True))
        self.assertTrue(M.is_abstention("정상 답변", False))
        self.assertFalse(M.is_abstention("정상 답변", True))


class DeterministicMetricsTest(unittest.TestCase):
    def test_full_record_scoring(self) -> None:
        result = M.deterministic_metrics(_record())
        self.assertEqual(result["hit@1"], 1.0)
        self.assertAlmostEqual(result["context_recall_id"], 1.0)
        self.assertAlmostEqual(result["context_precision_id"], 0.5)
        self.assertEqual(result["citation_accuracy"], 1.0)
        self.assertEqual(result["resolved_cited_record_ids"], ["kdca-6256-0"])
        self.assertEqual(result["source_uri_match"], 1.0)
        self.assertEqual(result["is_abstention"], 0.0)
        self.assertEqual(result["abstention_correct"], 1.0)

    def test_screening_id_mismatch_is_normalized(self) -> None:
        record = _record(
            gold={
                "answerable": True,
                "reference_answer": "흉부방사선촬영 설명",
                "gold_document_ids": ["screening:chest_xray:001"],
                "acceptable_document_ids": ["screening:chest_xray:001"],
                "source_uri": "https://example.com",
            },
            retrieved_documents=[_document("CHEST_XRAY")],
            candidate_documents=[_document("CHEST_XRAY")],
        )
        result = M.deterministic_metrics(record)
        self.assertEqual(result["hit@1"], 1.0)
        self.assertAlmostEqual(result["context_recall_id"], 1.0)

    def test_group_hit_credits_other_section_of_same_disease(self) -> None:
        record = _record(
            retrieved_documents=[_document("kdca-6256-17")],
            candidate_documents=[_document("kdca-6256-17")],
            cited_chunk_ids=[],
        )
        result = M.deterministic_metrics(record)
        self.assertEqual(result["hit@1"], 0.0)
        self.assertEqual(result["group_hit@1"], 1.0)

    def test_unanswerable_question_expects_abstention(self) -> None:
        record = _record(
            gold={
                "answerable": False,
                "reference_answer": "답변할 수 없습니다.",
                "gold_document_ids": [],
                "acceptable_document_ids": [],
                "source_uri": "",
            },
            answer="지식베이스에 근거 없음",
            grounded=False,
        )
        result = M.deterministic_metrics(record)
        self.assertEqual(result["is_abstention"], 1.0)
        self.assertEqual(result["abstention_correct"], 1.0)
        self.assertTrue(math.isnan(result["hit@1"]))


if __name__ == "__main__":
    unittest.main()
