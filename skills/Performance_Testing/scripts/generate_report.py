#!/usr/bin/env python3
"""
Generate Markdown Report from Benchmark Results
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def load_results(filepath: str) -> dict:
    """Load benchmark results from JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_markdown_report(results: dict) -> str:
    """Generate markdown report from results."""
    lines = []

    # Header
    metadata = results.get("metadata", {})
    timestamp = metadata.get("timestamp", "N/A")

    lines.append("# Performance Benchmark Report")
    lines.append("")
    lines.append(f"**Generated:** {timestamp}")
    lines.append("")

    # Configuration summary
    config = metadata.get("config", {})
    if config:
        lines.append("## Configuration")
        lines.append("")
        lines.append(f"- **Server:** {config.get('server', {}).get('host')}:{config.get('server', {}).get('port')}")
        lines.append(f"- **Model:** {config.get('model', {}).get('name')}")
        lines.append(f"- **Tokenizer:** {config.get('model', {}).get('tokenizer_path')}")
        lines.append("")

    # Results by test case
    test_results = results.get("results", {})

    lines.append("## Results Summary")
    lines.append("")

    # Summary table
    lines.append("| Test Case | Max Throughput (tok/s) | Mean TTFT (ms) | Mean TPOT (ms) | P99 TTFT (ms) |")
    lines.append("|-----------|------------------------|----------------|----------------|---------------|")

    for test_case, concurrency_results in test_results.items():
        max_result = concurrency_results.get("max", {})
        if isinstance(max_result, dict) and "error" not in max_result:
            throughput = max_result.get("Output token throughput (tok/s)", "N/A")
            mean_ttft = max_result.get("Mean TTFT (ms)", "N/A")
            mean_tpot = max_result.get("Mean TPOT (ms)", "N/A")
            p99_ttft = max_result.get("P99 TTFT (ms)", "N/A")
            lines.append(f"| {test_case} | {throughput} | {mean_ttft} | {mean_tpot} | {p99_ttft} |")
        else:
            lines.append(f"| {test_case} | ERROR | - | - | - |")

    lines.append("")

    # Detailed results per test case
    lines.append("## Detailed Results")
    lines.append("")

    for test_case, concurrency_results in test_results.items():
        lines.append(f"### {test_case}")
        lines.append("")

        lines.append("| Concurrency | Throughput (tok/s) | TTFT (ms) | TPOT (ms) |")
        lines.append("|-------------|--------------------|-----------| ----------|")

        for conc_key, metrics in sorted(concurrency_results.items(), key=lambda x: (x[0] != 'max', x[0])):
            if isinstance(metrics, dict) and "error" not in metrics:
                throughput = metrics.get("Output token throughput (tok/s)", "N/A")
                ttft = metrics.get("Mean TTFT (ms)", "N/A")
                tpot = metrics.get("Mean TPOT (ms)", "N/A")
                lines.append(f"| {conc_key} | {throughput} | {ttft} | {tpot} |")

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark report")
    parser.add_argument("input", help="Input JSON results file")
    parser.add_argument("-o", "--output", help="Output markdown file")
    args = parser.parse_args()

    results = load_results(args.input)
    report = generate_markdown_report(results)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"Report saved to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
