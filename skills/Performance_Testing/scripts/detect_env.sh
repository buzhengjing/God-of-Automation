#!/bin/bash
# Environment Detection Script
# Outputs JSON with detected environment information

echo "{"
echo "  \"hostname\": \"$(hostname 2>/dev/null || echo 'unknown')\","

# Detect GPU
GPU_INFO=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "N/A")
echo "  \"gpu_name\": \"$GPU_INFO\","

# GPU count
GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | wc -l || echo "0")
echo "  \"gpu_count\": $GPU_COUNT,"

# vLLM version
VLLM_VERSION=$(pip show vllm 2>/dev/null | grep "^Version:" | awk '{print $2}' || echo "not installed")
echo "  \"vllm_version\": \"$VLLM_VERSION\","

# Python version
PYTHON_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "unknown")
echo "  \"python_version\": \"$PYTHON_VERSION\","

# CUDA version
CUDA_VERSION=$(nvcc --version 2>/dev/null | grep "release" | awk '{print $6}' | tr -d ',' || echo "N/A")
echo "  \"cuda_version\": \"$CUDA_VERSION\","

# Relevant environment variables
echo "  \"env_vars\": {"
echo "    \"CUDA_VISIBLE_DEVICES\": \"${CUDA_VISIBLE_DEVICES:-not set}\","
echo "    \"MODEL_PATH\": \"${MODEL_PATH:-not set}\","
echo "    \"TOKENIZER_PATH\": \"${TOKENIZER_PATH:-not set}\","
echo "    \"HOST\": \"${HOST:-not set}\","
echo "    \"PORT\": \"${PORT:-not set}\""
echo "  },"

# Find model directories (limited search)
echo "  \"model_paths\": ["
FOUND_PATHS=0
for dir in /nfs /models /data/models; do
    if [ -d "$dir" ] && [ $FOUND_PATHS -lt 5 ]; then
        for model_dir in $(find "$dir" -maxdepth 3 -name "config.json" -exec dirname {} \; 2>/dev/null | head -5); do
            if [ $FOUND_PATHS -gt 0 ]; then
                echo ","
            fi
            echo -n "    \"$model_dir\""
            FOUND_PATHS=$((FOUND_PATHS + 1))
        done
    fi
done
echo ""
echo "  ]"

echo "}"
