#!/usr/bin/env bash
set -euo pipefail

DOCKER_IMAGE=${DOCKER_IMAGE:-"parakeet-onnx:latest"}
DOCKER_NAME_FILTER=${DOCKER_NAME_FILTER:-"parakeet-onnx"}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker not available" >&2
  exit 1
fi

# Find running containers by image and by name filter
cids_img=$(docker ps --filter "ancestor=$DOCKER_IMAGE" --format '{{.ID}}' || true)
cids_name=$(docker ps --filter "name=$DOCKER_NAME_FILTER" --format '{{.ID}}' || true)

# Merge and stop
allcids=$(printf "%s\n%s\n" "$cids_img" "$cids_name" | sort -u | tr '\n' ' ')
if [[ -z "${allcids// /}" ]]; then
  echo "No running containers matched image=$DOCKER_IMAGE or name filter=$DOCKER_NAME_FILTER"
  exit 0
fi

echo "Stopping containers: $allcids"
docker stop $allcids >/dev/null
echo "Stopped."
