#!/usr/bin/env python3
"""LLM 키 없이 vdb/chunk 의 청크(.jsonl)를 chroma 에 적재하는 독립 스크립트.

앱(app/services/rag.py)과 '같은' persist 경로·컬렉션명·임베딩 모델을 쓰므로,
여기서 적재해두면 앱은 재인덱싱 없이 컬렉션을 열기만 한다.
답변 생성용 LLM(Gemini) 키는 필요 없다 — 임베딩(ko-sroberta)만 사용.

사용 예:
    python ingest_vdb.py                              # health_checkup_info 적재
    python ingest_vdb.py --collection disease_info --rebuild
    python ingest_vdb.py --collection health_checkup_info --test   # 적재 후 스모크 테스트
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[2]   # vdb/script/ → repo 루트
CHUNK_ROOT = ROOT / "vdb" / "chunk"

# --- 아래 3개는 app/core/config.py 와 반드시 일치해야 앱이 그대로 연다 ---
PERSIST_DIR = str(ROOT / "vdb" / "chroma")     # config.PERSIST_DIR
EMBED_MODEL = "jhgan/ko-sroberta-multitask"    # config.EMBED_MODEL
SPACE = {"hnsw:space": "cosine"}               # config 의 collection_metadata

# 컬렉션명 -> 청크 폴더 (config.COLLECTIONS 와 정합; 폴더명은 vdb/chunk 아래 기준)
COLLECTION_DIRS = {
    "health_checkup_info": CHUNK_ROOT / "health_checkup_info",
    "disease_info": CHUNK_ROOT / "disease_info",
}


def load_chunks(chunk_dir: Path) -> tuple[list[str], list[Document]]:
    """chunk_dir 의 *.jsonl 을 읽어 (ids, documents) 로 만든다.

    각 줄 = {"text": <본문>, "metadata": {...스칼라...}}.
    id 는 canonical_key(있으면)로 → 재실행 시 중복이 아니라 upsert 된다.
    """
    ids: list[str] = []
    docs: list[Document] = []
    files = sorted(chunk_dir.rglob("*.jsonl"))
    if not files:
        raise FileNotFoundError(f"청크(.jsonl)를 찾지 못했습니다: {chunk_dir}")

    for jf in files:
        for i, line in enumerate(jf.read_text(encoding="utf-8").splitlines()):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            text = rec.get("text", "").strip()
            if not text:
                print(f"  ! 빈 text 건너뜀: {jf.name}:{i+1}", file=sys.stderr)
                continue
            meta = dict(rec.get("metadata", {}))
            meta.setdefault("source_file", jf.name)
            # chroma 메타데이터는 스칼라만 허용 → 혹시 모를 list/dict 방어
            for k, v in list(meta.items()):
                if not isinstance(v, (str, int, float, bool)) and v is not None:
                    meta[k] = json.dumps(v, ensure_ascii=False)
            # 안정적 id: top-level "id" > metadata.canonical_key > 파일명-줄번호
            cid = str(rec.get("id") or meta.get("canonical_key") or f"{jf.stem}-{i}")
            ids.append(cid)
            docs.append(Document(page_content=text, metadata=meta))
    return ids, docs


def ingest(collection: str, rebuild: bool) -> Chroma:
    chunk_dir = COLLECTION_DIRS[collection]
    ids, docs = load_chunks(chunk_dir)
    print(f"[{collection}] 청크 {len(docs)}개 로드 ({chunk_dir})")

    print(f"임베딩 모델 로드 중: {EMBED_MODEL} (최초 1회 다운로드/시간 소요)")
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)

    vs = Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=PERSIST_DIR,
        collection_metadata=SPACE,
    )

    if rebuild and vs._collection.count() > 0:
        print(f"기존 컬렉션 {vs._collection.count()}건 삭제(--rebuild)")
        vs.delete_collection()
        vs = Chroma(
            collection_name=collection,
            embedding_function=embeddings,
            persist_directory=PERSIST_DIR,
            collection_metadata=SPACE,
        )

    # chroma 는 1회 upsert 최대 5461건 → 배치로 나눠 적재(진행률 표시)
    # id 지정 → 재실행해도 중복 없이 덮어쓴다(upsert)
    batch = 4000
    for start in range(0, len(docs), batch):
        end = min(start + batch, len(docs))
        vs.add_documents(documents=docs[start:end], ids=ids[start:end])
        print(f"  적재 {end}/{len(docs)}", flush=True)
    print(f"적재 완료: 컬렉션 '{collection}' 총 {vs._collection.count()}건 -> {PERSIST_DIR}")
    return vs


def smoke_test(vs: Chroma, top_k: int = 3) -> int:
    """평가셋(screening_core_queries.json)으로 검색 정확도 확인."""
    cases_path = next(ROOT.rglob("screening_core_queries.json"), None)
    if cases_path is None:
        print("평가셋(screening_core_queries.json)을 찾지 못해 스모크 테스트를 건너뜁니다.")
        return 0
    suite = json.loads(cases_path.read_text(encoding="utf-8"))
    hit1 = hitk = 0
    rr = 0.0
    for case in suite["cases"]:
        results = vs.similarity_search(case["query"], k=top_k)
        got = [d.metadata.get("canonical_key") for d in results]
        expected = set(case["expected_keys"])
        rank = next((p for p, k in enumerate(got, 1) if k in expected), None)
        if rank == 1:
            hit1 += 1
        if rank is not None:
            hitk += 1
            rr += 1.0 / rank
        else:
            print(f"  MISS [{case['id']}] '{case['query']}' -> {got} (기대 {case['expected_keys']})")
    n = len(suite["cases"])
    print(f"\n스모크 테스트: {n}건 | hit@1={hit1/n:.3f} hit@{top_k}={hitk/n:.3f} MRR={rr/n:.3f}")
    return 0 if hit1 / n >= 0.9 and hitk == n else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", default="health_checkup_info", choices=sorted(COLLECTION_DIRS))
    ap.add_argument("--rebuild", action="store_true", help="기존 컬렉션을 지우고 새로 적재")
    ap.add_argument("--test", action="store_true", help="적재 후 평가셋으로 검색 스모크 테스트")
    args = ap.parse_args()

    vs = ingest(args.collection, args.rebuild)
    if args.test:
        return smoke_test(vs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
