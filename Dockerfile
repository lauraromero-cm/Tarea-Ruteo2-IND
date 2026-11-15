FROM postgres:17-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-17-postgis-3 \
        postgresql-17-pgrouting \
        python3 python3-pip python3-venv \
        postgis \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /app/venv && \
    /app/venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PATH="/app/venv/bin:$PATH"
ENV RESIL_DSN="host=localhost port=5432 user=postgres dbname=resiliencia"
ENV RESIL_ADMIN_DSN="host=localhost port=5432 user=postgres dbname=postgres"

EXPOSE 5000

ENTRYPOINT ["docker-entrypoint.sh"]
