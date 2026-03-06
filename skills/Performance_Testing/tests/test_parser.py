#!/usr/bin/env python3
"""
Tests for benchmark output parser
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser import parse_benchmark_output


SAMPLE_OUTPUT = """
============ Serving Benchmark Result ============
Successful requests:                     100
Failed requests:                         0
Benchmark duration (s):                  45.23
Total input tokens:                      102400
Total generated tokens:                  51200
Request throughput (req/s):              2.21
Output token throughput (tok/s):         1132.45
Peak output token throughput (tok/s):    1567.89
Peak concurrent requests:                32.5
Total Token throughput (tok/s):          3397.35
---------------Time to First Token----------------
Mean TTFT (ms):                          125.67
Median TTFT (ms):                        112.34
P99 TTFT (ms):                           345.67
---------------Time per Output Token--------------
Mean TPOT (ms):                          8.45
Median TPOT (ms):                        7.89
P99 TPOT (ms):                           15.23
---------------Inter-token Latency----------------
Mean ITL (ms):                           8.12
Median ITL (ms):                         7.56
P99 ITL (ms):                            14.89
==================================================
"""


def test_parse_benchmark_output():
    """Test parsing of benchmark output."""
    metrics = parse_benchmark_output(SAMPLE_OUTPUT)

    assert metrics['Successful requests'] == 100
    assert metrics['Failed requests'] == 0
    assert metrics['Benchmark duration (s)'] == 45.23
    assert metrics['Total input tokens'] == 102400
    assert metrics['Total generated tokens'] == 51200
    assert metrics['Request throughput (req/s)'] == 2.21
    assert metrics['Output token throughput (tok/s)'] == 1132.45
    assert metrics['Mean TTFT (ms)'] == 125.67
    assert metrics['Mean TPOT (ms)'] == 8.45
    assert metrics['P99 TTFT (ms)'] == 345.67

    print("All parser tests passed!")


def test_parse_empty_output():
    """Test parsing of empty output."""
    metrics = parse_benchmark_output("")

    for value in metrics.values():
        assert value is None

    print("Empty output test passed!")


if __name__ == "__main__":
    test_parse_benchmark_output()
    test_parse_empty_output()
    print("\nAll tests passed!")
