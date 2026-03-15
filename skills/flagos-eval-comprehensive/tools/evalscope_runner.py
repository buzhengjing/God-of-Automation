#!/usr/bin/env python3
"""
EvalScope 原生 Benchmark 执行器
封装 EvalScope TaskConfig 调用，统一执行原生支持的 benchmark。
"""

import os
import sys
import json
import traceback
from typing import Dict, List, Optional, Any

from utils import ProgressLogger, load_config, build_detail


def run_evalscope_benchmark(
    model_name: str,
    api_url: str,
    api_key: str,
    benchmark_name: str,
    benchmark_args: Dict,
    generation_config: Dict,
    evalscope_config: Dict,
    work_dir: str = "outputs/evalscope",
    limit: Optional[int] = None,
    dataset_filters: Optional[Dict] = None,
    logger: Optional[ProgressLogger] = None,
) -> Dict:
    """
    运行单个 EvalScope 原生 benchmark。

    Args:
        model_name: 模型名称
        api_url: OpenAI 兼容 API 地址
        api_key: API 密钥
        benchmark_name: benchmark 名称（如 mmlu, aime24, gpqa_diamond）
        benchmark_args: benchmark 特定参数（如 few_shot_num）
        generation_config: 生成配置
        evalscope_config: evalscope 框架配置
        work_dir: 输出目录
        limit: 样本数限制（调试用）
        dataset_filters: 数据集过滤配置（如 thinking 模型的 remove_until）
        logger: 日志器

    Returns:
        EvalScope 原始结果 dict，或错误信息 dict
    """
    try:
        from evalscope import TaskConfig, run_task
        from evalscope.constants import EvalType
    except ImportError:
        error_msg = "evalscope not installed. Run: pip install evalscope"
        if logger:
            logger.log(f"[ERROR] {error_msg}")
        return {"error": error_msg, "benchmark": benchmark_name}

    if logger:
        logger.log(f"[EvalScope] Starting {benchmark_name} ...")

    # 构建 dataset_args
    dataset_args = {benchmark_name: benchmark_args or {}}
    if dataset_filters:
        dataset_args[benchmark_name]['filters'] = dataset_filters

    # 构建 TaskConfig
    try:
        # 将 timeout/stream 迁移到 generation_config 内（避免 EvalScope v2.0 废弃警告）
        gen_config = dict(generation_config)
        if 'timeout' not in gen_config:
            gen_config['timeout'] = evalscope_config.get('timeout', 60000)
        if 'stream' not in gen_config:
            gen_config['stream'] = evalscope_config.get('stream', True)

        # Build TaskConfig kwargs
        task_kwargs = dict(
            model=model_name,
            api_url=api_url,
            api_key=api_key,
            eval_type=EvalType.OPENAI_API,
            datasets=[benchmark_name],
            dataset_args=dataset_args,
            eval_batch_size=evalscope_config.get('eval_batch_size', 64),
            generation_config=gen_config,
            dataset_hub=evalscope_config.get('dataset_hub', 'modelscope'),
            work_dir=work_dir,
        )

        # 支持本地预下载缓存目录，跳过在线下载
        dataset_dir = evalscope_config.get('dataset_dir')
        if dataset_dir:
            task_kwargs['dataset_dir'] = dataset_dir

        task_cfg = TaskConfig(**task_kwargs)

        if limit is not None:
            task_cfg.limit = limit

        result = run_task(task_cfg=task_cfg)

        if logger:
            logger.log(f"[EvalScope] {benchmark_name} completed successfully")

        return result

    except Exception as e:
        error_msg = f"EvalScope error on {benchmark_name}: {str(e)}"
        if logger:
            logger.log(f"[ERROR] {error_msg}")
            logger.log(traceback.format_exc())
        return {"error": error_msg, "benchmark": benchmark_name}


def run_batch_evalscope(
    benchmarks: List[Dict],
    config: dict,
    work_dir: str = "outputs/evalscope",
    limit: Optional[int] = None,
    logger: Optional[ProgressLogger] = None,
) -> List[Dict]:
    """
    批量运行多个 EvalScope 原生 benchmark。

    Args:
        benchmarks: benchmark 列表，每项包含 name, args, display_name
        config: 主配置
        work_dir: 输出目录
        limit: 样本数限制
        logger: 日志器

    Returns:
        结果列表
    """
    model_name = config['model']['name']
    api_url = config['model']['api_base']
    api_key = config['model'].get('api_key', 'EMPTY')
    generation_config = config.get('generation_config', {})
    evalscope_config = config.get('evalscope', {})
    dataset_filters = config.get('dataset_filters', None)

    results = []

    for bench in benchmarks:
        bench_name = bench['name']
        bench_args = bench.get('args', {})
        display_name = bench.get('display_name', bench_name)

        if logger:
            logger.separator("-", 40)
            logger.log(f"Running: {display_name} ({bench_name})")

        result = run_evalscope_benchmark(
            model_name=model_name,
            api_url=api_url,
            api_key=api_key,
            benchmark_name=bench_name,
            benchmark_args=bench_args,
            generation_config=generation_config,
            evalscope_config=evalscope_config,
            work_dir=os.path.join(work_dir, bench_name),
            limit=limit,
            dataset_filters=dataset_filters,
            logger=logger,
        )

        results.append({
            "benchmark": bench_name,
            "display_name": display_name,
            "runner": "evalscope",
            "result": result,
        })

    return results


def parse_evalscope_result(result: Dict, display_name: str) -> Optional[Dict]:
    """
    解析 EvalScope 返回的结果，转换为标准 detail 格式。

    run_task() 返回 {benchmark_name: Report_object}，其中 Report 是 evalscope
    的 dataclass，需要调用 .to_dict() 转为 dict 后才能 JSON 序列化和提取分数。

    Args:
        result: run_evalscope_benchmark 返回的原始结果
        display_name: 显示名称

    Returns:
        标准 detail dict 或 None
    """
    if "error" in result:
        return build_detail(
            dataset=display_name,
            accuracy=0.0,
            raw_details={"error": result["error"]},
            status="F",
        )

    try:
        # run_task returns {benchmark_name: Report_object}
        # Convert Report objects to dicts and extract score
        serializable_result = {}
        score = None
        for key, val in result.items():
            if hasattr(val, 'to_dict'):
                # Report object — convert to dict for serialization
                val_dict = val.to_dict()
                serializable_result[key] = val_dict
                if score is None and 'score' in val_dict:
                    score = val_dict['score']
            elif isinstance(val, dict):
                serializable_result[key] = val
                if score is None:
                    score = _extract_score(val)
            else:
                serializable_result[key] = val

        if score is not None:
            return build_detail(
                dataset=display_name,
                accuracy=score * 100 if score <= 1.0 else score,
                raw_details=serializable_result,
            )

        return build_detail(
            dataset=display_name,
            accuracy=0.0,
            raw_details=serializable_result,
            status="S",
        )
    except Exception:
        return build_detail(
            dataset=display_name,
            accuracy=0.0,
            raw_details={"parse_error": str(result)},
            status="F",
        )


def _extract_score(result: dict, depth: int = 0) -> Optional[float]:
    """递归从结果中提取分数。"""
    if depth > 5:
        return None

    # 直接有 score / accuracy / acc 字段
    for key in ('score', 'accuracy', 'acc', 'overall_score', 'weighted_avg'):
        if key in result:
            val = result[key]
            if isinstance(val, (int, float)):
                return float(val)

    # 在嵌套 dict 中查找
    for key, val in result.items():
        if isinstance(val, dict):
            score = _extract_score(val, depth + 1)
            if score is not None:
                return score

    return None


if __name__ == '__main__':
    # 简单测试入口
    import argparse
    parser = argparse.ArgumentParser(description='EvalScope Runner')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--benchmark', required=True, help='Benchmark name')
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger("eval_progress.log")
    result = run_evalscope_benchmark(
        model_name=config['model']['name'],
        api_url=config['model']['api_base'],
        api_key=config['model'].get('api_key', 'EMPTY'),
        benchmark_name=args.benchmark,
        benchmark_args={},
        generation_config=config.get('generation_config', {}),
        evalscope_config=config.get('evalscope', {}),
        limit=args.limit,
        logger=logger,
    )
    parsed = parse_evalscope_result(result, args.benchmark)
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
