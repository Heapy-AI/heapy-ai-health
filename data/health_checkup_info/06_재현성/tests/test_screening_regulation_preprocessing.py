import csv
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts/preprocess_screening_regulation.py"
OUTPUT_DIR = ROOT / "storage/source_document/mohw_screening/normalized"

spec = importlib.util.spec_from_file_location("screening_preprocess", SCRIPT_PATH)
screening_preprocess = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(screening_preprocess)


class ScreeningRegulationPreprocessingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        dataset_path = OUTPUT_DIR / screening_preprocess.DATASET_JSON
        cls.dataset = json.loads(dataset_path.read_text(encoding="utf-8"))

    def test_official_source_pdfs_are_unchanged_and_anchored(self):
        documents, errors = screening_preprocess.verify_documents()
        self.assertEqual([], errors)
        self.assertEqual(3, len(documents))

    def test_rule_graph_is_valid(self):
        self.assertEqual([], screening_preprocess.validate_rules())
        item_codes = {row["item_code"] for row in self.dataset["items"]}
        for rule in self.dataset["rules"]:
            self.assertTrue(
                screening_preprocess.expression_fields(rule["expression"]) <= item_codes
            )

    def test_all_boundary_cases_match(self):
        for case in screening_preprocess.BOUNDARY_CASES:
            with self.subTest(case=case["id"]):
                result = screening_preprocess.evaluate_target(case["target"], case["values"])
                self.assertIsNotNone(result)
                self.assertEqual(case["expected"], result["result_code"])

    def test_phq9_item9_rule_has_priority_over_total_score(self):
        result = screening_preprocess.evaluate_target(
            "DEPRESSION_SCREEN", {"PHQ9_TOTAL": 8, "PHQ9_ITEM9": 1}
        )
        self.assertEqual("PHQ9_SEVERE_SUSPECTED", result["result_code"])

    def test_multi_input_rules_are_not_flattened(self):
        composite_targets = {
            rule["target_condition"]
            for rule in self.dataset["rules"]
            if rule["rule_type"] == "COMPOSITE"
        }
        self.assertTrue(
            {
                "HYPERTENSION",
                "EARLY_PSYCHOSIS_SCREEN",
                "HEARING_WHISPER",
                "PULMONARY_BASIC",
                "PULMONARY_SIMPLE",
            }
            <= composite_targets
        )

    def test_quality_report_passes(self):
        report = json.loads(
            (OUTPUT_DIR / screening_preprocess.QUALITY_JSON).read_text(encoding="utf-8")
        )
        self.assertEqual("PASS", report["status"])
        self.assertTrue(all(report["checks"].values()))

    def test_csv_exports_match_json_grain(self):
        mappings = (
            (screening_preprocess.ITEMS_CSV, "items"),
            (screening_preprocess.RULES_CSV, "rules"),
            (screening_preprocess.ELIGIBILITY_CSV, "eligibility"),
        )
        for filename, key in mappings:
            with self.subTest(filename=filename):
                with (OUTPUT_DIR / filename).open(encoding="utf-8", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(len(self.dataset[key]), len(rows))

    def test_overall_and_oral_result_definitions_are_preserved(self):
        codes = {row["result_code"] for row in self.dataset["result_definitions"]}
        self.assertTrue(
            {
                "NORMAL_A",
                "NORMAL_B",
                "GENERAL_DISEASE_SUSPECTED",
                "CARDIOMETABOLIC_DISEASE_SUSPECTED",
                "KNOWN_DISEASE",
                "ORAL_GOOD",
                "ORAL_CAUTION",
                "ORAL_DISEASE_SUSPECTED",
                "ORAL_TREATMENT_REQUIRED",
            }
            <= codes
        )


if __name__ == "__main__":
    unittest.main()
