FROM python:3.13-slim
WORKDIR /worker
COPY pyproject.toml .
RUN pip install --no-cache-dir . && playwright install --with-deps chromium
COPY worker.py .
CMD ["python", "worker.py"]
