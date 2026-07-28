# Intent 분류기 MVP 운영 가이드

- 작성자: 김진우

## 현재 MVP 구성

현재 HEAPY MVP는 다음 순서로 intent를 결정합니다.

```text
사용자 질문
→ 의료 Safety Guard
→ 통과 시 Sentence Transformer 임베딩
→ 768→4 Linear Layer
→ Softmax
→ intent 결정
```

Intent는 다음 네 개를 사용합니다.

- `simple_lookup`
- `comprehensive`
- `general_chat`
- `ignore`

## 기본 모델

- 모델 버전: `intent-linear-f958f959253e`
- 운영 artifact: `classifier/artifacts/intent_linear.json`
- 학습 데이터: `classifier/data/HEAPY_intent_dataset_v3_500.csv`
- 임베딩 모델: `jhgan/ko-sroberta-multitask`
- Sentence Transformer: frozen
- Linear Layer: `768 → 4`, 랜덤 초기화 후 학습
- confidence threshold: `0.55`

기존 체크포인트를 이어서 학습하지 않습니다. `train_intent_classifier.py`는 seed 42로 새로운 Linear Layer를 생성합니다.

```powershell
$env:HF_HUB_OFFLINE="1"
python classifier/script/train_intent_classifier.py
```

학습 결과는 `classifier/artifacts/intent_linear_v5_candidate.json`에 저장됩니다. 검증 후 운영 모델로 사용할 때만 `intent_linear.json`으로 승격합니다.

## Safety Guard

Safety Guard는 임베딩과 Linear Classifier보다 먼저 실행합니다.

| reason | 차단 대상 |
|---|---|
| `definitive_diagnosis` | 질병 확정·배제·진단·단정 요구 |
| `medication_decision` | 약 선택·용량·증감·중단·변경 결정 요구 |
| `medical_visit_decision` | 병원 방문 또는 응급 여부 결정 요구 |

단순 복약 목록·일정·기록 조회와 명시적인 용량 변경이 없는 개인 복약 상호작용 조회에는 Guard가 작동하지 않습니다.

Guard가 작동하면 다음 값을 반환합니다.

```json
{
  "intent": "ignore",
  "confidence": 1.0,
  "uncertain": false,
  "source": "safety_guard",
  "guard_triggered": true,
  "guard_reason": "medication_decision"
}
```

`confidence=1.0`은 모델 확률이 아니라 명시적인 안전 규칙으로 라우팅했다는 의미입니다.

## 평가 결과

| 평가셋 | Classifier Accuracy | Guard 포함 Accuracy | Guard 포함 Macro F1 |
|---|---:|---:|---:|
| 기존 60 | 0.9500 | 0.9667 | 0.9554 |
| 독립 54 | 0.9444 | 0.9630 | 0.9404 |
| Blind 48 | 0.9792 | 0.9792 | 0.9791 |

상세 결과는 `classifier/evaluation/intent_v5/intent_v5_training_report.md`에서 확인합니다.

## 평가 재실행

재평가에 필요한 기존 60문항과 Blind 48 데이터는 평가 폴더에 보존합니다.

```powershell
$env:HF_HUB_OFFLINE="1"
python classifier/script/evaluate_intent_v5.py
python classifier/script/report_intent_v5.py
```

## API 응답 확장 필드

기존 `intent`, `confidence`, `probabilities`, `uncertain`, `model_version`은 유지합니다. 다음 필드가 추가됩니다.

- `source`
- `guard_triggered`
- `guard_reason`
- `matched_patterns`

기존 클라이언트가 사용하는 필드는 삭제하거나 이름을 변경하지 않습니다.

## 알려진 잔여 오류

다음 Blind 문장은 현재 v5에서도 `ignore`로 오분류합니다.

```text
오늘 내 복약 목록에서 저녁에 먹기로 한 것만 보여줘
```

정답은 `comprehensive`이며 Guard는 작동하지 않습니다. MVP 이후 데이터 개선 대상으로 유지합니다.
