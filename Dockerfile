FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    WUJI_DATA_DIR=/data WUJI_CONFIG_FILE=/data/runtime.env WUJI_RESOURCE_DIR=/app \
    WUJI_SITE_AUTH_ENABLED=true WUJI_SITE_SECURE_COOKIES=true PORT=8000
WORKDIR /app
COPY backend/requirements-prod.txt /app/backend/requirements-prod.txt
RUN pip install --no-cache-dir -r /app/backend/requirements-prod.txt \
    && apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home wuji && mkdir /data && chown wuji:wuji /data
COPY backend/app /app/backend/app
COPY index.html /app/index.html
COPY web /app/web
COPY data/worlds /app/data/worlds
COPY research/*.json /app/research/
COPY tools/serve_web.py /app/tools/serve_web.py
COPY tools/docker-entrypoint.sh /app/tools/docker-entrypoint.sh
RUN chmod +x /app/tools/docker-entrypoint.sh
VOLUME /data
EXPOSE 8000
ENTRYPOINT ["/app/tools/docker-entrypoint.sh"]
CMD ["python", "tools/serve_web.py"]
