import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CORPUS_PATH = ROOT / "vdb/corpus/screening_core_v1.json"
GENERATED_SQL_PATH = ROOT / "database/seeds/030_vdb_core.sql"
SCREENING_RULE_SQL_PATH = ROOT / "database/seeds/020_screening_dictionary.sql"
RULE_PDF_PATH = (
    ROOT
    / "storage/source_document/mohw_screening/raw/2026-01-07__MOHW-2026-6__v2026-6.pdf"
)

spec = importlib.util.spec_from_file_location("build_vdb_seed", ROOT / "scripts/build_vdb_seed.py")
build_vdb_seed = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(build_vdb_seed)


class VdbCorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))

    def test_corpus_passes_validator(self):
        self.assertEqual([], build_vdb_seed.validate(self.corpus))

    def test_mvp_has_exactly_thirty_chunks(self):
        self.assertEqual(30, len(self.corpus["chunks"]))

    def test_every_chunk_has_real_evidence_and_safe_route(self):
        for chunk in self.corpus["chunks"]:
            self.assertEqual(["SIMPLE_LOOKUP"], chunk["route_scope"])
            self.assertIn(chunk["review_status"], {"SOURCE_VERIFIED", "CLINICALLY_APPROVED"})
            for evidence in chunk["evidence"]:
                self.assertTrue(evidence["url"].startswith("https://"))
                self.assertNotIn("slack.com", evidence["url"])

    def test_generated_sql_is_synchronized(self):
        self.assertEqual(
            build_vdb_seed.build_sql(self.corpus),
            GENERATED_SQL_PATH.read_text(encoding="utf-8"),
        )

    def test_rule_pdf_checksum(self):
        digest = hashlib.sha256(RULE_PDF_PATH.read_bytes()).hexdigest()
        self.assertEqual(
            "5f804efa7257c067eabe8084cff6b9fb3d140f8f33e10234fc5423351f6ed11a",
            digest,
        )

    def test_numeric_rules_are_not_embedded_in_chunk_metadata(self):
        generated_sql = GENERATED_SQL_PATH.read_text(encoding="utf-8")
        self.assertEqual(30, generated_sql.count('"contains_numeric_rule":false'))

    def test_hdl_direction_matches_current_ministry_rule(self):
        rules = SCREENING_RULE_SQL_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "('HDL_CHOLESTEROL', 'ANY', 'NORMAL_A', 60, TRUE, NULL",
            rules,
        )
        self.assertIn(
            "('HDL_CHOLESTEROL', 'ANY', 'DISEASE_SUSPECTED', NULL, TRUE, 40, FALSE",
            rules,
        )


if __name__ == "__main__":
    unittest.main()
