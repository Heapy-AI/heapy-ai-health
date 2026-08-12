# HEAPY Intent v6 사용 가이드

- 작성자: 김진우
- 모델 버전: `intent-v6-8aeae9eced50`
- 운영 체크포인트: `classifier/artifacts/intent-v6/best_model.json`

## 모델 구성

```text
사용자 질문
→ Safety Guard
→ jhgan/ko-sroberta-multitask 임베딩(768차원)
→ Linear Layer
→ Softmax
→ 4개 Intent 중 하나로 분류
```

| Intent | 의미 |
|---|---|
| `simple_lookup` | 일반 건강·질환·검사 정보 조회 |
| `comprehensive` | 개인 건강·검진·복약 데이터 조회 또는 분석 |
| `general_chat` | 일상 대화, 감정 표현, 단순 반응 |
| `ignore` | 서비스 범위 밖 요청 또는 진단·처방·의료적 결정 요구 |

## 팀원 실행 방법

Python 3.11.9 가상환경에서 저장소 루트를 기준으로 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

처음 실행할 때 Hugging Face에서 `jhgan/ko-sroberta-multitask` 모델을 다운로드하므로 인터넷 연결이 필요합니다. 이후에는 로컬 캐시를 사용합니다.

Intent 분류 API 확인:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/intent/classify `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"question":"오늘 내 저녁 복약 목록 알려줘"}'
```

Gradio 실행:

```powershell
python -m app.ui
```

기본 경로를 사용하면 `.env`에 `INTENT_MODEL_PATH`를 추가하지 않아도 됩니다. 다른 위치를 사용할 때만 다음 값을 설정합니다.

```text
INTENT_MODEL_PATH=classifier/artifacts/intent-v6/best_model.json
INTENT_MIN_CONFIDENCE=0.55
```

## 평가 요약

| Split | 방식 | Accuracy | Macro F1 |
|---|---|---:|---:|
| Validation | Linear classifier | 0.9747 | 0.9747 |
| Test | Linear + Safety Guard | 0.9367 | 0.9379 |
| Blind 48 | Linear + Safety Guard | 0.9583 | 0.9580 |

개인 복약 목록 조회와 개인 증상 서술은 `comprehensive`로 분류하도록 학습했습니다. 현재 상대적으로 약한 경계는 일반 증상 설명을 개인 증상으로 오인하는 경우와 일부 안전 요청의 `ignore` 판별입니다.

## Git 공유 범위

팀 실행에는 다음 파일만 필요합니다.

- `classifier/artifacts/intent-v6/best_model.json`
- `app/services/intent_classifier.py`
- `app/services/safety_guard.py`
- `app/core/config.py`
- `requirements.txt`

학습 데이터, Test·Blind 문장, 예측 결과 및 중간 체크포인트는 `.gitignore`로 제외합니다. 따라서 팀원은 모델 사용은 가능하지만 저장소만으로 재학습하거나 평가셋을 재현할 수는 없습니다.
