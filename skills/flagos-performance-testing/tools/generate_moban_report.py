#!/usr/bin/env python3
"""
生成 moban 格式的性能报告文件。

按 V3 → V2 → V1 顺序输出三版原始 benchmark JSON 数据和算子信息。
没有数据的版本自动跳过，不写入对应模块。

Usage:
    python generate_moban_report.py \
        --results-dir /flagos-workspace/results \
        --output /flagos-workspace/results/benchmark_report_moban.md \
        [--v3-debug-log /flagos-workspace/logs/startup_flagos_optimized.log] \
        [--v2-debug-log /flagos-workspace/logs/startup_flagos.log] \
        [--v2-reached-target]
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 测试用例名称映射：JSON key → 报告标题
TC_NAME_MAP = [
    (["prefill1_decode512", "1_input_512_output"], "1&512"),
    (["1k_input_1k_output"], "1k&1k"),
    (["4k_input_1k_output"], "4k&1k"),
    (["16k_input_1k_output"], "16k&1k"),
    (["32k_input_1k_output"], "32k&1k"),
]


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_results_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """兼容新旧 JSON 格式"""
    if "results" in data and isinstance(data["results"], dict):
        return data["results"]
    return data


def extract_debug_lines(log_path: Optional[str]) -> List[str]:
    """从启动日志中提取 [DEBUG] flag_gems 行"""
    if not log_path:
        return []
    p = Path(log_path)
    if not p.exists():
        return []
    lines = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            if "[DEBUG] flag_gems" in line:
                lines.append(line.rstrip())
    return lines


def format_tc_json(tc_data: Dict[str, Any]) -> str:
    """格式化单个测试用例的 JSON 数据"""
    return json.dumps(tc_data, indent=2, ensure_ascii=False)


def build_tc_order(benchmark_data: Dict[str, Any]) -> List[Tuple[str, str]]:
    """根据实际数据中存在的测试用例，构建有序列表"""
    results = get_results_data(benchmark_data)
    order = []
    for aliases, display in TC_NAME_MAP:
        for alias in aliases:
            if alias in results:
                order.append((alias, display))
                break
    return order


def generate_report(args) -> str:
    results_dir = Path(args.results_dir)
    out_lines: List[str] = []

    # 加载三版数据
    v1_data = load_json(results_dir / "native_performance.json")
    v2_data = load_json(results_dir / "flagos_full.json")
    v3_data = load_json(results_dir / "flagos_optimized.json")

    # 加载算子列表
    ops_list = load_json(results_dir / "ops_list.json")

    # V3 DEBUG 日志
    v3_debug = extract_debug_lines(args.v3_debug_log)
    # V2 DEBUG 日志
    v2_debug = extract_debug_lines(args.v2_debug_log)

    # === V3 部分 ===
    if v3_data is not None:
        v3_ops_count = len(v3_debug) if v3_debug else 0
        # 如果没有 debug 日志，尝试从 context 获取算子数
        if v3_ops_count == 0 and args.v3_ops_count:
            v3_ops_count = args.v3_ops_count

        out_lines.append(f"# V3-gems替换数{v3_ops_count}")
        out_lines.append("")
        out_lines.append(f"## 算子替换数-{v3_ops_count}")
        out_lines.append("")
        if v3_debug:
            out_lines.append("```python")
            for line in v3_debug:
                out_lines.append(line)
            out_lines.append("```")
            out_lines.append("")

        tc_order = build_tc_order(v3_data)
        for json_key, display_name in tc_order:
            results = get_results_data(v3_data)
            if json_key in results:
                out_lines.append(f"## {display_name}")
                out_lines.append("")
                out_lines.append("```python")
                out_lines.append("")
                out_lines.append("")
                out_lines.append(format_tc_json(results[json_key]))
                out_lines.append("```")
                out_lines.append("")

    # === V2 部分 ===
    if v2_data is not None:
        v2_ops_count = len(v2_debug) if v2_debug else 0
        if v2_ops_count == 0 and args.v2_ops_count:
            v2_ops_count = args.v2_ops_count

        if args.v2_reached_target:
            out_lines.append(f"V2-最大gems数版本，已达到80%）")
        else:
            out_lines.append(f"V2-最大gems数版本，未达到80，待升级）")

        out_lines.append(f"算子替换数-{v2_ops_count}")
        if v2_debug:
            for line in v2_debug:
                out_lines.append(line)

        # 算子列表
        if ops_list is not None:
            out_lines.append(json.dumps(ops_list, indent=4, ensure_ascii=False))

        tc_order = build_tc_order(v2_data)
        for json_key, display_name in tc_order:
            results = get_results_data(v2_data)
            if json_key in results:
                # V2 部分的第一个用例用 "1-512" 而非 "1&512"（与模版一致）
                out_lines.append(display_name)
                out_lines.append(format_tc_json(results[json_key]))
        out_lines.append("")

    # === V1 部分 ===
    if v1_data is not None:
        out_lines.append("V1-不带gems")

        tc_order = build_tc_order(v1_data)
        for json_key, display_name in tc_order:
            results = get_results_data(v1_data)
            if json_key in results:
                out_lines.append(display_name)
                out_lines.append(format_tc_json(results[json_key]))
        out_lines.append("")

    return "\n".join(out_lines)


def main():
    parser = argparse.ArgumentParser(description="生成 moban 格式性能报告")
    parser.add_argument("--results-dir", required=True, help="结果文件目录")
    parser.add_argument("--output", required=True, help="输出文件路径")
    parser.add_argument("--v3-debug-log", default=None, help="V3 启动日志路径（提取 DEBUG 行）")
    parser.add_argument("--v2-debug-log", default=None, help="V2 启动日志路径（提取 DEBUG 行）")
    parser.add_argument("--v3-ops-count", type=int, default=None, help="V3 算子数（无 debug 日志时使用）")
    parser.add_argument("--v2-ops-count", type=int, default=None, help="V2 算子数（无 debug 日志时使用）")
    parser.add_argument("--v2-reached-target", action="store_true", help="V2 是否已达标")
    args = parser.parse_args()

    report = generate_report(args)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"moban 格式报告已生成: {args.output}")


if __name__ == "__main__":
    main()
