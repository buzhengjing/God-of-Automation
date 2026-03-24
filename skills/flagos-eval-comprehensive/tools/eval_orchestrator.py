#!/usr/bin/env python3
"""
评测主编排器
根据模型类型自动选择 benchmark、调度执行、收集结果、生成报告。

用法:
  python eval_orchestrator.py --config config.yaml
  python eval_orchestrator.py --config config.yaml --quick
  python eval_orchestrator.py --config config.yaml --benchmarks mmlu,aime24
  python eval_orchestrator.py --config config.yaml --skip-custom --skip-optional
  python eval_orchestrator.py --config config.yaml --dry-run
"""

import argparse
import json
import os
import sys
import subprocess
import time
import traceback
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils import (
    ProgressLogger, load_config, load_benchmark_registry,
    build_detail, save_json, load_json, ensure_dir,
)


# Thinking model 自动检测关键词
THINKING_MODEL_PATTERNS = [
    'qwen3', 'qwq', 'deepseek-r1', 'deepseek-r2',
]


def is_thinking_model(model_name: str) -> bool:
    """根据模型名称自动检测是否为 thinking model。"""
    name_lower = model_name.lower()
    return any(pattern in name_lower for pattern in THINKING_MODEL_PATTERNS)


def detect_thinking_model(config: dict, logger: Optional[ProgressLogger] = None) -> bool:
    """
    检测模型是否为 thinking model，仅做检测不修改 config。
    优先级: model.thinking 显式设置 > 自动检测模型名。
    """
    model_cfg = config.get('model', {})
    model_name = model_cfg.get('name', '')
    thinking_explicit = model_cfg.get('thinking', None)

    if thinking_explicit is True:
        result = True
    elif thinking_explicit is False:
        result = False
    else:
        result = is_thinking_model(model_name)

    if logger:
        if result:
            logger.log(f"[Thinking Model] Detected thinking model: {model_name}")
            logger.log(f"[Thinking Model] Per-benchmark thinking config will be applied")
        else:
            logger.log(f"[Model] Standard (non-thinking) model: {model_name}")

    return result


def get_benchmark_config(
    bench: Dict,
    config: dict,
    model_is_thinking: bool,
) -> Tuple[Dict, Optional[Dict]]:
    """
    根据 benchmark 的 thinking 字段和模型是否为 thinking model，
    返回该 benchmark 应使用的 (generation_config, dataset_filters)。

    逻辑:
    - 模型是 thinking + benchmark.thinking=true → 使用 thinking_generation_config + dataset_filters
    - 其它情况 → 使用标准 generation_config，无 dataset_filters

    Args:
        bench: benchmark 注册表条目（含 thinking 字段）
        config: 主配置
        model_is_thinking: 模型是否为 thinking model

    Returns:
        (generation_config, dataset_filters)
    """
    bench_wants_thinking = bench.get('thinking', False)
    use_thinking = model_is_thinking and bench_wants_thinking

    if use_thinking:
        # 优先用 thinking_generation_config，fallback 到默认值
        thinking_gen = config.get('thinking_generation_config')
        if thinking_gen:
            gen_config = dict(thinking_gen)
        else:
            gen_config = {
                'max_tokens': 30000,
                'temperature': 0.6,
                'top_p': 0.95,
                'top_k': 20,
                'n': 1,
            }
        # 启用 dataset_filters
        ds_filters = config.get('dataset_filters') or {'remove_until': '</think>'}
        if 'remove_until' not in ds_filters:
            ds_filters['remove_until'] = '</think>'
        return gen_config, ds_filters
    else:
        return dict(config.get('generation_config', {})), None


def resolve_benchmarks(
    model_type: str,
    registry: dict,
    skip_custom: bool = False,
    skip_optional: bool = False,
    only_benchmarks: Optional[List[str]] = None,
) -> List[Dict]:
    """
    根据模型类型和选项，从注册表中解析出需要运行的 benchmark 列表。

    Args:
        model_type: 模型类型 (LLM/VL/Omni/Robotics/ImageGen)
        registry: benchmark 注册表
        skip_custom: 跳过自研 benchmark
        skip_optional: 跳过可选 benchmark
        only_benchmarks: 仅运行指定的 benchmark（名称列表）

    Returns:
        benchmark 列表
    """
    type_cfg = registry.get(model_type, {})
    benchmarks = []

    # 处理继承（Omni = LLM + VL）
    inherit_types = type_cfg.get('inherit', [])
    if inherit_types:
        for parent_type in inherit_types:
            parent_cfg = registry.get(parent_type, {})
            benchmarks.extend(parent_cfg.get('required', []))
            if not skip_optional:
                benchmarks.extend(parent_cfg.get('optional', []))

    # 自身的 benchmark
    benchmarks.extend(type_cfg.get('required', []))
    if not skip_optional:
        benchmarks.extend(type_cfg.get('optional', []))

    # 过滤自研
    if skip_custom:
        benchmarks = [b for b in benchmarks if b.get('runner') != 'custom']

    # 过滤指定 benchmark
    if only_benchmarks:
        benchmarks = [b for b in benchmarks if b['name'] in only_benchmarks]

    # 去重（按 name）
    seen = set()
    unique = []
    for b in benchmarks:
        if b['name'] not in seen:
            seen.add(b['name'])
            unique.append(b)

    return unique


def run_single_benchmark(
    bench: Dict,
    config: dict,
    work_dir: str,
    limit: Optional[int],
    logger: ProgressLogger,
    model_is_thinking: bool = False,
) -> Dict:
    """
    运行单个 benchmark。

    Args:
        bench: benchmark 注册表条目
        config: 主配置
        work_dir: 输出目录
        limit: 样本数限制
        logger: 日志器
        model_is_thinking: 模型是否为 thinking model

    Returns:
        {"benchmark": str, "display_name": str, "runner": str, "detail": dict}
    """
    bench_name = bench['name']
    display_name = bench.get('display_name', bench_name)
    runner = bench.get('runner', 'evalscope')
    bench_args = bench.get('args', {})

    # 按 benchmark 粒度选择 generation_config 和 dataset_filters
    bench_gen_config, bench_ds_filters = get_benchmark_config(bench, config, model_is_thinking)
    use_thinking = model_is_thinking and bench.get('thinking', False)

    logger.separator("-", 50)
    logger.log(f">>> Running: {display_name} (runner={runner}, thinking={'ON' if use_thinking else 'OFF'})")

    start = time.time()
    try:
        if runner == 'evalscope':
            detail = _run_evalscope(bench_name, bench_args, display_name, config,
                                    work_dir, limit, logger,
                                    generation_config=bench_gen_config,
                                    dataset_filters=bench_ds_filters)
        elif runner == 'vlmeval':
            detail = _run_vlmeval(bench_name, bench_args, display_name, config, work_dir, limit, logger)
        elif runner == 'custom':
            script = bench.get('script', '')
            detail = _run_custom(bench_name, bench_args, script, display_name, config, work_dir, limit, logger)
        else:
            detail = build_detail(display_name, 0.0, {"error": f"Unknown runner: {runner}"}, "F")

        elapsed = round(time.time() - start, 2)

        # 将耗时注入 detail
        if isinstance(detail, list):
            for d in detail:
                d['duration_seconds'] = elapsed
        else:
            detail['duration_seconds'] = elapsed

        logger.log(f"<<< {display_name}: accuracy={detail.get('accuracy', 'N/A')}, status={detail.get('status', 'N/A')}, duration={elapsed}s")

    except Exception as e:
        elapsed = round(time.time() - start, 2)
        logger.log(f"[ERROR] {display_name} failed: {str(e)}")
        logger.log(traceback.format_exc())
        detail = build_detail(display_name, 0.0, {"error": str(e)}, "F")
        detail['duration_seconds'] = elapsed

    return {
        "benchmark": bench_name,
        "display_name": display_name,
        "runner": runner,
        "detail": detail,
    }


def _run_evalscope(
    bench_name: str, bench_args: dict, display_name: str,
    config: dict, work_dir: str, limit: Optional[int],
    logger: ProgressLogger,
    generation_config: Optional[Dict] = None,
    dataset_filters: Optional[Dict] = None,
) -> Dict:
    """通过 EvalScope 执行器运行 benchmark。"""
    from evalscope_runner import run_evalscope_benchmark, parse_evalscope_result

    # 使用传入的 per-benchmark 配置，fallback 到全局配置
    gen_config = generation_config or config.get('generation_config', {})
    ds_filters = dataset_filters  # None 表示不过滤

    result = run_evalscope_benchmark(
        model_name=config['model']['name'],
        api_url=config['model']['api_base'],
        api_key=config['model'].get('api_key', 'EMPTY'),
        benchmark_name=bench_name,
        benchmark_args=bench_args,
        generation_config=gen_config,
        evalscope_config=config.get('evalscope', {}),
        work_dir=os.path.join(work_dir, 'evalscope', bench_name),
        limit=limit,
        dataset_filters=ds_filters,
        logger=logger,
    )

    return parse_evalscope_result(result, display_name)


def _run_vlmeval(
    bench_name: str, bench_args: dict, display_name: str,
    config: dict, work_dir: str, limit: Optional[int],
    logger: ProgressLogger,
) -> Dict:
    """通过 VLMEvalKit 执行器运行 benchmark。"""
    from vlmeval_runner import run_vlmeval_via_api, parse_vlmeval_result

    result = run_vlmeval_via_api(
        model_name=config['model']['name'],
        api_url=config['model']['api_base'],
        api_key=config['model'].get('api_key', 'EMPTY'),
        datasets=[bench_name],
        work_dir=os.path.join(work_dir, 'vlmeval', bench_name),
        limit=limit,
        logger=logger,
    )

    return parse_vlmeval_result(result, display_name)


def _run_custom(
    bench_name: str, bench_args: dict, script: str, display_name: str,
    config: dict, work_dir: str, limit: Optional[int],
    logger: ProgressLogger,
) -> Dict:
    """运行自研评测脚本。"""
    if not script:
        return build_detail(display_name, 0.0, {"error": "No script specified"}, "F")

    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)
    if not os.path.exists(script_path):
        return build_detail(display_name, 0.0, {"error": f"Script not found: {script_path}"}, "F")

    # 动态导入并调用对应的评测函数
    # 根据脚本名称确定调用方式
    module_name = os.path.basename(script).replace('.py', '')

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 约定：每个自研脚本导出一个 evaluate_xxx 函数
        # 函数签名: (config, dataset_path=..., limit=..., logger=...) -> detail dict
        eval_funcs = [name for name in dir(module) if name.startswith('evaluate_')]
        if not eval_funcs:
            return build_detail(display_name, 0.0, {"error": f"No evaluate_* function in {script}"}, "F")

        eval_func = getattr(module, eval_funcs[0])

        # 构建参数
        kwargs = {'config': config, 'logger': logger}
        if limit is not None:
            kwargs['limit'] = limit

        # 特殊处理：robotics benchmark 需要 benchmark 参数
        if 'benchmark' in bench_args:
            kwargs['benchmark'] = bench_args['benchmark']
            # 从 config 中获取数据集路径
            robotics_datasets = config.get('robotics_datasets', {})
            path_key = f"{bench_args['benchmark']}_path"
            if path_key in robotics_datasets:
                kwargs['dataset_path'] = robotics_datasets[path_key]

        result = eval_func(**kwargs)

        # 结果可能是 detail dict 或 list of detail dicts
        if isinstance(result, list):
            # 多个 benchmark 结果（如 evaluate_all_robotics）
            return result
        return result

    except Exception as e:
        logger.log(f"[ERROR] Custom script {script} failed: {str(e)}")
        logger.log(traceback.format_exc())
        return build_detail(display_name, 0.0, {"error": str(e)}, "F")


def run_orchestrator(
    config: dict,
    registry: dict,
    skip_custom: bool = False,
    skip_optional: bool = False,
    only_benchmarks: Optional[List[str]] = None,
    parallel: int = 1,
    limit: Optional[int] = None,
    dry_run: bool = False,
    preflight: bool = False,
    quick: bool = False,
    logger: Optional[ProgressLogger] = None,
) -> Dict:
    """
    主编排入口。

    Args:
        config: 主配置
        registry: benchmark 注册表
        skip_custom: 跳过自研 benchmark
        skip_optional: 跳过可选 benchmark
        only_benchmarks: 仅运行指定 benchmark
        parallel: 并行度
        limit: 样本数限制
        dry_run: 仅打印计划不执行
        preflight: 正式评测前用 limit=2 快速验证所有 benchmark
        quick: Quick 模式，只跑 registry 中标记了 quick=true 的 benchmark
        logger: 日志器

    Returns:
        最终报告 dict
    """
    total_start = time.time()

    model_name = config['model']['name']
    model_type = config['model'].get('type', 'LLM')
    output_cfg = config.get('output', {})
    work_dir = output_cfg.get('work_dir', 'outputs')

    if not logger:
        log_path = output_cfg.get('progress_log', 'eval_progress.log')
        logger = ProgressLogger(log_path)

    logger.section(f"Evaluation Orchestrator")
    logger.log(f"Model: {model_name}")
    logger.log(f"Type: {model_type}")

    # 检测模型是否为 thinking model（仅检测，不修改全局 config）
    model_is_thinking = detect_thinking_model(config, logger)

    # 解析 benchmark 列表
    benchmarks = resolve_benchmarks(
        model_type, registry, skip_custom, skip_optional, only_benchmarks
    )

    # Quick 模式：只跑标记了 quick=true 的 benchmark
    if quick:
        benchmarks = [b for b in benchmarks if b.get('quick', False)]
        if not benchmarks:
            logger.log("[ERROR] Quick mode: no benchmarks marked with quick=true in registry")
            return {"error": "No quick benchmarks found"}
        logger.log(f"[QUICK MODE] Running {len(benchmarks)} quick benchmark(s)")

    logger.log(f"Benchmarks to run: {len(benchmarks)}")
    for b in benchmarks:
        thinking_tag = " [thinking]" if (model_is_thinking and b.get('thinking', False)) else ""
        logger.log(f"  - {b.get('display_name', b['name'])} (runner={b.get('runner', 'evalscope')}){thinking_tag}")

    if dry_run:
        logger.section("DRY RUN - No execution")
        return {"dry_run": True, "benchmarks": [b['name'] for b in benchmarks]}

    # Preflight 预检
    ensure_dir(work_dir)

    if preflight:
        logger.section("Preflight Check (limit=2)")
        preflight_dir = os.path.join(work_dir, 'preflight')
        ensure_dir(preflight_dir)
        preflight_ok = True
        for bench in benchmarks:
            name = bench.get('display_name', bench['name'])
            logger.log(f"  Preflight: {name} ...")
            r = run_single_benchmark(bench, config, preflight_dir, 2, logger)
            detail = r['detail']
            if isinstance(detail, list):
                failed = any(d.get('status') == 'F' for d in detail)
                err_msg = 'sub-benchmark failed'
            else:
                failed = detail.get('status') == 'F'
                err_msg = detail.get('error', 'unknown error')
            if failed:
                preflight_ok = False
                logger.log(f"  [FAIL] {name}: {err_msg}")
            else:
                logger.log(f"  [OK] {name}")

        if not preflight_ok:
            logger.log("[ABORT] Preflight failed. Fix errors above before running full evaluation.")
            return {"preflight": False, "error": "Preflight check failed"}
        else:
            logger.log("[PASS] All benchmarks passed preflight. Starting full evaluation...")

    # 执行
    all_details = []

    if parallel > 1 and len(benchmarks) > 1:
        logger.log(f"Running with parallelism={parallel}")
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {}
            for bench in benchmarks:
                future = executor.submit(
                    run_single_benchmark, bench, config, work_dir, limit, logger,
                    model_is_thinking,
                )
                futures[future] = bench['name']

            for future in as_completed(futures):
                bench_name = futures[future]
                try:
                    result = future.result()
                    detail = result['detail']
                    if isinstance(detail, list):
                        all_details.extend(detail)
                    else:
                        all_details.append(detail)
                except Exception as e:
                    logger.log(f"[ERROR] {bench_name} thread failed: {e}")
                    all_details.append(build_detail(bench_name, 0.0, {"error": str(e)}, "F"))
    else:
        for bench in benchmarks:
            result = run_single_benchmark(bench, config, work_dir, limit, logger, model_is_thinking)
            detail = result['detail']
            if isinstance(detail, list):
                all_details.extend(detail)
            else:
                all_details.append(detail)

    # 生成报告
    total_elapsed = round(time.time() - total_start, 2)
    logger.section("Generating Report")

    from report_generator import generate_report
    report = generate_report(
        model_name=model_name,
        model_type=model_type,
        details=all_details,
        output_dir=os.path.dirname(output_cfg.get('report_json', 'eval_report.json')) or '.',
        report_json=os.path.basename(output_cfg.get('report_json', 'eval_report.json')),
        report_md=os.path.basename(output_cfg.get('report_md', 'eval_report.md')),
        total_duration_seconds=total_elapsed,
        registry=registry,
    )

    logger.section("Evaluation Complete")
    logger.log(f"Total benchmarks: {len(all_details)}")
    success = sum(1 for d in all_details if d.get('status') == 'S')
    failed = len(all_details) - success
    logger.log(f"Success: {success}, Failed: {failed}")
    logger.log(f"Total duration: {total_elapsed}s ({total_elapsed/60:.1f} min)")
    logger.log(f"Report: {output_cfg.get('report_json', 'eval_report.json')}")

    return report


def main():
    parser = argparse.ArgumentParser(
        description='FlagOS Comprehensive Evaluation Orchestrator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 全量评测
  python eval_orchestrator.py --config config.yaml

  # 仅 EvalScope 原生 benchmark + 必测项
  python eval_orchestrator.py --config config.yaml --skip-custom --skip-optional

  # 指定 benchmark
  python eval_orchestrator.py --config config.yaml --benchmarks mmlu,aime24,gpqa_diamond

  # 调试模式（小样本）
  python eval_orchestrator.py --config config.yaml --limit 5

  # 预检后再全量评测
  python eval_orchestrator.py --config config.yaml --preflight

  # 仅查看执行计划
  python eval_orchestrator.py --config config.yaml --dry-run

  # 并行执行
  python eval_orchestrator.py --config config.yaml --parallel 3
        """,
    )
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='配置文件路径 (default: config.yaml)')
    parser.add_argument('--registry', type=str, default='benchmark_registry.yaml',
                        help='Benchmark 注册表路径 (default: benchmark_registry.yaml)')
    parser.add_argument('--benchmarks', type=str, default=None,
                        help='指定运行的 benchmark，逗号分隔')
    parser.add_argument('--selection', type=str, default=None,
                        help='从 benchmark_selector 生成的选择配置文件读取 benchmark 列表')
    parser.add_argument('--skip-custom', action='store_true',
                        help='跳过自研 benchmark，仅运行 EvalScope 原生')
    parser.add_argument('--skip-optional', action='store_true',
                        help='跳过可选 benchmark，仅运行必测')
    parser.add_argument('--parallel', type=int, default=1,
                        help='并行执行的 benchmark 数量 (default: 1)')
    parser.add_argument('--limit', type=int, default=None,
                        help='限制每个 benchmark 的样本数（调试用）')
    parser.add_argument('--quick', action='store_true',
                        help='Quick 模式：只跑标记了 quick=true 的 benchmark（迁移流程用）')
    parser.add_argument('--preflight', action='store_true',
                        help='正式评测前先用 limit=2 快速验证所有 benchmark')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅打印执行计划，不实际运行')
    parser.add_argument('--log', type=str, default=None,
                        help='进度日志路径（覆盖配置文件中的设置）')
    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)
    if not config:
        print(f"[ERROR] Failed to load config: {args.config}", file=sys.stderr)
        sys.exit(1)

    registry = load_benchmark_registry(args.registry)
    if not registry:
        print(f"[ERROR] Failed to load registry: {args.registry}", file=sys.stderr)
        sys.exit(1)

    # 日志
    log_path = args.log or config.get('output', {}).get('progress_log', 'eval_progress.log')
    logger = ProgressLogger(log_path)

    # 解析 benchmark 过滤
    only_benchmarks = None
    if args.selection and args.benchmarks:
        print("[ERROR] --selection and --benchmarks are mutually exclusive", file=sys.stderr)
        sys.exit(1)
    if args.selection:
        selection = load_json(args.selection)
        if not selection or 'selected' not in selection:
            print(f"[ERROR] Invalid selection file: {args.selection}", file=sys.stderr)
            sys.exit(1)
        only_benchmarks = selection['selected']
        print(f"Loaded {len(only_benchmarks)} benchmarks from selection: {args.selection}")
    elif args.benchmarks:
        only_benchmarks = [b.strip() for b in args.benchmarks.split(',')]

    # 运行
    report = run_orchestrator(
        config=config,
        registry=registry,
        skip_custom=args.skip_custom,
        skip_optional=args.skip_optional,
        only_benchmarks=only_benchmarks,
        parallel=args.parallel,
        limit=args.limit,
        dry_run=args.dry_run,
        preflight=args.preflight,
        quick=args.quick,
        logger=logger,
    )

    if args.dry_run:
        print("\n[DRY RUN] Execution plan:")
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("\n[DONE] Report generated:")
        print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
