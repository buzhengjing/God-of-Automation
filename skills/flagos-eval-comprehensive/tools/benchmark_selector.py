#!/usr/bin/env python3
"""
Benchmark 交互式选择器
一站式流程：推荐展示 → 交互选择 → 自动下载数据集 → 启动评测。

用法:
  # 交互式选择
  python benchmark_selector.py --config config.yaml

  # 非交互：自动选择必测项
  python benchmark_selector.py --config config.yaml --auto

  # 非交互：全选
  python benchmark_selector.py --config config.yaml --select all

  # 仅保存选择配置
  python benchmark_selector.py --config config.yaml --save-only
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Registry loading (reuse logic from dataset_prefetch)
# ---------------------------------------------------------------------------

def load_yaml(path: str) -> Optional[dict]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except (FileNotFoundError, yaml.YAMLError) as e:
        print(f"[ERROR] Failed to load {path}: {e}", file=sys.stderr)
        return None


def resolve_benchmarks_by_tier(
    registry: dict, model_type: str
) -> Tuple[List[Dict], List[Dict]]:
    """
    Resolve benchmarks for a model type into (required, optional) lists.
    Handles 'inherit' for Omni-like types.
    """
    type_cfg = registry.get(model_type, {})
    required = list(type_cfg.get('required', []) or [])
    optional = list(type_cfg.get('optional', []) or [])

    for parent in (type_cfg.get('inherit') or []):
        parent_cfg = registry.get(parent, {})
        required.extend(parent_cfg.get('required', []) or [])
        optional.extend(parent_cfg.get('optional', []) or [])

    # Deduplicate by name, preserving order
    seen = set()
    dedup_req, dedup_opt = [], []
    for b in required:
        if b['name'] not in seen:
            seen.add(b['name'])
            dedup_req.append(b)
    for b in optional:
        if b['name'] not in seen:
            seen.add(b['name'])
            dedup_opt.append(b)

    return dedup_req, dedup_opt


# ---------------------------------------------------------------------------
# Terminal UI
# ---------------------------------------------------------------------------

def render_selection(
    required: List[Dict],
    optional: List[Dict],
    selected: set,
    model_type: str,
):
    """Render the interactive selection UI."""
    print()
    print("══════════════════════════════════════════════════════════")
    print(f"  Benchmark 选择 — 模型类型: {model_type}")
    print("══════════════════════════════════════════════════════════")
    print()

    idx = 1
    index_map = {}  # idx -> benchmark dict

    if required:
        print("  ● 必测 (推荐全选):")
        print("  ─────────────────────────────────────")
        for b in required:
            name = b['name']
            display = b.get('display_name', name)
            runner = b.get('runner', 'evalscope')
            desc = b.get('description', '')
            check = "✓" if name in selected else " "
            print(f"  [{check}] {idx:>2}. {display:<22s} {runner:<10s} {desc}")
            index_map[idx] = b
            idx += 1

    if optional:
        print()
        print("  ○ 可选:")
        print("  ─────────────────────────────────────")
        for b in optional:
            name = b['name']
            display = b.get('display_name', name)
            runner = b.get('runner', 'evalscope')
            desc = b.get('description', '')
            check = "✓" if name in selected else " "
            print(f"  [{check}] {idx:>2}. {display:<22s} {runner:<10s} {desc}")
            index_map[idx] = b
            idx += 1

    print()
    print('  输入序号切换 (如 "7 8 10"), "all" 全选, "required" 仅必测, "ok" 确认')

    return index_map


def interactive_select(
    required: List[Dict],
    optional: List[Dict],
    model_type: str,
) -> List[str]:
    """Run interactive selection loop, return list of selected benchmark names."""
    # Default: required checked, optional unchecked
    selected = {b['name'] for b in required}
    all_benchmarks = required + optional
    all_names = {b['name'] for b in all_benchmarks}

    while True:
        index_map = render_selection(required, optional, selected, model_type)
        try:
            user_input = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  已取消")
            sys.exit(0)

        if user_input == 'ok':
            break
        elif user_input == 'all':
            selected = set(all_names)
        elif user_input == 'required':
            selected = {b['name'] for b in required}
        elif user_input == 'none':
            selected = set()
        else:
            # Parse space/comma separated indices
            tokens = user_input.replace(',', ' ').split()
            for token in tokens:
                try:
                    idx = int(token)
                    if idx in index_map:
                        name = index_map[idx]['name']
                        if name in selected:
                            selected.discard(name)
                        else:
                            selected.add(name)
                    else:
                        print(f"  [WARN] 无效序号: {idx}")
                except ValueError:
                    print(f"  [WARN] 无法识别: {token}")

    # Return in original order
    return [b['name'] for b in all_benchmarks if b['name'] in selected]


# ---------------------------------------------------------------------------
# Save selection
# ---------------------------------------------------------------------------

def save_selection(
    model_type: str,
    model_name: str,
    all_benchmarks: List[Dict],
    selected_names: List[str],
    output_path: str,
):
    """Save selection config to JSON."""
    selected_set = set(selected_names)
    skipped = [b['name'] for b in all_benchmarks if b['name'] not in selected_set]

    data = {
        "model_type": model_type,
        "model_name": model_name,
        "selected": selected_names,
        "skipped": skipped,
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n  选择配置已保存: {output_path}")
    print(f"  已选: {len(selected_names)}, 跳过: {len(skipped)}")
    return data


# ---------------------------------------------------------------------------
# Download datasets for selected benchmarks
# ---------------------------------------------------------------------------

def download_selected(
    selected_names: List[str],
    config_path: str,
    registry_path: str,
):
    """Call dataset_prefetch.py to download datasets for selected evalscope benchmarks."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prefetch_script = os.path.join(script_dir, 'dataset_prefetch.py')

    if not os.path.isfile(prefetch_script):
        print(f"[WARN] dataset_prefetch.py not found at {prefetch_script}, skipping download")
        return

    # Load config to get model type and cache dir
    config = load_yaml(config_path)
    if not config:
        print("[WARN] Cannot load config for download, skipping")
        return

    model_type = config.get('model', {}).get('type', 'LLM')
    cache_dir = config.get('evalscope', {}).get('dataset_dir', '')

    cmd = [
        sys.executable, prefetch_script,
        '--model-type', model_type,
        '--registry', registry_path,
        '--benchmarks', ','.join(selected_names),
    ]
    if cache_dir:
        cmd.extend(['--cache-dir', cache_dir])

    print(f"\n{'='*60}")
    print(f"  下载所选 benchmark 数据集 ({len(selected_names)} 项)")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[WARN] 数据集下载过程中存在失败项，评测可能受影响")


# ---------------------------------------------------------------------------
# Launch evaluation
# ---------------------------------------------------------------------------

def launch_eval(
    selection_path: str,
    config_path: str,
    registry_path: str,
    limit: Optional[int] = None,
    parallel: int = 1,
):
    """Launch eval_orchestrator.py with --selection."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    orchestrator = os.path.join(script_dir, 'eval_orchestrator.py')

    if not os.path.isfile(orchestrator):
        print(f"[ERROR] eval_orchestrator.py not found at {orchestrator}")
        return

    cmd = [
        sys.executable, orchestrator,
        '--config', config_path,
        '--registry', registry_path,
        '--selection', selection_path,
    ]
    if limit is not None:
        cmd.extend(['--limit', str(limit)])
    if parallel > 1:
        cmd.extend(['--parallel', str(parallel)])

    print(f"\n{'='*60}")
    print(f"  启动评测: {' '.join(cmd)}")
    print(f"{'='*60}\n")

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Benchmark 交互式选择 + 自动下载 + 评测启动',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 交互式选择
  python benchmark_selector.py --config config.yaml

  # 非交互：自动选择必测项，直接下载+评测
  python benchmark_selector.py --config config.yaml --auto

  # 非交互：全选
  python benchmark_selector.py --config config.yaml --select all

  # 仅保存选择配置，不下载不评测
  python benchmark_selector.py --config config.yaml --save-only

  # 下载数据集后不启动评测
  python benchmark_selector.py --config config.yaml --no-eval
        """,
    )
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='配置文件路径 (default: config.yaml)')
    parser.add_argument('--registry', type=str, default=None,
                        help='benchmark_registry.yaml 路径 (默认: 同目录下)')
    parser.add_argument('--auto', action='store_true',
                        help='非交互模式：自动选择必测项，直接下载+评测')
    parser.add_argument('--select', type=str, default=None, choices=['all', 'required'],
                        help='非交互模式：指定选择范围 (all=全选, required=仅必测)')
    parser.add_argument('--no-eval', action='store_true',
                        help='下载数据集后不启动评测')
    parser.add_argument('--save-only', action='store_true',
                        help='仅保存选择配置，不下载不评测')
    parser.add_argument('--output', type=str, default='benchmark_selection.json',
                        help='选择配置输出路径 (default: benchmark_selection.json)')
    parser.add_argument('--limit', type=int, default=None,
                        help='传递给 eval_orchestrator 的样本数限制')
    parser.add_argument('--parallel', type=int, default=1,
                        help='传递给 eval_orchestrator 的并行度')

    args = parser.parse_args()

    # Resolve paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config
    registry_path = args.registry or os.path.join(script_dir, 'benchmark_registry.yaml')

    # Load config
    config = load_yaml(config_path)
    if not config:
        print(f"[ERROR] Failed to load config: {config_path}", file=sys.stderr)
        sys.exit(1)

    model_name = config.get('model', {}).get('name', 'unknown')
    model_type = config.get('model', {}).get('type', 'LLM')

    # Load registry
    registry = load_yaml(registry_path)
    if not registry:
        print(f"[ERROR] Failed to load registry: {registry_path}", file=sys.stderr)
        sys.exit(1)

    # Resolve benchmarks
    required, optional = resolve_benchmarks_by_tier(registry, model_type)
    all_benchmarks = required + optional

    if not all_benchmarks:
        print(f"[WARN] No benchmarks found for model type: {model_type}")
        sys.exit(0)

    # Determine selection
    if args.auto or args.select == 'required':
        selected_names = [b['name'] for b in required]
        print(f"自动选择必测项: {len(selected_names)} 个 benchmark")
    elif args.select == 'all':
        selected_names = [b['name'] for b in all_benchmarks]
        print(f"全选: {len(selected_names)} 个 benchmark")
    else:
        # Interactive mode
        selected_names = interactive_select(required, optional, model_type)

    if not selected_names:
        print("[WARN] 未选择任何 benchmark，退出")
        sys.exit(0)

    # Save selection
    save_selection(model_type, model_name, all_benchmarks, selected_names, args.output)

    if args.save_only:
        return

    # Download datasets
    download_selected(selected_names, config_path, registry_path)

    if args.no_eval:
        print("\n已完成数据集下载，跳过评测 (--no-eval)")
        return

    # Launch evaluation
    launch_eval(args.output, config_path, registry_path, args.limit, args.parallel)


if __name__ == '__main__':
    main()
