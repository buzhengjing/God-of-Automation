#!/usr/bin/env python3
"""
Benchmark Runner - Executes vLLM benchmark commands
"""

import subprocess
from typing import Dict, Any, List, Optional

from src.parser import parse_benchmark_output


class BenchmarkRunner:
    """Executes benchmark tests based on configuration."""

    def __init__(self, config: Dict[str, Any], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run

    def build_base_cmd(self, test_case: Dict[str, Any]) -> List[str]:
        """Build base command from configuration and test case."""
        server = self.config["server"]
        model = self.config["model"]
        benchmark = self.config["benchmark"]

        cmd = [
            "vllm", "bench", "serve",
            "--host", server["host"],
            "--port", str(server["port"]),
            "--model", model["name"],
            "--tokenizer", model["tokenizer_path"],
            "--dataset-name", benchmark["dataset_name"],
            "--random-input-len", str(test_case["input_len"]),
            "--random-output-len", str(test_case["output_len"]),
            "--endpoint", benchmark["endpoint"],
        ]

        if benchmark.get("ignore_eos", True):
            cmd.append("--ignore-eos")

        if benchmark.get("trust_remote_code", True):
            cmd.append("--trust-remote-code")

        return cmd

    def run_single_benchmark(
        self,
        base_cmd: List[str],
        num_prompts: int,
        max_concurrency: Optional[int] = None
    ) -> Dict[str, Any]:
        """Run a single benchmark with specified parameters."""
        cmd = base_cmd + ["--num-prompts", str(num_prompts)]

        if max_concurrency is not None:
            cmd += ["--max-concurrency", str(max_concurrency)]

        if self.dry_run:
            print(f"  [DRY RUN] Would execute: {' '.join(cmd)}")
            return {"dry_run": True, "command": " ".join(cmd)}

        concurrency_str = f"concurrency={max_concurrency}" if max_concurrency else "unlimited"
        print(f"  Running: num_prompts={num_prompts}, {concurrency_str}")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                print(f"    WARNING: Command failed with return code {result.returncode}")
                return {"error": result.stderr, "returncode": result.returncode}

            metrics = parse_benchmark_output(result.stdout)
            print(f"    OK - throughput: {metrics.get('Output token throughput (tok/s)', 'N/A')} tok/s")
            return metrics

        except subprocess.TimeoutExpired:
            print(f"    ERROR: Command timed out after 600 seconds")
            return {"error": "timeout"}
        except Exception as e:
            print(f"    ERROR: {str(e)}")
            return {"error": str(e)}

    def run_test_case(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """Run all concurrency levels for a test case."""
        base_cmd = self.build_base_cmd(test_case)
        results = {}

        concurrency_levels = self.config["concurrency"]["levels"]
        final_num_prompts = self.config["concurrency"]["final_num_prompts"]

        # Run each concurrency level
        for concurrency in concurrency_levels:
            key = f"concurrency_{concurrency}"
            results[key] = self.run_single_benchmark(
                base_cmd,
                num_prompts=concurrency,
                max_concurrency=concurrency
            )

        # Final test without concurrency limit
        print(f"  Running final test: num_prompts={final_num_prompts}, unlimited concurrency")
        results["max"] = self.run_single_benchmark(
            base_cmd,
            num_prompts=final_num_prompts,
            max_concurrency=None
        )

        return results
