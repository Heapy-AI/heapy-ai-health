# Pinecone 사용 및 데이터 적재 가이드

- 작성자: 김진우
- Python: `3.11.9`
- Pinecone 인덱스: `heapy-rag`
- 임베딩 모델: `jhgan/ko-sroberta-multitask`

## 1. 데이터 저장 구조

이 프로젝트는 하나의 Pinecone 인덱스 안에서 namespace로 데이터를 구분합니다.

| 로컬 collection | Pinecone namespace | 현재 대상 수 |
|---|---|---:|
| `health_checkup_info` | `health_checkup_info` | 30건 |
| `disease_info` | `disease_info` | 54,330건 |

처리 흐름은 다음과 같습니다.

```text
vdb/chunk/<collection>/*.jsonl
  → 중복 ID와 적재 불가능한 청크 제외
  → 로컬 임베딩 모델로 768차원 벡터 생성
  → heapy-rag 인덱스의 collection별 namespace에 upsert
  → FastAPI가 질문을 같은 모델로 임베딩
  → Pinecone에서 유사한 청크 검색
```

Pinecone 통합 임베딩은 사용하지 않습니다. 임베딩 계산은 실행 중인 PC에서 수행하고, Pinecone에는 벡터·본문·메타데이터를 저장합니다.

## 2. 최초 환경 준비

프로젝트 루트에서 가상환경을 만들고 의존성을 설치합니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

프로젝트 루트의 `.env`를 설정합니다.

```env
PINECONE_API_KEY=공유받은_Pinecone_API_KEY
PINECONE_INDEX_NAME=heapy-rag
GOOGLE_API_KEY=개인_Gemini_API_KEY
```

`.env`와 API Key는 Git이나 공개 채널에 올리지 않습니다.

## 3. Pinecone 인덱스 생성

`heapy-rag` 인덱스가 이미 있으면 이 단계는 건너뜁니다.

```powershell
python vdb/script/manage_pinecone.py create-index
```

생성 사양은 다음과 같습니다.

| 항목 | 값 |
|---|---|
| 벡터 종류 | dense |
| 차원 | 768 |
| 거리 측정 | cosine |
| Cloud / Region | AWS / us-east-1 |

다른 차원이나 Pinecone 통합 임베딩으로 만든 인덱스에는 현재 벡터를 적재할 수 없습니다.

## 4. 청크 collection 준비

`[collection_name]`은 실제 사용할 collection 이름으로 바꿉니다. 대괄호는 입력하지 않습니다.

```text
예: [collection_name] → disease_info
예: [collection_name] → medication_info
```

collection 이름은 소문자 영문 또는 숫자로 시작해야 하며 소문자 영문, 숫자, `_`, `-`만 사용할 수 있습니다.

collection과 같은 이름의 폴더를 만들고 JSONL 청크를 넣습니다.

```text
vdb/chunk/[collection_name]/*.jsonl
```

각 JSONL 행의 기본 구조는 다음과 같습니다.

```json
{"id":"고유하고_변하지_않는_ID","text":"검색할 청크 본문","metadata":{"source":"출처 URL","source_label":"출처명"}}
```

- `id`는 collection 안에서 고유해야 합니다.
- `text`는 임베딩하고 검색할 본문입니다.
- `metadata`에는 출처 등 검색 결과와 함께 사용할 정보를 넣습니다.
- 동일한 ID와 동일한 내용이 여러 파일에 있으면 한 번만 적재합니다.
- 동일한 ID인데 내용이 다르면 오류로 중단합니다.
- `text`가 비어 있거나 Base64 데이터가 포함된 청크는 제외합니다.

## 5. 적재 전 확인

실제 임베딩과 업로드 없이 처리 대상 수를 확인합니다.

```powershell
python vdb/script/manage_pinecone.py ingest --collection [collection_name] --dry-run
```

출력에서 JSONL 행, 중복 제거, 제외, 적재 대상, 신규·변경 건수를 확인합니다.

## 6. collection 전체 적재

다음 명령을 실행합니다.

```powershell
python vdb/script/manage_pinecone.py ingest --collection [collection_name]
```

실행 중에는 다음 작업이 순서대로 진행됩니다.

1. `vdb/chunk/[collection_name]/*.jsonl`을 읽습니다.
2. 같은 ID의 중복 청크를 제거합니다.
3. 신규·변경 청크를 찾습니다.
4. 로컬 임베딩 모델을 메모리에 불러옵니다.
5. 기본 64건 단위로 임베딩하고 Pinecone에 upsert합니다.
6. 성공한 배치마다 로컬 manifest를 저장합니다.

첫 실행은 모든 청크를 로컬 CPU 또는 GPU에서 임베딩하므로 데이터 수에 따라 시간이 걸리고 실행 중 메모리를 사용합니다. Pinecone 통합 임베딩 토큰은 소비하지 않습니다.

실행이 중단되면 같은 명령을 다시 실행합니다.

```powershell
python vdb/script/manage_pinecone.py ingest --collection [collection_name]
```

`vdb/manifest/pinecone/heapy-rag/[collection_name].json`에 완료 상태가 저장되므로 이미 성공한 청크는 건너뛰고 나머지를 처리합니다.

## 7. 적재 결과 확인

namespace별 레코드 수를 확인합니다.

```powershell
python vdb/script/manage_pinecone.py stats
```

출력에서 적재한 collection과 같은 이름의 namespace 레코드 수를 확인합니다.

```text
index: heapy-rag
dimension: 768
[collection_name]: 적재된_레코드_수
```

검색도 직접 확인할 수 있습니다.

```powershell
python vdb/script/manage_pinecone.py search --collection [collection_name] --query "검색할 질문"
```

Pinecone 콘솔에서는 `heapy-rag` 인덱스의 `Namespaces` 메뉴에서 `[collection_name]`과 같은 이름의 namespace를 확인합니다.

## 8. 기존 collection에 데이터 추가 및 수정

추가 데이터를 기존 전처리·청킹 규칙으로 JSONL 형태로 만든 뒤 해당 폴더에 저장합니다.

```text
vdb/chunk/[collection_name]/*.jsonl
```

추가 또는 수정 후 같은 적재 명령을 실행합니다.

```powershell
python vdb/script/manage_pinecone.py ingest --collection [collection_name]
```

- 새로운 ID는 새 레코드로 추가됩니다.
- 기존 ID의 본문이나 metadata가 바뀌면 해당 레코드만 다시 임베딩하고 덮어씁니다.
- 변경되지 않은 ID는 다시 임베딩하지 않습니다.
- ID를 바꾸면 기존 레코드 수정이 아니라 새로운 레코드 추가로 판단합니다.

## 9. 삭제된 데이터 동기화

JSONL에서 제거한 ID를 Pinecone에서도 삭제하려면 `--delete-stale`을 명시합니다.

```powershell
python vdb/script/manage_pinecone.py ingest --collection [collection_name] --delete-stale
```

이 옵션은 현재 로컬 청크 전체가 정상적으로 준비된 경우에만 사용합니다. 일부 파일이 빠진 상태에서 실행하면 빠진 파일의 레코드도 Pinecone에서 삭제될 수 있습니다.

`--limit`과 `--delete-stale`은 함께 사용할 수 없습니다.

## 10. 전체 재임베딩

같은 ID와 내용이어도 모든 청크를 다시 임베딩하려면 다음 명령을 사용합니다.

```powershell
python vdb/script/manage_pinecone.py ingest --collection [collection_name] --force
```

모델의 벡터 차원이 달라진 경우에는 `--force`가 아니라 새 차원에 맞는 Pinecone 인덱스를 별도로 만들어야 합니다.

## 11. 일부 데이터로 동작 확인

처음 몇 건만 임베딩·적재하려면 `--limit`을 사용합니다.

```powershell
python vdb/script/manage_pinecone.py ingest --collection [collection_name] --limit 100
```

전체 적재 전에 실행 흐름을 확인할 때만 사용합니다. 이후 제한 없이 같은 명령을 실행하면 나머지 데이터를 이어서 적재합니다.

## 12. FastAPI에서 사용

Pinecone 적재가 끝난 뒤 서버를 다시 시작합니다.

```powershell
uvicorn app.main:app --reload
```

FastAPI는 다음과 같이 Pinecone을 사용합니다.

```text
사용자 질문
  → 로컬 모델로 질문 벡터 생성
  → 요청 collection과 같은 Pinecone namespace 검색
  → /search는 검색 청크 반환
  → /ask는 검색 청크를 근거로 Gemini 답변 생성
```

확인 주소:

```text
상태 확인: http://localhost:8000/health
Swagger:    http://localhost:8000/docs
Gradio:     http://localhost:7860
```

새 collection 폴더는 FastAPI 시작 시 자동 등록됩니다. 폴더를 추가하거나 적재를 마친 뒤 서버를 재시작하고 `/health`에서 collection별 건수를 확인합니다. 등록된 collection 중 하나라도 0건이면 `ready`가 `false`입니다.

## 13. 명령 요약

| 목적 | 명령 |
|---|---|
| 인덱스 생성 | `python vdb/script/manage_pinecone.py create-index` |
| 적재 대상 확인 | `python vdb/script/manage_pinecone.py ingest --collection [collection_name] --dry-run` |
| 신규·변경 적재 | `python vdb/script/manage_pinecone.py ingest --collection [collection_name]` |
| 삭제까지 동기화 | `python vdb/script/manage_pinecone.py ingest --collection [collection_name] --delete-stale` |
| 전체 재임베딩 | `python vdb/script/manage_pinecone.py ingest --collection [collection_name] --force` |
| 일부만 적재 | `python vdb/script/manage_pinecone.py ingest --collection [collection_name] --limit 100` |
| 레코드 수 확인 | `python vdb/script/manage_pinecone.py stats` |
| 검색 확인 | `python vdb/script/manage_pinecone.py search --collection [collection_name] --query "질문"` |

## 14. 운영 주의사항

- 같은 인덱스를 사용하는 팀원은 같은 `PINECONE_API_KEY`와 `PINECONE_INDEX_NAME`이 필요합니다.
- 여러 팀원이 동시에 같은 namespace를 적재하지 않습니다.
- 개인 의료정보와 사용자 식별정보는 공용 namespace에 적재하지 않습니다.
- 청크 ID는 재실행과 갱신을 위해 안정적으로 유지합니다.
- `.env`와 `vdb/manifest/`는 Git에 커밋하지 않습니다.
- Hugging Face 경고가 표시되어도 로컬에 모델이 정상 로드되면 적재는 진행됩니다.
