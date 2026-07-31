FROM python:3.12-slim-bookworm

ARG VCS_REF=unknown

LABEL org.opencontainers.image.title="Salt All The Things"
LABEL org.opencontainers.image.revision="${VCS_REF}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN addgroup --system satt \
    && adduser --system --ingroup satt --home /app satt

COPY requirements.lock .
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.lock

COPY VERSION alembic.ini ./
COPY src/satt/ src/satt/
COPY src/sv_common/ src/sv_common/
COPY css/ css/
COPY images/ images/
COPY js/ js/
COPY *.html ./
COPY scripts/container-entrypoint.sh /usr/local/bin/satt-entrypoint

RUN chmod 0555 /usr/local/bin/satt-entrypoint \
    && chown -R satt:satt /app

USER satt

EXPOSE 8200

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=6 \
    CMD ["python", "-c", "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8200/api/health', timeout=2)); raise SystemExit(0 if data.get('status') == 'ok' else 1)"]

ENTRYPOINT ["satt-entrypoint"]
CMD ["uvicorn", "satt.main:app", "--host", "0.0.0.0", "--port", "8200", "--workers", "1"]
