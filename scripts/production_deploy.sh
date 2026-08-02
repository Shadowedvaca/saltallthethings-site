#!/usr/bin/env bash
set -euo pipefail

deploy_sha="${1:?deploy commit is required}"
deploy_tag="${2:?deploy tag is required}"
expected_version="${3:?expected version is required}"
previous_sha="${4:?previous checkout commit is required}"
repository="/opt/satt-platform"
environment_file="$repository/.env.production"
backup_dir="/opt/backups/satt-db/releases"
state_dir="$repository/.production-state"
assets_root="$repository/.production-assets"
systemd_service="satt"
volume_name="satt-production-postgres"
cron_file="/etc/cron.d/satt-backup"
current_runtime=""
previous_image=""
cutover_started="false"
static_swapped="false"
asset_container=""
candidate_static=""
rollback_static=""
rollback_cron=""
cron_changed="false"

printf '%s\n' "$deploy_sha" | grep -Eq '^[0-9a-f]{40}$'
printf '%s\n' "$previous_sha" | grep -Eq '^[0-9a-f]{40}$'
printf '%s\n' "$deploy_tag" | grep -Eq '^prod-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$'
test "$deploy_tag" = "prod-v$expected_version"
test "$PWD" = "$repository"
test "$(git rev-parse HEAD)" = "$deploy_sha"
test "$(tr -d '\r\n' < VERSION)" = "$expected_version"
test -f "$environment_file"
test "$(stat -c '%a' "$environment_file")" = "600"
for command in curl docker flock git pg_dump pg_restore python3 systemctl; do
  command -v "$command" >/dev/null
done

set -a
. "$environment_file"
set +a
for variable in \
  ENVIRONMENT DATABASE_ENVIRONMENT SATT_DB_NAME \
  SATT_DB_USER SATT_DB_PASSWORD SATT_APP_PORT SECRET_KEY; do
  test -n "${!variable:-}"
done
test "$ENVIRONMENT" = "production"
test "$DATABASE_ENVIRONMENT" = "production"
test -z "${DATABASE_URL:-}"

compose_with_image() {
  local commit="$1"
  local image="$2"
  shift 2
  COMMIT_SHA="$commit" \
    SATT_IMAGE="$image" \
    docker compose \
      --env-file "$environment_file" \
      -f compose.production.yaml \
      "$@"
}

compose() {
  compose_with_image "$deploy_sha" "satt:production-$deploy_sha" "$@"
}

compose config --quiet

if systemctl is-active --quiet "$systemd_service"; then
  current_runtime="systemd"
  test -n "${LEGACY_DATABASE_URL:-}"
  DATABASE_URL="$LEGACY_DATABASE_URL" python3 -c \
    'import os; from scripts.production_backup import host_runtime_database_url; host_runtime_database_url(os.environ["DATABASE_URL"])'

  test -z "$(docker ps --filter name='^/satt-production-app$' --format '{{.Names}}')"
  test -z "$(docker ps --filter name='^/satt-production-database$' --format '{{.Names}}')"
  if docker volume inspect "$volume_name" >/dev/null 2>&1; then
    echo "ERROR: first cutover refuses a pre-existing SATT production database volume"
    exit 1
  fi
elif docker ps --format '{{.Names}}' | grep -qx satt-production-app \
  && docker ps --format '{{.Names}}' | grep -qx satt-production-database; then
  current_runtime="container"
  previous_image="$(docker inspect --format '{{.Config.Image}}' satt-production-app)"
  printf '%s\n' "$previous_image" | grep -Eq '^satt:production-[0-9a-f]{40}$'
  docker volume inspect "$volume_name" >/dev/null
else
  echo "ERROR: no recognized complete SATT production runtime is active"
  exit 1
fi

install -d -m 0700 "$backup_dir" "$state_dir"
install -d -m 0755 "$assets_root"
test -f "$cron_file"
rollback_cron="$(mktemp "$state_dir/rollback-cron.XXXXXX")"
cp "$cron_file" "$rollback_cron"
chmod 0600 "$rollback_cron"

legacy_backup() {
  local phase="$1"
  DATABASE_URL="$LEGACY_DATABASE_URL" \
    python3 scripts/production_backup.py \
      --tag "$deploy_tag" \
      --phase "$phase"
}

container_backup() {
  local phase="$1"
  local timestamp backup_path digest
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  backup_path="$backup_dir/$phase-$deploy_tag-$timestamp.dump"
  test ! -e "$backup_path"
  umask 077
  if ! compose exec -T database sh -c \
    'exec pg_dump --format=custom --schema=satt --no-owner --no-privileges --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
    > "$backup_path" 2>/dev/null; then
    echo "ERROR: production database-container backup failed"
    return 1
  fi
  test -s "$backup_path"
  chmod 0600 "$backup_path"
  pg_restore --list "$backup_path" >/dev/null
  digest="$(sha256sum "$backup_path" | awk '{print $1}')"
  python3 -c \
    'import json,sys; print(json.dumps({"file":sys.argv[1],"sha256":sys.argv[2],"verified":True},sort_keys=True))' \
    "$(basename "$backup_path")" "$digest"
}

backup_path_from_json() {
  local payload="$1"
  local phase="$2"
  local filename
  filename="$(printf '%s' "$payload" | python3 -c 'import json,sys; print(json.load(sys.stdin)["file"])')"
  printf '%s\n' "$filename" | grep -Eq "^$phase-$deploy_tag-[0-9]{8}T[0-9]{6}Z[.]dump$"
  test -f "$backup_dir/$filename"
  printf '%s\n' "$backup_dir/$filename"
}

source_fingerprint() {
  if test "$current_runtime" = "systemd"; then
    local host_database_url
    host_database_url="$(
      DATABASE_URL="$LEGACY_DATABASE_URL" python3 -c \
        'import os; from scripts.production_backup import host_runtime_database_url; print(host_runtime_database_url(os.environ["DATABASE_URL"]))'
    )"
    DATABASE_URL="$host_database_url" \
      ENVIRONMENT=production \
      DATABASE_ENVIRONMENT=production \
      PYTHONPATH=src \
      "$repository/venv/bin/python" \
      -m satt.scripts.production_fingerprint \
      < /dev/null
    unset host_database_url
  else
    compose run --rm --no-deps --entrypoint python app \
      -m satt.scripts.production_fingerprint \
      < /dev/null
  fi
}

cleanup_candidate() {
  if test -n "$asset_container"; then
    docker rm -f "$asset_container" >/dev/null 2>&1 || true
    asset_container=""
  fi
  if test -n "$candidate_static" && test -d "$candidate_static"; then
    find "$candidate_static" -depth -delete >/dev/null 2>&1 || true
  fi
}

recover() {
  local status="$?"
  trap - EXIT
  if test "$status" -eq 0; then
    cleanup_candidate
    exit 0
  fi

  cleanup_candidate
  if test "$cutover_started" = "true"; then
    echo "Production verification failed; restoring the prior SATT runtime"
    if test "$static_swapped" = "true"; then
      failed_static="$assets_root/failed-$deploy_sha-$(date -u +%Y%m%dT%H%M%SZ)"
      mv "$repository/static" "$failed_static" || true
      mv "$rollback_static" "$repository/static" || true
    fi
    if test "$cron_changed" = "true"; then
      install -m 0644 "$rollback_cron" "$cron_file" || true
    fi
    compose down --remove-orphans || true
    if test "$current_runtime" = "systemd"; then
      git checkout --detach "$previous_sha" || true
      systemctl start "$systemd_service" || true
    elif test -n "$previous_image"; then
      compose_with_image "${previous_image#satt:production-}" "$previous_image" \
        up -d --wait --no-build database app || true
    fi
  else
    git checkout --detach "$previous_sha" || true
  fi
  exit "$status"
}
trap recover EXIT

if test "$current_runtime" = "systemd"; then
  preflight_backup="$(legacy_backup preflight)"
else
  preflight_backup="$(container_backup preflight)"
fi
printf '%s\n' "$preflight_backup"
backup_path_from_json "$preflight_backup" preflight >/dev/null

compose pull database
compose build --pull app

asset_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
candidate_static="$assets_root/candidate-$deploy_sha-$asset_stamp"
asset_container="satt-assets-${deploy_sha:0:12}-$RANDOM"
install -d -m 0755 "$candidate_static"
docker create \
  --name "$asset_container" \
  --entrypoint /bin/true \
  "satt:production-$deploy_sha" >/dev/null
for directory in css images js; do
  docker cp "$asset_container:/app/$directory" "$candidate_static/$directory"
done
for page in config.html index.html jokes.html login.html postproduction.html register.html show_management.html songs.html top3.html; do
  docker cp "$asset_container:/app/$page" "$candidate_static/$page"
done
docker rm "$asset_container" >/dev/null
asset_container=""
test -s "$candidate_static/index.html"
find "$candidate_static" -type d -exec chmod 0755 {} +
find "$candidate_static" -type f -exec chmod 0644 {} +

if test "$current_runtime" = "systemd"; then
  systemctl stop "$systemd_service"
else
  compose stop app
fi
cutover_started="true"

if test "$current_runtime" = "systemd"; then
  final_backup="$(legacy_backup final)"
else
  final_backup="$(container_backup final)"
fi
printf '%s\n' "$final_backup"
final_backup_path="$(backup_path_from_json "$final_backup" final)"
source_state="$(source_fingerprint)"

if test "$current_runtime" = "systemd"; then
  compose up -d --wait database
  if ! compose exec -T database sh -c \
    'exec pg_restore --exit-on-error --no-owner --no-privileges --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"' \
    < "$final_backup_path" >/dev/null 2>&1; then
    echo "ERROR: restoring the final production backup failed"
    exit 1
  fi
  restored_state="$(
    compose run --rm --no-deps --entrypoint python app \
      -m satt.scripts.production_fingerprint \
      < /dev/null
  )"
  test "$source_state" = "$restored_state"
  echo "Restored production authentication and data fingerprints match"
fi

compose up -d --wait --remove-orphans app
compose exec -T app alembic current --check-heads < /dev/null
post_state="$(compose exec -T app python -m satt.scripts.production_fingerprint < /dev/null)"
test "$source_state" = "$post_state"
echo "Production authentication and data fingerprints match after migrations"

local_health="$(
  curl --fail --silent --show-error \
    --retry 6 --retry-delay 2 --retry-connrefused \
    http://127.0.0.1:8200/api/health
)"
printf '%s' "$local_health" | python3 -c \
  'import json,sys; version,commit=sys.argv[1:3]; data=json.load(sys.stdin); assert data["status"]=="ok"; assert data["environment"]=="production"; assert data["version"]==version; assert data["commit"]==commit' \
  "$expected_version" "$deploy_sha"

rollback_static="$assets_root/rollback-$previous_sha-$asset_stamp"
test -d "$repository/static"
mv "$repository/static" "$rollback_static"
mv "$candidate_static" "$repository/static"
candidate_static=""
static_swapped="true"

public_health="$(
  curl --fail --silent --show-error \
    --retry 6 --retry-delay 2 --retry-connrefused \
    https://saltallthethings.com/api/health
)"
printf '%s' "$public_health" | python3 -c \
  'import json,sys; version,commit=sys.argv[1:3]; data=json.load(sys.stdin); assert data["status"]=="ok"; assert data["environment"]=="production"; assert data["version"]==version; assert data["commit"]==commit' \
  "$expected_version" "$deploy_sha"
curl --fail --silent --show-error https://saltallthethings.com/ >/dev/null

printf '%s\n' "$deploy_sha" > "$state_dir/current-commit"
printf '%s\n' "$deploy_tag" > "$state_dir/current-tag"
printf '%s\n' "$current_runtime" > "$state_dir/rollback-runtime"
printf '%s\n' "$previous_sha" > "$state_dir/rollback-commit"
printf '%s\n' "$rollback_static" > "$state_dir/rollback-static"
printf '%s\n' "$final_backup_path" > "$state_dir/final-backup"
printf '%s\n' "$volume_name" > "$state_dir/database-volume"
cron_candidate="$state_dir/current-backup-cron"
printf '%s\n' '0 3 * * * root cd /opt/satt-platform && /usr/bin/flock -n /run/lock/satt-production-backup.lock /usr/bin/env bash scripts/production_nightly_backup.sh >> /var/log/satt-backup.log 2>&1' > "$cron_candidate"
chmod 0600 "$cron_candidate"
install -m 0644 "$cron_candidate" "$cron_file"
cron_changed="true"
printf '%s\n' "$rollback_cron" > "$state_dir/rollback-cron"
if test -n "$previous_image"; then
  printf '%s\n' "$previous_image" > "$state_dir/rollback-image"
fi
chmod 0600 "$state_dir"/*

trap - EXIT
echo "Production deploy verified at commit $deploy_sha"
