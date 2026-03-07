#!/bin/bash
# FlagOS Performance Benchmark Runner
# Usage: bash run_benchmark.sh [--config CONFIG] [--tag TAG]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

CONFIG="${PROJECT_DIR}/config/perf_config.yaml"
TAG=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --config) CONFIG="$2"; shift 2 ;;
        --tag) TAG="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--config CONFIG] [--tag TAG]"
            echo "  --config  Path to config file (default: config/perf_config.yaml)"
            echo "  --tag     Version tag for results"
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

cd "$PROJECT_DIR"

echo "=========================================="
echo "FlagOS Performance Benchmark"
echo "=========================================="
echo "Config: ${CONFIG}"
echo "Tag: ${TAG:-'default'}"
echo ""

# Create output directory
mkdir -p output

# Run benchmark
if [ -n "$TAG" ]; then
    python -m src.perf --config "$CONFIG" --tag "$TAG"
else
    python -m src.perf --config "$CONFIG"
fi

echo ""
echo "Benchmark complete. Results saved to output/"
ls -la output/*.json 2>/dev/null | tail -5
