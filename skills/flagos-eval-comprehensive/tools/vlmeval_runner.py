#!/usr/bin/env python3
"""
VLMEvalKit 后端 Benchmark 执行器
封装 VLMEvalKit 后端调用，支持 VL benchmark。
"""

import os
import sys
import json
import traceback
from typing import Dict, List, Optional

from utils import ProgressLogger, load_config, build_detail


def run_vlmeval_benchmark(
    model_name: str,
    model_path: str,
    datasets: List[str],
    work_dir: str = "outputs/vlmeval",
    limit: Optional[int] = None,
    judge_model_url: Optional[str] = None,
    judge_model_name: Optional[str] = None,
    nproc: int = 1,
    logger: Optional[ProgressLogger] = None,
) -> Dict:
    """
    通过 VLMEvalKit 后端运行 VL benchmark。

    Args:
        model_name: VLMEvalKit 中的模型名称
        model_path: 模型路径
        datasets: 数据集列表
        work_dir: 输出目录
        limit: 样本数限制
        judge_model_url: Judge 模型 API 地址
        judge_model_name: Judge 模型名称
        nproc: 并行进程数
        logger: 日志器

    Returns:
        结果 dict
    """
    try:
        from evalscope.run import run_task
    except ImportError:
        error_msg = "evalscope not installed. Run: pip install evalscope[vlmeval]"
        if logger:
            logger.log(f"[ERROR] {error_msg}")
        return {"error": error_msg}

    if logger:
        logger.log(f"[VLMEvalKit] Starting {datasets} ...")

    task_cfg = {
        'eval_backend': 'VLMEvalKit',
        'eval_config': {
            'model': [{
                'name': model_name,
                'model_path': model_path,
            }],
            'data': datasets,
            'mode': 'all',
            'work_dir': work_dir,
            'nproc': nproc,
            'reuse': True,
        }
    }

    if limit is not None:
        task_cfg['eval_config']['limit'] = limit

    if judge_model_url:
        task_cfg['eval_config']['OPENAI_API_KEY'] = 'EMPTY'
        task_cfg['eval_config']['OPENAI_API_BASE'] = judge_model_url
        if judge_model_name:
            task_cfg['eval_config']['LOCAL_LLM'] = judge_model_name

    try:
        result = run_task(task_cfg)
        if logger:
            logger.log(f"[VLMEvalKit] {datasets} completed successfully")
        return result
    except Exception as e:
        error_msg = f"VLMEvalKit error: {str(e)}"
        if logger:
            logger.log(f"[ERROR] {error_msg}")
            logger.log(traceback.format_exc())
        return {"error": error_msg}


def run_vlmeval_via_api(
    model_name: str,
    api_url: str,
    api_key: str,
    datasets: List[str],
    work_dir: str = "outputs/vlmeval",
    limit: Optional[int] = None,
    logger: Optional[ProgressLogger] = None,
) -> Dict:
    """
    通过 OpenAI 兼容 API 使用 VLMEvalKit 后端（适用于已部署的 VL 模型服务）。

    注意：VLMEvalKit 通常需要本地模型加载，API 方式需通过 evalscope 原生后端处理。
    此函数作为 fallback，当 VLMEvalKit 直接调用不可用时。
    """
    if logger:
        logger.log(f"[VLMEvalKit-API] Note: VLMEvalKit typically requires local model. "
                    f"Falling back to evalscope native for {datasets}")

    # 对于通过 API 部署的 VL 模型，使用 evalscope 原生后端
    from evalscope_runner import run_batch_evalscope

    benchmarks = [{"name": ds, "display_name": ds, "args": {"few_shot_num": 0}} for ds in datasets]
    config = {
        "model": {"name": model_name, "api_base": api_url, "api_key": api_key},
        "generation_config": {"max_tokens": 4096, "temperature": 0.0},
        "evalscope": {"eval_batch_size": 16, "stream": True, "timeout": 60000},
    }

    return run_batch_evalscope(benchmarks, config, work_dir, limit, logger)


def parse_vlmeval_result(result: Dict, display_name: str) -> Optional[Dict]:
    """解析 VLMEvalKit 返回的结果。"""
    if "error" in result:
        return build_detail(
            dataset=display_name,
            accuracy=0.0,
            raw_details={"error": result["error"]},
            status="F",
        )

    try:
        score = _extract_vlm_score(result)
        if score is not None:
            return build_detail(
                dataset=display_name,
                accuracy=score * 100 if score <= 1.0 else score,
                raw_details=result,
            )
        return build_detail(
            dataset=display_name,
            accuracy=0.0,
            raw_details=result,
            status="S",
        )
    except Exception:
        return build_detail(
            dataset=display_name,
            accuracy=0.0,
            raw_details={"parse_error": str(result)},
            status="F",
        )


def _extract_vlm_score(result: dict) -> Optional[float]:
    """从 VLMEvalKit 结果中提取分数。"""
    for key in ('score', 'accuracy', 'acc', 'overall'):
        if key in result:
            val = result[key]
            if isinstance(val, (int, float)):
                return float(val)
    for val in result.values():
        if isinstance(val, dict):
            score = _extract_vlm_score(val)
            if score is not None:
                return score
    return None


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='VLMEvalKit Runner')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--datasets', required=True, help='Comma-separated dataset names')
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger("eval_progress.log")
    datasets = [d.strip() for d in args.datasets.split(',')]

    result = run_vlmeval_via_api(
        model_name=config['model']['name'],
        api_url=config['model']['api_base'],
        api_key=config['model'].get('api_key', 'EMPTY'),
        datasets=datasets,
        limit=args.limit,
        logger=logger,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
