#!/bin/bash
set -euo pipefail

REGISTRY="${REGISTRY:-parasolnikov}"
VERSION="${VERSION:-0.7}"
TARGETS="${TARGETS:-frontend controller watcher}"
PUSH=true

usage() {
    echo "Usage: $0 [--no-push] [--only=<target>[,<target>...]] [-v|--version <version>]"
    echo "Builds (and pushes) the multi-stage Dockerfile targets."
    echo "Env overrides: REGISTRY (default: parasolnikov), VERSION (default: 0.7), TARGETS"
    echo "Example: $0                  # build + push all targets"
    echo "         $0 --no-push        # build only, no push"
    echo "         $0 --only=watcher   # build + push watcher only"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-push)        PUSH=false ;;
        --only=*)         TARGETS="${1#--only=}"; TARGETS="${TARGETS//,/ }" ;;
        -v|--version)     VERSION="$2"; shift ;;
        -h|--help)        usage; exit 0 ;;
        *)                echo "ERROR: unknown option: $1" >&2; usage; exit 1 ;;
    esac
    shift
done

if ! docker info >/dev/null 2>&1; then
    echo "ERROR: docker daemon not running" >&2
    exit 1
fi
if $PUSH && ! docker info 2>/dev/null | grep -q "Username:"; then
    echo "WARNING: not logged into Docker Hub (run: docker login) - push may fail" >&2
fi

for target in $TARGETS; do
    echo "=== building ${REGISTRY}/${target}:${VERSION} (target: ${target}) ==="
    docker image build --pull \
        --tag "${REGISTRY}/${target}:${VERSION}" \
        --target "${target}" .
    if $PUSH; then
        echo "=== pushing ${REGISTRY}/${target}:${VERSION} ==="
        docker image push "${REGISTRY}/${target}:${VERSION}"
    fi
done

echo "done: $TARGETS @ ${REGISTRY}:${VERSION}"
