"""인덱싱·리트리버·RAG 체인을 만드는 서비스(라우터·main은 이걸 호출만 한다)"""
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, JSONLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import MODEL, PERSIST_DIR, COLLECTIONS


def _load_documents(docs_dir: Path):
    """docs_dir 안의 파일을 확장자별로 로드한다.

    폴더마다 원천 포맷이 다를 수 있어(PDF 고시문 / 크롤링 jsonl 등) 확장자별로 분기한다.
    """
    docs = []
    for pdf in sorted(docs_dir.rglob("*.pdf")):
        docs.extend(PyPDFLoader(str(pdf)).load())

    for jsonl in sorted(docs_dir.rglob("*.jsonl")):
        docs.extend(
            JSONLoader(
                str(jsonl), jq_schema=".", content_key="text",
                metadata_func=lambda rec, meta: {**meta, "source": rec.get("source_url", jsonl.stem)},
                json_lines=True,
            ).load()
        )
    return docs


def build_or_load_vectorstore(collection_name: str, embeddings) -> Chroma:
    """주어진 컬렉션의 인덱스를 준비한다. (health_checkup_info / disease_info)

    - 이미 인덱싱돼 있으면 '열기만' 해서 빠르게 시작.
    - 비어 있으면 원천파일 → 청킹 → 임베딩 → Chroma 저장(처음 1회만 무겁다).
    """
    if collection_name not in COLLECTIONS:
        raise ValueError(
            f"알 수 없는 컬렉션입니다: {collection_name} (등록된 컬렉션: {list(COLLECTIONS)})"
        )

    vs = Chroma(collection_name=collection_name, embedding_function=embeddings,
                persist_directory=PERSIST_DIR,
                collection_metadata={"hnsw:space": "cosine"})
    if vs._collection.count() > 0:
        return vs

    docs = _load_documents(COLLECTIONS[collection_name])
    if not docs:
        raise RuntimeError(f"'{COLLECTIONS[collection_name]}'에서 로드할 원천 파일을 찾지 못했습니다.")

    splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=80)
    chunks = splitter.split_documents(docs)

    for c in chunks:
        c.metadata["source"] = Path(c.metadata.get("source", "")).stem

    vs.add_documents(chunks)
    return vs


def build_all_vectorstores(embeddings) -> dict[str, Chroma]:
    """등록된 모든 컬렉션을 준비한다. (서버 startup 시 한 번 호출)"""
    return {name: build_or_load_vectorstore(name, embeddings) for name in COLLECTIONS}


def cite(d) -> str:
    """청크 메타에서 '라벨 · URL' 형식의 일관된 출처 문자열을 만든다.

    두 컬렉션(health_checkup_info/disease_info) 모두 source(URL)·source_label 키를 공유하므로
    같은 표기를 쓴다. PDF 시절의 페이지(p.N) 표기는 청크 데이터엔 의미가 없어 제거했다.
    """
    label = d.metadata.get("source_label")
    url = d.metadata.get("source")
    if label and url:
        return f"{label} · {url}"
    return label or url or "출처 미상"


def format_docs(docs) -> str:
    """검색된 청크들을 LLM 프롬프트에 넣을 문자열로 만든다(출처 표기 포함)."""
    return "\n\n".join(f"[{cite(d)}] {d.page_content}" for d in docs)


SYSTEM_PROMPT = (
    "너는 HEAPY의 건강정보 안내 봇이다.\n"
    "아래 [문서]에 있는 내용만 근거로 답하라. 문서에 근거가 없으면 "
    "정확히 '지식베이스에 근거 없음' 이라고만 답하라. 추측하지 마라.\n"
    "답변 끝에는 항상 '이 답변은 의료 진단이 아닌 정보 제공 목적입니다'를 덧붙여라.\n\n"
    "[문서]\n{context}\n\n[질문] {question}\n\n[답변]"
)


def build_chain(retriever):
    """검색결과를 context 로, 질문은 그대로 흘려보내는 LCEL 체인을 만든다."""
    prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    return ({"context": retriever | format_docs, "question": RunnablePassthrough()}
            | prompt | llm | StrOutputParser())