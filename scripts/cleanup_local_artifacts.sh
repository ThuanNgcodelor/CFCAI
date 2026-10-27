#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

for cache_dir in .mypy_cache .pytest_cache .ruff_cache; do
    target="${repository_root}/${cache_dir}"
    if [[ -d "${target}" ]]; then
        rm -rf -- "${target}"
        echo "removed ${cache_dir}"
    fi
done

find "${repository_root}" \
    -type d -name __pycache__ \
    -not -path "${repository_root}/.git/*" \
    -not -path "${repository_root}/.venv/*" \
    -not -path "${repository_root}/.codegraph/*" \
    -writable \
    -prune -exec rm -rf -- {} +

protected_count="$({
    find "${repository_root}" \
        -type d -name __pycache__ \
        -not -path "${repository_root}/.git/*" \
        -not -path "${repository_root}/.venv/*" \
        -not -path "${repository_root}/.codegraph/*" \
        -not -writable -print
} | wc -l)"
if [[ "${protected_count}" -gt 0 ]]; then
    echo "skipped ${protected_count} protected container-owned __pycache__ directories"
fi

echo "local generated caches cleaned"
