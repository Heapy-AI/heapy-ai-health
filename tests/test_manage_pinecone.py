"""Pinecone 사전 계산 벡터 적재 도구 단위 테스트.

작성자: 김진우
"""
from __future__ import annotations

import unittest
from pathlib import Path

from vdb.script.manage_pinecone import (
    EMBED_DIMENSION,
    _build_precomputed_vector,
    build_parser,
)


class PrecomputedPineconeIngestTest(unittest.TestCase):
    """사전 계산 임베딩의 명령행 및 메타데이터 계약을 검증한다."""

    def test_parser_accepts_precomputed_ingest(self) -> None:
        """외부 패키지 경로와 namespace를 명령행에서 받는다."""
        args = build_parser().parse_args(
            [
                "ingest-precomputed",
                "--source",
                "data/eyak/eyak",
                "--collection",
                "medication_info",
                "--batch-size",
                "100",
                "--dry-run",
            ]
        )

        self.assertEqual(args.source, Path("data/eyak/eyak"))
        self.assertEqual(args.collection, "medication_info")
        self.assertEqual(args.batch_size, 100)
        self.assertTrue(args.dry_run)

    def test_precomputed_record_adds_search_metadata(self) -> None:
        """검색 서비스가 요구하는 본문과 collection metadata를 보완한다."""
        record = {
            "id": "eyak:test:efficacy:001",
            "text": "의약품 효능 정보",
            "embedding": [0.0] * EMBED_DIMENSION,
            "metadata": {"item_seq": "test", "section_code": "efficacy"},
        }

        vector = _build_precomputed_vector(record, "medication_info")

        self.assertEqual(vector["id"], record["id"])
        self.assertEqual(len(vector["values"]), EMBED_DIMENSION)
        self.assertEqual(vector["metadata"]["chunk_text"], record["text"])
        self.assertEqual(vector["metadata"]["collection"], "medication_info")


if __name__ == "__main__":
    unittest.main()
