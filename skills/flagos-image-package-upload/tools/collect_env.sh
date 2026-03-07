#!/bin/bash
# FlagOS Environment Collection Script
# Usage: bash collect_env.sh <container_name>

set -e

CONTAINER_NAME="$1"
OUTPUT_FILE="env_info.json"

if [ -z "$CONTAINER_NAME" ]; then
    echo "Usage: $0 <container_name>"
    exit 1
fi

echo "Collecting environment info from container: $CONTAINER_NAME"

# Function to run command in container
run_in_container() {
    docker exec "$CONTAINER_NAME" bash -c "$1" 2>/dev/null || echo ""
}

# Collect versions
PYTHON_VERSION=$(run_in_container "python --version 2>&1 | grep -oP '\d+\.\d+'")
TORCH_VERSION=$(run_in_container "python -c 'import torch; print(torch.__version__)' 2>/dev/null | sed 's/+/-/g'")
TRITON_VERSION=$(run_in_container "pip show triton 2>/dev/null | grep Version | awk '{print \$2}'" | sed 's/+/-/g')
GEMS_VERSION=$(run_in_container "pip show flag-gems 2>/dev/null | grep Version | awk '{print \$2}'" | sed 's/+/-/g')
SCALE_VERSION=$(run_in_container "pip show flagscale 2>/dev/null | grep Version | awk '{print \$2}'" | sed 's/+/-/g')
CUDA_VERSION=$(run_in_container "nvcc --version 2>/dev/null | grep release | grep -oP '\d+\.\d+'")
GPU_TYPE=$(run_in_container "nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | tr '[:upper:]' '[:lower:]' | tr ' ' '_'")
ARCH=$(run_in_container "uname -m")
DRIVER_VERSION=$(run_in_container "nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1")

# Generate JSON
cat > "$OUTPUT_FILE" << EOF
{
  "vendor": "",
  "model_name": "",
  "tree_version": "${TRITON_VERSION:-unknown}",
  "gems_version": "${GEMS_VERSION:-unknown}",
  "scale_version": "${SCALE_VERSION:-unknown}",
  "cx_version": "",
  "python_version": "${PYTHON_VERSION:-unknown}",
  "torch_version": "${TORCH_VERSION:-unknown}",
  "cuda_version": "${CUDA_VERSION:-unknown}",
  "gpu_type": "${GPU_TYPE:-unknown}",
  "architecture": "${ARCH:-unknown}",
  "driver_version": "${DRIVER_VERSION:-unknown}"
}
EOF

echo "Environment info saved to: $OUTPUT_FILE"
echo ""
echo "Please fill in the following fields manually:"
echo "  - vendor (e.g., iluvatar, nvidia)"
echo "  - model_name (e.g., qwen2.5-7b)"
echo "  - cx_version"
echo ""
cat "$OUTPUT_FILE"
