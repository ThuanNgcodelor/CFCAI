#!/usr/bin/env bash
# Deliberately guarded restore: this command replaces database contents.
set -euo pipefail

if [[ "${1:-}" == "--help" || $# -eq 0 ]]; then
    cat <<'USAGE'
Usage: bash scripts/restore_postgres.sh --confirm-restore backups/<file>.dump

WARNING: pg_restore --clean replaces database objects. First stop api/worker,
create a fresh backup, have a second operator verify the target file, then pass
the exact confirmation flag above. The dump must live under backups/.
USAGE
    exit 0
fi

if [[ "${1:-}" != "--confirm-restore" || $# -ne 2 ]]; then
    echo "Refusing restore without --confirm-restore and one backup file." >&2
    exit 2
fi

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backup_root="${repository_root}/backups"
backup_path="$(realpath -m "${2}")"

if [[ "${backup_path}" != "${backup_root}/"* || "${backup_path}" != *.dump || ! -f "${backup_path}" ]]; then
    echo "Backup must be an existing .dump inside ${backup_root}" >&2
    exit 2
fi

echo "Restoring ${backup_path}. API and worker must already be stopped."
docker compose exec -T postgres pg_restore \
    -U "${POSTGRES_USER:-cfc_admin}" \
    --clean --if-exists --no-owner \
    -d "${POSTGRES_DB:-cfc_zeo_db}" < "${backup_path}"
echo "restore_completed=${backup_path}"
