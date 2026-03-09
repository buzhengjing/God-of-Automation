#!/usr/bin/env python3
"""
vLLM 性能基准测试工具

Usage:
    python perf.py                           # 使用默认配置
    python perf.py --config config.yaml      # 指定配置文件
    python perf.py --test-case 1k_input_1k_output  # 运行单个测试用例
    python perf.py --dry-run                 # 仅打印命令不执行
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# =============================================================================
# 配置加载
# =============================================================================

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "perf_config.yaml"


def load_yaml(path: Path) -> Dict[str, Any]:
    """加载 YAML 文件"""
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载配置文件 (perf_config.yaml 包含所有必要信息)
    """
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = load_yaml(cfg_path)

    # 确保 server 和 model 字段存在
    if "server" not in config:
        config["server"] = {"host": "", "port": 8000}
    if "model" not in config:
        config["model"] = {"name": "", "tokenizer_path": ""}

    return config


def validate_config(config: Dict[str, Any]) -> bool:
    """验证配置完整性"""
    errors = []

    if not config.get("server", {}).get("host"):
        errors.append("server.host 未配置 (检查 shared/context.yaml)")
    if not config.get("model", {}).get("tokenizer_path"):
        errors.append("model.tokenizer_path 未配置 (检查 shared/context.yaml)")
    if not config.get("test_matrix"):
        errors.append("test_matrix 为空")
    if not config.get("concurrency", {}).get("levels"):
        errors.append("concurrency.levels 未配置")

    for err in errors:
        print(f"ERROR: {err}")

    return len(errors) == 0


# =============================================================================
# 输出解析
# =============================================================================

METRIC_PATTERNS = {
    'Successful requests': r'Successful requests:\s+(\d+)',
    'Failed requests': r'Failed requests:\s+(\d+)',
    'Benchmark duration (s)': r'Benchmark duration \(s\):\s+([\d.]+)',
    'Total input tokens': r'Total input tokens:\s+(\d+)',
    'Total generated tokens': r'Total generated tokens:\s+(\d+)',
    'Request throughput (req/s)': r'Request throughput \(req/s\):\s+([\d.]+)',
    'Output token throughput (tok/s)': r'Output token throughput \(tok/s\):\s+([\d.]+)',
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


def parse_output(output: str) -> Dict[str, Any]:
    """从 vllm bench 输出中提取指标"""
    metrics = {}
    for key, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, output)
        if match:
            val = match.group(1)
            metrics[key] = float(val) if '.' in val else int(val)
        else:
            metrics[key] = None
    return metrics


# =============================================================================
# 基准测试执行
# =============================================================================

def build_command(config: Dict[str, Any], test_case: Dict[str, Any]) -> List[str]:
    """构建 vllm bench 命令"""
    server = config["server"]
    model = config["model"]
    bench = config.get("benchmark", {})

    cmd = [
        "vllm", "bench", "serve",
        "--host", server["host"],
        "--port", str(server["port"]),
        "--model", model["name"],
        "--tokenizer", model["tokenizer_path"],
        "--dataset-name", bench.get("dataset_name", "random"),
        "--random-input-len", str(test_case["input_len"]),
        "--random-output-len", str(test_case["output_len"]),
        "--endpoint", bench.get("endpoint", "/v1/completions"),
    ]

    if bench.get("ignore_eos", True):
        cmd.append("--ignore-eos")
    if bench.get("trust_remote_code", True):
        cmd.append("--trust-remote-code")

    return cmd


def run_benchmark(cmd: List[str], num_prompts: int, max_concurrency: Optional[int] = None,
                  dry_run: bool = False) -> Dict[str, Any]:
    """执行单次基准测试"""
    full_cmd = cmd + ["--num-prompts", str(num_prompts)]
    if max_concurrency:
        full_cmd += ["--max-concurrency", str(max_concurrency)]

    if dry_run:
        print(f"  [DRY RUN] {' '.join(full_cmd)}")
        return {"dry_run": True}

    conc_str = f"concurrency={max_concurrency}" if max_concurrency else "unlimited"
    print(f"  Running: num_prompts={num_prompts}, {conc_str}")

    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            print(f"    FAILED: {result.stderr[:200]}")
            return {"error": result.stderr}

        metrics = parse_output(result.stdout)
        throughput = metrics.get('Output token throughput (tok/s)', 'N/A')
        print(f"    OK - {throughput} tok/s")
        return metrics

    except subprocess.TimeoutExpired:
        print("    TIMEOUT")
        return {"error": "timeout"}
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"error": str(e)}


def run_test_case(config: Dict[str, Any], test_case: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """运行单个测试用例的所有并发级别"""
    base_cmd = build_command(config, test_case)
    results = {}

    levels = config["concurrency"]["levels"]
    final_prompts = config["concurrency"]["final_num_prompts"]

    # 逐级并发测试
    for conc in levels:
        results[f"concurrency_{conc}"] = run_benchmark(base_cmd, conc, conc, dry_run)

    # 最终无限制并发测试
    print(f"  Running: num_prompts={final_prompts}, unlimited")
    results["max"] = run_benchmark(base_cmd, final_prompts, None, dry_run)

    return results


# =============================================================================
# 结果保存
# =============================================================================

def save_results(results: Dict[str, Any], config: Dict[str, Any]) -> str:
    """保存测试结果到 JSON 文件"""
    output_cfg = config.get("output", {})
    output_dir = Path(output_cfg.get("dir", "./output"))
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = output_dir / f"benchmark_{timestamp}.json"

    data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "config": config if output_cfg.get("include_config_snapshot", True) else None,
        },
        "results": results,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(filepath)


# =============================================================================
# 主入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="vLLM 性能基准测试")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--test-case", help="运行指定测试用例")
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令")
    args = parser.parse_args()

    # 加载配置
    print("加载配置...")
    config = load_config(args.config)

    if not validate_config(config):
        sys.exit(1)

    # 筛选测试用例
    test_matrix = config["test_matrix"]
    if args.test_case:
        test_matrix = [tc for tc in test_matrix if tc["name"] == args.test_case]
        if not test_matrix:
            print(f"ERROR: 测试用例 '{args.test_case}' 不存在")
            sys.exit(1)
    else:
        test_matrix = [tc for tc in test_matrix if tc.get("enabled", True)]

    print(f"将运行 {len(test_matrix)} 个测试用例")

    # 执行测试
    all_results = {}
    for tc in test_matrix:
        print(f"\n{'='*50}")
        print(f"测试用例: {tc['name']} (input={tc['input_len']}, output={tc['output_len']})")
        print('='*50)
        all_results[tc["name"]] = run_test_case(config, tc, args.dry_run)

    # 保存结果
    if not args.dry_run:
        output_path = save_results(all_results, config)
        print(f"\n结果已保存: {output_path}")

    return all_results


if __name__ == "__main__":
    main()
