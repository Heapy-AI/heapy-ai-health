# Gradio UI 사용 가이드

- 작성자: 김진우
- API: `http://localhost:8000`
- UI: `http://localhost:7860`

## 실행

터미널 1:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

터미널 2:

```powershell
.\.venv\Scripts\Activate.ps1
python run_ui.py
```

## Health

Pinecone 인덱스와 namespace별 레코드 수를 표시합니다.

```text
벡터 백엔드: pinecone
임베딩 모델: jhgan/ko-sroberta-multitask
```

등록된 namespace 중 하나가 비어 있으면 `준비 안 됨`으로 표시됩니다.

## Chat

`Chat` 탭은 Safety Guard → Intent v6 → 네 가지 응답 경로를 한 번에 테스트합니다. Intent와 신뢰도, 최종 답변, 검색 namespace, 실제 Pinecone 청크, 인용 출처 및 전체 JSON을 확인할 수 있습니다.

현재 `comprehensive`는 공용 지식 다중 검색과 강화 근거 검증까지 동작합니다. 사용자 개인 건강·복약 RDB는 아직 연결되지 않아 `personal_context_used=false`로 표시됩니다.

## Search

1. collection을 선택합니다.
2. 질문을 입력합니다.
3. 검색을 누릅니다.

질문은 FastAPI에 로딩된 로컬 모델로 임베딩되고 선택한 Pinecone namespace에서 검색됩니다. Gemini를 호출하지 않습니다.

## Intent

질문을 로컬 모델로 임베딩한 뒤 Linear/Softmax 분류 결과를 확인합니다. 최상위 intent, 신뢰도, intent별 확률과 `uncertain` 여부를 표시합니다.

현재 기본 모델은 `classifier/artifacts/intent-v7/best_model.json`이다. `INTENT_MODEL_PATH`로 선택한 모델 파일이 없으면 Intent 탭만 사용할 수 없으며 Search와 Ask는 계속 동작합니다.

## Ask

Search와 같은 Pinecone 검색 결과를 근거로 Gemini가 답변합니다. 근거가 없으면 추측하지 않고 회피합니다.

## collection

| 선택값 | 내용 |
|---|---|
| `health_checkup_info` | 건강검진정보 |
| `disease_info` | 질병정보 |

## 테스트 질문

```text
simple_lookup: 공복혈당이 무엇인가요?
comprehensive: 건강검진에서 AST가 높게 나왔는데 왜 그런가요?
general_chat: 요즘 일이 많아서 피곤하고 지쳐요.
ignore: 오늘 환율 알려줘.
Safety Guard: 이 약을 두 알 먹어도 돼?
```

## 오류 확인

| 증상 | 확인 |
|---|---|
| FastAPI 연결 실패 | `uvicorn app.main:app --reload` 실행 여부 |
| Pinecone 인덱스 없음 | `.env`의 `PINECONE_INDEX_NAME` |
| 차원 오류 | 768차원 dense 인덱스 사용 여부 |
| 검색 결과 없음 | 선택한 namespace의 적재 수 |
| 최초 시작이 느림 | 로컬 임베딩 모델 다운로드·로딩 진행 여부 |
