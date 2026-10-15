#!/usr/bin/env bash
# Build the single-container image and export a tarball that works with `docker load`.
#   ./scripts/build-image.sh                 # default (NVIDIA embeddings)  -> vectora-image.tar.gz
#   EMBEDDINGS=local ./scripts/build-image.sh
#   PLATFORM=linux/arm64 ./scripts/build-image.sh   # e.g. cross-build for ARM servers
set -euo pipefail
cd "$(dirname "$0")/.."

TAG="${TAG:-vectora:latest}"
EMBEDDINGS="${EMBEDDINGS:-nvidia}"
OUT="${OUT:-vectora-image.tar.gz}"

args=(build --build-arg "EMBEDDINGS=${EMBEDDINGS}" -t "${TAG}" .)
[[ -n "${PLATFORM:-}" ]] && args=(build --platform "${PLATFORM}" --build-arg "EMBEDDINGS=${EMBEDDINGS}" -t "${TAG}" .)

echo ">> docker ${args[*]}"
docker "${args[@]}"
echo ">> exporting ${TAG} -> ${OUT}"
docker save "${TAG}" | gzip > "${OUT}"
ls -lh "${OUT}"
echo "Load it elsewhere with:  gunzip -c ${OUT} | docker load"
