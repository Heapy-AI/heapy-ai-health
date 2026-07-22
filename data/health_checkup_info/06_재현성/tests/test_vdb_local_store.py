import json
import math
import tempfile
import unittest
from pathlib import Path

from vdb.local_store import audit, build_index, get_by_key, search_index, write_index

from scripts.evaluate_vdb import evaluate


ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "vdb/corpus/screening_core_v1.json"
INDEX_PATH = ROOT / "vdb/index/screening_core_v1.local.json"
EVALUATION_PATH = ROOT / "vdb/evaluation/screening_core_queries.json"


class LocalVdbTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        cls.index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))

    def test_index_is_complete_and_passes_quality_audit(self):
        report = audit(self.corpus, self.index)
        self.assertEqual("PASS", report["status"], report["issues"])
        self.assertEqual(30, report["index"]["indexed_chunk_count"])
        self.assertEqual(0, report["index"]["invalid_vector_count"])

    def test_vectors_are_1536_dimensional_and_normalized(self):
        for chunk in self.index["chunks"]:
            self.assertEqual(1536, len(chunk["embedding"]))
            norm = math.sqrt(sum(value * value for value in chunk["embedding"]))
            self.assertAlmostEqual(1.0, norm, places=6)

    def test_build_is_deterministic(self):
        rebuilt = build_index(self.corpus)
        self.assertEqual(self.index, rebuilt)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.json"
            write_index(rebuilt, output)
            self.assertEqual(self.index, json.loads(output.read_text(encoding="utf-8")))

    def test_search_finds_fasting_glucose(self):
        rows = search_index(self.index, "공복혈당이 높으면 무엇을 확인해야 하나요?", limit=3)
        self.assertTrue(rows)
        self.assertEqual("FASTING_GLUCOSE", rows[0]["canonical_key"])

    def test_search_finds_alcohol_guidance(self):
        rows = search_index(self.index, "술 음주 습관을 줄이고 싶어요", limit=3)
        self.assertTrue(rows)
        self.assertEqual("ALCOHOL", rows[0]["canonical_key"])

    def test_direct_key_lookup_returns_evidence(self):
        row = get_by_key(self.index, "BMI")
        self.assertIsNotNone(row)
        self.assertTrue(row["evidence"])
        self.assertNotIn("embedding", row)

    def test_unapproved_high_risk_route_is_blocked(self):
        rows = search_index(
            self.index,
            "공복혈당 종합 분석",
            route="COMPREHENSIVE_ANALYSIS",
        )
        self.assertEqual([], rows)

    def test_retrieval_evaluation_passes(self):
        suite = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
        report = evaluate(self.index, suite)
        self.assertEqual("PASS", report["status"])
        self.assertGreaterEqual(report["metrics"]["hit_at_1"], 0.9)
        self.assertEqual(1.0, report["metrics"]["hit_at_3"])


if __name__ == "__main__":
    unittest.main()
