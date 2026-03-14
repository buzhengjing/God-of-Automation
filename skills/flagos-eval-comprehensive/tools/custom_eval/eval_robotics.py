#!/usr/bin/env python3
"""
具身智能/机器人模型 Benchmark 集合评测脚本
支持: SAT, All-Angles, Where2Place, Blink_ev, RoboSpatial-Home,
      EgoPlan-Bench2, ERQA, CV-Bench, EmbSpatial-Bench, VSI-Bench, EmbodiedVerse-Open

所有 benchmark 统一为多模态选择题格式评测。
"""

import json
import os
import sys
from collections import defaultdict

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


# Benchmark 配置映射
ROBOTICS_BENCHMARKS = {
    "erqa": {
        "display_name": "ERQA",
        "categories": [
            "Other", "Pointing", "Task Reasoning", "Action Reasoning",
            "State Estimation", "Spatial Reasoning", "Multi-view Reasoning",
            "Trajectory Reasoning"
        ],
        "category_field": "question_type",
    },
    "sat": {
        "display_name": "SAT",
        "categories": [],
        "category_field": "category",
    },
    "all_angles": {
        "display_name": "All-Angles_Bench",
        "categories": [],
        "category_field": "category",
    },
    "where2place": {
        "display_name": "Where2Place",
        "categories": [],
        "category_field": "category",
    },
    "blink_ev": {
        "display_name": "Blink_val_ev",
        "categories": [],
        "category_field": "category",
    },
    "robospatial": {
        "display_name": "RoboSpatial-Home",
        "categories": [],
        "category_field": "category",
    },
    "egoplan2": {
        "display_name": "EgoPlan-Bench2",
        "categories": [],
        "category_field": "category",
    },
    "cv_bench": {
        "display_name": "CV-Bench",
        "categories": [],
        "category_field": "category",
    },
    "embspatial": {
        "display_name": "EmbSpatial-Bench",
        "categories": [],
        "category_field": "category",
    },
    "vsi_bench": {
        "display_name": "VSI-Bench",
        "categories": [],
        "category_field": "category",
    },
    "embodiedverse": {
        "display_name": "EmbodiedVerse-Open",
        "categories": [],
        "category_field": "category",
    },
}


def load_robotics_dataset(dataset_path: str):
    """加载具身智能数据集，支持 parquet 和 jsonl 格式。"""
    from pathlib import Path

    # parquet 格式（如 ERQA）
    parquet_dir = Path(dataset_path) / "data"
    if parquet_dir.exists() and pd:
        parquet_files = list(parquet_dir.glob("*.parquet"))
        if parquet_files:
            dfs = [pd.read_parquet(pf) for pf in parquet_files]
            return pd.concat(dfs, ignore_index=True)

    # jsonl 格式
    for fname in ["test.jsonl", "data.jsonl"]:
        jsonl_file = Path(dataset_path) / fname
        if jsonl_file.exists():
            return load_jsonl(str(jsonl_file))

    return None


def evaluate_robotics_benchmark(
    config: dict,
    benchmark: str,
    dataset_path: str,
    limit: int = None,
    logger: ProgressLogger = None,
) -> dict:
    """
    评测单个具身智能 benchmark。

    通用数据格式：
    - question: 问题文本
    - answer: 正确答案 (A/B/C/D)
    - images: 图片数据
    - question_type/category: 问题类别
    """
    bench_cfg = ROBOTICS_BENCHMARKS.get(benchmark)
    if not bench_cfg:
        return build_detail(benchmark, 0.0, {"error": f"Unknown benchmark: {benchmark}"}, "F")

    model_name = config['model']['name']
    display_name = bench_cfg['display_name']
    category_field = bench_cfg['category_field']

    data = load_robotics_dataset(dataset_path)
    if data is None:
        if logger:
            logger.log(f"[ERROR] {display_name} dataset not found at {dataset_path}")
        return build_detail(display_name, 0.0, {"error": f"Dataset not found: {dataset_path}"}, "F")

    # 统一转为 list of dict
    if pd and isinstance(data, pd.DataFrame):
        if limit:
            data = data.head(limit)
        records = [row.to_dict() for _, row in data.iterrows()]
    else:
        if limit:
            data = data[:limit]
        records = data

    total = len(records)
    if logger:
        logger.section(f"{display_name} Evaluation - {model_name}")
        logger.log(f"Total samples: {total}")

    cat_correct = defaultdict(int)
    cat_total = defaultdict(int)
    correct = 0

    # Token 统计
    total_prompt_tokens = 0
    total_completion_tokens = 0

    for i, item in enumerate(records):
        qid = item.get('question_id', item.get('id', i))
        question = item.get('question', '')
        expected = str(item.get('answer', '')).strip().upper()
        category = item.get(category_field, 'general')
        images = item.get('images', item.get('image', None))

        cat_total[category] += 1

        prompt = MULTIMODAL_CHOICE_PROMPT_TEMPLATE.format(
            question=question, choices="A, B, C, D"
        )

        img_list = [images] if images is not None and not isinstance(images, list) else images
        response, token_info = call_multimodal_api(prompt, img_list, config)

        if response is None:
            if logger:
                logger.log(f"[{i+1}/{total}] ID={qid} [{category}]: API_ERROR")
            continue

        if token_info:
            total_prompt_tokens += token_info.get('prompt_tokens', 0)
            total_completion_tokens += token_info.get('completion_tokens', 0)

        predicted = extract_choice_answer(response)
        is_correct = predicted == expected

        if is_correct:
            correct += 1
            cat_correct[category] += 1

        status = "CORRECT" if is_correct else "WRONG"
        if logger:
            logger.log(f"[{i+1}/{total}] ID={qid} [{category}]: {status} | Pred={predicted} | Exp={expected}")

    accuracy = (correct / total * 100) if total > 0 else 0.0

    raw_details = {"accuracy": round(accuracy, 2)}
    for cat in sorted(cat_total.keys()):
        if cat_total[cat] > 0:
            raw_details[cat] = round(cat_correct[cat] / cat_total[cat] * 100, 2)

    # Token 统计
    if total > 0:
        raw_details["average_prompt_tokens"] = round(total_prompt_tokens / total, 2)
        raw_details["average_completion_tokens"] = round(total_completion_tokens / total, 2)
        raw_details["average_tokens"] = round((total_prompt_tokens + total_completion_tokens) / total, 2)

    if logger:
        logger.separator()
        logger.log(f"{display_name} Complete: {correct}/{total} = {accuracy:.2f}%")
        for cat in sorted(cat_total.keys()):
            if cat_total[cat] > 0:
                logger.log(f"  {cat}: {raw_details[cat]}%")
        logger.separator()

    return build_detail(display_name, accuracy, raw_details)


def evaluate_all_robotics(config: dict, limit: int = None,
                          logger: ProgressLogger = None) -> list:
    """评测所有具身智能 benchmark。"""
    robotics_datasets = config.get('robotics_datasets', {})
    results = []

    # Benchmark 名称到配置中数据集路径 key 的映射
    path_key_map = {
        "erqa": "erqa_path",
        "sat": "sat_path",
        "all_angles": "all_angles_path",
        "where2place": "where2place_path",
        "blink_ev": "blink_ev_path",
        "robospatial": "robospatial_path",
        "egoplan2": "egoplan2_path",
        "cv_bench": "cv_bench_path",
        "embspatial": "embspatial_path",
        "vsi_bench": "vsi_bench_path",
        "embodiedverse": "embodiedverse_path",
    }

    for bench_name, path_key in path_key_map.items():
        dataset_path = robotics_datasets.get(path_key)
        if not dataset_path:
            if logger:
                logger.log(f"[SKIP] {bench_name}: no dataset path configured")
            continue

        result = evaluate_robotics_benchmark(config, bench_name, dataset_path, limit, logger)
        results.append(result)

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Robotics Benchmark Evaluation')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--benchmark', default=None,
                        help='Specific benchmark name (e.g., erqa, sat). If not set, run all.')
    parser.add_argument('--dataset-path', default=None, help='Override dataset path')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--output', default='outputs/custom/robotics_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_robotics.log')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger(args.log)

    if args.benchmark:
        dataset_path = args.dataset_path or config.get('robotics_datasets', {}).get(
            f"{args.benchmark}_path", f"datasets/{args.benchmark}")
        result = evaluate_robotics_benchmark(config, args.benchmark, dataset_path, args.limit, logger)
        save_json(result, args.output)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        results = evaluate_all_robotics(config, args.limit, logger)
        save_json(results, args.output)
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
