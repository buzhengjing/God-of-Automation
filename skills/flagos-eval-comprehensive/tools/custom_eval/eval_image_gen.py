#!/usr/bin/env python3
"""
图像生成模型评测辅助脚本
由于图像生成模型（如 Emu3.5）主要依赖专家定性评估，
本脚本提供：
1. 批量生成图片的自动化工具
2. 生成结果的目录组织
3. 评估记录模板生成

不提供自动化打分，需人工评估。
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import ProgressLogger, load_config, build_detail, save_json, ensure_dir, load_jsonl

import requests


def generate_images(config: dict, prompts_file: str = "datasets/ImageGen/prompts.jsonl",
                    output_dir: str = "outputs/custom/image_gen",
                    logger: ProgressLogger = None) -> dict:
    """
    批量调用图像生成 API 生成图片。

    prompts 格式（JSONL）：
    {"id": str, "prompt": str, "category": str}
    如: {"id": "001", "prompt": "A cat sitting on a red chair", "category": "text2image"}
    """
    model_name = config['model']['name']
    api_base = config['model']['api_base']
    api_key = config['model'].get('api_key', 'EMPTY')

    prompts = load_jsonl(prompts_file)
    if not prompts:
        if logger:
            logger.log(f"[ERROR] Prompts file not found: {prompts_file}")
        return build_detail("Image_Gen_Qualitative", 0.0,
                          {"error": f"Prompts not found: {prompts_file}"}, "F")

    ensure_dir(output_dir)

    if logger:
        logger.section(f"Image Generation - {model_name}")
        logger.log(f"Total prompts: {len(prompts)}")

    results = []
    success_count = 0

    for i, item in enumerate(prompts):
        pid = item.get('id', str(i))
        prompt_text = item.get('prompt', '')
        category = item.get('category', 'general')

        if logger:
            logger.log(f"[{i+1}/{len(prompts)}] Generating: {prompt_text[:50]}...")

        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}'
            }
            payload = {
                'model': model_name,
                'prompt': prompt_text,
                'n': 1,
                'size': '1024x1024',
            }

            response = requests.post(
                f"{api_base}/images/generations",
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()

            # 保存图片信息
            img_data = result.get('data', [{}])[0]
            results.append({
                "id": pid,
                "prompt": prompt_text,
                "category": category,
                "status": "success",
                "url": img_data.get('url', ''),
            })
            success_count += 1

            if logger:
                logger.log(f"  -> Success")

        except Exception as e:
            results.append({
                "id": pid,
                "prompt": prompt_text,
                "category": category,
                "status": "failed",
                "error": str(e),
            })
            if logger:
                logger.log(f"  -> Failed: {e}")

    # 生成评估模板
    template = _generate_eval_template(model_name, results)
    template_path = os.path.join(output_dir, "eval_template.md")
    with open(template_path, 'w', encoding='utf-8') as f:
        f.write(template)

    # 保存生成记录
    record_path = os.path.join(output_dir, "generation_records.json")
    save_json(results, record_path)

    if logger:
        logger.section(f"Generation Complete: {success_count}/{len(prompts)}")
        logger.log(f"Eval template: {template_path}")
        logger.log(f"Records: {record_path}")

    return build_detail(
        "Image_Gen_Qualitative",
        0.0,  # 需人工打分
        {
            "note": "Qualitative evaluation required. See eval_template.md",
            "total_prompts": len(prompts),
            "successful_generations": success_count,
            "template_path": template_path,
        },
        status="S",
    )


def _generate_eval_template(model_name: str, results: list) -> str:
    """生成人工评估 Markdown 模板。"""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lines = [
        f"# 图像生成评估表 - {model_name}",
        f"",
        f"> 生成时间: {now}",
        f"> 评估维度: 视觉编辑、文生图、视觉引导、视觉叙事",
        "",
        "## 评分标准",
        "",
        "| 评分 | 含义 |",
        "|------|------|",
        "| 5 | 优秀：高质量、准确、创意 |",
        "| 4 | 良好：基本准确、质量尚可 |",
        "| 3 | 一般：部分正确、有明显缺陷 |",
        "| 2 | 较差：偏离主题、质量低 |",
        "| 1 | 很差：完全不相关或无法使用 |",
        "",
        "## 评估记录",
        "",
        "| ID | Prompt | Category | Status | Score | 备注 |",
        "|-----|--------|----------|--------|-------|------|",
    ]

    for r in results:
        status = r.get('status', 'unknown')
        lines.append(
            f"| {r['id']} | {r['prompt'][:40]}... | {r['category']} | {status} | ___/5 | |"
        )

    lines.extend([
        "",
        "## 总评",
        "",
        "- 综合评分: ___/5",
        "- 评估人: ___",
        "- 评估日期: ___",
        "",
    ])

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Image Generation Evaluation Helper')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--prompts', default='datasets/ImageGen/prompts.jsonl')
    parser.add_argument('--output-dir', default='outputs/custom/image_gen')
    parser.add_argument('--output', default='outputs/custom/image_gen_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_image_gen.log')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger(args.log)
    result = generate_images(config, args.prompts, args.output_dir, logger)
    save_json(result, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
