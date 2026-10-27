#!/usr/bin/env bash
# Run from any directory. Never source .env as shell code.
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose --project-directory "$PROJECT_ROOT" -f "$PROJECT_ROOT/docker-compose.yml" --profile app)

usage() {
    printf '%s\n' \
        'CFC–ZEO: ./build/manage.sh COMMAND' \
        '  start                 Build and start API, worker, PostgreSQL, Redis' \
        '  stop                  Stop all Compose services; KEEP volumes/data' \
        '  restart               Build/recreate API + worker; KEEP chat state' \
        '  status                Show containers (including stopped ones)' \
        '  logs [api|worker|all]  Follow logs; Ctrl+C does NOT stop the bot' \
        '  check                 Read-only API/Ollama/configuration preflight' \
        '  reset-chat --yes      Delete state of META_TEST_RECIPIENT_ID only' \
        '  reset-chat --all --yes Delete ALL chat state on BOTH pages' \
        '  test                  Offline tests for these management commands' \
        '  help                  Show this help' \
        'See build/README.md before resetting. No Messenger UI messages are deleted.'
}

die() { printf 'Error: %s\n' "$*" >&2; exit 2; }

action="${1:-help}"
if (( $# )); then shift; fi

# Validate everything before any Docker operation, especially destructive flags.
case "$action" in
    help|-h|--help) usage; exit 0 ;;
    start|stop|restart|status|check|test)
        (( $# == 0 )) || die "Unexpected arguments for $action" ;;
    logs)
        (( $# <= 1 )) || die 'logs accepts one service only'
        case "${1:-all}" in api|worker|all) ;; *) die 'Use logs api, worker or all' ;; esac ;;
    reset-chat)
        reset_all=false
        confirmed=false
        for argument in "$@"; do
            case "$argument" in
                --all) reset_all=true ;;
                --yes) confirmed=true ;;
                *) die 'Use reset-chat --yes or reset-chat --all --yes' ;;
            esac
        done
        "$confirmed" || die 'Reset deletes chat state. Add --yes to confirm; --all includes BOTH pages.' ;;
    *) usage >&2; die "Unknown command: $action" ;;
esac

if [[ "$action" == test ]]; then
    cd "$PROJECT_ROOT"
    exec python3 -m unittest discover -s tests/unit -p test_build_commands.py -v
fi

command -v docker >/dev/null || die 'Docker is not installed or not on PATH'
[[ -f "$PROJECT_ROOT/.env" ]] || die 'Missing .env; copy .env.example and configure it first'

case "$action" in
    start|restart)
        # Recreate, rather than `restart`, to apply changed Compose environment.
        options=(up -d --build)
        [[ "$action" != restart ]] || options+=(--force-recreate)
        "${COMPOSE[@]}" "${options[@]}" api worker
        "${COMPOSE[@]}" ps
        printf '%s\n' 'Containers started; run ./build/manage.sh check and test a NEW Messenger message.' ;;
    stop)
        "${COMPOSE[@]}" --profile '*' stop ;;
    status)
        "${COMPOSE[@]}" --profile '*' ps --all ;;
    logs)
        services=(api worker)
        [[ "${1:-all}" == all ]] || services=("$1")
        "${COMPOSE[@]}" logs --tail 100 --follow "${services[@]}" ;;
    check)
        "${COMPOSE[@]}" exec -T worker python scripts/verify_go_live.py --api-url http://api:8000 ;;
    reset-chat)
        running="$("${COMPOSE[@]}" ps --services --status running)"
        restore_services=()
        while IFS= read -r service; do
            case "$service" in api|worker) restore_services+=("$service") ;; esac
        done <<< "$running"
        [[ $'\n'"$running"$'\n' == *$'\nworker\n'* ]] || die 'Start the project first; worker must be running'

        # Resolve the test recipient INSIDE the container; never shell-source .env.
        # Use the same Compose run environment for precheck and reset.
        if ! "$reset_all"; then
            "${COMPOSE[@]}" run --rm --no-deps -T worker sh -c \
                'test -n "$META_TEST_RECIPIENT_ID" || { echo "META_TEST_RECIPIENT_ID is empty; reset refused" >&2; exit 2; }'
        fi

        restore_after_reset() {
            local result=$?
            trap - EXIT
            if ! "${COMPOSE[@]}" start "${restore_services[@]}"; then
                printf '%s\n' 'Could not restore services. Run ./build/manage.sh start' >&2
                result=1
            fi
            exit "$result"
        }
        # Pause ingestion AND processing to avoid deleting a batch while sending.
        # Restore only services that were already running, even if reset fails.
        trap restore_after_reset EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        "${COMPOSE[@]}" stop "${restore_services[@]}"
        if "$reset_all"; then
            "${COMPOSE[@]}" run --rm --no-deps -T worker python -m apps.tools.reset_conversations --all
        else
            "${COMPOSE[@]}" run --rm --no-deps -T worker sh -c \
                'test -n "$META_TEST_RECIPIENT_ID" && exec python -m apps.tools.reset_conversations --sender-id "$META_TEST_RECIPIENT_ID"'
        fi
        printf '%s\n' 'Chat state reset. CRM/catalog/FAQ/audit retained. Messenger history is unchanged.' ;;
esac
