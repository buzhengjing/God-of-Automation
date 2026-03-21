#!/usr/bin/env python3
"""
AIME Dataset Evaluation Script
Evaluates math competition answers with numerical tolerance support.
All configuration is loaded dynamically from config.yaml.

Supports concurrent evaluation for faster quick-mode screening:
    --concurrency N     并发请求数（默认 1 串行）
    --quick             quick 模式默认全量并发（AIME25 ~30题）
"""

import json
import re
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime
from typing import Optional

import yaml
import requests


class ProgressLogger:
    """线程安全的进度日志器，支持实时写入文件"""
    def __init__(self, log_file: str):
        self.log_file = log_file
        self._lock = threading.Lock()
        # 清空旧日志
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Log started\n")

    def log(self, message: str):
        """写入日志并立即刷新（线程安全）"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self._lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
                f.flush()


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except yaml.YAMLError as e:
        return None


def load_aime_dataset(dataset_path: str) -> list:
    """Load AIME test data from JSONL file."""
    data = []
    test_file = Path(dataset_path) / "test.jsonl"

    if not test_file.exists():
        return None

    with open(test_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def extract_answer_from_response(response: str) -> str:
    """
    Extract the final numerical answer from model response.
    Expects format: [[ANSWER]] followed by the answer value.
    """
    if not response:
        return None

    # Primary: Look for our specified format [[ANSWER]]xxx[[/ANSWER]]
    pattern = r'\[\[ANSWER\]\]\s*([+-]?\d+(?:\.\d+)?)\s*\[\[/ANSWER\]\]'
    match = re.search(pattern, response)
    if match:
        return match.group(1).strip()

    # Fallback: Look for [[ANSWER]] followed by a number
    pattern2 = r'\[\[ANSWER\]\]\s*([+-]?\d+(?:\.\d+)?)'
    match = re.search(pattern2, response)
    if match:
        return match.group(1).strip()

    # Fallback: Look for \boxed{xxx}
    boxed_pattern = r'\\boxed\{([^}]+)\}'
    matches = re.findall(boxed_pattern, response)
    if matches:
        return matches[-1].strip()

    # Last resort: find the last number in response
    numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', response)
    if numbers:
        return numbers[-1]

    return None


def normalize_answer(answer) -> float:
    """Normalize answer to float for comparison."""
    if answer is None:
        return None

    try:
        # Handle string answers
        if isinstance(answer, str):
            # Remove common formatting
            answer = answer.strip()
            answer = re.sub(r'[,\s]', '', answer)
            answer = re.sub(r'\\', '', answer)
        return float(answer)
    except (ValueError, TypeError):
        return None


def compare_answers(predicted, expected, tolerance: float = 0.01) -> bool:
    """
    Compare predicted answer with expected answer.
    Uses numerical tolerance for floating point comparison.
    """
    pred_val = normalize_answer(predicted)
    exp_val = normalize_answer(expected)

    if pred_val is None or exp_val is None:
        # Fall back to string comparison for non-numeric answers
        return str(predicted).strip() == str(expected).strip()

    # Use tolerance for numerical comparison
    return abs(pred_val - exp_val) <= tolerance


def call_model_api(prompt: str, config: dict) -> tuple:
    """
    Call the model API and return (response_text, token_info, is_timeout).
    Returns (None, None, False) on failure, (None, None, True) on timeout.
    """
    api_base = config['model']['api_base']
    api_key = config['model'].get('api_key', 'EMPTY')
    model_name = config['model']['name']

    inference_config = config.get('inference', {})
    temperature = inference_config.get('temperature', 0)
    max_tokens = inference_config.get('max_tokens', 2048)
    top_p = inference_config.get('top_p', 1)

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    # Build prompt with strict output format requirement
    user_prompt = f"""Please solve this math problem step by step.

Problem: {prompt}

IMPORTANT: After your reasoning, you MUST output your final numerical answer in this EXACT format:
[[ANSWER]]your_numerical_answer[[/ANSWER]]

For example, if the answer is 42, write: [[ANSWER]]42[[/ANSWER]]
Only include the number, no units or explanations inside the answer tags."""

    payload = {
        'model': model_name,
        'messages': [
            {
                'role': 'user',
                'content': user_prompt
            }
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
        'top_p': top_p
    }

    max_retries = config.get('inference', {}).get('max_retries', 3)
    timeout = config.get('inference', {}).get('timeout', 300)

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout
            )
            response.raise_for_status()
            result = response.json()

            content = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            token_info = {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'total_tokens': usage.get('total_tokens', 0)
            }
            return content, token_info, False
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return None, None, True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(5)  # 重试前等待5秒
                continue
            return None, None, False


def _evaluate_single(item: dict, index: int, total: int, config: dict,
                     tolerance: float, dry_run: bool,
                     progress: ProgressLogger) -> dict:
    """评测单道题目，返回结果 dict（线程安全）"""
    problem = item.get('problem', '')
    expected_answer = item.get('answer')
    item_id = item.get('id', index)

    if dry_run:
        model_response = f"[[ANSWER]]{expected_answer}[[/ANSWER]]"
        token_info = {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}
        is_timeout = False
    else:
        model_response, token_info, is_timeout = call_model_api(problem, config)

    if model_response is None:
        if is_timeout:
            progress.log(f"[{index+1}/{total}] ID={item_id}: TIMEOUT")
            return {"index": index, "item_id": item_id, "correct": False, "error": False, "timeout": True}
        progress.log(f"[{index+1}/{total}] ID={item_id}: API_ERROR")
        return {"index": index, "item_id": item_id, "correct": False, "error": True, "timeout": False}

    predicted_answer = extract_answer_from_response(model_response)
    is_correct = compare_answers(predicted_answer, expected_answer, tolerance)

    status = "CORRECT" if is_correct else "WRONG"
    progress.log(f"[{index+1}/{total}] ID={item_id}: {status} | Pred={predicted_answer} | Exp={expected_answer}")

    return {"index": index, "item_id": item_id, "correct": is_correct, "error": False, "timeout": False}


def evaluate_aime(config: dict, dry_run: bool = False, quick: bool = False,
                  concurrency: int = 1, log_file: str = "eval_aime_progress.log") -> dict:
    """
    Main evaluation function for AIME dataset.

    Args:
        config: Configuration dictionary from config.yaml
        dry_run: If True, use mock responses instead of API calls
        quick: If True, use AIME25 dataset with no sample limit
        concurrency: Number of concurrent API requests (0 = auto = total samples)
        log_file: Progress log file path

    Returns:
        Evaluation results in the required JSON format
    """
    model_name = config['model']['name']
    tolerance = config.get('evaluation', {}).get('tolerance', 0.01)

    if quick:
        dataset_path = config['datasets']['aime25_path']
        dataset_label = "AIME25_0fewshot_@avg1"
        max_samples = None  # AIME25 题量少，全跑
    else:
        dataset_path = config['datasets']['aime_path']
        dataset_label = "AIME_0fewshot_@avg1"
        max_samples = config.get('evaluation', {}).get('aime_samples', 150)

    # 初始化进度日志
    progress = ProgressLogger(log_file)

    # Load dataset
    data = load_aime_dataset(dataset_path)
    if data is None:
        progress.log(f"ERROR: Failed to load AIME dataset from {dataset_path}")
        return {
            "err_code": 1,
            "err_msg": f"Failed to load AIME dataset from {dataset_path}",
            "eval_results": {}
        }

    # Limit samples if configured
    if max_samples and len(data) > max_samples:
        data = data[:max_samples]

    total = len(data)

    # 确定并发数：0 或未指定时自动决定
    if concurrency <= 0:
        effective_concurrency = total  # 全量并发
    else:
        effective_concurrency = min(concurrency, total)

    progress.log("=" * 50)
    progress.log(f"AIME Evaluation Started")
    progress.log(f"Model: {model_name}")
    progress.log(f"Dataset: {dataset_path} ({'quick' if quick else 'full'})")
    progress.log(f"Total samples: {total}")
    progress.log(f"Concurrency: {effective_concurrency}")
    progress.log("=" * 50)

    start_time = time.time()

    if effective_concurrency <= 1:
        # 串行模式（原始逻辑）
        results_list = []
        for i, item in enumerate(data):
            r = _evaluate_single(item, i, total, config, tolerance, dry_run, progress)
            results_list.append(r)
    else:
        # 并发模式
        results_list = [None] * total
        with ThreadPoolExecutor(max_workers=effective_concurrency) as executor:
            futures = {}
            for i, item in enumerate(data):
                future = executor.submit(
                    _evaluate_single, item, i, total, config, tolerance, dry_run, progress
                )
                futures[future] = i

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results_list[idx] = future.result()
                except Exception as e:
                    progress.log(f"[{idx+1}/{total}] THREAD_ERROR: {e}")
                    results_list[idx] = {"index": idx, "item_id": idx, "correct": False, "error": True, "timeout": False}

    elapsed = time.time() - start_time

    # 统计结果
    correct = sum(1 for r in results_list if r and r.get("correct"))
    errors = sum(1 for r in results_list if r and r.get("error"))
    timeouts = sum(1 for r in results_list if r and r.get("timeout"))
    completed = total - errors - timeouts
    accuracy = (correct / total * 100) if total > 0 else 0.0
    effective_accuracy = (correct / completed * 100) if completed > 0 else 0.0

    progress.log("=" * 50)
    progress.log(f"Evaluation Complete: {correct}/{total} = {accuracy:.2f}%")
    progress.log(f"Effective Accuracy (excl timeouts/errors): {correct}/{completed} = {effective_accuracy:.2f}%")
    progress.log(f"Errors: {errors}, Timeouts: {timeouts}, Elapsed: {elapsed:.1f}s")
    progress.log(f"Concurrency: {effective_concurrency}, Avg per question: {elapsed/max(total,1):.1f}s")
    progress.log("=" * 50)

    # Build result in required format
    result = {
        "err_code": 0,
        "err_msg": "Get Evaluations Details Sucess!",
        "eval_results": {
            model_name: {
                "status": "S",
                "details": [
                    {
                        "status": "S",
                        "dataset": dataset_label,
                        "accuracy": round(accuracy, 2),
                        "rawDetails": {
                            "total": total,
                            "correct": correct,
                            "errors": errors,
                            "timeouts": timeouts,
                            "completed": completed,
                            "effective_accuracy": round(effective_accuracy, 2),
                            "elapsed_seconds": round(elapsed, 1),
                            "concurrency": effective_concurrency,
                        }
                    }
                ]
            }
        }
    }

    return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='AIME Dataset Evaluation Script')
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='Path to configuration file (default: config.yaml)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run in dry-run mode with mock responses')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: use AIME25 dataset, default full concurrency')
    parser.add_argument('--concurrency', type=int, default=None,
                        help='Number of concurrent API requests (default: 1 for full, 0=auto for quick)')
    parser.add_argument('--output', type=str, default='aime_result.json',
                        help='Output JSON file path (default: aime_result.json)')
    parser.add_argument('--log', type=str, default='eval_aime_progress.log',
                        help='Progress log file path (default: eval_aime_progress.log)')
    args = parser.parse_args()

    # 确定并发数
    if args.concurrency is not None:
        concurrency = args.concurrency
    elif args.quick:
        concurrency = 0  # quick 模式默认全量并发
    else:
        concurrency = 1  # 完整模式默认串行

    # Load configuration
    config = load_config(args.config)
    if config is None:
        error_result = {
            "err_code": 1,
            "err_msg": f"Failed to load configuration from {args.config}",
            "eval_results": {}
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, indent=2, ensure_ascii=False)
        sys.exit(1)

    # Run evaluation
    result = evaluate_aime(config, dry_run=args.dry_run, quick=args.quick,
                           concurrency=concurrency, log_file=args.log)

    # Output result to JSON file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
