"""건강검진 인사이트의 근거 조회와 우선순위를 검증한다."""

import unittest

from app.services.checkup_persona_prompt import get_checkup_persona_prompt
from app.services.checkup_report import CheckupReportService
from app.services.vector_search import PineconeSearchService


class _FakeIndex:
    def fetch(self, *, ids, namespace):
        self.ids = ids
        self.namespace = namespace
        return {
            "vectors": {
                "ALT": {
                    "metadata": {
                        "chunk_text": "ALT는 간세포 안에 주로 존재하는 효소입니다.",
                        "domain": "LIVER",
                    }
                }
            }
        }


class CheckupEvidenceTest(unittest.TestCase):
    def test_fetches_canonical_records_without_embedding(self):
        service = PineconeSearchService.__new__(PineconeSearchService)
        service._index = _FakeIndex()

        documents = service.fetch_by_ids(
            "health_checkup_info",
            ["ALT", "ALT", "UNKNOWN"],
        )

        self.assertEqual(["ALT", "UNKNOWN"], service._index.ids)
        self.assertEqual("health_checkup_info", service._index.namespace)
        self.assertEqual(1, len(documents))
        self.assertEqual("ALT", documents[0].metadata["record_id"])
        self.assertEqual("LIVER", documents[0].metadata["domain"])

    def test_non_normal_reference_status_has_priority(self):
        risky = {"reference_status": "경계", "status": "개선", "change": 1}
        normal = {"reference_status": "정상", "status": "관리 필요", "change": 100}

        self.assertGreater(
            CheckupReportService._evidence_priority(risky),
            CheckupReportService._evidence_priority(normal),
        )

    def test_prompt_analysis_limits_metrics_and_reports_omissions(self):
        metrics = [
            {
                "metric_id": f"M{index}",
                "reference_status": "정상",
                "status": "변화 확인",
                "change": index,
            }
            for index in range(12)
        ]

        result = CheckupReportService._build_prompt_analysis(
            {"checkup_count": 4, "metrics": metrics}
        )

        self.assertEqual(8, len(result["metrics"]))
        self.assertEqual(12, result["metric_count"])
        self.assertEqual(4, result["omitted_metric_count"])
        self.assertEqual("M11", result["metrics"][0]["metric_id"])

    def test_prompt_forbids_internal_db_wording_and_requires_evidence(self):
        prompt = get_checkup_persona_prompt("coach").format(
            analysis_data="[]",
            evidence_data="[]",
        )

        self.assertIn("모든 수치를 나열하지 말고", prompt)
        self.assertIn("검증된 건강정보 근거에서만", prompt)
        self.assertIn('"DB 판정상"', prompt)
        self.assertIn("검사기관 판정에서는", prompt)


if __name__ == "__main__":
    unittest.main()
