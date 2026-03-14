#!/usr/bin/env python3
"""
共享工具库
提供日志、API 调用、答案提取、配置加载等通用功能。
"""

import json
import re
import os
import sys
import time
import base64
import io
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Union

import yaml
import requests


# ==============================================================================
# 配置加载
# ==============================================================================

def load_yaml(path: str) -> Optional[dict]:
    """加载 YAML 配置文件。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"[ERROR] Failed to load {path}: {e}", file=sys.stderr)
        return None


def load_config(config_path: str = "config.yaml") -> Optional[dict]:
    """加载主配置文件。"""
    return load_yaml(config_path)


def load_benchmark_registry(registry_path: str = "benchmark_registry.yaml") -> Optional[dict]:
    """加载 benchmark 注册表。"""
    return load_yaml(registry_path)


# ==============================================================================
# 日志
# ==============================================================================

class ProgressLogger:
    """进度日志器，支持实时写入文件和终端输出。"""

    def __init__(self, log_file: str, also_print: bool = True):
        self.log_file = log_file
        self.also_print = also_print
        os.makedirs(os.path.dirname(log_file) if os.path.dirname(log_file) else '.', exist_ok=True)
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write(f"[{self._ts()}] Log started\n")

    @staticmethod
    def _ts() -> str:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    def log(self, message: str):
        """写入日志并立即刷新。"""
        line = f"[{self._ts()}] {message}"
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
            f.flush()
        if self.also_print:
            print(line)

    def separator(self, char: str = "=", length: int = 60):
        self.log(char * length)

    def section(self, title: str):
        self.separator()
        self.log(title)
        self.separator()


# ==============================================================================
# API 调用
# ==============================================================================

def call_text_api(
    prompt: str,
    config: dict,
    system_prompt: Optional[str] = None,
) -> Tuple[Optional[str], Optional[Dict]]:
    """
    调用纯文本模型 API（OpenAI 兼容）。
    返回 (response_text, token_info)，失败返回 (None, None)。
    """
    api_base = config['model']['api_base']
    api_key = config['model'].get('api_key', 'EMPTY')
    model_name = config['model']['name']

    gen_cfg = config.get('generation_config', {})
    custom_cfg = config.get('custom_eval', {})

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': prompt})

    payload = {
        'model': model_name,
        'messages': messages,
        'temperature': gen_cfg.get('temperature', 0.0),
        'max_tokens': gen_cfg.get('max_tokens', 4096),
        'top_p': gen_cfg.get('top_p', 1.0),
        'n': gen_cfg.get('n', 1),
    }
    if 'top_k' in gen_cfg:
        payload['top_k'] = gen_cfg['top_k']

    max_retries = custom_cfg.get('max_retries', 3)
    retry_delay = custom_cfg.get('retry_delay', 5)
    timeout = custom_cfg.get('request_timeout', 300)

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()

            content = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            token_info = {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'total_tokens': usage.get('total_tokens', 0),
            }
            return content, token_info
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None, None


def call_multimodal_api(
    text: str,
    images: Optional[List] = None,
    config: dict = None,
    system_prompt: Optional[str] = None,
) -> Tuple[Optional[str], Optional[Dict]]:
    """
    调用多模态模型 API（OpenAI 兼容，支持图片）。
    images: list of bytes/PIL.Image/base64 str
    返回 (response_text, token_info)，失败返回 (None, None)。
    """
    api_base = config['model']['api_base']
    api_key = config['model'].get('api_key', 'EMPTY')
    model_name = config['model']['name']

    gen_cfg = config.get('generation_config', {})
    custom_cfg = config.get('custom_eval', {})

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    # 构建 multimodal content
    content = []
    if images:
        for img in images:
            img_b64 = encode_image_to_base64(img)
            if img_b64:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}
                })
    content.append({"type": "text", "text": text})

    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.append({'role': 'user', 'content': content})

    payload = {
        'model': model_name,
        'messages': messages,
        'temperature': gen_cfg.get('temperature', 0.0),
        'max_tokens': gen_cfg.get('max_tokens', 4096),
        'top_p': gen_cfg.get('top_p', 1.0),
        'n': gen_cfg.get('n', 1),
    }
    if 'top_k' in gen_cfg:
        payload['top_k'] = gen_cfg['top_k']

    max_retries = custom_cfg.get('max_retries', 3)
    retry_delay = custom_cfg.get('retry_delay', 5)
    timeout = custom_cfg.get('request_timeout', 300)

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            result = response.json()

            resp_content = result['choices'][0]['message']['content']
            usage = result.get('usage', {})
            token_info = {
                'prompt_tokens': usage.get('prompt_tokens', 0),
                'completion_tokens': usage.get('completion_tokens', 0),
                'total_tokens': usage.get('total_tokens', 0),
            }
            return resp_content, token_info
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None, None


def encode_image_to_base64(image_data) -> Optional[str]:
    """将图片数据编码为 base64 字符串。支持 bytes / PIL.Image / base64 str。"""
    if image_data is None:
        return None
    if isinstance(image_data, str):
        # 已经是 base64
        return image_data
    if isinstance(image_data, bytes):
        return base64.b64encode(image_data).decode('utf-8')
    if hasattr(image_data, 'tobytes'):
        # PIL Image
        buffer = io.BytesIO()
        image_data.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    return None


# ==============================================================================
# 答案提取
# ==============================================================================

def extract_numerical_answer(response: str) -> Optional[str]:
    """
    从模型响应中提取数值答案。
    优先匹配 [[ANSWER]]xxx[[/ANSWER]]，然后 \\boxed{}，最后取最后一个数字。
    """
    if not response:
        return None

    # [[ANSWER]]xxx[[/ANSWER]]
    pattern = r'\[\[ANSWER\]\]\s*([+-]?\d+(?:\.\d+)?)\s*\[\[/ANSWER\]\]'
    match = re.search(pattern, response)
    if match:
        return match.group(1).strip()

    # [[ANSWER]] 后跟数字
    pattern2 = r'\[\[ANSWER\]\]\s*([+-]?\d+(?:\.\d+)?)'
    match = re.search(pattern2, response)
    if match:
        return match.group(1).strip()

    # \boxed{xxx}
    boxed_matches = re.findall(r'\\boxed\{([^}]+)\}', response)
    if boxed_matches:
        return boxed_matches[-1].strip()

    # 最后一个数字
    numbers = re.findall(r'\b(\d+(?:\.\d+)?)\b', response)
    if numbers:
        return numbers[-1]

    return None


def extract_choice_answer(response: str, choices: str = "ABCD") -> Optional[str]:
    """
    从模型响应中提取选择题答案。
    优先匹配 [[ANSWER]]X[[/ANSWER]]，然后常见格式。
    """
    if not response:
        return None

    choice_pattern = f"[{choices}{choices.lower()}]"

    # [[ANSWER]]X[[/ANSWER]]
    pattern = rf'\[\[ANSWER\]\]\s*({choice_pattern})\s*\[\[/ANSWER\]\]'
    match = re.search(pattern, response)
    if match:
        return match.group(1).upper()

    # [[ANSWER]] + letter
    pattern2 = rf'\[\[ANSWER\]\]\s*({choice_pattern})'
    match = re.search(pattern2, response)
    if match:
        return match.group(1).upper()

    # "The answer is X"
    fallback_patterns = [
        rf'[Tt]he\s+(?:correct\s+)?answer\s+is[:\s]+({choice_pattern})',
        rf'[Aa]nswer[:\s]+({choice_pattern})',
        rf'\(({choice_pattern})\)',
    ]
    for pat in fallback_patterns:
        match = re.search(pat, response)
        if match:
            return match.group(1).upper()

    # 末尾字母
    tail = response[-100:] if len(response) > 100 else response
    letters = re.findall(rf'\b({choice_pattern})\b', tail)
    if letters:
        return letters[-1].upper()

    return None


def normalize_number(answer) -> Optional[float]:
    """将答案归一化为浮点数进行比较。"""
    if answer is None:
        return None
    try:
        if isinstance(answer, str):
            answer = answer.strip()
            answer = re.sub(r'[,\s\\]', '', answer)
        return float(answer)
    except (ValueError, TypeError):
        return None


def compare_numerical(predicted, expected, tolerance: float = 0.01) -> bool:
    """比较数值答案，支持容差。"""
    pred_val = normalize_number(predicted)
    exp_val = normalize_number(expected)
    if pred_val is None or exp_val is None:
        return str(predicted).strip() == str(expected).strip()
    return abs(pred_val - exp_val) <= tolerance


# ==============================================================================
# 结果格式
# ==============================================================================

def build_result(
    model_name: str,
    details: List[Dict],
    err_code: int = 0,
    err_msg: str = "Get Evaluations Details Sucess!",
) -> Dict:
    """构建标准化评测结果 JSON。"""
    return {
        "err_code": err_code,
        "err_msg": err_msg,
        "eval_results": {
            model_name: {
                "status": "S" if err_code == 0 else "F",
                "details": details,
            }
        }
    }


def build_detail(
    dataset: str,
    accuracy: float,
    raw_details: Optional[Dict] = None,
    status: str = "S",
) -> Dict:
    """构建单个 benchmark 评测结果详情。"""
    return {
        "status": status,
        "dataset": dataset,
        "accuracy": round(accuracy, 2),
        "rawDetails": raw_details or {},
    }


# ==============================================================================
# Prompt 模板
# ==============================================================================

MATH_PROMPT_TEMPLATE = """Please solve this math problem step by step.

Problem: {problem}

IMPORTANT: After your reasoning, you MUST output your final numerical answer in this EXACT format:
[[ANSWER]]your_numerical_answer[[/ANSWER]]

For example, if the answer is 42, write: [[ANSWER]]42[[/ANSWER]]
Only include the number, no units or explanations inside the answer tags."""

CHOICE_PROMPT_TEMPLATE = """{question}

IMPORTANT: After your reasoning, you MUST output your final answer in this EXACT format:
[[ANSWER]]X[[/ANSWER]]

Where X is one of: {choices}.
For example, if you choose option B, write: [[ANSWER]]B[[/ANSWER]]"""

MULTIMODAL_CHOICE_PROMPT_TEMPLATE = """{question}

IMPORTANT: After your reasoning, you MUST output your final answer in this EXACT format:
[[ANSWER]]X[[/ANSWER]]

Where X is one of: {choices}.
For example, if you choose option B, write: [[ANSWER]]B[[/ANSWER]]"""


# ==============================================================================
# 工具函数
# ==============================================================================

def ensure_dir(path: str):
    """确保目录存在。"""
    os.makedirs(path, exist_ok=True)


def save_json(data: Any, path: str):
    """保存 JSON 文件。"""
    ensure_dir(os.path.dirname(path) if os.path.dirname(path) else '.')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: str) -> Optional[Any]:
    """加载 JSON 文件。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_jsonl(path: str) -> List[dict]:
    """加载 JSONL 文件。"""
    data = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    data.append(json.loads(line))
    except FileNotFoundError:
        pass
    return data
