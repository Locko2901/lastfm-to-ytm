FROM python:3.14-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/
COPY web/ ./web/
COPY run.py .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . gunicorn flask>=3.0.0 flask-babel>=4.0.0 apscheduler>=3.10.0 cryptography>=41.0.0 argon2-cffi>=23.1.0

RUN pybabel compile -d web/translations

RUN ARCH=$(uname -m) && \
    ESBUILD_ARCH=$([ "$ARCH" = "aarch64" ] && echo "linux-arm64" || echo "linux-x64") && \
    curl -fsSL "https://registry.npmjs.org/@esbuild/${ESBUILD_ARCH}/-/${ESBUILD_ARCH}-0.25.0.tgz" \
        | tar xzC /tmp && \
    mv /tmp/package/bin/esbuild /usr/local/bin/esbuild && \
    chmod +x /usr/local/bin/esbuild

RUN mkdir -p web/static/dist && \
    esbuild web/static/js/app.js \
        --bundle --minify --format=esm \
        --outfile=web/static/dist/app.min.js && \
    esbuild web/static/css/bundle.css \
        --bundle --minify \
        --outfile=web/static/dist/bundle.min.css


FROM python:3.14-slim AS production

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gosu passwd curl \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true

RUN groupadd -r lastfm && useradd -r -g lastfm lastfm

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY src/ ./src/
COPY web/ ./web/
COPY run.py .
COPY run_tags.py .
COPY pyproject.toml .
COPY devops/gunicorn.conf.py ./gunicorn.conf.py

COPY --from=builder /build/web/static/dist/ ./web/static/dist/
COPY --from=builder /build/web/translations/ ./web/translations/

COPY COMMIT_SHA ./COMMIT_SHA

COPY devops/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /app/runtime /app/config && \
    chown -R lastfm:lastfm /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    RUNTIME_DIR=/app/runtime \
    CONFIG_DIR=/app/config

ENTRYPOINT ["docker-entrypoint.sh"]

EXPOSE 2002

CMD ["gunicorn", "--config", "gunicorn.conf.py", "web.app:app"]
