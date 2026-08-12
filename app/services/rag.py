"""검색된 Pinecone 청크의 출처를 표현한다.

작성자: 김진우
"""

def cite(document) -> str:
    """청크 메타데이터로 일관된 출처 문자열을 만든다."""
    label = document.metadata.get("source_label")
    url = document.metadata.get("source")
    if label and url:
        return f"{label} · {url}"
    return label or url or "출처 미상"
