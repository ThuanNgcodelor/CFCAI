#!/usr/bin/env bash
# Create a PostgreSQL custom-format backup without printing credentials.
set -euo pipefail

if [[ "${1:-}" == "--help" ]]; then
    cat <<'USAGE'
Usage: bash scripts/backup_postgres.sh [backup-directory]

Creates a timestamped .dump below this repository's backups/ directory. The
directory is intentionally constrained to backups/ so an operator cannot
accidentally overwrite an arbitrary path while performing a routine backup.
USAGE
    exit 0
fi

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_root="${repository_root}/backups"
requested_directory="${1:-${backup_root}}"
target_directory="$(realpath -m "${requested_directory}")"

if [[ "${target_directory}" != "${backup_root}" && "${target_directory}" != "${backup_root}/"* ]]; then
    echo "Backup directory must be inside ${backup_root}" >&2
    exit 2
fi

mkdir -p -- "${target_directory}"
umask 077
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output_path="${target_directory}/cfc_zeo_${timestamp}.dump"
temporary_path="${output_path}.partial"

trap 'rm -f -- "${temporary_path}"' EXIT
docker compose exec -T postgres pg_dump \
    -U "${POSTGRES_USER:-cfc_admin}" \
    --format=custom --no-owner --no-privileges \
    "${POSTGRES_DB:-cfc_zeo_db}" > "${temporary_path}"
mv -- "${temporary_path}" "${output_path}"
trap - EXIT

echo "backup_created=${output_path}"
