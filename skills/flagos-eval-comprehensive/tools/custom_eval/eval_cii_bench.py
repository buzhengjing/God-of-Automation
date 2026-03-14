#!/usr/bin/env python3
"""
CII-Bench 评测脚本
中文图像信息理解评测（Chinese Image Information Understanding Benchmark）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import (
    ProgressLogger, load_config, call_multimodal_api,
    extract_choice_answer, build_detail, save_json, load_jsonl,
    MULTIMODAL_CHOICE_PROMPT_TEMPLATE,
)

try:
    import pandas as pd
except ImportError:
    pd = None


def load_cii_dataset(dataset_path: str):
    """加载 CII-Bench 数据集。支持 parquet 和 jsonl。"""
    from pathlib import Path

    # 尝试 parquet
    parquet_dir = Path(dataset_path) / "data"
    if parquet_dir.exists() and pd:
        parquet_files = list(parquet_dir.glob("*.parquet"))
        if parquet_files:
            dfs = [pd.read_parquet(pf) for pf in parquet_files]
            return pd.concat(dfs, ignore_index=True)

    # 尝试 jsonl
    jsonl_file = Path(dataset_path) / "test.jsonl"
    if jsonl_file.exists():
        return load_jsonl(str(jsonl_file))

    return None


def evaluate_cii_bench(config: dict, dataset_path: str = "datasets/CII-Bench",
                       limit: int = None, logger: ProgressLogger = None) -> dict:
    """
    评测 CII-Bench。

    数据集每条样本包含：question, image(s), answer (A/B/C/D), category
    """
    model_name = config['model']['name']
    data = load_cii_dataset(dataset_path)

    if data is None:
        if logger:
            logger.log(f"[ERROR] CII-Bench dataset not found at {dataset_path}")
        return build_detail("CII-Bench", 0.0, {"error": f"Dataset not found: {dataset_path}"}, "F")

    if pd and isinstance(data, pd.DataFrame):
        if limit:
            data = data.head(limit)
        total = len(data)
        iterator = data.iterrows()
        get_field = lambda row, key: row.get(key, '')
        get_images = lambda row: row.get('images', None)
    else:
        if limit:
            data = data[:limit]
        total = len(data)
        iterator = enumerate(data)
        get_field = lambda row, key: row.get(key, '')
        get_images = lambda row: row.get('images', None)

    if logger:
        logger.section(f"CII-Bench Evaluation - {model_name}")
        logger.log(f"Total samples: {total}")

    from collections import defaultdict
    cat_correct = defaultdict(int)
    cat_total = defaultdict(int)
    correct = 0

    for idx, row in iterator:
        qid = get_field(row, 'question_id') or idx
        question = get_field(row, 'question')
        expected = str(get_field(row, 'answer')).strip().upper()
        category = get_field(row, 'category') or 'general'
        images = get_images(row)

        cat_total[category] += 1

        prompt = MULTIMODAL_CHOICE_PROMPT_TEMPLATE.format(
            question=question, choices="A, B, C, D"
        )

        img_list = [images] if images is not None and not isinstance(images, list) else images
        response, _ = call_multimodal_api(prompt, img_list, config)

        if response is None:
            if logger:
                logger.log(f"[{idx+1}/{total}] ID={qid}: API_ERROR")
            continue

        predicted = extract_choice_answer(response)
        is_correct = predicted == expected

        if is_correct:
            correct += 1
            cat_correct[category] += 1

        status = "CORRECT" if is_correct else "WRONG"
        if logger:
            logger.log(f"[{idx+1}/{total}] ID={qid} [{category}]: {status} | Pred={predicted} | Exp={expected}")

    accuracy = (correct / total * 100) if total > 0 else 0.0

    raw_details = {"accuracy": round(accuracy, 2)}
    for cat in sorted(cat_total.keys()):
        if cat_total[cat] > 0:
            raw_details[cat] = round(cat_correct[cat] / cat_total[cat] * 100, 2)

    if logger:
        logger.section(f"CII-Bench Complete: {correct}/{total} = {accuracy:.2f}%")

    return build_detail("CII-Bench", accuracy, raw_details)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='CII-Bench Evaluation')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--dataset-path', default='datasets/CII-Bench')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--output', default='outputs/custom/cii_bench_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_cii_bench.log')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger(args.log)
    result = evaluate_cii_bench(config, args.dataset_path, args.limit, logger)
    save_json(result, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
