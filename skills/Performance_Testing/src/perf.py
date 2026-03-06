#!/usr/bin/env python3
"""
Performance Testing Main Entry Point

Usage:
    python -m src.perf --config config/perf_config.yaml
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config_loader import load_config, validate_config
from src.runner import BenchmarkRunner
from src.reporter import save_results


def parse_args():
    parser = argparse.ArgumentParser(description="vLLM Performance Benchmark Tool")
    parser.add_argument(
        "--config",
        type=str,
        default="config/perf_config.yaml",
        help="Path to configuration file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing"
    )
    parser.add_argument(
        "--test-case",
        type=str,
        help="Run specific test case only (e.g., 1k_input_1k_output)"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Load and validate configuration
    print(f"Loading configuration from: {args.config}")
    config = load_config(args.config)

    if not validate_config(config):
        print("Configuration validation failed!")
        sys.exit(1)

    print("Configuration validated successfully.")

    # Filter test cases if specific one requested
    if args.test_case:
        config["test_matrix"] = [
            tc for tc in config["test_matrix"]
            if tc["name"] == args.test_case
        ]
        if not config["test_matrix"]:
            print(f"Test case '{args.test_case}' not found!")
            sys.exit(1)

    # Filter only enabled test cases
    enabled_tests = [tc for tc in config["test_matrix"] if tc.get("enabled", True)]

    if not enabled_tests:
        print("No enabled test cases found!")
        sys.exit(1)

    print(f"\nRunning {len(enabled_tests)} test case(s):")
    for tc in enabled_tests:
        print(f"  - {tc['name']}: input={tc['input_len']}, output={tc['output_len']}")
    print()

    # Initialize runner
    runner = BenchmarkRunner(config, dry_run=args.dry_run)

    # Run all test cases
    all_results = {}

    for test_case in enabled_tests:
        print(f"\n{'='*60}")
        print(f"Running test case: {test_case['name']}")
        print(f"{'='*60}")

        results = runner.run_test_case(test_case)
        all_results[test_case["name"]] = results

    # Save results
    if not args.dry_run:
        output_path = save_results(all_results, config)
        print(f"\n{'='*60}")
        print(f"All tests completed!")
        print(f"Results saved to: {output_path}")
        print(f"{'='*60}")
    else:
        print("\n[DRY RUN] No results saved.")

    return all_results


if __name__ == "__main__":
    main()
