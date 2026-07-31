#!/usr/bin/env bash
set -euo pipefail

repository="/opt/satt-platform"
environment_file="$repository/.env.production"
state_dir="$repository/.production-state"
backup_dir="/opt/backups/satt-db/nightly"

volume_name="satt-production-postgres"
cd "$repository"
test "$(id -u)" = "0"
test -f "$environment_file"
test "$(stat -c '%a' "$environment_file")" = "600"
test -f "$state_dir/current-commit"

set -a
. "$environment_file"
set +a
for variable in ENVIRONMENT DATABASE_ENVIRONMENT SATT_DB_NAME SATT_DB_USER SATT_DB_PASSWORD; do
  test -n "${!variable:-}"
done
test "$ENVIRONMENT" = "production"
test "$DATABASE_ENVIRONMENT" = "production"
docker volume inspect "$volume_name" >/dev/null
docker ps --format '{{.Names}}' | grep -qx satt-production-database
test -z "${DATABASE_URL:-}"

commit="$(cat "$state_dir/current-commit")"
printf '%s\n' "$commit" | grep -Eq '^[0-9a-f]{40}$'
image="satt:production-$commit"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path="$backup_dir/satt-production-$timestamp.dump"

install -d -m 0700 "$backup_dir"
test ! -e "$backup_path"
umask 077
if ! COMMIT_SHA="$commit" SATT_IMAGE="$image" \
  docker compose \
    --env-file "$environment_file" \
    -f compose.production.yaml \
    exec -T database sh -c \
      'exec pg_dump --format=custom --schema=satt --no-owner --no-privileges --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
    > "$backup_path" 2>/dev/null; then
  echo "ERROR: SATT nightly database backup failed"
  exit 1
fi

test -s "$backup_path"
chmod 0600 "$backup_path"
pg_restore --list "$backup_path" >/dev/null
digest="$(sha256sum "$backup_path" | awk '{print $1}')"
python3 -c \
  'import json,sys; print(json.dumps({"file":sys.argv[1],"sha256":sys.argv[2],"verified":True},sort_keys=True))' \
  "$(basename "$backup_path")" "$digest"

find "$backup_dir" \
  -maxdepth 1 \
  -type f \
  -name 'satt-production-*.dump' \
  -mtime +14 \
  -delete
