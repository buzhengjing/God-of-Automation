#!/usr/bin/env python3
"""
EvalScope 数据集预下载脚本
从 benchmark_registry.yaml 解析所有 evalscope runner 的 benchmark，
预下载数据集到本地缓存目录，支持离线评测。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Utility helpers (mirrored from evalscope to compute identical cache paths)
# ---------------------------------------------------------------------------

def gen_hash(name: str, bits: int = 32) -> str:
    return hashlib.md5(name.encode(encoding='UTF-8')).hexdigest()[:bits]


def safe_filename(s: str, max_length: int = 255) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', s)
    s = s.strip('. ')
    return s[:max_length] if len(s) > max_length else s


# ---------------------------------------------------------------------------
# Locate evalscope _meta directory
# ---------------------------------------------------------------------------

def find_evalscope_meta_dir() -> Optional[str]:
    """Find the evalscope benchmarks/_meta directory."""
    try:
        import evalscope
        pkg_dir = os.path.dirname(evalscope.__file__)
        meta_dir = os.path.join(pkg_dir, 'benchmarks', '_meta')
        if os.path.isdir(meta_dir):
            return meta_dir
    except ImportError:
        pass

    # Fallback: search common locations
    for candidate in [
        '/flagos-workspace/eval/evalscope/benchmarks/_meta',
        os.path.join(os.path.dirname(__file__), '..', '..', '..', 'evalscope-main', 'evalscope', 'benchmarks', '_meta'),
    ]:
        candidate = os.path.abspath(candidate)
        if os.path.isdir(candidate):
            return candidate
    return None


# ---------------------------------------------------------------------------
# Parse benchmark registry and _meta
# ---------------------------------------------------------------------------

def load_benchmark_registry(registry_path: str) -> Dict:
    with open(registry_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def resolve_inherited(registry: Dict, model_type: str) -> List[Dict]:
    """Resolve benchmarks for a model type, handling 'inherit'."""
    type_cfg = registry.get(model_type, {})
    benchmarks = []
    benchmarks.extend(type_cfg.get('required', []) or [])
    benchmarks.extend(type_cfg.get('optional', []) or [])

    for parent in (type_cfg.get('inherit') or []):
        parent_cfg = registry.get(parent, {})
        benchmarks.extend(parent_cfg.get('required', []) or [])
        benchmarks.extend(parent_cfg.get('optional', []) or [])

    return benchmarks


def get_evalscope_benchmarks(registry: Dict, model_types: List[str]) -> List[Dict]:
    """Get all evalscope-runner benchmarks for given model types (deduplicated)."""
    seen = set()
    result = []
    for mt in model_types:
        for bench in resolve_inherited(registry, mt):
            if bench.get('runner') != 'evalscope':
                continue
            name = bench['name']
            if name not in seen:
                seen.add(name)
                result.append(bench)
    return result


def load_meta(meta_dir: str, benchmark_name: str) -> Optional[Dict]:
    """Load _meta/<benchmark_name>.json."""
    path = os.path.join(meta_dir, f'{benchmark_name}.json')
    if not os.path.isfile(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Detect adapter loading mode (reformat_subset / split_as_subset)
# ---------------------------------------------------------------------------

def detect_adapter_mode(benchmark_name: str) -> Tuple[str, str]:
    """
    Detect how EvalScope's adapter loads datasets for a given benchmark.

    Returns a tuple of (mode, default_subset):
        mode:
            'reformat_subset': adapter downloads default_subset and splits in-memory
            'split_as_subset': adapter uses subset names as split names, with default_subset
            'normal': adapter downloads each subset separately
        default_subset:
            The actual subset name the adapter uses (usually 'default', but some
            benchmarks override it, e.g. MMLU uses 'all').
    """
    mode = None
    default_subset = 'default'

    try:
        from evalscope.benchmarks import Benchmark
        bench_cls = Benchmark.get(benchmark_name)
        if bench_cls is not None:
            import inspect
            source = inspect.getsource(bench_cls.__init__)
            if 'reformat_subset' in source and 'True' in source:
                mode = 'reformat_subset'
            elif 'split_as_subset' in source and 'True' in source:
                mode = 'split_as_subset'
            # Extract default_subset from source
            import re
            m = re.search(r"default_subset\s*=\s*['\"]([^'\"]+)['\"]", source)
            if m:
                default_subset = m.group(1)
    except Exception:
        pass

    # Fallback: known benchmarks from evalscope source code analysis
    REFORMAT_SUBSET_BENCHMARKS = {
        'mmlu', 'math_500', 'mmlu_pro', 'math_vision', 'cmmmu', 'mmmu_pro',
        'ocr_bench', 'competition_math', 'chartqa', 'cmmu', 'mm_star',
        'cmmlu', 'hle', 'multi_if', 'seed_bench_2_plus', 'math_verse',
        'visu_logic', 'chinese_simple_qa', 'torgo',
    }
    SPLIT_AS_SUBSET_BENCHMARKS = {
        'musr', 'docmath', 'amc', 'refcoco', 'pope', 'process_bench',
    }

    # Known default_subset overrides (from evalscope adapter source code)
    DEFAULT_SUBSET_OVERRIDES = {
        'mmlu': 'all',
        'pope': 'Full',
        'math_verse': 'testmini',
        'halu_eval': 'Full',
        'mm_star': 'val',
    }

    if mode is None:
        if benchmark_name in REFORMAT_SUBSET_BENCHMARKS:
            mode = 'reformat_subset'
        elif benchmark_name in SPLIT_AS_SUBSET_BENCHMARKS:
            mode = 'split_as_subset'
        else:
            mode = 'normal'

    if default_subset == 'default' and benchmark_name in DEFAULT_SUBSET_OVERRIDES:
        default_subset = DEFAULT_SUBSET_OVERRIDES[benchmark_name]

    return mode, default_subset


# ---------------------------------------------------------------------------
# Dataset info extraction
# ---------------------------------------------------------------------------

def extract_dataset_info(meta: Dict, benchmark_name: str = '') -> List[Dict]:
    """
    Extract download tasks from a _meta json, respecting adapter loading modes.

    For 'reformat_subset' benchmarks: only download the adapter's default_subset
    (e.g. 'all' for MMLU) — adapter downloads once and splits in memory.

    For 'split_as_subset' benchmarks: each subset name is used as a split,
    with the adapter's default_subset as the subset.

    For 'normal' benchmarks: download each (subset, split) combination.

    Returns a list of dicts with keys: dataset_id, split, subset, version.
    """
    m = meta.get('meta', {})
    dataset_id = m.get('dataset_id')
    if not dataset_id:
        return []

    eval_split = m.get('eval_split', 'test')
    train_split = m.get('train_split', '')
    subset_list = m.get('subset_list', ['default'])
    version = m.get('version', None)

    if not isinstance(subset_list, list):
        subset_list = ['default']

    mode, adapter_default_subset = detect_adapter_mode(benchmark_name)
    tasks = []

    if mode == 'reformat_subset':
        # Download only the adapter's default_subset with eval_split (and train_split if present).
        # The adapter will split data in memory by field values.
        # Note: some benchmarks override default_subset (e.g. MMLU uses 'all', not 'default').
        for split in [eval_split, train_split]:
            if not split:
                continue
            tasks.append({
                'dataset_id': dataset_id,
                'split': split,
                'subset': adapter_default_subset,
                'version': version,
            })

    elif mode == 'split_as_subset':
        # Each subset name is used as a split name, subset is the adapter's default_subset.
        # e.g., MuSR: split='murder_mysteries', subset='default'
        for subset_as_split in subset_list:
            tasks.append({
                'dataset_id': dataset_id,
                'split': subset_as_split,
                'subset': adapter_default_subset,
                'version': version,
            })

    else:
        # Normal mode: download each (subset, split) combination
        splits = [eval_split]
        if train_split:
            splits.append(train_split)
        for subset in subset_list:
            for split in splits:
                if not split:
                    continue
                tasks.append({
                    'dataset_id': dataset_id,
                    'split': split,
                    'subset': subset,
                    'version': version,
                })

    return tasks


def compute_cache_dir(cache_root: str, dataset_id: str, split: str,
                      subset: str, version: Optional[str]) -> str:
    """Compute the cache directory path identical to EvalScope's RemoteDataLoader."""
    kwargs = {}  # default empty kwargs
    dataset_hash = gen_hash(f'{dataset_id}{split}{subset}{version}{kwargs}')
    datasets_cache_dir = os.path.join(cache_root, 'datasets')
    return os.path.join(datasets_cache_dir, f'{safe_filename(dataset_id)}-{dataset_hash}')


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

def download_single(
    dataset_id: str,
    split: str,
    subset: str,
    version: Optional[str],
    cache_dir: str,
    source: str = 'modelscope',
    hf_mirror: Optional[str] = None,
    max_retries: int = 3,
) -> Tuple[bool, str]:
    """
    Download a single dataset split/subset and save to cache_dir in arrow format.
    Returns (success, message).
    """
    os.makedirs(os.path.dirname(cache_dir), exist_ok=True)

    for attempt in range(1, max_retries + 1):
        try:
            import datasets as hf_datasets

            if source == 'modelscope':
                from modelscope import MsDataset
                ds = MsDataset.load(
                    dataset_name=dataset_id,
                    split=split,
                    subset_name=subset if subset != 'default' else None,
                    version=version,
                    trust_remote_code=True,
                )
                if not isinstance(ds, hf_datasets.Dataset):
                    ds = ds.to_hf_dataset()
            else:
                # huggingface
                if hf_mirror:
                    os.environ['HF_ENDPOINT'] = hf_mirror
                ds = hf_datasets.load_dataset(
                    path=dataset_id,
                    name=subset if subset != 'default' else None,
                    split=split,
                    revision=version,
                    trust_remote_code=True,
                )

            ds.save_to_disk(cache_dir)
            return True, f"OK ({len(ds)} samples)"

        except Exception as e:
            msg = str(e)
            if attempt < max_retries:
                wait = 2 ** attempt
                print(f"    Retry {attempt}/{max_retries} in {wait}s: {msg}")
                time.sleep(wait)
            else:
                return False, f"FAILED after {max_retries} attempts: {msg}"

    return False, "FAILED: unknown error"


def verify_cache(cache_dir: str) -> Tuple[bool, str]:
    """Verify a cached dataset can be loaded."""
    try:
        import datasets as hf_datasets
        ds = hf_datasets.load_from_disk(cache_dir)
        return True, f"OK ({len(ds)} samples)"
    except Exception as e:
        return False, f"CORRUPT: {e}"


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

ALL_MODEL_TYPES = ['LLM', 'VL', 'Omni', 'Robotics', 'ImageGen']


def collect_download_tasks(
    registry_path: str,
    meta_dir: str,
    model_types: List[str],
    cache_root: str,
    only_benchmarks: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Collect all download tasks: list of dicts with keys:
      benchmark, dataset_id, split, subset, version, cache_dir, display_name
    """
    registry = load_benchmark_registry(registry_path)
    benchmarks = get_evalscope_benchmarks(registry, model_types)
    tasks = []

    for bench in benchmarks:
        name = bench['name']
        if only_benchmarks and name not in only_benchmarks:
            continue
        display_name = bench.get('display_name', name)
        meta = load_meta(meta_dir, name)
        if meta is None:
            print(f"[WARN] No _meta found for benchmark '{name}', skipping")
            continue

        infos = extract_dataset_info(meta, benchmark_name=name)
        if not infos:
            print(f"[WARN] No dataset_id in _meta for '{name}', skipping")
            continue

        for info in infos:
            cache_dir = compute_cache_dir(
                cache_root, info['dataset_id'], info['split'],
                info['subset'], info['version'],
            )
            tasks.append({
                'benchmark': name,
                'display_name': display_name,
                **info,
                'cache_dir': cache_dir,
            })

    return tasks


def cmd_list(tasks: List[Dict]) -> None:
    """List mode: print all datasets that need to be downloaded."""
    # Group by benchmark
    by_bench = {}
    for t in tasks:
        by_bench.setdefault(t['benchmark'], []).append(t)

    print(f"\n{'='*60}")
    print(f"Datasets to download: {len(tasks)} items across {len(by_bench)} benchmarks")
    print(f"{'='*60}\n")

    for bench, items in by_bench.items():
        dataset_id = items[0]['dataset_id']
        splits = sorted(set(t['split'] for t in items))
        subsets = sorted(set(t['subset'] for t in items))
        print(f"  {bench:20s} | {dataset_id}")
        print(f"  {'':20s} | splits: {', '.join(splits)}")
        print(f"  {'':20s} | subsets: {len(subsets)} ({', '.join(subsets[:5])}{'...' if len(subsets) > 5 else ''})")
        print()


def cmd_status(tasks: List[Dict]) -> None:
    """Status mode: check which datasets are cached and which are missing."""
    cached = 0
    missing = 0
    corrupt = 0

    print(f"\n{'='*60}")
    print(f"Cache status check: {len(tasks)} items")
    print(f"{'='*60}\n")

    by_bench = {}
    for t in tasks:
        by_bench.setdefault(t['benchmark'], []).append(t)

    for bench, items in by_bench.items():
        bench_cached = 0
        bench_missing = 0
        bench_corrupt = 0

        for t in items:
            if os.path.exists(t['cache_dir']):
                ok, msg = verify_cache(t['cache_dir'])
                if ok:
                    bench_cached += 1
                else:
                    bench_corrupt += 1
            else:
                bench_missing += 1

        status_icon = "✓" if bench_missing == 0 and bench_corrupt == 0 else "✗"
        total = len(items)
        print(f"  {status_icon} {bench:20s} | {bench_cached}/{total} cached, {bench_missing} missing, {bench_corrupt} corrupt")

        cached += bench_cached
        missing += bench_missing
        corrupt += bench_corrupt

    print(f"\n{'─'*60}")
    print(f"  Total: {cached} cached, {missing} missing, {corrupt} corrupt")
    if missing == 0 and corrupt == 0:
        print("  All datasets are ready for offline evaluation!")
    print()


def cmd_download(
    tasks: List[Dict],
    source: str,
    hf_mirror: Optional[str],
    max_retries: int,
    force: bool = False,
) -> Tuple[int, int, int]:
    """Download mode: download all missing datasets."""
    total = len(tasks)
    downloaded = 0
    skipped = 0
    failed = 0

    print(f"\n{'='*60}")
    print(f"Downloading {total} dataset items (source={source})")
    print(f"{'='*60}\n")

    for i, t in enumerate(tasks, 1):
        label = f"[{i}/{total}] {t['benchmark']} / {t['dataset_id']} ({t['subset']}:{t['split']})"

        # Skip if already cached (unless force)
        if os.path.exists(t['cache_dir']) and not force:
            ok, msg = verify_cache(t['cache_dir'])
            if ok:
                print(f"  SKIP  {label} — already cached {msg}")
                skipped += 1
                continue
            else:
                print(f"  RE-DL {label} — cache corrupt, re-downloading")

        print(f"  DL    {label}")
        ok, msg = download_single(
            dataset_id=t['dataset_id'],
            split=t['split'],
            subset=t['subset'],
            version=t['version'],
            cache_dir=t['cache_dir'],
            source=source,
            hf_mirror=hf_mirror,
            max_retries=max_retries,
        )

        if ok:
            print(f"        → {msg}")
            downloaded += 1
        else:
            print(f"        → {msg}")
            failed += 1

    print(f"\n{'─'*60}")
    print(f"  Downloaded: {downloaded}, Skipped: {skipped}, Failed: {failed}")
    if failed > 0:
        print(f"  WARNING: {failed} downloads failed. Re-run to retry.")
    else:
        print("  All datasets downloaded successfully!")
    print()

    return downloaded, skipped, failed


def main():
    parser = argparse.ArgumentParser(
        description='EvalScope 数据集预下载工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出 LLM 类型需要的所有数据集
  python dataset_prefetch.py --model-type LLM --list

  # 检查缓存状态
  python dataset_prefetch.py --model-type LLM --status

  # 下载 LLM 数据集到指定目录
  python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache

  # 下载所有类型，使用 HuggingFace 源 + 镜像
  python dataset_prefetch.py --model-type All --source huggingface --hf-mirror https://hf-mirror.com

  # 强制重新下载
  python dataset_prefetch.py --model-type LLM --force
        """,
    )

    parser.add_argument(
        '--model-type', type=str, default='All',
        help='模型类型: LLM / VL / Omni / Robotics / ImageGen / All (默认 All)',
    )
    parser.add_argument(
        '--cache-dir', type=str, default=None,
        help='本地缓存目录 (默认: ~/.cache/evalscope)',
    )
    parser.add_argument(
        '--registry', type=str, default=None,
        help='benchmark_registry.yaml 路径 (默认: 同目录下)',
    )
    parser.add_argument(
        '--source', type=str, default='modelscope', choices=['modelscope', 'huggingface'],
        help='数据源 (默认: modelscope)',
    )
    parser.add_argument(
        '--hf-mirror', type=str, default=None,
        help='HuggingFace 镜像地址 (如 https://hf-mirror.com)',
    )
    parser.add_argument(
        '--max-retries', type=int, default=3,
        help='下载重试次数 (默认: 3)',
    )
    parser.add_argument(
        '--force', action='store_true',
        help='强制重新下载，忽略已有缓存',
    )
    parser.add_argument(
        '--list', action='store_true', dest='list_mode',
        help='仅列出需要下载的数据集，不实际下载',
    )
    parser.add_argument(
        '--status', action='store_true',
        help='检查缓存状态',
    )
    parser.add_argument(
        '--benchmarks', type=str, default=None,
        help='仅下载指定 benchmark 的数据集，逗号分隔 (如 mmlu,aime24)',
    )

    args = parser.parse_args()

    # Resolve registry path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    registry_path = args.registry or os.path.join(script_dir, 'benchmark_registry.yaml')
    if not os.path.isfile(registry_path):
        print(f"[ERROR] benchmark_registry.yaml not found at {registry_path}")
        sys.exit(1)

    # Resolve meta dir
    meta_dir = find_evalscope_meta_dir()
    if meta_dir is None:
        print("[ERROR] Cannot find evalscope benchmarks/_meta directory.")
        print("  Make sure evalscope is installed: pip install evalscope")
        sys.exit(1)
    print(f"Using _meta dir: {meta_dir}")

    # Resolve cache dir
    if args.cache_dir:
        cache_root = os.path.abspath(args.cache_dir)
    else:
        cache_root = os.path.expanduser(os.getenv('EVALSCOPE_CACHE', '~/.cache/evalscope'))
    print(f"Cache root: {cache_root}")

    # Resolve model types
    if args.model_type == 'All':
        model_types = ALL_MODEL_TYPES
    else:
        model_types = [t.strip() for t in args.model_type.split(',')]

    print(f"Model types: {', '.join(model_types)}")

    # Resolve benchmark filter
    only_benchmarks = None
    if args.benchmarks:
        only_benchmarks = [b.strip() for b in args.benchmarks.split(',')]
        print(f"Benchmark filter: {', '.join(only_benchmarks)}")

    # Collect tasks
    tasks = collect_download_tasks(registry_path, meta_dir, model_types, cache_root, only_benchmarks)
    if not tasks:
        print("[WARN] No download tasks found. Check model types and registry.")
        sys.exit(0)

    # Execute mode
    if args.list_mode:
        cmd_list(tasks)
    elif args.status:
        cmd_status(tasks)
    else:
        _, _, failed = cmd_download(
            tasks, args.source, args.hf_mirror, args.max_retries, args.force,
        )
        sys.exit(1 if failed > 0 else 0)


if __name__ == '__main__':
    main()
