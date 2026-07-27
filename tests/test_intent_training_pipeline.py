"""Intent 학습 데이터 분할과 평가 로직 단위 테스트.

작성자: 김진우
"""
import unittest

import torch

from classifier.script.train_intent_classifier import (
    INTENT_LABELS,
    _classification_metrics,
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


if __name__ == "__main__":
    unittest.main()
