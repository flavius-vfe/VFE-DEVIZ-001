FROM python:3.13-slim
WORKDIR /app

COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir .

COPY alembic.ini .
COPY alembic ./alembic
COPY docker-entrypoint.sh ./docker-entrypoint.sh
RUN chmod +x ./docker-entrypoint.sh

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=30s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2)" || exit 1
ENTRYPOINT ["./docker-entrypoint.sh"]
