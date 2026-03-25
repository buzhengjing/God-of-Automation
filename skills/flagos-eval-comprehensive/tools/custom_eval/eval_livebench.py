#!/usr/bin/env python3
"""
LiveBench 评测脚本
实时综合能力评测（持续更新的动态评测）。

数据集来源：
  - 官方 HuggingFace: livebench/live_bench (自动下载)
  - 本地 JSONL: datasets/LiveBench/test.jsonl (回退)

LiveBench 包含多个子任务：math, coding, reasoning, language, data_analysis, instruction_following
"""

import json
import os
import sys
import traceback

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

# 官方 HuggingFace 数据集 ID
HF_DATASET_ID = "livebench/live_bench"


def _download_livebench(cache_dir: str, logger: ProgressLogger = None) -> list:
    """
    从 HuggingFace 下载 LiveBench 官方数据集并转换为统一格式。

    官方数据集包含两个 config:
      - livebench/live_bench (questions): question_id, category, question, ...
      - livebench/live_bench (ground_truth): question_id, ground_truth, ...

    Returns:
        list of dict: 统一格式的数据列表，失败时返回空列表
    """
    try:
        import datasets as hf_datasets
    except ImportError:
        if logger:
            logger.log("[WARN] 'datasets' library not installed, cannot auto-download LiveBench")
        return []

    if logger:
        logger.log(f"[LiveBench] Attempting to download from HuggingFace: {HF_DATASET_ID}")

    try:
        # 尝试加载 questions
        questions_ds = hf_datasets.load_dataset(
            HF_DATASET_ID, "live_bench", split="test",
            trust_remote_code=True,
        )

        # 尝试加载 ground_truth
        try:
            gt_ds = hf_datasets.load_dataset(
                HF_DATASET_ID, "live_bench_ground_truth", split="test",
                trust_remote_code=True,
            )
            gt_map = {row['question_id']: row for row in gt_ds}
        except Exception:
            gt_map = {}

        if logger:
            logger.log(f"[LiveBench] Downloaded {len(questions_ds)} questions"
                        f", {len(gt_map)} ground truth entries")

        # 转换为统一格式
        data = []
        for row in questions_ds:
            qid = row.get('question_id', '')
            category = row.get('category', 'unknown')
            question = row.get('turns', row.get('question', ''))
            # turns 可能是 list
            if isinstance(question, list):
                question = question[0] if question else ''

            gt_row = gt_map.get(qid, {})
            answer = gt_row.get('ground_truth', row.get('answer', ''))

            # 判断题型：有 choices 字段视为 mcq
            q_type = 'open'
            if row.get('choices') or row.get('options'):
                q_type = 'mcq'
                choices = row.get('choices', row.get('options', []))
                if choices:
                    options_str = "\n".join(
                        [f"{chr(65+j)}. {opt}" for j, opt in enumerate(choices)]
                    )
                    question = f"{question}\n\n{options_str}"

            data.append({
                'question_id': qid,
                'category': category,
                'question': question,
                'answer': str(answer),
                'type': q_type,
            })

        # 缓存到本地
        if data:
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, "test.jsonl")
            with open(cache_file, 'w', encoding='utf-8') as f:
                for item in data:
                    f.write(json.dumps(item, ensure_ascii=False) + '\n')
            if logger:
                logger.log(f"[LiveBench] Cached {len(data)} samples to {cache_file}")

        return data

    except Exception as e:
        if logger:
            logger.log(f"[WARN] LiveBench auto-download failed: {e}")
            logger.log(traceback.format_exc())
        return []


def _load_livebench_data(dataset_path: str, logger: ProgressLogger = None) -> list:
    """
    加载 LiveBench 数据集。优先本地文件，不存在时自动下载。

    Args:
        dataset_path: 本地数据集目录
        logger: 日志器

    Returns:
        list of dict: 数据列表
    """
    # 1. 尝试本地 JSONL
    data_file = os.path.join(dataset_path, "test.jsonl")
    data = load_jsonl(data_file)
    if data:
        if logger:
            logger.log(f"[LiveBench] Loaded {len(data)} samples from local: {data_file}")
        return data

    # 2. 自动下载
    if logger:
        logger.log(f"[LiveBench] Local dataset not found at {data_file}, trying auto-download...")
    data = _download_livebench(dataset_path, logger)
    if data:
        return data

    # 3. 全部失败
    return []


def evaluate_livebench(config: dict, dataset_path: str = "datasets/LiveBench",
                       limit: int = None, logger: ProgressLogger = None) -> dict:
    """
    评测 LiveBench。

    数据集格式（JSONL）：
    {"question_id": str, "category": str, "question": str, "answer": str, "type": "mcq"|"open"}
    """
    model_name = config['model']['name']
    data = _load_livebench_data(dataset_path, logger)

    if not data:
        msg = (f"LiveBench dataset not available. "
               f"Place test.jsonl in {dataset_path}/ or ensure network access "
               f"for auto-download from HuggingFace ({HF_DATASET_ID}).")
        if logger:
            logger.log(f"[ERROR] {msg}")
        return build_detail("LiveBench", 0.0, {"error": msg}, "F")

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
