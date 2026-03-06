#!/bin/bash
# Performance Benchmark Runner Script
# Usage: bash scripts/run_benchmark.sh [config_file]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${1:-$PROJECT_DIR/config/perf_config.yaml}"

echo "========================================"
echo "Performance Benchmark Runner"
echo "========================================"
echo "Project Dir: $PROJECT_DIR"
echo "Config File: $CONFIG_FILE"
echo ""

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: Configuration file not found: $CONFIG_FILE"
    exit 1
fi

# Check if vllm is available
if ! command -v vllm &> /dev/null; then
    echo "ERROR: vllm command not found. Please install vllm first."
    exit 1
fi

# Check Python dependencies
echo "Checking dependencies..."
python3 -c "import yaml" 2>/dev/null || {
    echo "Installing PyYAML..."
    pip install pyyaml
}

# Run benchmark
echo ""
echo "Starting benchmark..."
echo "========================================"
cd "$PROJECT_DIR"
python3 -m src.perf --config "$CONFIG_FILE"

echo ""
echo "========================================"
echo "Benchmark completed!"
echo "========================================"
