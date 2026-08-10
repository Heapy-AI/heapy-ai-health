"""workspace 청크를 사용하는 로컬 검색 회귀 테스트."""
from __future__ import annotations

import unittest

from app.services.local_dev import LocalSearchService, build_local_query_resolver


class LocalWorkspaceResolverTest(unittest.TestCase):
    def test_high_pressure_initials_are_loaded_from_workspace_terms(self) -> None:
        result = build_local_query_resolver().resolve("ㄱㅎㅇ")

        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.terms[0].canonical_name, "고혈압")
        self.assertEqual(result.terms[0].match_kind, "initials")
        self.assertIn("고혈압", result.confirmation_question)

    def test_low_pressure_initials_are_loaded_from_workspace_terms(self) -> None:
        result = build_local_query_resolver().resolve("ㅈㅎㅇ")

        self.assertTrue(result.needs_confirmation)
        self.assertEqual(result.terms[0].canonical_name, "저혈압")
        self.assertEqual(result.terms[0].match_kind, "initials")
        self.assertIn("저혈압", result.confirmation_question)

    def test_ambiguous_initials_are_not_forced_to_one_medical_term(self) -> None:
        result = build_local_query_resolver().resolve("ㅎㄷ")

        self.assertEqual(result.resolution_status, "AMBIGUOUS")
        self.assertEqual(result.terms, ())

    def test_shared_alias_is_searchable_without_picking_one_test(self) -> None:
        resolver = build_local_query_resolver()

        exact = resolver.resolve("간수치")
        typo = resolver.resolve("갼슈치")

        self.assertEqual(exact.resolution_status, "RESOLVED")
        self.assertEqual(exact.terms[0].term_type, "ALIAS_GROUP")
        self.assertEqual(exact.terms[0].canonical_name, "간수치")
        self.assertTrue(typo.needs_confirmation)
        self.assertIn("간수치", typo.confirmation_question)

    def test_shared_alias_prefers_alias_metadata_over_body_mentions(self) -> None:
        service = LocalSearchService(build_local_query_resolver())
        documents = service.search("health_checkup_info", "간수치", 3)

        self.assertEqual(len(documents), 3)
        self.assertTrue(
            all("간수치" in document.metadata.get("aliases", []) for document in documents)
        )


if __name__ == "__main__":
    unittest.main()
