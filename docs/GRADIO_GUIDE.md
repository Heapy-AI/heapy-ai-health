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

## Search

1. collection을 선택합니다.
2. 질문을 입력합니다.
3. 검색을 누릅니다.

질문은 FastAPI에 로딩된 로컬 모델로 임베딩되고 선택한 Pinecone namespace에서 검색됩니다. Gemini를 호출하지 않습니다.

## Ask

Search와 같은 Pinecone 검색 결과를 근거로 Gemini가 답변합니다. 근거가 없으면 추측하지 않고 회피합니다.

## collection

| 선택값 | 내용 |
|---|---|
| `health_checkup_info` | 건강검진정보 |
| `disease_info` | 질병정보 |

## 테스트 질문

```text
건강검진 정상B는 무슨 뜻이야?
공복혈당이 무엇인가요?
감기 원인이 뭐야?
```

## 오류 확인

| 증상 | 확인 |
|---|---|
| FastAPI 연결 실패 | `uvicorn app.main:app --reload` 실행 여부 |
| Pinecone 인덱스 없음 | `.env`의 `PINECONE_INDEX_NAME` |
| 차원 오류 | 768차원 dense 인덱스 사용 여부 |
| 검색 결과 없음 | 선택한 namespace의 적재 수 |
| 최초 시작이 느림 | 로컬 임베딩 모델 다운로드·로딩 진행 여부 |
