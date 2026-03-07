#!/bin/bash
# FlagOS Service Health Check Script
# Usage: bash check_health.sh --host localhost --port 8000 --model model_name

set -e

# Default values
HOST="localhost"
PORT="8000"
MODEL=""
TIMEOUT=30

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --host) HOST="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 --host HOST --port PORT --model MODEL [--timeout TIMEOUT]"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

BASE_URL="http://${HOST}:${PORT}"

echo "=========================================="
echo "FlagOS Service Health Check"
echo "=========================================="
echo "Target: ${BASE_URL}"
echo "Model: ${MODEL:-'auto-detect'}"
echo ""

# Step 1: Check process
echo "[Step 1] Checking vLLM process..."
if pgrep -f "vllm" > /dev/null 2>&1; then
    echo "  [OK] vLLM process is running"
    pgrep -fa "vllm" | head -3
else
    echo "  [WARN] vLLM process not found, checking sglang..."
    if pgrep -f "sglang" > /dev/null 2>&1; then
        echo "  [OK] SGLang process is running"
    else
        echo "  [FAIL] No inference process found"
    fi
fi
echo ""

# Step 2: Query models API
echo "[Step 2] Querying models API..."
MODELS_RESPONSE=$(curl -s --max-time ${TIMEOUT} "${BASE_URL}/v1/models" 2>&1) || {
    echo "  [FAIL] Cannot reach API endpoint"
    exit 1
}

if echo "${MODELS_RESPONSE}" | grep -q "data"; then
    echo "  [OK] API is responding"
    echo "  Response: ${MODELS_RESPONSE}" | head -c 500

    # Auto-detect model if not specified
    if [ -z "${MODEL}" ]; then
        MODEL=$(echo "${MODELS_RESPONSE}" | grep -oP '"id"\s*:\s*"\K[^"]+' | head -1)
        echo ""
        echo "  Auto-detected model: ${MODEL}"
    fi
else
    echo "  [FAIL] Invalid API response"
    echo "  Response: ${MODELS_RESPONSE}"
    exit 1
fi
echo ""

# Step 3: Run inference test
echo "[Step 3] Running inference test..."
if [ -z "${MODEL}" ]; then
    echo "  [SKIP] No model specified, cannot run inference test"
    exit 0
fi

INFERENCE_RESPONSE=$(curl -s --max-time ${TIMEOUT} \
    -X POST "${BASE_URL}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{
        \"model\": \"${MODEL}\",
        \"messages\": [{\"role\": \"user\", \"content\": \"Say hello in one word.\"}],
        \"max_tokens\": 10
    }" 2>&1) || {
    echo "  [FAIL] Inference request failed"
    exit 1
}

if echo "${INFERENCE_RESPONSE}" | grep -q "choices"; then
    echo "  [OK] Inference successful"
    CONTENT=$(echo "${INFERENCE_RESPONSE}" | grep -oP '"content"\s*:\s*"\K[^"]+' | head -1)
    echo "  Model response: ${CONTENT}"
else
    echo "  [FAIL] Invalid inference response"
    echo "  Response: ${INFERENCE_RESPONSE}" | head -c 500
    exit 1
fi

echo ""
echo "=========================================="
echo "Health Check: PASSED"
echo "=========================================="
