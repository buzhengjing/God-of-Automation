#!/usr/bin/env python3
"""
评测报告生成器
汇总所有 benchmark 结果，生成 JSON 报告和 Markdown 可读报告。
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

from utils import build_result, save_json, ensure_dir


def generate_report(
    model_name: str,
    model_type: str,
    details: List[Dict],
    output_dir: str = ".",
    report_json: str = "eval_report.json",
    report_md: str = "eval_report.md",
    total_duration_seconds: Optional[float] = None,
    registry: Optional[Dict] = None,
) -> Dict:
    """
    汇总评测结果并生成报告。

    Args:
        model_name: 模型名称
        model_type: 模型类型 (LLM/VL/Omni/Robotics/ImageGen)
        details: 所有 benchmark 的 detail 列表
        output_dir: 输出目录
        report_json: JSON 报告文件名
        report_md: Markdown 报告文件名
        total_duration_seconds: 整体评测耗时（秒）

    Returns:
        汇总结果 dict
    """
    ensure_dir(output_dir)

    # 分类 detail
    success_details = [d for d in details if d.get('status') == 'S']
    failed_details = [d for d in details if d.get('status') != 'S']

    # 构建 JSON 报告
    all_success = len(failed_details) == 0 and len(success_details) > 0
    result = build_result(
        model_name=model_name,
        details=details,
        err_code=0 if all_success else (1 if len(success_details) == 0 else 2),
        err_msg="Get Evaluations Details Success!" if all_success
                else f"Partial: {len(success_details)} ok, {len(failed_details)} failed",
    )

    if total_duration_seconds is not None:
        result['total_duration_seconds'] = total_duration_seconds

    # 保存 JSON
    json_path = os.path.join(output_dir, report_json)
    save_json(result, json_path)

    # 构建 benchmark name -> reference_scores 映射
    ref_scores = _build_reference_scores(registry, model_name) if registry else {}

    # 生成 Markdown
    md_content = _generate_markdown(model_name, model_type, details, success_details, failed_details, total_duration_seconds, ref_scores)
    md_path = os.path.join(output_dir, report_md)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return result


def _build_reference_scores(registry: Dict, model_name: str) -> Dict[str, Optional[float]]:
    """
    从 benchmark 注册表中提取每个 benchmark display_name 对应的参考分数。
    尝试精确匹配模型名，否则返回 None。

    Returns:
        {display_name: reference_score_or_None}
    """
    ref_map = {}
    # 提取模型短名（如 "/nfs/models/Qwen3-8B/" -> "Qwen3-8B"）
    model_short = model_name.strip('/').split('/')[-1] if model_name else ''

    for type_key, type_cfg in registry.items():
        if not isinstance(type_cfg, dict):
            continue
        for section in ('required', 'optional'):
            for bench in type_cfg.get(section, []):
                display = bench.get('display_name', bench.get('name', ''))
                ref_scores = bench.get('reference_scores', {})
                if not ref_scores:
                    ref_map[display] = None
                    continue
                # 尝试精确匹配
                if model_short in ref_scores:
                    ref_map[display] = ref_scores[model_short]
                else:
                    # 尝试部分匹配（如 model_short="Qwen3-8B" 匹配 key 含 "Qwen3-8B"）
                    matched = None
                    for key, val in ref_scores.items():
                        if key in model_short or model_short in key:
                            matched = val
                            break
                    ref_map[display] = matched
    return ref_map


def _generate_markdown(
    model_name: str,
    model_type: str,
    all_details: List[Dict],
    success_details: List[Dict],
    failed_details: List[Dict],
    total_duration_seconds: Optional[float] = None,
    reference_scores: Optional[Dict[str, Optional[float]]] = None,
) -> str:
    """生成 Markdown 格式的评测报告。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lines = [
        f"# 评测报告: {model_name}",
        "",
        f"> 模型类型: {model_type}",
        f"> 生成时间: {now}",
        f"> Benchmark 总数: {len(all_details)}",
        f"> 成功: {len(success_details)} | 失败: {len(failed_details)}",
    ]

    if total_duration_seconds is not None:
        minutes = int(total_duration_seconds // 60)
        seconds = round(total_duration_seconds % 60, 1)
        lines.append(f"> 总耗时: {minutes}m {seconds}s")

    has_ref = reference_scores and any(v is not None for v in reference_scores.values())

    lines.extend([
        "",
        "---",
        "",
        "## 评测结果总览",
        "",
    ])

    if has_ref:
        lines.append("| Benchmark | 状态 | 得分 | 参考分数 | 差异 | 耗时 |")
        lines.append("|-----------|------|------|----------|------|------|")
    else:
        lines.append("| Benchmark | 状态 | 得分 | 耗时 |")
        lines.append("|-----------|------|------|------|")

    for d in all_details:
        status = "Pass" if d.get('status') == 'S' else "Fail"
        accuracy = d.get('accuracy', 'N/A')
        if isinstance(accuracy, (int, float)):
            accuracy_val = accuracy
            accuracy = f"{accuracy:.2f}"
        else:
            accuracy_val = None
        duration = d.get('duration_seconds')
        duration_str = f"{duration}s" if duration is not None else "-"
        dataset_name = d.get('dataset', 'Unknown')

        if has_ref:
            ref = reference_scores.get(dataset_name) if reference_scores else None
            ref_str = f"{ref:.1f}" if ref is not None else "-"
            if ref is not None and accuracy_val is not None:
                diff = accuracy_val - ref
                diff_str = f"**{diff:+.1f}**" if abs(diff) > 5 else f"{diff:+.1f}"
            else:
                diff_str = "-"
            lines.append(f"| {dataset_name} | {status} | {accuracy} | {ref_str} | {diff_str} | {duration_str} |")
        else:
            lines.append(f"| {dataset_name} | {status} | {accuracy} | {duration_str} |")

    lines.extend(["", "---", ""])

    # 成功的详细信息
    if success_details:
        lines.extend([
            "## 详细结果",
            "",
        ])
        for d in success_details:
            lines.append(f"### {d.get('dataset', 'Unknown')}")
            lines.append("")
            lines.append(f"- **得分**: {d.get('accuracy', 'N/A')}")
            raw = d.get('rawDetails', {})
            if raw and not isinstance(raw, str):
                # 只显示非 error 的关键信息
                filtered = {k: v for k, v in raw.items()
                           if k not in ('error', 'parse_error') and not isinstance(v, dict)}
                if filtered:
                    lines.append(f"- **详情**:")
                    for k, v in filtered.items():
                        lines.append(f"  - {k}: {v}")
            lines.append("")

    # 失败的信息
    if failed_details:
        lines.extend([
            "## 失败的 Benchmark",
            "",
        ])
        for d in failed_details:
            lines.append(f"- **{d.get('dataset', 'Unknown')}**: {d.get('rawDetails', {}).get('error', 'Unknown error')}")
        lines.append("")

    lines.extend([
        "---",
        "",
        f"*报告由 flagos-eval-comprehensive 自动生成于 {now}*",
    ])

    return "\n".join(lines)


def merge_reports(report_files: List[str], output_path: str) -> Dict:
    """
    合并多个报告文件为一个汇总报告。

    Args:
        report_files: JSON 报告文件路径列表
        output_path: 输出文件路径

    Returns:
        合并后的结果 dict
    """
    all_details = []
    model_name = "Unknown"

    for path in report_files:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for mn, model_data in data.get('eval_results', {}).items():
                model_name = mn
                all_details.extend(model_data.get('details', []))
        except Exception:
            continue

    result = build_result(model_name=model_name, details=all_details)
    save_json(result, output_path)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Report Generator')
    parser.add_argument('--input', nargs='+', help='Input JSON result files')
    parser.add_argument('--output-dir', default='.')
    parser.add_argument('--model-name', default='Unknown')
    parser.add_argument('--model-type', default='LLM')
    args = parser.parse_args()

    if args.input:
        # 合并多个报告
        all_details = []
        for path in args.input:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for mn, model_data in data.get('eval_results', {}).items():
                    all_details.extend(model_data.get('details', []))
            except Exception:
                continue

        result = generate_report(
            model_name=args.model_name,
            model_type=args.model_type,
            details=all_details,
            output_dir=args.output_dir,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
