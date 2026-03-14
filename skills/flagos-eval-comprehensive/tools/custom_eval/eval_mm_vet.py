#!/usr/bin/env python3
"""
MM-Vet v2 评测脚本
多模态综合能力评测，使用 GPT-judge 或模型自评打分。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import (
    ProgressLogger, load_config, call_multimodal_api, call_text_api,
    build_detail, save_json, load_jsonl,
)

try:
    import pandas as pd
except ImportError:
    pd = None


JUDGE_PROMPT = """You are an expert evaluator. Compare the model's response with the reference answer and rate the response quality.

Question: {question}
Reference Answer: {reference}
Model Response: {response}

Rate the model's response on a scale of 0 to 1:
- 1.0: Fully correct and complete
- 0.5: Partially correct
- 0.0: Completely wrong or irrelevant

Output ONLY a single number between 0 and 1. Do not include any other text."""


def load_mm_vet_dataset(dataset_path: str):
    """加载 MM-Vet v2 数据集。"""
    from pathlib import Path

    jsonl_file = Path(dataset_path) / "test.jsonl"
    if jsonl_file.exists():
        return load_jsonl(str(jsonl_file))

    json_file = Path(dataset_path) / "mm_vet_v2.json"
    if json_file.exists():
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    if pd:
        parquet_dir = Path(dataset_path) / "data"
        if parquet_dir.exists():
            parquet_files = list(parquet_dir.glob("*.parquet"))
            if parquet_files:
                dfs = [pd.read_parquet(pf) for pf in parquet_files]
                df = pd.concat(dfs, ignore_index=True)
                return [row.to_dict() for _, row in df.iterrows()]

    return None


def judge_response(question: str, reference: str, response: str, config: dict) -> float:
    """使用模型对响应进行打分。"""
    prompt = JUDGE_PROMPT.format(
        question=question, reference=reference, response=response
    )
    judge_resp, _ = call_text_api(prompt, config)
    if judge_resp is None:
        return 0.0
    try:
        score = float(judge_resp.strip())
        return max(0.0, min(1.0, score))
    except ValueError:
        import re
        numbers = re.findall(r'([01]\.?\d*)', judge_resp)
        if numbers:
            return max(0.0, min(1.0, float(numbers[0])))
        return 0.0


def evaluate_mm_vet(config: dict, dataset_path: str = "datasets/MM-Vet-v2",
                    limit: int = None, logger: ProgressLogger = None,
                    judge_config: dict = None) -> dict:
    """
    评测 MM-Vet v2。

    如果提供 judge_config，使用该配置的模型作为 judge。
    否则使用被评测模型自身打分（self-judge）。

    数据集格式（JSONL）：
    {"id": str, "question": str, "answer": str, "image": base64/path, "capability": str}
    """
    model_name = config['model']['name']
    data = load_mm_vet_dataset(dataset_path)

    if data is None:
        if logger:
            logger.log(f"[ERROR] MM-Vet v2 dataset not found at {dataset_path}")
        return build_detail("MM-Vet_v2", 0.0, {"error": f"Dataset not found: {dataset_path}"}, "F")

    if isinstance(data, dict):
        data = list(data.values()) if not isinstance(list(data.values())[0], str) else [data]

    if limit:
        data = data[:limit]

    if logger:
        logger.section(f"MM-Vet v2 Evaluation - {model_name}")
        logger.log(f"Total samples: {len(data)}")

    judge_cfg = judge_config or config
    total_score = 0.0
    total = len(data)
    from collections import defaultdict
    cap_scores = defaultdict(list)

    for i, item in enumerate(data):
        qid = item.get('id', i)
        question = item.get('question', '')
        reference = item.get('answer', '')
        images = item.get('image', item.get('images', None))
        capability = item.get('capability', 'general')

        img_list = [images] if images is not None and not isinstance(images, list) else images
        response, _ = call_multimodal_api(question, img_list, config)

        if response is None:
            if logger:
                logger.log(f"[{i+1}/{total}] ID={qid}: API_ERROR")
            cap_scores[capability].append(0.0)
            continue

        score = judge_response(question, reference, response, judge_cfg)
        total_score += score
        cap_scores[capability].append(score)

        if logger:
            logger.log(f"[{i+1}/{total}] ID={qid} [{capability}]: Score={score:.2f}")

    avg_score = (total_score / total * 100) if total > 0 else 0.0

    raw_details = {"accuracy": round(avg_score, 2)}
    for cap, scores in sorted(cap_scores.items()):
        if scores:
            raw_details[cap] = round(sum(scores) / len(scores) * 100, 2)

    if logger:
        logger.section(f"MM-Vet v2 Complete: Avg Score = {avg_score:.2f}")

    return build_detail("MM-Vet_v2", avg_score, raw_details)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='MM-Vet v2 Evaluation')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--dataset-path', default='datasets/MM-Vet-v2')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--output', default='outputs/custom/mm_vet_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_mm_vet.log')
    parser.add_argument('--judge-config', default=None, help='Judge model config YAML')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    judge_config = None
    if args.judge_config:
        judge_config = load_config(args.judge_config)

    logger = ProgressLogger(args.log)
    result = evaluate_mm_vet(config, args.dataset_path, args.limit, logger, judge_config)
    save_json(result, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
