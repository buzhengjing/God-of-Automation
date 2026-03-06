#!/bin/bash
set -euo pipefail

# Usage: push_image.sh <tag> <full_image_name>
# Tag and push image to Harbor registry with retry

HARBOR_REGISTRY="harbor.baai.ac.cn"
MAX_RETRIES=3
RETRY_DELAY=5

show_help() {
    echo "Usage: $0 <tag> <full_image_name>"
    echo "Tag and push a FlagOS image to Harbor"
    echo ""
    echo "Arguments:"
    echo "  tag              Image tag (e.g., 2603031041)"
    echo "  full_image_name  Full image name without tag"
    echo ""
    echo "Example:"
    echo "  $0 2603031041 harbor.baai.ac.cn/flagrelease-public/flagrelease-nvidia-release-model_qwen3.5"
    exit 0
}

[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && show_help

# Validate arguments
if [[ $# -lt 2 ]]; then
    echo "Error: Missing arguments" >&2
    echo "Usage: $0 <tag> <full_image_name>" >&2
    exit 1
fi

IMAGE_TAG="$1"
FULL_IMAGE_NAME="$2"

# Check source image exists
if ! docker image inspect "flagos:$IMAGE_TAG" &>/dev/null; then
    echo "Error: Source image 'flagos:$IMAGE_TAG' not found" >&2
    exit 1
fi

# Tag image
echo "Tagging image..."
docker tag "flagos:$IMAGE_TAG" "$FULL_IMAGE_NAME:$IMAGE_TAG"

# Check Harbor login status
if ! docker pull "$HARBOR_REGISTRY/library/alpine" &>/dev/null 2>&1; then
    echo "Harbor login required..."
    docker login "$HARBOR_REGISTRY"
fi

# Push with retry
push_with_retry() {
    local attempt=1
    while [[ $attempt -le $MAX_RETRIES ]]; do
        echo "Push attempt $attempt/$MAX_RETRIES..."
        if docker push "$FULL_IMAGE_NAME:$IMAGE_TAG"; then
            return 0
        fi
        echo "Push failed, retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
        ((attempt++))
    done
    return 1
}

if push_with_retry; then
    echo "Success: Image pushed to $FULL_IMAGE_NAME:$IMAGE_TAG"
else
    echo "Error: Failed to push image after $MAX_RETRIES attempts" >&2
    exit 1
fi