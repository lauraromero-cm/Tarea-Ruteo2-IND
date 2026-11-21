#!/bin/bash
set -e

PGDATA="${PGDATA:-/var/lib/postgresql/data}"

# --- 1. Init PostgreSQL if needed ---
if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "=== Initializing PostgreSQL cluster ==="
    su postgres -c "initdb -D $PGDATA"
    # Trust local connections
    echo "host all all 127.0.0.1/32 trust" >> "$PGDATA/pg_hba.conf"
    echo "local all all trust" >> "$PGDATA/pg_hba.conf"
fi

# --- 2. Start PostgreSQL ---
echo "=== Starting PostgreSQL ==="
su postgres -c "pg_ctl -D $PGDATA -l /tmp/pg.log start -w"

# Wait for readiness
until su postgres -c "pg_isready -h localhost" > /dev/null 2>&1; do
    sleep 1
done
echo "PostgreSQL ready."

# --- 3. Build the database (initdb + attr) ---
if ! su postgres -c "psql -h localhost -lqt" | grep -qw resiliencia; then
    echo "=== Building database (initdb) ==="
    python3 main.py initdb

    echo "=== Computing ATTR (Monte Carlo) ==="
    python3 main.py attr -n 5000
else
    echo "=== Database 'resiliencia' already exists, skipping init ==="
fi

# --- 4. Serve ---
PORT="${APP_PORT:-5000}"
echo "=== Starting web server on http://0.0.0.0:${PORT} ==="
exec python3 main.py serve --host 0.0.0.0 --port "$PORT"
