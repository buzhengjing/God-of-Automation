#!/usr/bin/env python3
"""
Result Reporter - Saves and formats benchmark results
"""

import json
import csv
import os
from datetime import datetime
from typing import Dict, Any
from pathlib import Path


def save_results(results: Dict[str, Any], config: Dict[str, Any]) -> str:
    """
    Save benchmark results to file.

    Args:
        results: Dictionary of test case results
        config: Configuration used for the benchmark

    Returns:
        Path to saved results file
    """
    output_config = config["output"]
    output_dir = Path(output_config["dir"])
    output_format = output_config.get("format", "json")
    include_timestamp = output_config.get("include_timestamp", True)
    include_config = output_config.get("include_config_snapshot", True)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    if include_timestamp:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"benchmark_{timestamp}"
    else:
        base_filename = "benchmark_results"

    # Prepare output data
    output_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
        },
        "results": results,
    }

    if include_config:
        output_data["metadata"]["config"] = config

    # Save based on format
    saved_paths = []

    if output_format in ["json", "both"]:
        json_path = output_dir / f"{base_filename}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        saved_paths.append(str(json_path))
        print(f"  Saved JSON: {json_path}")

    if output_format in ["csv", "both"]:
        csv_path = output_dir / f"{base_filename}.csv"
        save_results_csv(results, csv_path)
        saved_paths.append(str(csv_path))
        print(f"  Saved CSV: {csv_path}")

    return saved_paths[0] if saved_paths else ""


def save_results_csv(results: Dict[str, Any], filepath: Path) -> None:
    """Save results in CSV format for easy analysis."""
    rows = []

    for test_case, concurrency_results in results.items():
        for concurrency_key, metrics in concurrency_results.items():
            if isinstance(metrics, dict) and "error" not in metrics:
                row = {
                    "test_case": test_case,
                    "concurrency": concurrency_key,
                }
                row.update(metrics)
                rows.append(row)

    if not rows:
        return

    # Get all unique columns
    columns = ["test_case", "concurrency"]
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def generate_summary(results: Dict[str, Any]) -> str:
    """Generate human-readable summary of results."""
    lines = ["=" * 60, "BENCHMARK SUMMARY", "=" * 60, ""]

    for test_case, concurrency_results in results.items():
        lines.append(f"Test Case: {test_case}")
        lines.append("-" * 40)

        max_result = concurrency_results.get("max", {})
        if max_result and "error" not in max_result:
            throughput = max_result.get("Output token throughput (tok/s)", "N/A")
            ttft = max_result.get("Mean TTFT (ms)", "N/A")
            tpot = max_result.get("Mean TPOT (ms)", "N/A")

            lines.append(f"  Max Throughput: {throughput} tok/s")
            lines.append(f"  Mean TTFT: {ttft} ms")
            lines.append(f"  Mean TPOT: {tpot} ms")
        else:
            lines.append("  ERROR: Test failed")

        lines.append("")

    return "\n".join(lines)
