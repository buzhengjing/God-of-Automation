#!/bin/bash
set -euo pipefail

# Usage: upload_modelscope.sh <model_name> <model_path>
# Upload model to ModelScope with retry
# Token is read from MODELSCOPE_TOKEN environment variable

MAX_RETRIES=3
RETRY_DELAY=10

show_help() {
    echo "Usage: $0 <model_name> <model_path>"
    echo "Upload a FlagOS model to ModelScope"
    echo ""
    echo "Arguments:"
    echo "  model_name  Model name (e.g., Qwen3.5-35B-A3B-FlagOS)"
    echo "  model_path  Local path to model directory"
    echo ""
    echo "Environment:"
    echo "  MODELSCOPE_TOKEN  API token (required)"
    echo ""
    echo "Example:"
    echo "  export MODELSCOPE_TOKEN='your-token-here'"
    echo "  $0 Qwen3.5-35B-A3B-FlagOS /data/Qwen3.5-35B-A3B"
    exit 0
}

[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && show_help

# Validate arguments
if [[ $# -lt 2 ]]; then
    echo "Error: Missing arguments" >&2
    echo "Usage: $0 <model_name> <model_path>" >&2
    exit 1
fi

MODEL_NAME="$1"
MODEL_PATH="$2"

# Check token
if [[ -z "${MODELSCOPE_TOKEN:-}" ]]; then
    echo "Error: MODELSCOPE_TOKEN environment variable not set" >&2
    echo "Set it with: export MODELSCOPE_TOKEN='your-token-here'" >&2
    exit 1
fi

# Check model path exists
if [[ ! -d "$MODEL_PATH" ]]; then
    echo "Error: Model path '$MODEL_PATH' not found" >&2
    exit 1
fi

# Check ModelScope CLI
if ! command -v modelscope &>/dev/null; then
    echo "Error: 'modelscope' CLI not found. Install with: pip install modelscope" >&2
    exit 1
fi

# Upload with retry
upload_with_retry() {
    local attempt=1
    while [[ $attempt -le $MAX_RETRIES ]]; do
        echo "Upload attempt $attempt/$MAX_RETRIES..."
        if modelscope upload "FlagRelease/$MODEL_NAME" "$MODEL_PATH" --token "$MODELSCOPE_TOKEN"; then
            return 0
        fi
        echo "Upload failed, retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
        ((attempt++))
    done
    return 1
}

echo "Uploading to FlagRelease/$MODEL_NAME ..."

if upload_with_retry; then
    echo "Success: Model uploaded to https://modelscope.cn/models/FlagRelease/$MODEL_NAME"
else
    echo "Error: Failed to upload after $MAX_RETRIES attempts" >&2
    exit 1
fi