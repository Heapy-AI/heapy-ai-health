#!/usr/bin/env python3
"""HEAPY 개발자 모니터링 UI 실행 스크립트.

작성자: 김진우
"""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.admin_frontend:app",
        host="0.0.0.0",
        port=3000,
        reload=False,
    )
