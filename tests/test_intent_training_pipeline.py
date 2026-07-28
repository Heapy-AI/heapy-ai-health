"""Intent 학습 데이터 분할과 평가 로직 단위 테스트.

작성자: 김진우
"""
import csv
import tempfile
import unittest
from pathlib import Path

import torch

from classifier.script.train_intent_classifier import (
    INTENT_LABELS,
    _classification_metrics,
    _load_dataset,
    _split_indices,
)


class IntentTrainingPipelineTest(unittest.TestCase):
    def _example(
        self,
        text: str,
        intent: str,
        source: str = "curated",
        group_id: str | None = None,
    ) -> dict[str, str]:
        return {
            "text": text,
            "intent": intent,
            "source": source,
            "group_id": group_id or text,
        }

    def test_split_reserves_typo_challenge_and_preserves_groups(self) -> None:
        examples: list[dict[str, str]] = []
        for label in INTENT_LABELS:
            for index in range(12):
                group_id = f"{label}-paired" if index < 2 else None
                examples.append(
                    self._example(
                        text=f"{label}-{index}",
                        intent=label,
                        group_id=group_id,
                    )
                )
            examples.append(
                self._example(
                    text=f"{label}-typo",
                    intent=label,
                    source="curated_typo",
                )
            )

        train, validation, test, challenge = _split_indices(examples, 42, True)
        split_sets = list(map(set, (train, validation, test, challenge)))

        self.assertEqual(sum(map(len, split_sets)), len(examples))
        self.assertEqual(len(set().union(*split_sets)), len(examples))
        self.assertTrue(
            all(examples[index]["source"] == "curated_typo" for index in challenge)
        )
        for label in INTENT_LABELS:
            paired_indices = {
                index
                for index, example in enumerate(examples)
                if example["group_id"] == f"{label}-paired"
            }
            self.assertTrue(any(paired_indices <= indices for indices in split_sets))

    def test_split_keeps_cross_intent_hard_pair_in_one_partition(self) -> None:
        examples: list[dict[str, str]] = []
        for label in INTENT_LABELS:
            for index in range(15):
                examples.append(self._example(f"{label}-{index}", label))
        examples.extend(
            [
                self._example(
                    "개인 기록을 분석해줘",
                    "comprehensive",
                    source="manual_hard_pair",
                    group_id="hard_pair:CI01",
                ),
                self._example(
                    "개인 기록으로 진단을 확정해줘",
                    "ignore",
                    source="manual_hard_pair",
                    group_id="hard_pair:CI01",
                ),
            ]
        )

        split = _split_indices(examples, 42, True)
        split_sets = list(map(set, split))
        hard_pair_indices = {
            index
            for index, example in enumerate(examples)
            if example["group_id"] == "hard_pair:CI01"
        }

        self.assertTrue(any(hard_pair_indices <= indices for indices in split_sets))
        self.assertEqual(
            sum(bool(hard_pair_indices & indices) for indices in split_sets),
            1,
        )

    def test_classification_metrics_for_perfect_predictions(self) -> None:
        logits = torch.eye(len(INTENT_LABELS), dtype=torch.float32)
        labels = torch.arange(len(INTENT_LABELS), dtype=torch.long)

        metrics = _classification_metrics(logits, labels)

        self.assertIsNotNone(metrics)
        assert metrics is not None
        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertEqual(metrics["macro_f1"], 1.0)
        self.assertEqual(
            metrics["confusion_matrix"],
            [
                [1, 0, 0, 0],
                [0, 1, 0, 0],
                [0, 0, 1, 0],
                [0, 0, 0, 1],
            ],
        )

    def test_csv_label_column_is_loaded_as_intent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=("id", "text", "label", "source"),
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "id": "SI001",
                        "text": "혈압 정상 범위 알려줘",
                        "label": "simple_lookup",
                        "source": "curated",
                    }
                )

            rows = _load_dataset(path)

        self.assertEqual(rows[0]["intent"], "simple_lookup")
        self.assertEqual(rows[0]["text"], "혈압 정상 범위 알려줘")


if __name__ == "__main__":
    unittest.main()
