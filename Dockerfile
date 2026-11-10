FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MOTIVA_HOST=0.0.0.0 \
    MOTIVA_PORT=8787 \
    MOTIVA_DB_PATH=/data/motiva.sqlite3

WORKDIR /opt/motiva/app

RUN addgroup --system motiva && adduser --system --ingroup motiva motiva \
    && mkdir -p /data \
    && chown motiva:motiva /data

COPY app/server.py app/navigation.py app/integration.py app/index.html ./

USER motiva
VOLUME ["/data"]
EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8787/api/health', timeout=3)"

CMD ["python", "server.py"]
