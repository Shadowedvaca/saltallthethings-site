#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
    DATABASE_URL="$(
        python -c 'from satt.database_url import private_database_url_from_environment; print(private_database_url_from_environment())'
    )"
    export DATABASE_URL
fi

# Validate environment/data ownership and external-service guards before any
# migration opens a database connection.
python -c "from satt.config import get_settings; get_settings()"

echo "Applying database migrations..."
alembic upgrade head

echo "Starting SATT..."
exec "$@"
