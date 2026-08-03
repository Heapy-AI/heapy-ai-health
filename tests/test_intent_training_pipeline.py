"""Intent v6 JSONL·metric·checkpoint 파이프라인 테스트.

작성자: 김진우
"""
import json
import tempfile
import unittest
from pathlib import Path

import torch

from classifier.script.intent_v6_utils import (
    EMBED_DIMENSION,
    LABELS,
    LABEL_TO_ID,
    audit_data_integrity,
    classification_metrics,
    load_checkpoint,
    load_dataset,
    logits_from_checkpoint,
    prediction_rows,
    write_json,
)
from classifier.script.prepare_intent_v6_data import policy_label


class IntentTrainingPipelineTest(unittest.TestCase):
    def _write_lines(self, path: Path, lines: list[str]) -> None:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_normal_jsonl_is_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "normal.jsonl"
            self._write_lines(
                path,
                [
                    "",
                    json.dumps(
                        {"text": "복통은 왜 생겨?", "label": "simple_lookup"},
                        ensure_ascii=False,
                    ),
                ],
            )
            rows = load_dataset(path)

        self.assertEqual(
            rows,
            [{"text": "복통은 왜 생겨?", "label": "simple_lookup"}],
        )

    def test_invalid_json_reports_file_and_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jsonl"
            self._write_lines(path, ['{"text": "정상", "label": "ignore"}', "{"])
            with self.assertRaisesRegex(
                ValueError,
                r"invalid\.jsonl:2",
            ):
                load_dataset(path)

    def test_missing_text_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing_text.jsonl"
            self._write_lines(path, ['{"label":"ignore"}'])
            with self.assertRaisesRegex(ValueError, "text 필드"):
                load_dataset(path)

    def test_missing_label_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing_label.jsonl"
            self._write_lines(path, ['{"text":"질문"}'])
            with self.assertRaisesRegex(ValueError, "label 필드"):
                load_dataset(path)

    def test_invalid_label_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid_label.jsonl"
            self._write_lines(path, ['{"text":"질문","label":"unknown"}'])
            with self.assertRaisesRegex(ValueError, "허용하지 않는 label"):
                load_dataset(path)

    def test_label_id_mapping_order_is_fixed(self) -> None:
        self.assertEqual(
            LABELS,
            ["simple_lookup", "comprehensive", "general_chat", "ignore"],
        )
        self.assertEqual(
            LABEL_TO_ID,
            {
                "simple_lookup": 0,
                "comprehensive": 1,
                "general_chat": 2,
                "ignore": 3,
            },
        )

    def test_linear_model_output_dimension_is_four(self) -> None:
        model = torch.nn.Linear(EMBED_DIMENSION, len(LABELS))
        logits = model(torch.zeros((2, EMBED_DIMENSION)))
        self.assertEqual(tuple(logits.shape), (2, 4))

    def test_metrics_include_per_class_and_confusion_matrix(self) -> None:
        logits = torch.eye(len(LABELS), dtype=torch.float32)
        targets = torch.arange(len(LABELS), dtype=torch.long)
        metrics = classification_metrics(logits, targets, loss=0.1)

        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertEqual(metrics["macro_f1"], 1.0)
        self.assertEqual(metrics["loss"], 0.1)
        self.assertEqual(metrics["per_class"]["ignore"]["f1"], 1.0)
        self.assertEqual(
            metrics["confusion_matrix"],
            [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
        )

    def test_confidence_and_uncertain_are_calculated(self) -> None:
        examples = [{"text": "오늘 기분이 좋아", "label": "general_chat"}]
        rows = prediction_rows(
            examples,
            torch.zeros((1, len(LABELS))),
            threshold=0.55,
        )
        self.assertAlmostEqual(rows[0]["confidence"], 0.25)
        self.assertTrue(rows[0]["uncertain"])

    def test_checkpoint_is_saved_reloaded_and_used_for_inference(self) -> None:
        weights = [[0.0] * EMBED_DIMENSION for _ in LABELS]
        checkpoint = {
            "schema_version": 1,
            "model_type": "linear_softmax",
            "model_version": "intent-v6-test",
            "embedding_model": "jhgan/ko-sroberta-multitask",
            "embedding_dimension": EMBED_DIMENSION,
            "labels": LABELS,
            "weights": weights,
            "bias": [5.0, 0.0, 0.0, 0.0],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "best_model.json"
            write_json(path, checkpoint)
            reloaded = load_checkpoint(path)

        logits = logits_from_checkpoint(
            torch.zeros((1, EMBED_DIMENSION)),
            reloaded,
        )
        rows = prediction_rows(
            [{"text": "복통은 왜 생겨?", "label": "simple_lookup"}],
            logits,
            threshold=0.55,
        )
        self.assertEqual(rows[0]["predicted_label"], "simple_lookup")
        self.assertFalse(rows[0]["uncertain"])

    def test_integrity_audit_reports_split_leakage(self) -> None:
        datasets = {
            "train": [{"text": "같은   문장", "label": "simple_lookup"}],
            "validation": [{"text": "같은 문장", "label": "simple_lookup"}],
        }
        paths = {
            "train": Path("train.jsonl"),
            "validation": Path("validation.jsonl"),
        }
        report = audit_data_integrity(datasets, paths)

        overlap = report["overlaps"]["train__validation"]
        self.assertEqual(overlap["exact_text_overlap_count"], 0)
        self.assertEqual(overlap["normalized_text_overlap_count"], 1)
        self.assertTrue(report["warnings"])

    def test_personal_medication_lookup_is_comprehensive(self) -> None:
        row = {
            "text": "오늘 내 저녁 복약 목록 알려줘",
            "label": "general_chat",
            "topic": "복약공유",
            "source": "curated",
        }
        self.assertEqual(policy_label(row), "comprehensive")

    def test_personal_symptom_statement_is_comprehensive(self) -> None:
        row = {
            "text": "오늘 속이 불편해",
            "label": "general_chat",
            "topic": "증상공유",
            "source": "curated",
        }
        self.assertEqual(policy_label(row), "comprehensive")

    def test_medical_decision_keeps_ignore_priority(self) -> None:
        row = {
            "text": "내 약 기록을 보고 용량을 정해줘",
            "label": "ignore",
            "topic": "처방",
            "source": "curated",
        }
        self.assertEqual(policy_label(row), "ignore")

    def test_general_emotion_is_not_relabelled(self) -> None:
        row = {
            "text": "두근거림 얘기 들으니까 조금 무섭네",
            "label": "general_chat",
            "topic": "증상_두근거림_검사",
            "source": "symptom_collection_v6",
        }
        self.assertEqual(policy_label(row), "general_chat")


if __name__ == "__main__":
    unittest.main()
