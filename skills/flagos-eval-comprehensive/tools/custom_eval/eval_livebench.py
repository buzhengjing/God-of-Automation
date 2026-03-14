#!/usr/bin/env python3
"""
LiveBench 评测脚本
实时综合能力评测（持续更新的动态评测）。
通过调用 LiveBench 官方 API 或本地数据集进行评测。

LiveBench 包含多个子任务：math, coding, reasoning, language, data_analysis, instruction_following
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import (
    ProgressLogger, load_config, call_text_api,
    extract_numerical_answer, extract_choice_answer,
    build_detail, save_json, load_jsonl,
    MATH_PROMPT_TEMPLATE, CHOICE_PROMPT_TEMPLATE,
)


LIVEBENCH_CATEGORIES = [
    "math", "coding", "reasoning", "language",
    "data_analysis", "instruction_following"
]


def evaluate_livebench(config: dict, dataset_path: str = "datasets/LiveBench",
                       limit: int = None, logger: ProgressLogger = None) -> dict:
    """
    评测 LiveBench。

    数据集格式（JSONL）：
    {"question_id": str, "category": str, "question": str, "answer": str, "type": "mcq"|"open"}
    """
    model_name = config['model']['name']
    data_file = os.path.join(dataset_path, "test.jsonl")
    data = load_jsonl(data_file)

    if not data:
        if logger:
            logger.log(f"[ERROR] LiveBench dataset not found at {data_file}")
        return build_detail("LiveBench", 0.0, {"error": f"Dataset not found: {data_file}"}, "F")

    if limit:
        data = data[:limit]

    if logger:
        logger.section(f"LiveBench Evaluation - {model_name}")
        logger.log(f"Total samples: {len(data)}")

    from collections import defaultdict
    cat_correct = defaultdict(int)
    cat_total = defaultdict(int)
    total_correct = 0

    for i, item in enumerate(data):
        qid = item.get('question_id', i)
        category = item.get('category', 'unknown')
        question = item.get('question', '')
        expected = item.get('answer', '')
        q_type = item.get('type', 'open')

        cat_total[category] += 1

        if q_type == 'mcq':
            prompt = CHOICE_PROMPT_TEMPLATE.format(question=question, choices="A, B, C, D")
        else:
            prompt = question

        response, token_info = call_text_api(prompt, config)
        if response is None:
            if logger:
                logger.log(f"[{i+1}/{len(data)}] ID={qid} [{category}]: API_ERROR")
            continue

        if q_type == 'mcq':
            predicted = extract_choice_answer(response)
            is_correct = predicted == expected.strip().upper()
        else:
            predicted = response.strip()
            is_correct = expected.strip().lower() in predicted.lower()

        if is_correct:
            total_correct += 1
            cat_correct[category] += 1

        status = "CORRECT" if is_correct else "WRONG"
        if logger:
            logger.log(f"[{i+1}/{len(data)}] ID={qid} [{category}]: {status}")

    total = len(data)
    accuracy = (total_correct / total * 100) if total > 0 else 0.0

    raw_details = {}
    for cat in LIVEBENCH_CATEGORIES:
        if cat_total[cat] > 0:
            raw_details[cat] = round(cat_correct[cat] / cat_total[cat] * 100, 2)
    raw_details["accuracy"] = round(accuracy, 2)

    if logger:
        logger.section(f"LiveBench Complete: {total_correct}/{total} = {accuracy:.2f}%")
        for cat, acc in raw_details.items():
            if cat != "accuracy":
                logger.log(f"  {cat}: {acc}%")

    return build_detail("LiveBench", accuracy, raw_details)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='LiveBench Evaluation')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--dataset-path', default='datasets/LiveBench')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--output', default='outputs/custom/livebench_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_livebench.log')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger(args.log)
    result = evaluate_livebench(config, args.dataset_path, args.limit, logger)
    save_json(result, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
