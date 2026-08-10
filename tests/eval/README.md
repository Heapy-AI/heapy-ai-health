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
PYTHONPATH=. python tests/eval/run_golden_eval.py --sample-size 300 --workers 6

# 2) ragas 채점
PYTHONPATH=. python tests/eval/score_ragas.py --workers 8

# 3) 집계 및 리포트
PYTHONPATH=. python tests/eval/aggregate_report.py
```

산출물은 기본적으로 `output/golden_test/`에 저장됩니다 (`--out-dir`로 변경).

주요 옵션:

- `--sample-size 0` — 전량(2,290건) 평가
- `--split test` — 특정 split만
- `--workers 1` — 동시성 없이 순수 지연시간 측정
- `--seed` — 표본 재현성

## 계측 설계

- 운영 코드(`app/services/chat_orchestrator.py`)를 수정하지 않고, 얇은 래퍼로
  `embed_query` / `search_many_by_vector` / 계획·생성·감사 체인의 호출 시간만 기록합니다.
- TTFB는 `stream_answer`가 사용자에게 첫 `token` 이벤트를 내보내는 시점으로,
  운영 `/chat/stream` 엔드포인트와 동일한 의미입니다.
- 로컬 임베딩은 락으로 직렬화해 동시 실행 시 계측 왜곡을 줄입니다.
- 답변–정답 임베딩 유사도는 지연시간 측정이 끝난 뒤 별도로 계산합니다.

## 문서 ID 정규화

골든셋의 건강검진 문서 ID(`screening:chest_xray:001`)와 인덱스 벡터 ID(`CHEST_XRAY`)는
표기만 다른 동일 청크입니다. `vdb/chunk/health_checkup_info/screening_core_v1.jsonl`의
`canonical_key` 30개와 골든셋 screening ID 30개가 1:1 대응함을 확인해
`metrics.normalize_document_id()`에서 정규화합니다. 이 처리를 하지 않으면
건강검진 도메인 재현율이 실제 1.00 대신 0.00으로 잘못 집계됩니다.

## ragas 호환성

설치된 `ragas 0.4.3`은 `langchain_community.chat_models.vertexai`를 하드 임포트하지만
이 모듈은 `langchain-community 0.4.x`에서 제거되었습니다. ragas는 해당 클래스를
토큰 한도 판정용 `isinstance` 검사에만 쓰므로, `score_ragas._install_vertexai_shim()`이
자리표시자 모듈을 주입해 우회합니다. site-packages는 수정하지 않습니다.

심판 LLM은 `gemini-2.5-flash`, 임베딩은 `jhgan/ko-sroberta-multitask`를 사용합니다.
