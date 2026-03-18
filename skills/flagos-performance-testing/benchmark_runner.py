#!/usr/bin/env python3
"""
vLLM 性能基准测试工具 (重构版)

基于 perf.py 重构，新增:
- --concurrency-search: 自动搜索最优并发级别，增强早停（连续2级<3% 或 下降>5%）
- --pilot: 先导测试模式，快速评估（1k→1k, 4并发点, 50 prompts）
- --output-name: 指定输出文件名
- --output-dir: 指定输出目录
- --mode: 标记测试模式 (native/flagos_initial/flagos_optimized)
- per-test-case timeout: 从配置文件中读取 timeout 字段
- 最低样本量: 并发搜索阶段 max(concurrency, 100)

Usage:
    python benchmark_runner.py --config config.yaml
    python benchmark_runner.py --config config.yaml --concurrency-search
    python benchmark_runner.py --config config.yaml --pilot
    python benchmark_runner.py --output-name native_performance
    python benchmark_runner.py --test-case 1k_input_1k_output
    python benchmark_runner.py --dry-run
"""

import sys

# IO 缓冲修复：确保容器内实时输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
else:
    import functools
    print = functools.partial(print, flush=True)

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# =============================================================================
# 配置加载
# =============================================================================

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "perf_config.yaml"

# 先导测试默认参数
PILOT_CONCURRENCY_LEVELS = [1, 16, 64, 256]
PILOT_NUM_PROMPTS = 50
PILOT_TEST_CASE = "1k_input_1k_output"

# 默认超时（秒）
DEFAULT_TIMEOUT = 600


def load_yaml(path: Path) -> Dict[str, Any]:
    """加载 YAML 文件"""
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """加载配置文件"""
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    config = load_yaml(cfg_path)

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
                  dry_run: bool = False, timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """执行单次基准测试"""
    full_cmd = cmd + ["--num-prompts", str(num_prompts)]
    if max_concurrency:
        full_cmd += ["--max-concurrency", str(max_concurrency)]

    if dry_run:
        print(f"  [DRY RUN] {' '.join(full_cmd)}")
        return {"dry_run": True}

    conc_str = f"concurrency={max_concurrency}" if max_concurrency else "unlimited"
    print(f"  Running: num_prompts={num_prompts}, {conc_str}, timeout={timeout}s")

    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"    FAILED: {result.stderr[:200]}")
            return {"error": result.stderr}

        metrics = parse_output(result.stdout)
        throughput = metrics.get('Output token throughput (tok/s)', 'N/A')
        total_tp = metrics.get('Total Token throughput (tok/s)', 'N/A')
        failed = metrics.get('Failed requests', 0)
        print(f"    OK - output={throughput} tok/s, total={total_tp} tok/s, failed={failed}")
        return metrics

    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT (>{timeout}s)")
        return {"error": f"timeout after {timeout}s"}
    except Exception as e:
        print(f"    ERROR: {e}")
        return {"error": str(e)}


def get_test_case_timeout(test_case: Dict[str, Any]) -> int:
    """获取测试用例的超时时间，支持从配置中读取"""
    return test_case.get("timeout", DEFAULT_TIMEOUT)


def run_test_case(config: Dict[str, Any], test_case: Dict[str, Any],
                  dry_run: bool = False, concurrency_search: bool = False) -> Dict[str, Any]:
    """运行单个测试用例的所有并发级别"""
    base_cmd = build_command(config, test_case)
    results = {}
    timeout = get_test_case_timeout(test_case)

    levels = config["concurrency"]["levels"]
    final_prompts = config["concurrency"]["final_num_prompts"]

    if concurrency_search:
        # 自动搜索模式：增强早停
        return run_concurrency_search(base_cmd, levels, final_prompts, dry_run, timeout)

    # 标准模式：逐级并发测试，使用最低样本量
    for conc in levels:
        min_prompts = max(conc, 100)
        results[f"concurrency_{conc}"] = run_benchmark(base_cmd, min_prompts, conc, dry_run, timeout)

    # 最终无限制并发测试
    print(f"  Running: num_prompts={final_prompts}, unlimited")
    results["max"] = run_benchmark(base_cmd, final_prompts, None, dry_run, timeout)

    return results


def run_concurrency_search(base_cmd: List[str], levels: List[int],
                           final_prompts: int, dry_run: bool = False,
                           timeout: int = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    自动搜索最优并发级别。

    增强早停条件：
    1. 连续 2 级增长 < 3% → 早停
    2. 吞吐下降 > 5% → 早停
    3. 请求失败数 > 0 → 早停
    """
    GROWTH_THRESHOLD = 0.03      # 3% 增长阈值
    DECLINE_THRESHOLD = 0.05     # 5% 下降阈值
    CONSECUTIVE_LOW = 2          # 连续低增长次数

    results = {}
    prev_throughput = 0.0
    best_throughput = 0.0
    best_concurrency = levels[0]
    early_stopped = False
    consecutive_low_growth = 0

    print(f"  [CONCURRENCY SEARCH] levels={levels}")
    print(f"    early_stop: growth<{GROWTH_THRESHOLD*100}% x{CONSECUTIVE_LOW} | decline>{DECLINE_THRESHOLD*100}% | failures")

    for conc in levels:
        # 最低样本量：max(concurrency, 100)
        min_prompts = max(conc, 100)
        metrics = run_benchmark(base_cmd, min_prompts, conc, dry_run, timeout)
        results[f"concurrency_{conc}"] = metrics

        if dry_run or "error" in metrics:
            if "error" in metrics and not dry_run:
                print(f"  [EARLY STOP] Error at concurrency={conc}: {metrics['error'][:100]}")
                early_stopped = True
                break
            continue

        # 检查请求失败
        failed_requests = metrics.get('Failed requests', 0)
        if failed_requests and failed_requests > 0:
            print(f"  [EARLY STOP] {failed_requests} failed requests at concurrency={conc}")
            early_stopped = True
            break

        current_throughput = metrics.get('Output token throughput (tok/s)', 0) or 0

        if current_throughput > best_throughput:
            best_throughput = current_throughput
            best_concurrency = conc

        # 检查早停条件
        if prev_throughput > 0 and current_throughput > 0:
            growth = (current_throughput - prev_throughput) / prev_throughput

            # 条件 2：吞吐下降超过 5%
            if current_throughput < prev_throughput * (1 - DECLINE_THRESHOLD):
                print(f"    Growth: {growth*100:.1f}% — throughput declined >{DECLINE_THRESHOLD*100}%")
                print(f"  [EARLY STOP] Throughput decline at concurrency={conc}")
                early_stopped = True
                break

            # 条件 1：连续低增长
            if growth < GROWTH_THRESHOLD:
                consecutive_low_growth += 1
                print(f"    Growth: {growth*100:.1f}% — low growth {consecutive_low_growth}/{CONSECUTIVE_LOW}")
                if consecutive_low_growth >= CONSECUTIVE_LOW:
                    print(f"  [EARLY STOP] {CONSECUTIVE_LOW} consecutive low-growth levels at concurrency={conc}")
                    early_stopped = True
                    break
            else:
                consecutive_low_growth = 0
                print(f"    Growth: {growth*100:.1f}%")

        prev_throughput = current_throughput

    # 使用最优并发级别运行最终大规模测试
    if not dry_run and not early_stopped:
        print(f"  Running final test: num_prompts={final_prompts}, unlimited")
        results["max"] = run_benchmark(base_cmd, final_prompts, None, dry_run, timeout)

    # 记录搜索元信息
    results["_search_meta"] = {
        "early_stopped": early_stopped,
        "best_concurrency": best_concurrency,
        "best_throughput": best_throughput,
        "tested_levels": [l for l in levels if f"concurrency_{l}" in results],
    }

    return results


def run_pilot_test(config: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """
    先导测试：快速评估性能水平。

    使用 1k→1k 用例，4 个并发点 [1, 16, 64, 256]，每个 50 prompts。
    约 5 分钟出结果，用于决策是否需要跑完整测试。
    """
    print("\n" + "=" * 50)
    print("[PILOT TEST] 快速先导测试")
    print("=" * 50)

    # 找到 1k→1k 测试用例
    test_matrix = config.get("test_matrix", [])
    pilot_tc = None
    for tc in test_matrix:
        if tc["name"] == PILOT_TEST_CASE:
            pilot_tc = tc
            break

    if not pilot_tc:
        # 使用第一个用例作为 pilot
        if test_matrix:
            pilot_tc = test_matrix[0]
            print(f"  未找到 {PILOT_TEST_CASE}, 使用 {pilot_tc['name']}")
        else:
            print("ERROR: test_matrix 为空")
            return {"error": "no test cases"}

    base_cmd = build_command(config, pilot_tc)
    timeout = get_test_case_timeout(pilot_tc)

    results = {}
    best_throughput = 0.0
    best_concurrency = PILOT_CONCURRENCY_LEVELS[0]

    print(f"  用例: {pilot_tc['name']} (input={pilot_tc['input_len']}, output={pilot_tc['output_len']})")
    print(f"  并发: {PILOT_CONCURRENCY_LEVELS}")
    print(f"  样本量: {PILOT_NUM_PROMPTS}")

    for conc in PILOT_CONCURRENCY_LEVELS:
        metrics = run_benchmark(base_cmd, PILOT_NUM_PROMPTS, conc, dry_run, timeout)
        results[f"concurrency_{conc}"] = metrics

        if not dry_run and "error" not in metrics:
            throughput = metrics.get('Output token throughput (tok/s)', 0) or 0
            if throughput > best_throughput:
                best_throughput = throughput
                best_concurrency = conc

    results["_pilot_meta"] = {
        "test_case": pilot_tc["name"],
        "num_prompts": PILOT_NUM_PROMPTS,
        "levels": PILOT_CONCURRENCY_LEVELS,
        "best_throughput": best_throughput,
        "best_concurrency": best_concurrency,
    }

    print(f"\n  [PILOT RESULT] Best: {best_throughput:.2f} tok/s @ concurrency={best_concurrency}")

    return {pilot_tc["name"]: results}


# =============================================================================
# 结果保存
# =============================================================================

def save_results(results: Dict[str, Any], config: Dict[str, Any],
                 output_name: Optional[str] = None,
                 output_dir: Optional[str] = None,
                 mode: Optional[str] = None) -> str:
    """保存测试结果到 JSON 文件"""
    output_cfg = config.get("output", {})

    if output_dir:
        out_dir = Path(output_dir)
    else:
        out_dir = Path(output_cfg.get("dir", "./output"))
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_name:
        filepath = out_dir / f"{output_name}.json"
    else:
        filepath = out_dir / f"benchmark_{timestamp}.json"

    data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "mode": mode or "default",
            "config": config if output_cfg.get("include_config_snapshot", True) else None,
        },
        "results": results,
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return str(filepath)


# =============================================================================
# 摘要输出
# =============================================================================

def print_summary(results: Dict[str, Any], mode: str = "default"):
    """打印测试结果摘要"""
    print(f"\n{'='*60}")
    print(f"性能测试摘要 (mode: {mode})")
    print(f"{'='*60}")

    for tc_name, tc_results in results.items():
        print(f"\n{tc_name}:")

        if not isinstance(tc_results, dict):
            continue

        # 找到最优并发级别的结果
        best_throughput = 0
        best_key = ""

        for key, metrics in tc_results.items():
            if key.startswith("_"):
                continue
            if not isinstance(metrics, dict) or "error" in metrics:
                continue
            throughput = metrics.get('Output token throughput (tok/s)', 0) or 0
            if throughput > best_throughput:
                best_throughput = throughput
                best_key = key

        if best_key:
            metrics = tc_results[best_key]
            print(f"  Best: {best_key}")
            print(f"  Output throughput: {metrics.get('Output token throughput (tok/s)', 'N/A')} tok/s")
            print(f"  Total throughput:  {metrics.get('Total Token throughput (tok/s)', 'N/A')} tok/s")
            print(f"  Mean TTFT:         {metrics.get('Mean TTFT (ms)', 'N/A')} ms")
            print(f"  Mean TPOT:         {metrics.get('Mean TPOT (ms)', 'N/A')} ms")

        # 显示搜索元信息
        meta = tc_results.get("_search_meta")
        if meta:
            print(f"  Early stopped:     {meta.get('early_stopped', False)}")
            print(f"  Best concurrency:  {meta.get('best_concurrency', 'N/A')}")

        # 显示先导测试信息
        pilot_meta = tc_results.get("_pilot_meta")
        if pilot_meta:
            print(f"  [PILOT] prompts={pilot_meta['num_prompts']}, best={pilot_meta['best_concurrency']}")


# =============================================================================
# 主入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="vLLM 性能基准测试 (重构版)")
    parser.add_argument("--config", help="配置文件路径")
    parser.add_argument("--test-case", help="运行指定测试用例")
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令")
    parser.add_argument("--concurrency-search", action="store_true",
                        help="自动搜索最优并发级别（增强早停）")
    parser.add_argument("--pilot", action="store_true",
                        help="先导测试：1k→1k 用例，4个并发点，快速评估")
    parser.add_argument("--output-name", help="输出文件名（不含扩展名）")
    parser.add_argument("--output-dir", help="输出目录路径（默认 /flagos-workspace/results/）",
                        default=None)
    parser.add_argument("--mode", help="测试模式标记 (native/flagos_initial/flagos_optimized)",
                        default="default")
    args = parser.parse_args()

    # 加载配置
    print("加载配置...")
    config = load_config(args.config)

    if not validate_config(config):
        sys.exit(1)

    # 先导测试模式
    if args.pilot:
        all_results = run_pilot_test(config, args.dry_run)

        if not args.dry_run:
            print_summary(all_results, f"pilot_{args.mode}")
            output_name = args.output_name or f"pilot_{args.mode}"
            output_path = save_results(
                all_results, config,
                output_name=output_name,
                output_dir=args.output_dir,
                mode=f"pilot_{args.mode}"
            )
            print(f"\n结果已保存: {output_path}")

        return all_results

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
    if args.concurrency_search:
        print("[模式] 自动并发搜索 + 增强早停（连续2级<3% | 下降>5% | 失败）")

    # 执行测试
    all_results = {}
    for tc in test_matrix:
        print(f"\n{'='*50}")
        tc_timeout = get_test_case_timeout(tc)
        print(f"测试用例: {tc['name']} (input={tc['input_len']}, output={tc['output_len']}, timeout={tc_timeout}s)")
        print('='*50)
        all_results[tc["name"]] = run_test_case(config, tc, args.dry_run, args.concurrency_search)

    # 打印摘要
    if not args.dry_run:
        print_summary(all_results, args.mode)

    # 保存结果
    if not args.dry_run:
        output_path = save_results(
            all_results, config,
            output_name=args.output_name,
            output_dir=args.output_dir,
            mode=args.mode
        )
        print(f"\n结果已保存: {output_path}")

    return all_results


if __name__ == "__main__":
    main()
