#!/bin/sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
    : "${SATT_DB_HOST:?SATT_DB_HOST is required when DATABASE_URL is unset}"
    : "${SATT_DB_PORT:?SATT_DB_PORT is required when DATABASE_URL is unset}"
    : "${SATT_DB_NAME:?SATT_DB_NAME is required when DATABASE_URL is unset}"
    : "${SATT_DB_USER:?SATT_DB_USER is required when DATABASE_URL is unset}"
    : "${SATT_DB_PASSWORD:?SATT_DB_PASSWORD is required when DATABASE_URL is unset}"

    DATABASE_URL="$(
        python -c 'import os, urllib.parse; print("postgresql+asyncpg://{}:{}@{}:{}/{}".format(urllib.parse.quote(os.environ["SATT_DB_USER"], safe=""), urllib.parse.quote(os.environ["SATT_DB_PASSWORD"], safe=""), os.environ["SATT_DB_HOST"], os.environ["SATT_DB_PORT"], urllib.parse.quote(os.environ["SATT_DB_NAME"], safe="")))'
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
