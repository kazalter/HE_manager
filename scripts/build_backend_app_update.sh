#!/usr/bin/env bash
# Build an application-code-only backend image from an existing local image.
# Use the regular Dockerfile when requirements, OS packages, or deployment files change.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
base=${1:-he-manager-backend:latest}
output=${2:-he-manager-backend:app-update}
workdir=$(mktemp -d "${TMPDIR:-/tmp}/he-backend-app.XXXXXX")
trap 'rm -rf "$workdir"' EXIT

base_id=$(docker image inspect "$base" --format '{{.Id}}')
docker run --rm --network none --entrypoint cat "$base_id" /srv/requirements.txt > "$workdir/requirements.txt"
if ! cmp -s "$root/backend/requirements.txt" "$workdir/requirements.txt"; then
    echo 'Backend requirements differ from the base image; use the full Dockerfile build.' >&2
    exit 1
fi
mkdir "$workdir/app"
tar -C "$root/backend/app" --exclude='__pycache__' --exclude='*.pyc' -cf - . | tar -C "$workdir/app" -xf -
cat > "$workdir/Dockerfile" <<'DOCKERFILE'
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
COPY app/ /srv/app/
DOCKERFILE
# The legacy builder can reuse the local image directly on hosts where BuildKit's
# containerd snapshotter would first unpack the multi-GB machine-learning layers.
DOCKER_BUILDKIT=0 docker build --network none --build-arg "BASE_IMAGE=$base_id" -t "$output" "$workdir"
printf 'Built %s from %s. Verify it before changing the running service.\n' "$output" "$base_id"
