# KYS sorgu servisi: web sayfası + REST API + MCP. Salt okunur; veritabanı /data altına bağlanır
# veya KYS_DB_URL ile açılışta indirilir. Herhangi bir konteyner platformunda çalışır (Cloud Run, Koyeb,
# Render, Hugging Face Spaces, VPS...). Ayrıntılar: docs/DEPLOY.md
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

COPY backend/pyproject.toml backend/
COPY backend/kys backend/kys
RUN pip install "./backend[server]"

RUN useradd --create-home kys && mkdir -p /data && chown kys /data
USER kys

ENV KYS_DB_PATH=/data/kys.db \
    KYS_OVERRIDES_PATH=/data/kys_overrides.json \
    KYS_BASE_PATH=/qa \
    PORT=8080
EXPOSE 8080
VOLUME /data

CMD ["sh", "-c", "exec uvicorn kys.api.app:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
