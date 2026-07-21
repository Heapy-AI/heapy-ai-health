import csv
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/preprocess_nhis_screening.py"
OUTPUT_DIR = ROOT / "storage/source_document/nhis_screening/normalized"

spec = importlib.util.spec_from_file_location("nhis_preprocess", SCRIPT_PATH)
nhis_preprocess = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(nhis_preprocess)


def read_csv(filename):
    with (OUTPUT_DIR / filename).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class NHISScreeningPreprocessingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claim_history = read_csv(nhis_preprocess.CLAIM_HISTORY_CSV)
        cls.claim_current = read_csv(nhis_preprocess.CLAIM_CURRENT_CSV)
        cls.cohorts = read_csv(nhis_preprocess.COHORT_SUMMARY_CSV)
        cls.metrics = read_csv(nhis_preprocess.METRICS_LONG_CSV)
        cls.form_fields = read_csv(nhis_preprocess.RESULT_FORM_FIELDS_CSV)
        cls.roles = read_csv(nhis_preprocess.DATA_ROLE_CSV)
        cls.quality = json.loads(
            (OUTPUT_DIR / nhis_preprocess.QUALITY_JSON).read_text(encoding="utf-8")
        )

    def test_raw_sources_are_preserved_with_expected_checksums(self):
        self.assertEqual(nhis_preprocess.CLAIM_SHA256, sha256(nhis_preprocess.RAW_CLAIM))
        self.assertEqual(nhis_preprocess.STATS_SHA256, sha256(nhis_preprocess.RAW_STATS))
        self.assertEqual(nhis_preprocess.FORM_SHA256, sha256(nhis_preprocess.RAW_FORM))

    def test_claim_code_history_uses_year_and_code_as_the_key(self):
        self.assertEqual(3777, len(self.claim_history))
        keys = {(row["claim_basis_year"], row["claim_item_code"]) for row in self.claim_history}
        self.assertEqual(len(self.claim_history), len(keys))
        self.assertEqual(525, len({row["claim_item_code"] for row in self.claim_history}))
        self.assertEqual(243, len(self.claim_current))
        self.assertTrue(all(row["claim_basis_year"] == "2024" for row in self.claim_current))

    def test_claim_header_mismatch_is_not_silently_reconstructed(self):
        self.assertTrue(
            all(row["official_detail_code"] == "" for row in self.claim_history)
        )
        self.assertTrue(
            all(
                "SOURCE_TYPE_FIELD_CONTAINS_LABEL_NOT_CODE" in row["quality_flags"]
                for row in self.claim_history
            )
        )
        conflicts = [
            row
            for row in self.claim_history
            if "SOURCE_TYPE_FIELD_CONFLICTS_WITH_ITEM_NAME" in row["quality_flags"]
        ]
        self.assertEqual(1, len(conflicts))
        self.assertEqual("D3502017", conflicts[0]["claim_item_code"])

    def test_cohort_grain_is_complete_and_unique(self):
        self.assertEqual(180, len(self.cohorts))
        self.assertEqual(180, len({row["cohort_key"] for row in self.cohorts}))
        self.assertEqual({"2022", "2023"}, {row["screening_year"] for row in self.cohorts})
        self.assertEqual(3, len({row["employment_category_code"] for row in self.cohorts}))
        self.assertEqual(15, len({row["age_band_code"] for row in self.cohorts}))
        self.assertEqual(2, len({row["sex_code"] for row in self.cohorts}))

    def test_blank_counts_remain_null_and_reported_zero_remains_zero(self):
        unavailable = [row for row in self.metrics if row["value_status"] == "NOT_AVAILABLE"]
        self.assertEqual(428, len(unavailable))
        self.assertTrue(all(row["count"] == "" and row["rate"] == "" for row in unavailable))
        self.assertIsNone(nhis_preprocess.parse_count("   "))
        self.assertEqual(0, nhis_preprocess.parse_count("0"))

    def test_status_counts_are_explicitly_nonexclusive(self):
        self.assertTrue(
            all(row["status_counts_are_nonexclusive"] == "True" for row in self.cohorts)
        )
        self.assertTrue(
            all(
                int(row["status_count_sum_for_quality_check"])
                > int(row["screened_count"])
                for row in self.cohorts
            )
        )

    def test_result_form_dictionary_separates_identifiers_and_health_values(self):
        self.assertEqual(56, len(self.form_fields))
        self.assertEqual(56, len({row["field_code"] for row in self.form_fields}))
        national_id = next(row for row in self.form_fields if row["field_code"] == "NATIONAL_ID")
        self.assertEqual("DO_NOT_STORE_RAW", national_id["ingest_policy"])
        self.assertEqual("HIGH_RISK_IDENTIFIER", national_id["sensitivity_class"])
        personal_rows = [row for row in self.form_fields if row["sensitivity_class"] == "PERSONAL_HEALTH"]
        self.assertTrue(personal_rows)
        self.assertTrue(all(row["diagnostic_use_allowed"] == "False" for row in personal_rows))

    def test_source_roles_prevent_cross_use(self):
        roles = {row["data_role"]: row for row in self.roles}
        self.assertEqual("False", roles["INTERNAL_BILLING_REFERENCE"]["user_visible"])
        self.assertIn("개인 진단", roles["PUBLIC_AGGREGATE_BENCHMARK"]["prohibited_use"])
        self.assertEqual(
            "NEVER_EMBED_PERSONAL_VALUES",
            roles["PERSONAL_HEALTH_RECORD_SCHEMA"]["vdb_policy"],
        )

    def test_quality_report_passes_all_stable_checks(self):
        self.assertEqual("PASS_WITH_WARNINGS", self.quality["status"])
        self.assertTrue(all(self.quality["checks"].values()))
        self.assertEqual(180, self.quality["dataset"]["status_overlap_rows"])
        self.assertEqual(428, self.quality["dataset"]["source_blank_cells"])


if __name__ == "__main__":
    unittest.main()
