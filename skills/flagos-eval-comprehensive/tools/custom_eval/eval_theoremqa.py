#!/usr/bin/env python3
"""
TheoremQA 评测脚本
定理证明/数学推理评测。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import (
    ProgressLogger, load_config, call_text_api,
    extract_numerical_answer, extract_choice_answer,
    compare_numerical, build_detail, save_json, load_jsonl,
    MATH_PROMPT_TEMPLATE, CHOICE_PROMPT_TEMPLATE,
)


def evaluate_theoremqa(config: dict, dataset_path: str = "datasets/TheoremQA",
                       limit: int = None, logger: ProgressLogger = None) -> dict:
    """
    评测 TheoremQA。

    数据集格式（JSONL）：
    {"id": str, "question": str, "answer": str/number, "type": "mcq"|"numerical"|"bool"}
    """
    model_name = config['model']['name']
    data_file = os.path.join(dataset_path, "test.jsonl")
    data = load_jsonl(data_file)

    if not data:
        if logger:
            logger.log(f"[ERROR] TheoremQA dataset not found at {data_file}")
        return build_detail("TheoremQA", 0.0, {"error": f"Dataset not found: {data_file}"}, "F")

    if limit:
        data = data[:limit]

    if logger:
        logger.section(f"TheoremQA Evaluation - {model_name}")
        logger.log(f"Total samples: {len(data)}")

    correct = 0
    total = len(data)

    for i, item in enumerate(data):
        qid = item.get('id', i)
        question = item.get('question', '')
        expected = item.get('answer', '')
        q_type = item.get('type', 'numerical')

        if q_type == 'mcq':
            prompt = CHOICE_PROMPT_TEMPLATE.format(question=question, choices="A, B, C, D")
        elif q_type == 'bool':
            prompt = CHOICE_PROMPT_TEMPLATE.format(question=question, choices="True, False")
        else:
            prompt = MATH_PROMPT_TEMPLATE.format(problem=question)

        response, _ = call_text_api(prompt, config)
        if response is None:
            if logger:
                logger.log(f"[{i+1}/{total}] ID={qid}: API_ERROR")
            continue

        if q_type == 'mcq':
            predicted = extract_choice_answer(response)
            is_correct = predicted == str(expected).strip().upper()
        elif q_type == 'bool':
            pred_lower = response.strip().lower()
            is_correct = str(expected).lower() in pred_lower
        else:
            predicted = extract_numerical_answer(response)
            is_correct = compare_numerical(predicted, expected, tolerance=0.01)

        if is_correct:
            correct += 1

        status = "CORRECT" if is_correct else "WRONG"
        if logger:
            logger.log(f"[{i+1}/{total}] ID={qid}: {status}")

    accuracy = (correct / total * 100) if total > 0 else 0.0

    if logger:
        logger.section(f"TheoremQA Complete: {correct}/{total} = {accuracy:.2f}%")

    return build_detail("TheoremQA", accuracy)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='TheoremQA Evaluation')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--dataset-path', default='datasets/TheoremQA')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--output', default='outputs/custom/theoremqa_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_theoremqa.log')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger(args.log)
    result = evaluate_theoremqa(config, args.dataset_path, args.limit, logger)
    save_json(result, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
