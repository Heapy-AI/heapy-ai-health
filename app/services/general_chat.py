"""검색이 필요 없는 일반 대화 응답 서비스.

작성자: 김진우
"""
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import MODEL


GENERAL_CHAT_PROMPT = """너는 HEAPY의 친절한 건강관리 대화 도우미다.
사용자의 일상적인 건강 대화나 감정 표현에 한국어로 짧고 자연스럽게 답하라.

규칙:
1. 질병을 진단하거나 약의 복용 여부·용량을 결정하지 않는다.
2. 구체적인 의료 사실이나 수치를 추측해서 만들지 않는다.
3. 응급 상황이나 위험한 증상으로 보이면 전문 의료기관의 도움을 권한다.
4. 건강과 무관한 전문 업무를 대신 수행하지 않는다.
5. 사용자가 먼저 인사한 경우가 아니면 인사말이나 "HEAPY입니다" 같은 자기소개를 반복하지 않는다.

[사용자]
{question}

[답변]
"""


def build_general_chat_chain():
    """일반 대화 전용 Gemini 체인을 생성한다."""
    prompt = ChatPromptTemplate.from_template(GENERAL_CHAT_PROMPT)
    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0.3)
    return prompt | llm | StrOutputParser()
