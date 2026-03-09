#!/usr/bin/env python3
"""
ERQA Dataset Evaluation Script
Evaluates embodied reasoning QA with multi-category accuracy and token statistics.
All configuration is loaded dynamically from config.yaml.
"""

import json
import re
import os
import sys
import base64
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import yaml
import requests
import pandas as pd


class ProgressLogger:
    """简单的进度日志器，支持实时写入文件"""
    def __init__(self, log_file: str):
        self.log_file = log_file
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Log started\n")

    def log(self, message: str):
        """写入日志并立即刷新"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()


# ERQA category constants
ERQA_CATEGORIES = [
    "Other",
    "Pointing",
    "Task Reasoning",
    "Action Reasoning",
    "State Estimation",
    "Spatial Reasoning",
    "Multi-view Reasoning",
    "Trajectory Reasoning"
]


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None
    except yaml.YAMLError as e:
        return None


def load_erqa_dataset(dataset_path: str) -> pd.DataFrame:
    """Load ERQA test data from parquet file."""
    data_dir = Path(dataset_path) / "data"

    # Find parquet files
    parquet_files = list(data_dir.glob("*.parquet"))
    if not parquet_files:
        return None

    # Load all parquet files
    dfs = []
    for pf in parquet_files:
        dfs.append(pd.read_parquet(pf))

    if not dfs:
        return None

    return pd.concat(dfs, ignore_index=True)


def extract_choice_from_response(response: str) -> str:
    """
    Extract the choice (A/B/C/D) from model response.
    Expects format: [[ANSWER]]X[[/ANSWER]] where X is A, B, C, or D.
    """
    if not response:
        return None

    response = response.strip()

    # Primary: Look for our specified format [[ANSWER]]X[[/ANSWER]]
    pattern = r'\[\[ANSWER\]\]\s*([A-Da-d])\s*\[\[/ANSWER\]\]'
    match = re.search(pattern, response)
    if match:
        return match.group(1).upper()

    # Fallback: Look for [[ANSWER]] followed by a letter
    pattern2 = r'\[\[ANSWER\]\]\s*([A-Da-d])'
    match = re.search(pattern2, response)
    if match:
        return match.group(1).upper()

    # Fallback patterns for common formats
    fallback_patterns = [
        r'[Tt]he\s+(?:correct\s+)?answer\s+is[:\s]+([A-Da-d])',
        r'[Aa]nswer[:\s]+([A-Da-d])',
        r'\(([A-Da-d])\)',
    ]
    for pattern in fallback_patterns:
        match = re.search(pattern, response)
        if match:
            return match.group(1).upper()

    # Last resort: find any single A-D letter at the end
    letters = re.findall(r'\b([A-Da-d])\b', response[-100:] if len(response) > 100 else response)
    if letters:
        return letters[-1].upper()

    return None


def encode_image_to_base64(image_data) -> str:
    """Convert image data to base64 string."""
    if isinstance(image_data, bytes):
        return base64.b64encode(image_data).decode('utf-8')
    elif hasattr(image_data, 'tobytes'):
        # PIL Image
        import io
        buffer = io.BytesIO()
        image_data.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    return None


def call_model_api(question: str, images: list, config: dict) -> tuple:
    """
    Call the model API with text and images.
    Returns (response_text, token_info).
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

    # Build content with images
    content = []

    # Add images first
    if images is not None:
        for img in images:
            if img is not None:
                try:
                    img_base64 = encode_image_to_base64(img)
                    if img_base64:
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        })
                except Exception:
                    pass

    # Add question text with strict output format requirement
    prompt_text = f"""{question}

IMPORTANT: After your reasoning, you MUST output your final answer in this EXACT format:
[[ANSWER]]X[[/ANSWER]]

Where X is one of: A, B, C, or D.
For example, if you choose option B, write: [[ANSWER]]B[[/ANSWER]]"""

    content.append({
        "type": "text",
        "text": prompt_text
    })

    payload = {
        'model': model_name,
        'messages': [
            {
                'role': 'user',
                'content': content
            }
        ],
        'temperature': temperature,
        'max_tokens': max_tokens,
        'top_p': top_p
    }

    max_retries = 3
    timeout = 300  # 5分钟超时

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
            return content, token_info
        except Exception as e:
            if attempt < max_retries - 1:
                import time
                time.sleep(5)  # 重试前等待5秒
                continue
            return None, None


def evaluate_erqa(config: dict, dry_run: bool = False, log_file: str = "eval_erqa_progress.log") -> dict:
    """
    Main evaluation function for ERQA dataset.

    Args:
        config: Configuration dictionary from config.yaml
        dry_run: If True, use mock responses instead of API calls
        log_file: Progress log file path

    Returns:
        Evaluation results in the required JSON format
    """
    model_name = config['model']['name']
    dataset_path = config['datasets']['erqa_path']
    max_samples = config.get('evaluation', {}).get('erqa_samples', 400)

    # 初始化进度日志
    progress = ProgressLogger(log_file)

    # Load dataset
    df = load_erqa_dataset(dataset_path)
    if df is None:
        progress.log(f"ERROR: Failed to load ERQA dataset from {dataset_path}")
        return {
            "err_code": 1,
            "err_msg": f"Failed to load ERQA dataset from {dataset_path}",
            "eval_results": {}
        }

    # Limit samples if configured
    if max_samples and len(df) > max_samples:
        df = df.head(max_samples)

    # Initialize counters
    category_correct = defaultdict(int)
    category_total = defaultdict(int)
    total_correct = 0
    total_count = len(df)

    # Token statistics
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    progress.log("=" * 50)
    progress.log("ERQA Evaluation Started")
    progress.log(f"Model: {model_name}")
    progress.log(f"Total samples: {total_count}")
    progress.log("=" * 50)

    for idx, row in df.iterrows():
        question_id = row.get('question_id', idx)
        question = row.get('question', '')
        question_type = row.get('question_type', 'Other')
        expected_answer = row.get('answer', '').strip().upper()
        images = row.get('images', None)

        category_total[question_type] += 1

        if dry_run:
            model_response = f"[[ANSWER]]{expected_answer}[[/ANSWER]]"
            token_info = {'prompt_tokens': 500, 'completion_tokens': 10, 'total_tokens': 510}
        else:
            model_response, token_info = call_model_api(question, images, config)

        if model_response is None:
            progress.log(f"[{idx+1}/{total_count}] ID={question_id} [{question_type}]: API_ERROR")
            continue

        # Update token statistics
        if token_info:
            total_prompt_tokens += token_info.get('prompt_tokens', 0)
            total_completion_tokens += token_info.get('completion_tokens', 0)
            total_tokens += token_info.get('total_tokens', 0)

        predicted_answer = extract_choice_from_response(model_response)
        is_correct = (predicted_answer == expected_answer)

        if is_correct:
            total_correct += 1
            category_correct[question_type] += 1
            status = "CORRECT"
        else:
            status = "WRONG"

        progress.log(f"[{idx+1}/{total_count}] ID={question_id} [{question_type}]: {status} | Pred={predicted_answer} | Exp={expected_answer}")

    # Calculate accuracies
    overall_accuracy = (total_correct / total_count * 100) if total_count > 0 else 0.0

    # Calculate per-category accuracy
    category_accuracy = {}
    for cat in ERQA_CATEGORIES:
        if category_total[cat] > 0:
            category_accuracy[cat] = round(category_correct[cat] / category_total[cat] * 100, 2)
        else:
            category_accuracy[cat] = 0.0

    # Calculate average token statistics
    avg_prompt_tokens = total_prompt_tokens / total_count if total_count > 0 else 0.0
    avg_completion_tokens = total_completion_tokens / total_count if total_count > 0 else 0.0
    avg_tokens = total_tokens / total_count if total_count > 0 else 0.0

    # Log summary
    progress.log("=" * 50)
    progress.log(f"Evaluation Complete: {total_correct}/{total_count} = {overall_accuracy:.2f}%")
    progress.log("-" * 30)
    for cat in ERQA_CATEGORIES:
        if category_total[cat] > 0:
            progress.log(f"  {cat}: {category_accuracy[cat]:.2f}%")
    progress.log(f"Avg Tokens: {avg_tokens:.2f}")
    progress.log("=" * 50)

    # Build rawDetails in the exact required format
    raw_details = {
        "Other": category_accuracy.get("Other", 0.0),
        "Pointing": category_accuracy.get("Pointing", 0.0),
        "accuracy": round(overall_accuracy, 2),
        "Task Reasoning": category_accuracy.get("Task Reasoning", 0.0),
        "average_tokens": round(avg_tokens, 2),
        "Action Reasoning": category_accuracy.get("Action Reasoning", 0.0),
        "State Estimation": category_accuracy.get("State Estimation", 0.0),
        "Spatial Reasoning": category_accuracy.get("Spatial Reasoning", 0.0),
        "Multi-view Reasoning": category_accuracy.get("Multi-view Reasoning", 0.0),
        "Trajectory Reasoning": category_accuracy.get("Trajectory Reasoning", 0.0),
        "average_prompt_tokens": round(avg_prompt_tokens, 2),
        "average_completion_tokens": round(avg_completion_tokens, 2)
    }

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
                        "dataset": "ERQA",
                        "accuracy": round(overall_accuracy, 2),
                        "rawDetails": raw_details
                    }
                ]
            }
        }
    }

    return result


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='ERQA Dataset Evaluation Script')
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='Path to configuration file (default: config.yaml)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run in dry-run mode with mock responses')
    parser.add_argument('--output', type=str, default='erqa_result.json',
                        help='Output JSON file path (default: erqa_result.json)')
    parser.add_argument('--log', type=str, default='eval_erqa_progress.log',
                        help='Progress log file path (default: eval_erqa_progress.log)')
    args = parser.parse_args()

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
    result = evaluate_erqa(config, dry_run=args.dry_run, log_file=args.log)

    # Output result to JSON file
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == '__main__':
    main()
