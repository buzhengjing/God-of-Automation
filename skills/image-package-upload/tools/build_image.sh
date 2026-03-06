#!/bin/bash
set -euo pipefail

# Usage: build_image.sh <container_name> <tag>
# Commit a running container to a docker image

show_help() {
    echo "Usage: $0 <container_name> <tag>"
    echo "Commit a FlagOS container to a docker image"
    echo ""
    echo "Arguments:"
    echo "  container_name  Name or ID of the running container"
    echo "  tag             Image tag (e.g., 2603031041)"
    exit 0
}

[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && show_help

# Validate arguments
if [[ $# -lt 2 ]]; then
    echo "Error: Missing arguments" >&2
    echo "Usage: $0 <container_name> <tag>" >&2
    exit 1
fi

CONTAINER_NAME="$1"
TAG="$2"

# Check if container exists
if ! docker ps -a --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
    if ! docker ps -a --format '{{.ID}}' | grep -q "^${CONTAINER_NAME}"; then
        echo "Error: Container '$CONTAINER_NAME' not found" >&2
        exit 1
    fi
fi

echo "Committing container '$CONTAINER_NAME' to image flagos:$TAG ..."

if docker commit "$CONTAINER_NAME" "flagos:$TAG"; then
    echo "Success: Image built as flagos:$TAG"
    docker images "flagos:$TAG"
else
    echo "Error: Failed to commit container" >&2
    exit 1
fi