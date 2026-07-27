"""
HEAPY 건강정보 RAG — Gradio 웹 인터페이스

4개 탭:
1. Health : 서버·컬렉션별 인덱스 상태 확인
2. Intent : 사용자 질문의 최상위 intent 분류
3. Search : 유사 청크 검색 (LLM 호출 없음)
4. Ask    : 지식베이스 근거 답변 (LLM 호출)

※ 우리 API는 컬렉션(health_checkup_info / disease_info …) 지정이 필수라 각 탭에 컬렉션 선택을 둔다.
"""

import json
from typing import Tuple

import gradio as gr
import requests

API_BASE_URL = "http://localhost:8000"
FALLBACK_COLLECTIONS = ["disease_info", "health_checkup_info"]


def get_collections() -> list[str]:
    """서버 /health 의 컬렉션 목록을 가져온다(빌드 시 1회). 서버가 없으면 기본값."""
    try:
        data = requests.get(f"{API_BASE_URL}/health", timeout=5).json()
        counts = data.get("indexed_chunks", {}) or {}
        names = [name for name, count in counts.items() if count > 0]
        return names or FALLBACK_COLLECTIONS
    except Exception:
        return FALLBACK_COLLECTIONS


# ───────────────────────── Health ─────────────────────────
def check_health() -> str:
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        ready = data.get("ready", False)
        counts = data.get("indexed_chunks", {}) or {}
        intent_status = data.get("intent_classifier", {}) or {}
        lines = "\n".join(f"  - `{name}`: {cnt:,}개" for name, cnt in counts.items()) or "  - (없음)"
        return (
            f"🔍 **서버 상태**\n\n"
            f"- **Status**: {data.get('status', 'unknown')}\n"
            f"- **Ready**: {'✅ 준비 완료' if ready else '❌ 준비 안 됨'}\n"
            f"- **벡터 백엔드**: `{data.get('vector_backend', 'unknown')}`\n"
            f"- **임베딩 모델**: `{data.get('embed_model', 'unknown')}`\n"
            f"- **Intent 분류기**: "
            f"{'✅ 준비 완료' if intent_status.get('ready') else '❌ 모델 없음'}"
            f" (`{intent_status.get('model_version') or 'none'}`)\n"
            f"- **컬렉션별 인덱스**:\n{lines}"
        )
    except Exception as e:
        return f"❌ **오류**: {e}\n\n서버가 실행 중인지 확인하세요 (`uvicorn app.main:app`)."


# ───────────────────────── Intent ─────────────────────────
def classify_intent(question: str) -> Tuple[str, str]:
    """질문의 최상위 intent와 클래스별 확률을 표시한다."""
    if not question.strip():
        return "💡 질문을 입력하세요.", ""
    try:
        resp = requests.post(
            f"{API_BASE_URL}/intent/classify",
            json={"question": question},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        probabilities = data.get("probabilities", {}) or {}
        probability_lines = "\n".join(
            f"- `{label}`: {probability:.2%}"
            for label, probability in sorted(
                probabilities.items(),
                key=lambda item: item[1],
                reverse=True,
            )
        )
        return (
            f"🧭 **Intent 분류 결과**\n\n"
            f"- 질문: `{question}`\n"
            f"- intent: `{data.get('intent', 'unknown')}`\n"
            f"- 신뢰도: `{data.get('confidence', 0.0):.2%}`\n"
            f"- 검토 필요: `{'예' if data.get('uncertain') else '아니요'}`\n"
            f"- 모델: `{data.get('model_version', 'unknown')}`\n\n"
            f"**클래스별 확률**\n{probability_lines}"
        ), json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"❌ **오류**: {e}", ""


# ───────────────────────── Search ─────────────────────────
def search_chunks(question: str, collection: str) -> Tuple[str, str]:
    if not question.strip():
        return "💡 질문을 입력하세요.", ""
    try:
        resp = requests.post(
            f"{API_BASE_URL}/search",
            json={"question": question, "collection": collection},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        hits = data.get("hits", [])
        if not hits:
            return (f"🔎 **검색 결과** (`{collection}`)\n\n질문: `{question}`\n\n결과 없음",
                    json.dumps(data, ensure_ascii=False, indent=2))
        md = [f"🔎 **검색 결과** (`{collection}`)\n\n질문: `{question}`\n\n**청크 {len(hits)}개**:"]
        for i, hit in enumerate(hits, 1):
            md.append(f"\n**{i}. {hit.get('source', '출처 미상')}**\n```\n{hit.get('text', '')}…\n```")
        return "\n".join(md), json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"❌ **오류**: {e}", ""


# ───────────────────────── Ask ─────────────────────────
def ask_question(question: str, collection: str) -> Tuple[str, str]:
    if not question.strip():
        return "💡 질문을 입력하세요.", ""
    try:
        resp = requests.post(
            f"{API_BASE_URL}/ask",
            json={"question": question, "collection": collection},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        grounded = data.get("grounded", False)
        sources = data.get("sources", [])
        src_md = "\n".join(f"- {s}" for s in sources) if sources else "- (출처 없음)"
        return (
            f"💬 **답변** (`{collection}`)\n\n질문: `{question}`\n\n"
            f"{data.get('answer', '')}\n\n"
            f"**상태**: {'✅ 근거 있음' if grounded else '⚠️ 근거 없음'}\n\n"
            f"**출처**:\n{src_md}"
        ), json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"❌ **오류**: {e}", ""


# ───────────────────────── UI ─────────────────────────
def create_ui():
    collections = get_collections()
    default_col = "disease_info" if "disease_info" in collections else collections[0]
    ph = "예: 감기 원인이 뭐야? / 공복혈당 정상 수치는?"

    with gr.Blocks(title="HEAPY 건강정보 RAG", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🩺 HEAPY 건강정보 RAG\n\n검색(임베딩) + 답변(LLM) 분리 설계 · 컬렉션 선택형")

        with gr.Tabs():
            # ── Health ──
            with gr.TabItem("🔍 Health"):
                gr.Markdown("### 서버·컬렉션 인덱스 상태\nLLM을 호출하지 않습니다.")
                health_btn = gr.Button("상태 확인", variant="primary", size="lg")
                health_output = gr.Markdown("상태를 확인하려면 버튼을 클릭하세요.")
                health_btn.click(fn=check_health, outputs=health_output)

            # ── Intent ──
            with gr.TabItem("🧭 Intent"):
                gr.Markdown("### 최상위 Intent 분류\n질문을 임베딩한 뒤 Linear/Softmax 분류 결과와 확률을 표시합니다.")
                intent_question = gr.Textbox(label="질문", placeholder="예: 최근 AST가 높은데 왜 그런가요?", lines=2)
                intent_btn = gr.Button("분류", variant="primary", size="lg")
                with gr.Row():
                    intent_output = gr.Markdown(value="분류 결과가 여기 표시됩니다.")
                    intent_json = gr.Code(label="JSON 응답", language="json", interactive=False)
                intent_btn.click(classify_intent, intent_question, [intent_output, intent_json])
                intent_question.submit(classify_intent, intent_question, [intent_output, intent_json])

            # ── Search ──
            with gr.TabItem("🔎 Search"):
                gr.Markdown("### 유사 청크 검색\n질문과 가장 유사한 청크를 검색합니다. LLM 호출 없음 _(검색 품질 확인용)_")
                search_col = gr.Dropdown(collections, value=default_col, label="컬렉션")
                search_question = gr.Textbox(label="질문", placeholder=ph, lines=2)
                search_btn = gr.Button("검색", variant="primary", size="lg")
                with gr.Row():
                    search_output = gr.Markdown(value="검색 결과가 여기 표시됩니다.")
                    search_json = gr.Code(label="JSON 응답", language="json", interactive=False)
                search_btn.click(search_chunks, [search_question, search_col], [search_output, search_json])
                search_question.submit(search_chunks, [search_question, search_col], [search_output, search_json])

            # ── Ask ──
            with gr.TabItem("💬 Ask"):
                gr.Markdown("### 지식베이스 근거 답변\n검색 청크를 근거로 LLM이 답변합니다. _근거가 없으면 '지식베이스에 근거 없음'_")
                ask_col = gr.Dropdown(collections, value=default_col, label="컬렉션")
                ask_input = gr.Textbox(label="질문", placeholder=ph, lines=2)
                ask_btn = gr.Button("답변 생성", variant="primary", size="lg")
                with gr.Row():
                    ask_output = gr.Markdown(value="답변이 여기 표시됩니다.")
                    ask_json = gr.Code(label="JSON 응답", language="json", interactive=False)
                ask_btn.click(ask_question, [ask_input, ask_col], [ask_output, ask_json])
                ask_input.submit(ask_question, [ask_input, ask_col], [ask_output, ask_json])

        gr.Markdown("---\n**API**: `http://localhost:8000` · **UI 포트**: `7860`\n\n"
                    "⚠️ 이 답변은 의료 진단이 아닌 정보 제공 목적입니다.")
    return demo


if __name__ == "__main__":
    create_ui().launch(server_name="0.0.0.0", server_port=7860, share=False, show_error=True)
