#!/bin/bash
set -euo pipefail

# Usage: collect_env.sh [--json]
# Collect FlagOS environment versions for image naming

show_help() {
    echo "Usage: $0 [--json]"
    echo "Collect environment versions for FlagOS image naming"
    echo "  --json    Output in JSON format (default: table)"
    exit 0
}

# Normalize version: replace "+" with "-"
normalize_ver() {
    echo "$1" | sed 's/+/-/g'
}

# Get pip package version or "none"
get_pip_ver() {
    local ver
    ver=$(pip show "$1" 2>/dev/null | grep -i "^Version:" | awk '{print $2}') || true
    if [[ -z "$ver" ]]; then
        echo "none"
    else
        normalize_ver "$ver"
    fi
}

# Collect all versions
collect_versions() {
    TREE=$(get_pip_ver flagtree)
    GEMS=$(get_pip_ver flaggems)
    SCALE=$(get_pip_ver flagscale)
    CX=$(get_pip_ver flagcx)
    PYTHON=$(python -V 2>&1 | awk '{print $2}')
    TORCH=$(python -c "import torch;print(torch.__version__)" 2>/dev/null | head -1) || TORCH="none"
    TORCH=$(normalize_ver "$TORCH")

    # CUDA version
    if command -v nvcc &>/dev/null; then
        CUDA=$(nvcc -V 2>/dev/null | grep -oP 'release \K[0-9.]+' | head -1) || CUDA="none"
    else
        CUDA="none"
    fi

    # Driver version
    if command -v nvidia-smi &>/dev/null; then
        DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1) || DRIVER="none"
        GPU=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 | tr ' ' '_' | tr '[:upper:]' '[:lower:]') || GPU="unknown"
    else
        DRIVER="none"
        GPU="unknown"
    fi

    ARCH=$(uname -m)
}

# Output as JSON
output_json() {
    cat <<EOF
{
  "tree": "$TREE",
  "gems": "$GEMS",
  "scale": "$SCALE",
  "cx": "$CX",
  "python": "$PYTHON",
  "torch": "$TORCH",
  "cuda": "$CUDA",
  "driver": "$DRIVER",
  "gpu": "$GPU",
  "arch": "$ARCH"
}
EOF
}

# Output as table
output_table() {
    echo "===== FlagOS Environment Info ====="
    printf "%-10s %s\n" "Tree:" "$TREE"
    printf "%-10s %s\n" "Gems:" "$GEMS"
    printf "%-10s %s\n" "Scale:" "$SCALE"
    printf "%-10s %s\n" "CX:" "$CX"
    printf "%-10s %s\n" "Python:" "$PYTHON"
    printf "%-10s %s\n" "Torch:" "$TORCH"
    printf "%-10s %s\n" "CUDA:" "$CUDA"
    printf "%-10s %s\n" "Driver:" "$DRIVER"
    printf "%-10s %s\n" "GPU:" "$GPU"
    printf "%-10s %s\n" "Arch:" "$ARCH"
}

# Main
[[ "${1:-}" == "--help" || "${1:-}" == "-h" ]] && show_help

collect_versions

if [[ "${1:-}" == "--json" ]]; then
    output_json
else
    output_table
fi