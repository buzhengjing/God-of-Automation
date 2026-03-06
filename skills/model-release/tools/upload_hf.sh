#!/bin/bash
set -euo pipefail

# Usage: upload_hf.sh <model_name> <model_path>
# Upload model to HuggingFace with retry

MAX_RETRIES=3
RETRY_DELAY=10

show_help() {
    echo "Usage: $0 <model_name> <model_path>"
    echo "Upload a FlagOS model to HuggingFace"
    echo ""
    echo "Arguments:"
    echo "  model_name  Model name (e.g., Qwen3.5-35B-A3B-FlagOS)"
    echo "  model_path  Local path to model directory"
    echo ""
    echo "Prerequisites:"
    echo "  Run 'hf auth login' first to authenticate"
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

# Check model path exists
if [[ ! -d "$MODEL_PATH" ]]; then
    echo "Error: Model path '$MODEL_PATH' not found" >&2
    exit 1
fi

# Check HuggingFace CLI
if ! command -v hf &>/dev/null; then
    echo "Error: 'hf' CLI not found. Install with: pip install huggingface_hub[cli]" >&2
    exit 1
fi

# Check login status
if ! hf whoami &>/dev/null; then
    echo "Error: Not logged in to HuggingFace. Run 'hf auth login' first." >&2
    exit 1
fi

# Upload with retry
upload_with_retry() {
    local attempt=1
    while [[ $attempt -le $MAX_RETRIES ]]; do
        echo "Upload attempt $attempt/$MAX_RETRIES..."
        if hf upload "FlagRelease/$MODEL_NAME" "$MODEL_PATH" --repo-type model; then
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
    echo "Success: Model uploaded to https://huggingface.co/FlagRelease/$MODEL_NAME"
else
    echo "Error: Failed to upload after $MAX_RETRIES attempts" >&2
    exit 1
fi