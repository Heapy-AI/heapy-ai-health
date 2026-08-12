#!/usr/bin/env python3
"""HEAPY 개발자 모니터링 UI 실행 스크립트.

작성자: 김진우
수정자: 고수연 (자동실행 추가)
"""

import webbrowser
from threading import Timer

import uvicorn


def _open_browser() -> None:
    try:
        webbrowser.open("http://localhost:3000")
    except Exception:
        pass


if __name__ == "__main__":
    print("Starting demo UI server at http://localhost:3000 and opening browser...")
    Timer(1.0, _open_browser).start()
    uvicorn.run(
        "app.admin_frontend:app",
        host="0.0.0.0",
        port=3000,
        reload=False,
    )

