"""이미지 빌드 시 공개 임베딩 모델을 준비한다. 작성자: 김진우."""
from sentence_transformers import SentenceTransformer

SentenceTransformer("jhgan/ko-sroberta-multitask", device="cpu", trust_remote_code=False)
