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
        err_msg="Get Evaluations Details Sucess!" if all_success
                else f"Partial: {len(success_details)} ok, {len(failed_details)} failed",
    )

    # 保存 JSON
    json_path = os.path.join(output_dir, report_json)
    save_json(result, json_path)

    # 生成 Markdown
    md_content = _generate_markdown(model_name, model_type, details, success_details, failed_details)
    md_path = os.path.join(output_dir, report_md)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    return result


def _generate_markdown(
    model_name: str,
    model_type: str,
    all_details: List[Dict],
    success_details: List[Dict],
    failed_details: List[Dict],
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
        "",
        "---",
        "",
        "## 评测结果总览",
        "",
        "| Benchmark | 状态 | 得分 |",
        "|-----------|------|------|",
    ]

    for d in all_details:
        status = "Pass" if d.get('status') == 'S' else "Fail"
        accuracy = d.get('accuracy', 'N/A')
        if isinstance(accuracy, (int, float)):
            accuracy = f"{accuracy:.2f}"
        lines.append(f"| {d.get('dataset', 'Unknown')} | {status} | {accuracy} |")

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
