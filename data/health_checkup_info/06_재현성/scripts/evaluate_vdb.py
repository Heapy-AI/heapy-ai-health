#!/usr/bin/env python3
"""Evaluate local VDB retrieval against a versioned query set."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vdb.local_store import load_json, search_index  # noqa: E402


DEFAULT_INDEX = ROOT / "vdb/index/screening_core_v1.local.json"
DEFAULT_CASES = ROOT / "vdb/evaluation/screening_core_queries.json"
DEFAULT_OUTPUT = ROOT / "vdb/reports/retrieval_evaluation.json"


def evaluate(index: dict, suite: dict, top_k: int = 3) -> dict:
    results = []
    reciprocal_rank_sum = 0.0
    hit_at_1 = 0
    hit_at_k = 0

    for case in suite["cases"]:
        rows = search_index(index, case["query"], limit=top_k, min_score=0.0)
        returned = [row["canonical_key"] for row in rows]
        expected = set(case["expected_keys"])
        rank = next((position for position, key in enumerate(returned, start=1) if key in expected), None)
        if rank == 1:
            hit_at_1 += 1
        if rank is not None:
            hit_at_k += 1
            reciprocal_rank_sum += 1.0 / rank
        results.append(
            {
                "id": case["id"],
                "query": case["query"],
                "expected_keys": case["expected_keys"],
                "returned_keys": returned,
                "expected_rank": rank,
                "passed_at_1": rank == 1,
                f"passed_at_{top_k}": rank is not None,
            }
        )

    total = len(results)
    return {
        "suite_version": suite["version"],
        "case_count": total,
        "top_k": top_k,
        "metrics": {
            "hit_at_1": round(hit_at_1 / total, 6) if total else 0.0,
            f"hit_at_{top_k}": round(hit_at_k / total, 6) if total else 0.0,
            "mean_reciprocal_rank": round(reciprocal_rank_sum / total, 6) if total else 0.0,
        },
        "thresholds": {
            "hit_at_1": 0.9,
            f"hit_at_{top_k}": 1.0,
        },
        "status": "PASS" if total and hit_at_1 / total >= 0.9 and hit_at_k == total else "FAIL",
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    report = evaluate(load_json(args.index), load_json(args.cases), args.top_k)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in ("status", "case_count", "metrics")}, ensure_ascii=False, indent=2))
    print(f"report -> {args.output}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

