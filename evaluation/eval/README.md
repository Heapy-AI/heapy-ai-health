# 골든 데이터셋 RAG 종단 평가 하네스

`data/test_golden_dataset/`의 골든셋으로 **운영 응답 경로 그대로** 질의를 실행하고,
검색·생성·인용·지연 지표를 산출합니다.

`tests/`의 나머지 파일은 fake 의존성을 쓰는 **단위 테스트**입니다. 이 디렉터리는
실제 Pinecone·Gemini를 호출하는 **평가 하네스**로, pytest 수집 대상이 아닙니다
(`test_*.py` 명명 규칙을 쓰지 않음). 단, 지표 계산 로직은
`tests/test_eval_metrics.py`에서 단위 테스트로 검증됩니다.

## 구성

| 파일 | 역할 |
|---|---|
| `golden_dataset.py` | 골든셋 로딩, 도메인·split·난이도·답변가능 여부 층화 표본 추출 |
| `instrumentation.py` | 공유 자원(임베딩·Pinecone·Gemini 체인)을 1회 생성하고, 질문마다 단계별 시간을 재는 래퍼로 `ChatOrchestrator`를 조립 |
| `metrics.py` | 문서ID 정규화, Hit@k·MRR·nDCG·근거재현율/정밀도·인용정확도·어휘 F1 등 결정적 지표 |
| `run_golden_eval.py` | 종단 실행 → `per_question.jsonl`, `run_meta.json` |
| `score_ragas.py` | ragas LLM 심판 4개 지표 → `ragas_scores.jsonl`, `ragas_summary.json` |
| `aggregate_report.py` | 집계 → `metrics_summary.json`, `per_question.csv`, `report.md` |

## 실행

```bash
# 1) 종단 실행 (기본 300건 층화표본, 워커 6)
PYTHONPATH=. python evaluation/eval/run_golden_eval.py --sample-size 300 --workers 6

# 2) ragas 채점
PYTHONPATH=. python evaluation/eval/score_ragas.py --workers 8

# 3) 집계 및 리포트
PYTHONPATH=. python evaluation/eval/aggregate_report.py
```

산출물은 기본적으로 `output/golden_test/`에 저장됩니다 (`--out-dir`로 변경).
