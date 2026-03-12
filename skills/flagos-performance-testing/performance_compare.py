#!/usr/bin/env python3
"""
性能对比工具

对比多个 benchmark JSON 结果文件，生成 performance_compare.csv 和摘要报告。

Usage:
    python performance_compare.py --native results/native_performance.json \
                                   --flagos-initial results/flagos_initial.json
    python performance_compare.py --native results/native_performance.json \
                                   --flagos-initial results/flagos_initial.json \
                                   --flagos-optimized results/flagos_optimized.json
    python performance_compare.py --native results/native_performance.json \
                                   --flagos-before results/flagos_before_upgrade.json \
                                   --flagos-after results/flagos_after_upgrade.json
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def load_benchmark(path: str) -> Dict[str, Any]:
    """加载 benchmark JSON 文件"""
    p = Path(path)
    if not p.exists():
        print(f"ERROR: 文件不存在: {path}")
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_best_throughput(tc_results: Dict[str, Any]) -> Tuple[float, float, str]:
    """
    从测试用例结果中提取最优吞吐量。

    Returns:
        (output_throughput, total_throughput, best_concurrency_key)
    """
    best_output = 0.0
    best_total = 0.0
    best_key = ""

    for key, metrics in tc_results.items():
        if key.startswith("_"):
            continue
        if not isinstance(metrics, dict) or "error" in metrics:
            continue

        output_tp = metrics.get('Output token throughput (tok/s)', 0) or 0
        if output_tp > best_output:
            best_output = output_tp
            best_total = metrics.get('Total Token throughput (tok/s)', 0) or 0
            best_key = key

    return best_output, best_total, best_key


def compare_results(benchmarks: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    对比多个 benchmark 结果。

    Args:
        benchmarks: {"native": data, "flagos_initial": data, ...}

    Returns:
        对比行列表，每行包含 test_case 和各 benchmark 的指标。
    """
    # 收集所有测试用例名称
    all_test_cases = set()
    for name, data in benchmarks.items():
        results = data.get("results", {})
        all_test_cases.update(results.keys())

    rows = []
    for tc in sorted(all_test_cases):
        row = {"test_case": tc}

        native_output_tp = 0.0

        for bm_name, data in benchmarks.items():
            results = data.get("results", {})
            tc_results = results.get(tc, {})

            if tc_results:
                output_tp, total_tp, best_key = extract_best_throughput(tc_results)
                row[f"{bm_name}_output_throughput"] = output_tp
                row[f"{bm_name}_total_throughput"] = total_tp
                row[f"{bm_name}_best_concurrency"] = best_key

                if bm_name == "native":
                    native_output_tp = output_tp
            else:
                row[f"{bm_name}_output_throughput"] = 0
                row[f"{bm_name}_total_throughput"] = 0
                row[f"{bm_name}_best_concurrency"] = ""

        # 计算各 flagos 版本相对于 native 的比率
        if native_output_tp > 0:
            for bm_name in benchmarks:
                if bm_name == "native":
                    continue
                flagos_tp = row.get(f"{bm_name}_output_throughput", 0)
                ratio = flagos_tp / native_output_tp if native_output_tp > 0 else 0
                row[f"{bm_name}_ratio"] = ratio

        rows.append(row)

    return rows


def save_csv(rows: List[Dict[str, Any]], output_path: str, benchmark_names: List[str]):
    """保存对比结果到 CSV"""
    if not rows:
        print("WARNING: 无数据可保存")
        return

    # 构建列头
    headers = ["test_case"]
    for name in benchmark_names:
        headers.append(f"{name}_output_throughput")
        headers.append(f"{name}_total_throughput")
        headers.append(f"{name}_best_concurrency")
        if name != "native":
            headers.append(f"{name}_ratio")

    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            # 格式化比率为百分比
            formatted_row = {}
            for k, v in row.items():
                if k.endswith("_ratio") and isinstance(v, float):
                    formatted_row[k] = f"{v*100:.1f}%"
                elif isinstance(v, float):
                    formatted_row[k] = f"{v:.2f}"
                else:
                    formatted_row[k] = v
            writer.writerow(formatted_row)

    print(f"CSV 已保存: {output_path}")


def print_comparison(rows: List[Dict[str, Any]], benchmark_names: List[str]):
    """打印对比结果摘要"""
    print(f"\n{'='*80}")
    print("性能对比摘要")
    print(f"{'='*80}")

    # 表头
    header = f"{'Test Case':<25}"
    for name in benchmark_names:
        header += f" {name:>15}"
    for name in benchmark_names:
        if name != "native":
            header += f" {name+'_ratio':>15}"
    print(header)
    print("-" * len(header))

    # 数据行
    for row in rows:
        line = f"{row['test_case']:<25}"
        for name in benchmark_names:
            tp = row.get(f"{name}_output_throughput", 0)
            line += f" {tp:>15.2f}"
        for name in benchmark_names:
            if name != "native":
                ratio = row.get(f"{name}_ratio", 0)
                line += f" {ratio*100:>14.1f}%"
        print(line)

    # 总体判断
    print(f"\n{'='*80}")
    for name in benchmark_names:
        if name == "native":
            continue
        ratios = [row.get(f"{name}_ratio", 0) for row in rows if row.get(f"{name}_ratio")]
        if ratios:
            avg_ratio = sum(ratios) / len(ratios)
            min_ratio = min(ratios)
            status = "PASS" if min_ratio >= 0.8 else "FAIL"
            print(f"{name}: avg_ratio={avg_ratio*100:.1f}%, min_ratio={min_ratio*100:.1f}% [{status}]")


def check_target(rows: List[Dict[str, Any]], benchmark_names: List[str],
                 target_ratio: float = 0.8) -> Dict[str, bool]:
    """检查各 flagos 版本是否达标"""
    result = {}
    for name in benchmark_names:
        if name == "native":
            continue
        ratios = [row.get(f"{name}_ratio", 0) for row in rows if row.get(f"{name}_ratio")]
        if ratios:
            min_ratio = min(ratios)
            result[name] = min_ratio >= target_ratio
        else:
            result[name] = False
    return result


def main():
    parser = argparse.ArgumentParser(description="性能对比工具")
    parser.add_argument("--native", required=True, help="原生性能结果 JSON 路径")
    parser.add_argument("--flagos-initial", help="FlagOS 初始性能结果 JSON 路径")
    parser.add_argument("--flagos-optimized", help="FlagOS 优化后性能结果 JSON 路径")
    parser.add_argument("--flagos-before", help="FlagOS 升级前性能结果 JSON 路径 (Scenario B)")
    parser.add_argument("--flagos-after", help="FlagOS 升级后性能结果 JSON 路径 (Scenario B)")
    parser.add_argument("--output", default="./performance_compare.csv", help="CSV 输出路径")
    parser.add_argument("--target-ratio", type=float, default=0.8, help="性能目标比率 (默认 0.8)")
    args = parser.parse_args()

    # 加载 benchmark 数据
    benchmarks = {}
    benchmark_names = []

    benchmarks["native"] = load_benchmark(args.native)
    benchmark_names.append("native")

    if args.flagos_initial:
        benchmarks["flagos_initial"] = load_benchmark(args.flagos_initial)
        benchmark_names.append("flagos_initial")

    if args.flagos_optimized:
        benchmarks["flagos_optimized"] = load_benchmark(args.flagos_optimized)
        benchmark_names.append("flagos_optimized")

    if args.flagos_before:
        benchmarks["flagos_before_upgrade"] = load_benchmark(args.flagos_before)
        benchmark_names.append("flagos_before_upgrade")

    if args.flagos_after:
        benchmarks["flagos_after_upgrade"] = load_benchmark(args.flagos_after)
        benchmark_names.append("flagos_after_upgrade")

    if len(benchmarks) < 2:
        print("ERROR: 至少需要 native + 一个 flagos 结果文件")
        sys.exit(1)

    # 对比
    rows = compare_results(benchmarks)

    # 打印摘要
    print_comparison(rows, benchmark_names)

    # 保存 CSV
    save_csv(rows, args.output, benchmark_names)

    # 检查是否达标
    target_check = check_target(rows, benchmark_names, args.target_ratio)
    print(f"\n目标检查 (target >= {args.target_ratio*100:.0f}% native):")
    for name, passed in target_check.items():
        status = "PASS" if passed else "NEED OPTIMIZATION"
        print(f"  {name}: {status}")

    # 返回码：任一未达标返回 1
    if any(not passed for passed in target_check.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
