FROM python:3.12-slim

LABEL org.opencontainers.image.title="Atlas Server" \
      org.opencontainers.image.description="Dokumentation av Windows Server-miljöer" \
      org.opencontainers.image.licenses="MIT"

# HTTPS är på (TLS=auto): ett självsignerat certifikat skapas i /data/tls vid första start.
ARG PORT=8090

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ATLAS_SERVER_DATA=/data \
    HOST=0.0.0.0 \
    PORT=${PORT} \
    TZ=Europe/Stockholm \
    TLS=auto

# openssl skapar det självsignerade certifikatet för HTTPS vid första start.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata openssl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py atlas_server_cli.py server_model.py server_docx.py server_xlsx.py server_keepass.py LICENSE THIRD-PARTY-NOTICES.md ./
COPY static ./static
# Insamlaren följer med, så att den kan hämtas från webben.
COPY collector ./collector

RUN useradd --create-home --uid 1000 app \
 && mkdir -p /data \
 && chown app:app /data
USER app

VOLUME ["/data"]
EXPOSE ${PORT}
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import os, ssl, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8090'), timeout=3, context=ssl._create_unverified_context())" || exit 1

CMD ["python", "app.py"]
