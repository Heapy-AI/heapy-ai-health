"""원천 문서에서 검색용 표준용어 사전을 만드는 회귀 테스트."""
from __future__ import annotations

import unittest

from langchain_core.documents import Document

from app.services.medical_term_catalog import build_term_catalog


class MedicalTermCatalogTest(unittest.TestCase):
    def test_canonical_owner_wins_over_related_alias_collision(self) -> None:
        catalog = build_term_catalog(
            {
                "disease_info": [
                    Document(
                        page_content="고혈압의 설명",
                        metadata={
                            "disease": "고혈압",
                            "category": "disease",
                        },
                    )
                ],
                "health_checkup_info": [
                    Document(
                        page_content="혈압 검사\n\n관련어: 혈압, 고혈압",
                        metadata={
                            "canonical_key": "BLOOD_PRESSURE",
                            "heading": "혈압 검사",
                        },
                    )
                ],
            }
        )

        hypertension = next(
            term for term in catalog if term["canonical_name"] == "고혈압"
        )
        blood_pressure = next(
            term for term in catalog if term["canonical_key"] == "BLOOD_PRESSURE"
        )

        self.assertIn("고혈압", [alias["display"] for alias in hypertension["aliases"]])
        self.assertNotIn(
            "고혈압",
            [alias["display"] for alias in blood_pressure["aliases"]],
        )


if __name__ == "__main__":
    unittest.main()
