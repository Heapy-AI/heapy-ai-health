"""ragas LLM 심판 지표(근거충실도·정답일치율·근거재현율·근거정밀도)를 계산한다.

실행 예:
    PYTHONPATH=. python evaluation/eval/score_ragas.py --limit 0 --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_vertexai_shim() -> None:
    """ragas 0.4.x가 요구하지만 langchain-community 0.4에서 제거된 모듈을 대체한다.

    ragas는 ChatVertexAI를 토큰 한도 판정용 isinstance 검사에만 사용하므로
    빈 자리표시 클래스로 충분하다.
    """
    try:
        import langchain_community.chat_models.vertexai  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    module = types.ModuleType("langchain_community.chat_models.vertexai")

    class ChatVertexAI:  # pragma: no cover - 자리표시자
        """langchain-community에서 제거된 ChatVertexAI 자리표시자."""

    module.ChatVertexAI = ChatVertexAI
    sys.modules["langchain_community.chat_models.vertexai"] = module


_install_vertexai_shim()

from ragas import EvaluationDataset, SingleTurnSample, evaluate  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    AnswerCorrectness,
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
)
from ragas.run_config import RunConfig  # noqa: E402

from app.core.config import EMBED_MODEL, MODEL  # noqa: E402

METRIC_ALIASES = {
    "faithfulness": "근거충실도",
    "answer_correctness": "정답일치율(ragas)",
    "context_recall": "근거재현율(ragas)",
    "llm_context_precision_with_reference": "근거정밀도(ragas)",
}


def build_samples(records: list[dict]) -> tuple[list[SingleTurnSample], list[str], list[dict]]:
    """평가 결과 레코드를 ragas 샘플로 변환한다."""
    samples: list[SingleTurnSample] = []
    question_ids: list[str] = []
    skipped: list[dict] = []

    for record in records:
        if record.get("status") != "ok":
            skipped.append({"question_id": record["question_id"], "reason": "run_error"})
            continue
        contexts = [doc["text"] for doc in record.get("retrieved_documents", []) if doc.get("text")]
        response = (record.get("answer") or "").strip()
        reference = (record["gold"].get("reference_answer") or "").strip()
        if not contexts:
            skipped.append({"question_id": record["question_id"], "reason": "no_retrieved_context"})
            continue
        if not response or not reference:
            skipped.append({"question_id": record["question_id"], "reason": "empty_response_or_reference"})
            continue

        samples.append(
            SingleTurnSample(
                user_input=record["question"],
                retrieved_contexts=contexts,
                reference_contexts=record["gold"].get("gold_contexts") or None,
                response=response,
                reference=reference,
            )
        )
        question_ids.append(record["question_id"])

    return samples, question_ids, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="ragas 기반 RAG 품질 채점")
    parser.add_argument("--in-dir", type=Path, default=Path("output") / "golden_test")
    parser.add_argument("--limit", type=int, default=0, help="앞 N건만 채점(0=전량)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    in_dir = args.in_dir if args.in_dir.is_absolute() else ROOT / args.in_dir
    records_path = in_dir / "per_question.jsonl"
    if not records_path.is_file():
        print(f"[ragas] 실행 결과가 없습니다: {records_path}")
        return 1

    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        records = records[: args.limit]

    samples, question_ids, skipped = build_samples(records)
    print(f"[ragas] 채점 대상 {len(samples)}건 / 제외 {len(skipped)}건")
    if not samples:
        print("[ragas] 채점 가능한 샘플이 없습니다.")
        return 1

    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_huggingface import HuggingFaceEmbeddings

    judge_llm = LangchainLLMWrapper(
        ChatGoogleGenerativeAI(model=MODEL, temperature=0, max_retries=5)
    )
    judge_embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    )

    metrics = [
        Faithfulness(llm=judge_llm),
        AnswerCorrectness(llm=judge_llm, embeddings=judge_embeddings),
        LLMContextRecall(llm=judge_llm),
        LLMContextPrecisionWithReference(llm=judge_llm),
    ]

    started = perf_counter()
    result = evaluate(
        dataset=EvaluationDataset(samples=samples),
        metrics=metrics,
        llm=judge_llm,
        embeddings=judge_embeddings,
        run_config=RunConfig(max_workers=args.workers, timeout=args.timeout, max_retries=5),
        raise_exceptions=False,
        show_progress=True,
    )
    elapsed = perf_counter() - started
    print(f"[ragas] 채점 완료 {elapsed:.0f}s")

    frame = result.to_pandas()
    metric_columns = [column for column in frame.columns if column in METRIC_ALIASES]

    # to_pandas()가 입력 순서를 유지한다는 가정을 검증한다. 어긋나면 점수가
    # 엉뚱한 질문에 붙으므로 조용히 넘기지 않는다.
    if len(frame) != len(samples):
        raise RuntimeError(
            f"ragas 결과 행 수가 입력과 다릅니다: {len(frame)} != {len(samples)}"
        )
    misaligned = [
        index
        for index, (sample, user_input) in enumerate(zip(samples, frame["user_input"]))
        if str(user_input) != sample.user_input
    ]
    if misaligned:
        raise RuntimeError(
            f"ragas 결과 순서가 입력과 다릅니다 (불일치 {len(misaligned)}건, "
            f"첫 위치 {misaligned[0]})"
        )

    scores_path = in_dir / "ragas_scores.jsonl"
    with scores_path.open("w", encoding="utf-8") as handle:
        for question_id, (_, row) in zip(question_ids, frame.iterrows()):
            payload = {"question_id": question_id}
            for column in metric_columns:
                value = row[column]
                payload[column] = None if value != value else float(value)
            handle.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "judge_llm": MODEL,
        "judge_embeddings": EMBED_MODEL,
        "ragas_version": __import__("ragas").__version__,
        "scored": len(question_ids),
        "skipped": skipped,
        "elapsed_seconds": round(elapsed, 1),
        "metrics": {},
    }
    for column in metric_columns:
        values = [float(v) for v in frame[column].tolist() if v == v]
        summary["metrics"][column] = {
            "korean_name": METRIC_ALIASES[column],
            "mean": sum(values) / len(values) if values else None,
            "n": len(values),
            "failed": len(frame) - len(values),
        }

    (in_dir / "ragas_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ragas] 저장 완료: {scores_path}")
    for column, stats in summary["metrics"].items():
        mean_text = f"{stats['mean']:.4f}" if stats["mean"] is not None else "N/A"
        print(f"  - {stats['korean_name']:<20} {mean_text} (n={stats['n']}, 실패 {stats['failed']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
