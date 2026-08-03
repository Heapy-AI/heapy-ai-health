#!/usr/bin/env python3
"""
HEAPY 건강정보 RAG — Gradio UI 실행 스크립트

사용법:
    python run_ui.py

주의:
    - FastAPI 서버(uvicorn)가 이미 실행 중이어야 합니다
    - 서버: http://localhost:8000
    - Gradio UI: http://localhost:7860
"""

import sys

import gradio as gr

# Windows 콘솔(cp949)에서 이모지 print 시 UnicodeEncodeError 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.ui import create_ui

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🩺 HEAPY 건강정보 RAG — Gradio UI 시작")
    print("="*60)
    print("📌 사전 요구사항:")
    print("   1. FastAPI 서버가 실행 중이어야 합니다:")
    print("      uvicorn app.main:app --reload")
    print("   2. 다른 터미널에서 이 스크립트를 실행하세요")
    print("   3. /ask(LLM) 사용 시 GEMINI_API_KEY(또는 GOOGLE_API_KEY) 필요")
    print("\n📍 접속 URL:")
    print("   - Gradio UI: http://localhost:7860")
    print("   - API 서버: http://localhost:8000")
    print("="*60 + "\n")
    
    demo = create_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft(),
    )
