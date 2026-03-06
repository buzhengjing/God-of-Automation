#!/usr/bin/env python3
"""
Benchmark Output Parser - Extracts metrics from vLLM benchmark output
"""

import re
from typing import Dict, Any, Optional


# Metric patterns for parsing benchmark output
METRIC_PATTERNS = {
    'Successful requests': r'Successful requests:\s+(\d+)',
    'Failed requests': r'Failed requests:\s+(\d+)',
    'Benchmark duration (s)': r'Benchmark duration \(s\):\s+([\d.]+)',
    'Total input tokens': r'Total input tokens:\s+(\d+)',
    'Total generated tokens': r'Total generated tokens:\s+(\d+)',
    'Request throughput (req/s)': r'Request throughput \(req/s\):\s+([\d.]+)',
    'Output token throughput (tok/s)': r'Output token throughput \(tok/s\):\s+([\d.]+)',
    'Peak output token throughput (tok/s)': r'Peak output token throughput \(tok/s\):\s+([\d.]+)',
    'Peak concurrent requests': r'Peak concurrent requests:\s+([\d.]+)',
    'Total Token throughput (tok/s)': r'Total Token throughput \(tok/s\):\s+([\d.]+)',
    'Mean TTFT (ms)': r'Mean TTFT \(ms\):\s+([\d.]+)',
    'Median TTFT (ms)': r'Median TTFT \(ms\):\s+([\d.]+)',
    'P99 TTFT (ms)': r'P99 TTFT \(ms\):\s+([\d.]+)',
    'Mean TPOT (ms)': r'Mean TPOT \(ms\):\s+([\d.]+)',
    'Median TPOT (ms)': r'Median TPOT \(ms\):\s+([\d.]+)',
    'P99 TPOT (ms)': r'P99 TPOT \(ms\):\s+([\d.]+)',
    'Mean ITL (ms)': r'Mean ITL \(ms\):\s+([\d.]+)',
    'Median ITL (ms)': r'Median ITL \(ms\):\s+([\d.]+)',
    'P99 ITL (ms)': r'P99 ITL \(ms\):\s+([\d.]+)',
}


def parse_benchmark_output(output: str) -> Dict[str, Any]:
    """
    Extract key metrics from benchmark output.

    Args:
        output: Raw stdout from vllm bench command

    Returns:
        Dictionary of metric names to values (int or float)
    """
    metrics = {}

    for key, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, output)
        if match:
            value_str = match.group(1)
            # Auto-detect int vs float
            if '.' in value_str:
                metrics[key] = float(value_str)
            else:
                metrics[key] = int(value_str)
        else:
            metrics[key] = None

    return metrics


def extract_error_message(stderr: str) -> Optional[str]:
    """Extract meaningful error message from stderr."""
    if not stderr:
        return None

    # Look for common error patterns
    error_patterns = [
        r'Error:\s*(.+)',
        r'Exception:\s*(.+)',
        r'Failed:\s*(.+)',
    ]

    for pattern in error_patterns:
        match = re.search(pattern, stderr, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Return first non-empty line if no pattern matched
    for line in stderr.split('\n'):
        line = line.strip()
        if line:
            return line[:200]  # Truncate long errors

    return None
