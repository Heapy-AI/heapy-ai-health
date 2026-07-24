"""검색된 Pinecone 청크를 근거로 답변을 생성한다.

작성자: 김진우
"""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import MODEL


def cite(document) -> str:
    """청크 메타데이터로 일관된 출처 문자열을 만든다."""
    label = document.metadata.get("source_label")
    url = document.metadata.get("source")
    if label and url:
        return f"{label} · {url}"
    return label or url or "출처 미상"


def format_docs(documents) -> str:
    """검색 청크를 출처와 함께 LLM 프롬프트 문자열로 만든다."""
    return "\n\n".join(
        f"[{cite(document)}] {document.page_content}"
        for document in documents
    )


SYSTEM_PROMPT = (
    "너는 HEAPY의 건강정보 안내 봇이다.\n"
    "아래 [문서]에 있는 내용만 근거로 답하라. 문서에 근거가 없으면 "
    "정확히 '지식베이스에 근거 없음' 이라고만 답하라. 추측하지 마라.\n"
    "답변 끝에는 항상 '이 답변은 의료 진단이 아닌 정보 제공 목적입니다'를 "
    "덧붙여라.\n\n"
    "[문서]\n{context}\n\n[질문] {question}\n\n[답변]"
)


def build_answer_chain():
    """검색 문맥과 질문을 입력받는 Gemini 답변 체인을 만든다."""
    prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0)
    return prompt | llm | StrOutputParser()
