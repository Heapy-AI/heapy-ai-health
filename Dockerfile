# 작성자: 김진우
FROM python:3.11-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/opt/models \
    TOKENIZERS_PARALLELISM=false OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
COPY requirements-deploy.txt requirements.txt ./
RUN pip install --no-cache-dir torch==2.13.0+cpu --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements-deploy.txt \
    && useradd --uid 10001 --no-create-home app
COPY scripts/deploy/cache_model.py /tmp/cache_model.py
RUN python /tmp/cache_model.py && chmod -R a+rX /opt/models
COPY app/ ./app/
COPY model/classifier/artifacts/intent-v7/best_model.json ./model/classifier/artifacts/intent-v7/best_model.json
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=4s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=3)" || exit 1
CMD ["uvicorn", "app.internal:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "4", "--no-access-log"]
