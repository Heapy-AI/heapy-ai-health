# Intent 분류기 개발 가이드

- 작성자: 김진우

## 목적

챗봇 파이프라인의 A1~A4 단계인 `질문 임베딩 → Linear Layer → Softmax → intent 결정`을 구현합니다.

## Intent 기준

| Intent | 기준 |
|---|---|
| `simple_lookup` | 개인 데이터 없이 일반 건강·의약 지식 검색으로 답변 가능 |
| `comprehensive` | 개인 검진·복약·생활 데이터 조회 또는 개인화 분석 필요 |
| `general_chat` | 건강 관련 대화지만 지식 검색과 개인 데이터 분석이 불필요 |
| `ignore` | 건강과 무관하거나 서비스 상담 범위를 벗어남 |

## 현재 구현 범위

- 기존 `jhgan/ko-sroberta-multitask` 768차원 임베딩 재사용
- 768→4 Linear Layer와 Softmax
- intent별 확률과 최고 확률 반환
- 최고 확률이 기준 미만이면 `uncertain=true`
- JSON 모델 artifact의 임베딩 모델·차원·라벨 순서 검증
- `POST /intent/classify` API

Sub-intent 분류와 실제 intent별 챗봇 분기는 다음 단계에서 구현합니다.

## 학습 데이터

JSONL 한 줄에 하나의 질문과 라벨을 기록합니다.

```json
{"text":"혈압이 무엇인가요?","intent":"simple_lookup","source":"팀 검수"}
```

초기 `classifier/data/intent_seed.jsonl`의 10건은 설계 문서 fixture이며 운영 학습 데이터가 아닙니다. 현재 기본 학습 데이터는 `classifier/data/HEAPY_intent_train_v1_400.jsonl`이며 intent별 100건으로 구성합니다.

`source=curated` 데이터는 학습·검증·테스트에 `8:1:1`로 나누고, `source=curated_typo` 데이터는 학습에 포함하지 않은 별도 오타 강건성 평가셋으로 사용합니다. `group_id`가 있는 문장들은 같은 분할에 배치해 유사 문장 누수를 방지합니다.

기본 학습은 intent별 20건 미만이면 실패합니다.

```powershell
python classifier/script/train_intent_classifier.py
```

학습 결과에는 각 분할의 정확도, Macro Precision·Recall·F1, confusion matrix가 저장됩니다. 검증 손실이 개선되지 않으면 early stopping을 적용하고 가장 좋은 epoch의 가중치를 artifact에 기록합니다.

구조만 시험할 때는 seed fixture와 다음 옵션을 사용합니다.

```powershell
python classifier/script/train_intent_classifier.py --allow-small-dataset
```

이 옵션으로 만든 모델은 검증 정확도가 없으므로 운영에 사용하지 않습니다.

## v1 첫 학습 결과

- 모델 버전: `intent-linear-14a6af9a5aba`
- 분할: 학습 308건, 검증 40건, 테스트 40건, 오타 challenge 12건
- 검증 정확도: 82.5%, Macro F1 0.8168
- 테스트 정확도: 90.0%, Macro F1 0.9017
- 오타 challenge 정확도: 91.7%, Macro F1 0.9000

초기 결과이므로 운영 품질을 확정하는 수치가 아닙니다. 특히 `ignore`와 `simple_lookup`·`comprehensive` 경계 문장을 추가 검수해야 합니다.

## API

학습 모델을 `classifier/artifacts/intent_linear.json`에 배치하고 FastAPI를 재시작합니다.

```http
POST /intent/classify
```

요청:

```json
{"question":"최근 AST가 높은데 왜 그런가요?"}
```

응답:

```json
{
  "intent":"comprehensive",
  "confidence":0.81,
  "probabilities":{
    "simple_lookup":0.08,
    "comprehensive":0.81,
    "general_chat":0.07,
    "ignore":0.04
  },
  "uncertain":false,
  "model_version":"intent-linear-..."
}
```

모델 파일이 없으면 분류 API만 `503`을 반환하며 기존 `/search`, `/ask`는 계속 사용할 수 있습니다.

## 운영 전 필수 검증

- 한 사람이 만든 라벨을 다른 팀원이 교차 검수
- intent별 데이터 수 균형 확인
- 학습에 사용하지 않은 별도 테스트셋 평가
- confusion matrix로 `simple_lookup`과 `comprehensive` 혼동 확인
- `uncertain=true` 질문의 별도 처리 정책 결정
- 의료 상담 범위를 벗어나는 질문의 `ignore` 기준 합의
