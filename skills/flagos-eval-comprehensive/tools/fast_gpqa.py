#!/usr/bin/env python3
"""
GPQA Diamond 快速精度评测脚本

自动适配所有模型（thinking/non-thinking），自动探测吞吐选并发，一条命令跑完。

用法:
  python fast_gpqa.py --config config.yaml
  python fast_gpqa.py --model-name Qwen3-8B --api-base http://localhost:8000/v1
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Dict, Optional, Tuple

import requests
import yaml


# =============================================================================
# Thinking 模型检测
# =============================================================================

THINKING_PATTERNS = ['qwen3', 'qwq', 'deepseek-r1', 'deepseek-r2']


def detect_thinking(model_name: str) -> bool:
    """根据模型名自动检测是否为 thinking model。"""
    name_lower = model_name.lower()
    return any(p in name_lower for p in THINKING_PATTERNS)


# =============================================================================
# 模型服务查询
# =============================================================================

def query_model_max_len(api_base: str, api_key: str, model_name: str) -> Optional[int]:
    """查询 /v1/models 获取模型的 max_model_len。"""
    try:
        base = api_base.rstrip('/')
        if base.endswith('/v1'):
            base = base[:-3]
        url = f"{base}/v1/models"

        headers = {}
        if api_key and api_key != 'EMPTY':
            headers['Authorization'] = f'Bearer {api_key}'

        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        for m in data.get('data', []):
            if m.get('id') == model_name:
                val = m.get('max_model_len')
                if val is not None:
                    return int(val)

        # 只有一个模型时直接取
        models = data.get('data', [])
        if len(models) == 1:
            val = models[0].get('max_model_len')
            if val is not None:
                return int(val)
    except Exception as e:
        print(f"[WARN] 查询模型 max_model_len 失败: {e}")

    return None


def auto_max_tokens(api_base: str, api_key: str, model_name: str, is_thinking: bool = False) -> Tuple[int, Optional[int]]:
    """
    自动计算 max_tokens，基于服务端实际 max_model_len。

    thinking 模型：max_model_len - 8192，下限 8192，不设上限 cap
    标准模型：max_model_len - 8192，clamp 到 [4096, 32768]

    Returns:
        (max_tokens, max_model_len or None)
    """
    max_model_len = query_model_max_len(api_base, api_key, model_name)
    if max_model_len:
        tokens = max_model_len - 8192  # 预留 8K 给 prompt
        if is_thinking:
            tokens = max(tokens, 8192)
        else:
            tokens = max(tokens, 4096)
            tokens = min(tokens, 32768)
        return tokens, max_model_len
    # fallback
    return (16384 if is_thinking else 8192), None


# =============================================================================
# 截断检测
# =============================================================================

GPQA_SAMPLE_QUESTION = (
    "What is the probability that a randomly chosen integer between 1 and 100 "
    "is divisible by both 3 and 7? Show your reasoning step by step."
)


def check_truncation(
    api_base: str,
    api_key: str,
    model_name: str,
    max_tokens: int,
    max_model_len: Optional[int],
) -> Tuple[bool, int]:
    """
    发一条样题检查 finish_reason 是否为 length（截断）。

    如果截断，自动将 max_tokens 翻倍（在 max_model_len 允许范围内）。

    Returns:
        (truncation_detected, adjusted_max_tokens)
    """
    base = api_base.rstrip('/')
    if not base.endswith('/v1'):
        base = base + '/v1'
    url = f"{base}/chat/completions"

    headers = {'Content-Type': 'application/json'}
    if api_key and api_key != 'EMPTY':
        headers['Authorization'] = f'Bearer {api_key}'

    payload = {
        'model': model_name,
        'messages': [{'role': 'user', 'content': GPQA_SAMPLE_QUESTION}],
        'max_tokens': max_tokens,
        'temperature': 0.0,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        choices = data.get('choices', [])
        if choices:
            finish_reason = choices[0].get('finish_reason', '')
            if finish_reason == 'length':
                print(f"[WARN] 截断检测: finish_reason=length, max_tokens={max_tokens} 不足")
                # 尝试翻倍
                new_tokens = max_tokens * 2
                if max_model_len:
                    cap = max_model_len - 2048  # 留 2K 给 prompt
                    new_tokens = min(new_tokens, cap)
                new_tokens = max(new_tokens, max_tokens)  # 至少不降
                if new_tokens > max_tokens:
                    print(f"[WARN] 自动调整 max_tokens: {max_tokens} → {new_tokens}")
                return True, new_tokens
            else:
                print(f"[OK] 截断检测通过: finish_reason={finish_reason}")
    except Exception as e:
        print(f"[WARN] 截断检测请求失败: {e}")

    return False, max_tokens


# =============================================================================
# 探测吞吐 & 选并发
# =============================================================================

def _sanitize_model_id(model_name: str) -> str:
    """将模型名清理为安全的 model_id（不含 / 等特殊字符）。"""
    return model_name.strip('/').split('/')[-1] or model_name


def _preload_dataset(dataset_hub: str, dataset_dir: Optional[str] = None):
    """预加载 gpqa_diamond 数据集到缓存，确保探测阶段计时不含下载时间。"""
    try:
        if dataset_dir:
            # 检查本地缓存是否存在
            import glob as glob_mod
            if glob_mod.glob(os.path.join(dataset_dir, '**', 'gpqa*'), recursive=True):
                return
        if dataset_hub == 'modelscope':
            from modelscope import MsDataset
            MsDataset.load('AI-ModelScope/gpqa_diamond', split='train', trust_remote_code=True)
        else:
            import datasets as hf_datasets
            hf_datasets.load_dataset('Idavidrein/gpqa', name='gpqa_diamond', split='train', trust_remote_code=True)
    except Exception:
        pass  # 预加载失败不影响后续，evalscope 会自行下载


def probe_throughput(
    model_name: str,
    api_url: str,
    api_key: str,
    generation_config: Dict,
    dataset_args: Dict,
    evalscope_config: Dict,
) -> Tuple[int, float]:
    """
    用 limit=1 跑 1 题 GPQA Diamond，测量单条推理耗时，自动选并发。

    Returns:
        (eval_batch_size, probe_elapsed_seconds)
    """
    from evalscope import TaskConfig, run_task
    from evalscope.constants import EvalType

    # 先预加载数据集，排除下载时间对探测的影响
    print("[PROBE] 预加载数据集 ...")
    _preload_dataset(
        evalscope_config.get('dataset_hub', 'modelscope'),
        evalscope_config.get('dataset_dir'),
    )

    model_id = _sanitize_model_id(model_name)
    probe_work_dir = 'outputs/gpqa_diamond_probe'

    task_kwargs = dict(
        model=model_name,
        model_id=model_id,
        api_url=api_url,
        api_key=api_key,
        eval_type=EvalType.OPENAI_API,
        datasets=['gpqa_diamond'],
        dataset_args=dataset_args,
        eval_batch_size=1,
        generation_config=generation_config,
        dataset_hub=evalscope_config.get('dataset_hub', 'modelscope'),
        work_dir=probe_work_dir,
        no_timestamp=True,
    )
    dataset_dir = evalscope_config.get('dataset_dir')
    if dataset_dir:
        task_kwargs['dataset_dir'] = dataset_dir

    task_cfg = TaskConfig(**task_kwargs)
    task_cfg.limit = 1

    print("[PROBE] 探测阶段: 跑 1 题测量吞吐 ...")
    start = time.time()
    try:
        run_task(task_cfg=task_cfg)
    except Exception as e:
        print(f"[PROBE] 探测失败: {e}")
        print("[PROBE] 使用默认并发 16")
        return 16, 0.0

    elapsed = round(time.time() - start, 2)
    batch_size = 32 if elapsed <= 5 else 16
    print(f"[PROBE] 单条推理耗时: {elapsed}s → 选择并发: {batch_size}")
    return batch_size, elapsed


# =============================================================================
# 结果解析
# =============================================================================

def parse_result(result: Dict) -> Tuple[Optional[float], Dict]:
    """
    解析 EvalScope run_task 返回的结果。

    Returns:
        (score_percentage, raw_details)
    """
    if not result or 'error' in result:
        return None, result or {}

    for key, val in result.items():
        # Report 对象 → 转 dict
        if hasattr(val, 'to_dict'):
            val_dict = val.to_dict()
            score = val_dict.get('score')
            if score is not None:
                pct = score * 100 if score <= 1.0 else score
                return round(pct, 2), val_dict

        if isinstance(val, dict):
            score = _find_score(val)
            if score is not None:
                pct = score * 100 if score <= 1.0 else score
                return round(pct, 2), val

    return None, dict(result)


def _find_score(d: dict, depth: int = 0) -> Optional[float]:
    """递归查找 score/accuracy 字段。"""
    if depth > 3:
        return None
    for key in ('score', 'accuracy', 'acc', 'mean_acc'):
        if key in d and isinstance(d[key], (int, float)):
            return float(d[key])
    for val in d.values():
        if isinstance(val, dict):
            s = _find_score(val, depth + 1)
            if s is not None:
                return s
    return None


# =============================================================================
# 主流程
# =============================================================================

def run_fast_gpqa(
    model_name: str,
    api_base: str,
    api_key: str = 'EMPTY',
    dataset_dir: Optional[str] = None,
    dataset_hub: str = 'modelscope',
) -> Dict:
    """
    GPQA Diamond 快速评测主流程。

    Returns:
        结果 dict
    """
    from evalscope import TaskConfig, run_task
    from evalscope.constants import EvalType

    total_start = time.time()

    print("=" * 60)
    print("  GPQA Diamond 快速精度评测")
    print("=" * 60)
    print(f"  模型: {model_name}")
    print(f"  API:  {api_base}")

    # Step 1: 检测 thinking 模型
    is_thinking = detect_thinking(model_name)
    mode_str = "thinking" if is_thinking else "standard"
    print(f"  模式: {mode_str}")

    # Step 2: 自动设 max_tokens（基于 max_model_len 动态计算）
    max_tokens, max_model_len = auto_max_tokens(api_base, api_key, model_name, is_thinking)
    if max_model_len:
        print(f"  max_model_len: {max_model_len} (从服务端获取)")
    else:
        print(f"  max_model_len: 未知 (使用 fallback)")
    print(f"  max_tokens: {max_tokens}")

    # Step 3: 截断检测 — 发样题检查 finish_reason
    truncation_detected, max_tokens = check_truncation(
        api_base, api_key, model_name, max_tokens, max_model_len,
    )

    # Step 4: 构建 generation_config
    if is_thinking:
        gen_config = {
            'max_tokens': max_tokens,
            'temperature': 0.6,
            'top_p': 0.95,
            'stream': True,
            'timeout': 120000,
            'n': 1,
        }
    else:
        gen_config = {
            'max_tokens': max_tokens,
            'temperature': 0.0,
            'top_p': 1.0,
            'stream': True,
            'timeout': 120000,
            'n': 1,
        }

    # Step 5: 构建 dataset_args
    dataset_args = {'gpqa_diamond': {'few_shot_num': 0}}
    if is_thinking:
        dataset_args['gpqa_diamond']['filters'] = {'remove_until': '</think>'}

    evalscope_config = {
        'dataset_hub': dataset_hub,
    }
    if dataset_dir:
        evalscope_config['dataset_dir'] = dataset_dir

    # Step 6: 探测吞吐，选并发
    batch_size, probe_time = probe_throughput(
        model_name=model_name,
        api_url=api_base,
        api_key=api_key,
        generation_config=gen_config,
        dataset_args=dataset_args,
        evalscope_config=evalscope_config,
    )

    # Step 7: 正式评测
    print("-" * 60)
    print(f"[EVAL] 正式评测: gpqa_diamond (198题, 并发={batch_size})")
    print("-" * 60)

    model_id = _sanitize_model_id(model_name)
    work_dir = f'outputs/gpqa_diamond/{datetime.now().strftime("%Y%m%d_%H%M%S")}'

    task_kwargs = dict(
        model=model_name,
        model_id=model_id,
        api_url=api_base,
        api_key=api_key,
        eval_type=EvalType.OPENAI_API,
        datasets=['gpqa_diamond'],
        dataset_args=dataset_args,
        eval_batch_size=batch_size,
        generation_config=gen_config,
        dataset_hub=dataset_hub,
        work_dir=work_dir,
        no_timestamp=True,
    )
    if dataset_dir:
        task_kwargs['dataset_dir'] = dataset_dir

    task_cfg = TaskConfig(**task_kwargs)

    try:
        result = run_task(task_cfg=task_cfg)
    except Exception as e:
        print(f"[ERROR] 评测失败: {e}")
        traceback.print_exc()
        return {'error': str(e)}

    # Step 8: 解析结果
    score, raw_details = parse_result(result)
    total_elapsed = round(time.time() - total_start, 2)
    minutes = int(total_elapsed // 60)
    seconds = round(total_elapsed % 60, 1)

    # Step 9: 输出报告
    report = {
        'model': model_name,
        'benchmark': 'gpqa_diamond',
        'mode': mode_str,
        'score': score,
        'total_questions': 198,
        'eval_batch_size': batch_size,
        'max_tokens': max_tokens,
        'max_model_len': max_model_len,
        'truncation_detected': truncation_detected,
        'temperature': gen_config['temperature'],
        'probe_time_seconds': probe_time,
        'total_duration_seconds': total_elapsed,
        'timestamp': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'work_dir': work_dir,
    }

    # 写 JSON 报告
    os.makedirs('.', exist_ok=True)
    report_path = 'gpqa_result.json'
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # 终端打印
    print()
    print("=" * 60)
    print("  GPQA Diamond 快速评测结果")
    print("=" * 60)
    print(f"  模型:     {model_name}")
    print(f"  模式:     {mode_str} (temperature={gen_config['temperature']}, max_tokens={max_tokens})")
    print(f"  并发:     {batch_size}")
    print(f"  题数:     198")
    if score is not None:
        print(f"  得分:     {score:.2f}%")
    else:
        print(f"  得分:     解析失败 (查看 {work_dir} 原始输出)")
    print(f"  耗时:     {minutes}m {seconds}s")
    print(f"  报告:     {report_path}")
    print("=" * 60)

    return report


# =============================================================================
# CLI 入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='GPQA Diamond 快速精度评测',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python fast_gpqa.py --config config.yaml
  python fast_gpqa.py --model-name Qwen3-8B --api-base http://localhost:8000/v1
        """,
    )
    parser.add_argument('--config', type=str, default=None,
                        help='配置文件路径')
    parser.add_argument('--model-name', type=str, default=None,
                        help='模型名称 (覆盖 config)')
    parser.add_argument('--api-base', type=str, default=None,
                        help='API 地址 (覆盖 config)')
    parser.add_argument('--api-key', type=str, default=None,
                        help='API 密钥 (覆盖 config)')
    parser.add_argument('--dataset-dir', type=str, default=None,
                        help='数据集缓存目录 (覆盖 config)')
    args = parser.parse_args()

    # 加载配置
    config = {}
    if args.config:
        try:
            with open(args.config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[ERROR] 加载配置失败: {e}")
            sys.exit(1)

    model_cfg = config.get('model', {})

    # CLI 参数优先级 > config
    model_name = args.model_name or model_cfg.get('name', '')
    api_base = args.api_base or model_cfg.get('api_base', '')
    api_key = args.api_key or model_cfg.get('api_key', 'EMPTY')
    dataset_dir = args.dataset_dir or config.get('dataset_dir', '') or None
    dataset_hub = config.get('dataset_hub', 'modelscope')

    if not model_name:
        print("[ERROR] 必须指定模型名称: --model-name 或 config.yaml 中 model.name")
        sys.exit(1)
    if not api_base:
        print("[ERROR] 必须指定 API 地址: --api-base 或 config.yaml 中 model.api_base")
        sys.exit(1)

    # 验证 API 可达
    try:
        base = api_base.rstrip('/')
        if base.endswith('/v1'):
            base = base[:-3]
        resp = requests.get(f"{base}/v1/models", timeout=10)
        resp.raise_for_status()
        print(f"[OK] API 连通性检查通过")
    except Exception as e:
        print(f"[ERROR] API 不可达 ({api_base}): {e}")
        sys.exit(1)

    # 检查 evalscope
    try:
        import evalscope
        print(f"[OK] evalscope {getattr(evalscope, '__version__', 'unknown')} 已安装")
    except ImportError:
        print("[ERROR] evalscope 未安装，请执行: pip install evalscope")
        sys.exit(1)

    # 运行
    report = run_fast_gpqa(
        model_name=model_name,
        api_base=api_base,
        api_key=api_key,
        dataset_dir=dataset_dir,
        dataset_hub=dataset_hub,
    )

    sys.exit(0 if report.get('score') is not None else 1)


if __name__ == '__main__':
    main()
