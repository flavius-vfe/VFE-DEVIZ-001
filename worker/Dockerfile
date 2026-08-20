FROM python:3.13-slim
WORKDIR /worker
COPY pyproject.toml .
RUN pip install --no-cache-dir . && playwright install --with-deps chromium
COPY worker.py .
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s --retries=3 \
  CMD python -c "import os,time; p='/tmp/vfe-deviz-worker-health'; assert os.path.exists(p) and time.time()-os.path.getmtime(p) < int(os.getenv('REFRESH_INTERVAL_SECONDS','86400'))+300" || exit 1
CMD ["python", "worker.py"]
