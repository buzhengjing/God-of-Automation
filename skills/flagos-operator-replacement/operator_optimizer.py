#!/usr/bin/env python3
"""
算子优化器 — 分组二分搜索最优算子集

通过分组二分搜索 FlagGems 算子，找到使 FlagOS 性能 >= 目标比率（默认 80% native）的最优算子组合。

核心算法（分组二分搜索）：
1. 将算子按功能分为 5 组（compute/memory/math/index/reduce）
2. 整组禁用 → benchmark → 仍达标 → 整组全禁用，跳过组内搜索
3. 不达标 → 组内二分定位关键算子
4. 预计搜索轮次：5 组 × ~3 轮 = ~15 轮（vs 旧版逐个遍历 38 轮）

新增功能：
- --runtime-ops: 只搜索运行时实际调用的算子
- --group-search: 分组二分搜索（默认启用）
- --multi-throughput: 接受多并发级别吞吐量，用最小值判定
- mapping 子命令: 输出运行时算子名 <-> aten 算子名映射

注意：此脚本设计为被 Claude Code 调用，不直接执行 benchmark。
它生成配置文件和操作指令，由 Claude Code 执行实际的服务重启和 benchmark。

Usage:
    # 初始化（基本）
    python operator_optimizer.py init --ops-file ops.json --native-throughput 1000.0

    # 初始化（仅搜索运行时算子）
    python operator_optimizer.py init --ops-file ops.json --runtime-ops runtime.json --native-throughput 1000.0

    # 获取下一步操作（分组二分搜索）
    python operator_optimizer.py next --state-path state.json

    # 更新结果（多并发吞吐量）
    python operator_optimizer.py update --op-name softmax --throughputs '{"1":800,"64":900,"256":850}'

    # 生成算子名映射
    python operator_optimizer.py mapping --gems-path /path/to/flag_gems
"""

import sys

# IO 缓冲修复：确保容器内实时输出
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
else:
    import functools
    print = functools.partial(print, flush=True)

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# =============================================================================
# 算子分组定义
# =============================================================================

OPERATOR_GROUPS = {
    "compute": [
        "addmm", "mm", "bmm", "linear", "matmul",
        "conv2d", "conv_depthwise2d",
    ],
    "memory": [
        "copy_", "zero_", "zeros", "ones", "ones_like", "full", "fill_scalar_",
        "clone", "to_copy", "empty_like", "new_zeros", "new_ones",
    ],
    "math": [
        "cos", "sin", "pow_scalar", "reciprocal", "exp", "log", "sqrt", "rsqrt",
        "abs", "neg", "tanh", "sigmoid", "gelu", "silu", "relu",
        "add", "sub", "mul", "div", "add_scalar", "sub_scalar", "mul_scalar",
        "div_scalar",
    ],
    "index": [
        "gather", "scatter", "scatter_add_0", "index", "index_select",
        "embedding", "slice_scatter", "select_scatter",
    ],
    "reduce": [
        "cumsum", "sort", "sort_stable", "argmax", "arange_start",
        "sum", "mean", "max", "min", "softmax", "log_softmax",
        "layer_norm", "rms_norm", "group_norm",
    ],
}

# 运行时函数名 -> aten 算子名 映射（常见的不一致项）
RUNTIME_TO_ATEN_MAP = {
    "arange_start": "arange.start",
    "arange_start_step": "arange.start_step",
    "add_scalar": "add.Scalar",
    "sub_scalar": "sub.Scalar",
    "mul_scalar": "mul.Scalar",
    "div_scalar": "div.Scalar",
    "pow_scalar": "pow.Scalar",
    "pow_tensor_scalar": "pow.Tensor_Scalar",
    "fill_scalar_": "fill_.Scalar",
    "scatter_add_0": "scatter_add",
    "sort_stable": "sort.stable",
    "to_copy": "_to_copy",
    "conv_depthwise2d": "_conv_depthwise2d",
    "new_zeros": "new_zeros",
    "new_ones": "new_ones",
}

# aten 算子名 -> 运行时函数名 反向映射
ATEN_TO_RUNTIME_MAP = {v: k for k, v in RUNTIME_TO_ATEN_MAP.items()}


# =============================================================================
# 算子列表自动发现
# =============================================================================

def find_ops_list_file(gems_path: Optional[str] = None) -> Dict[str, Any]:
    """
    自动搜索 flaggems 源码中记录算子启动列表的 txt 文件。

    不硬编码 gems.txt，而是在 flag_gems 安装目录下搜索所有 .txt 文件，
    通过内容特征（每行一个算子名）识别算子列表文件。

    Returns:
        {
            "found": bool,
            "path": str,         # 找到的文件路径
            "ops": list,         # 解析出的算子列表
            "count": int,
            "search_paths": list # 搜索过的路径
        }
    """
    result = {
        "found": False,
        "path": "",
        "ops": [],
        "count": 0,
        "search_paths": [],
    }

    # 确定搜索起点
    search_root = gems_path
    if not search_root:
        try:
            import flag_gems
            search_root = os.path.dirname(flag_gems.__file__)
        except ImportError:
            result["error"] = "flag_gems not installed"
            return result

    if not os.path.isdir(search_root):
        result["error"] = f"path not found: {search_root}"
        return result

    # 搜索所有 .txt 文件
    candidates = []
    for root, dirs, files in os.walk(search_root):
        for fname in files:
            if not fname.endswith('.txt'):
                continue
            fpath = os.path.join(root, fname)
            result["search_paths"].append(fpath)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if not content:
                    continue
                lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
                # 特征判断：每行是一个短标识符（算子名通常 < 40 字符，无空格）
                if len(lines) >= 5 and all(len(l) < 40 and ' ' not in l for l in lines):
                    # 进一步验证：至少有一些已知的算子名
                    known_ops = {"addmm", "mm", "bmm", "softmax", "cos", "sin", "exp",
                                 "relu", "gelu", "silu", "mul", "add", "sub", "div",
                                 "layer_norm", "rms_norm", "embedding", "zeros", "ones"}
                    overlap = set(lines) & known_ops
                    score = len(overlap)
                    candidates.append((score, len(lines), fpath, lines))
            except Exception:
                continue

    if candidates:
        # 选择匹配已知算子数最多的文件
        candidates.sort(key=lambda x: (-x[0], -x[1]))
        best = candidates[0]
        result["found"] = True
        result["path"] = best[2]
        result["ops"] = best[3]
        result["count"] = len(best[3])
        if len(candidates) > 1:
            result["other_candidates"] = [c[2] for c in candidates[1:]]

    return result


# =============================================================================
# 状态管理
# =============================================================================

DEFAULT_STATE_PATH = Path("/flagos-workspace/results/operator_config.json")


def load_state(state_path: Optional[str] = None) -> Dict[str, Any]:
    """加载优化状态"""
    p = Path(state_path) if state_path else DEFAULT_STATE_PATH
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "all_ops": [],
        "search_ops": [],
        "enabled_ops": [],
        "disabled_ops": [],
        "native_throughput": 0.0,
        "target_ratio": 0.8,
        "current_ratio": 0.0,
        "search_log": [],
        "status": "not_started",  # not_started | in_progress | completed | failed
        "search_mode": "group",  # group | linear
        "group_state": {},
        "current_step": 0,
        "current_op": "",
    }


def save_state(state: Dict[str, Any], state_path: Optional[str] = None):
    """保存优化状态"""
    p = Path(state_path) if state_path else DEFAULT_STATE_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    print(f"状态已保存: {p}")


# =============================================================================
# 算子分组工具
# =============================================================================

def classify_ops(ops: List[str]) -> Dict[str, List[str]]:
    """将算子按功能分组，未归类的放入 'other'"""
    classified = {group: [] for group in OPERATOR_GROUPS}
    classified["other"] = []

    known_ops: Set[str] = set()
    for group_ops in OPERATOR_GROUPS.values():
        known_ops.update(group_ops)

    for op in ops:
        placed = False
        for group_name, group_ops in OPERATOR_GROUPS.items():
            if op in group_ops:
                classified[group_name].append(op)
                placed = True
                break
        if not placed:
            classified["other"].append(op)

    # 移除空组
    return {k: v for k, v in classified.items() if v}


def filter_runtime_ops(all_ops: List[str], runtime_ops: List[str]) -> List[str]:
    """过滤出运行时实际调用的算子（交集）"""
    all_set = set(all_ops)
    result = []
    for op in runtime_ops:
        # 直接匹配
        if op in all_set:
            result.append(op)
            continue
        # 尝试映射：运行时名 -> 注册名
        mapped = RUNTIME_TO_ATEN_MAP.get(op)
        if mapped and mapped in all_set:
            result.append(mapped)
            continue
        # 尝试反向映射：aten 名 -> 运行时名
        mapped = ATEN_TO_RUNTIME_MAP.get(op)
        if mapped and mapped in all_set:
            result.append(mapped)
            continue
    return sorted(set(result))


# =============================================================================
# 初始化
# =============================================================================

def init_optimization(ops_file: str, native_throughput: float,
                      target_ratio: float = 0.8,
                      runtime_ops_file: Optional[str] = None,
                      group_search: bool = True,
                      state_path: Optional[str] = None) -> Dict[str, Any]:
    """
    初始化优化状态。

    Args:
        ops_file: 算子列表 JSON 文件路径（全量注册算子）
        native_throughput: 原生性能基线吞吐量 (tok/s)
        target_ratio: 性能目标比率
        runtime_ops_file: 运行时实际调用的算子列表 JSON（可选）
        group_search: 启用分组二分搜索（默认 True）
    """
    with open(ops_file, "r", encoding="utf-8") as f:
        ops_data = json.load(f)

    if isinstance(ops_data, list):
        all_ops = ops_data
    elif isinstance(ops_data, dict):
        all_ops = ops_data.get("registered_ops", ops_data.get("ops", []))
    else:
        print("ERROR: 无法解析算子列表文件")
        sys.exit(1)

    all_ops = sorted(all_ops)

    # 确定搜索范围
    search_ops = all_ops
    if runtime_ops_file:
        with open(runtime_ops_file, "r", encoding="utf-8") as f:
            runtime_data = json.load(f)
        if isinstance(runtime_data, list):
            runtime_list = runtime_data
        elif isinstance(runtime_data, dict):
            runtime_list = runtime_data.get("ops", runtime_data.get("runtime_ops", []))
        else:
            runtime_list = []
        search_ops = filter_runtime_ops(all_ops, runtime_list)
        print(f"运行时算子过滤: {len(all_ops)} 全量 -> {len(search_ops)} 运行时")

    # 分组信息
    groups = classify_ops(search_ops)
    group_state = {}
    if group_search:
        group_order = ["compute", "memory", "math", "index", "reduce", "other"]
        group_state = {
            "group_order": [g for g in group_order if g in groups],
            "current_group_idx": 0,
            "phase": "group_test",  # group_test | binary_search | done
            "binary_state": None,  # {low, high, ops, mid_ops}
            "group_results": {},  # group_name -> "all_disabled" | "binary_searched"
        }

    state = {
        "all_ops": all_ops,
        "search_ops": search_ops,
        "enabled_ops": sorted(all_ops),
        "disabled_ops": [],
        "native_throughput": native_throughput,
        "target_ratio": target_ratio,
        "current_ratio": 0.0,
        "search_log": [],
        "status": "in_progress",
        "search_mode": "group" if group_search else "linear",
        "group_state": group_state,
        "groups": groups,
        "current_step": 0,
        "current_op": "",
        "created_at": datetime.now().isoformat(),
    }

    save_state(state, state_path)

    print(f"优化已初始化: {len(all_ops)} 个算子, 搜索范围 {len(search_ops)} 个")
    print(f"搜索模式: {'分组二分' if group_search else '线性'}")
    if group_search:
        for gname, gops in groups.items():
            print(f"  {gname}: {len(gops)} 个算子 ({', '.join(gops[:5])}{'...' if len(gops) > 5 else ''})")
    print(f"原生吞吐量: {native_throughput:.2f} tok/s")
    print(f"目标吞吐量: {native_throughput * target_ratio:.2f} tok/s")

    return state


# =============================================================================
# 分组二分搜索
# =============================================================================

def get_next_action_group(state: Dict[str, Any], state_path: Optional[str] = None) -> Dict[str, Any]:
    """分组二分搜索的下一步操作"""
    gs = state["group_state"]
    groups = state.get("groups", {})

    if gs["phase"] == "done" or gs["current_group_idx"] >= len(gs["group_order"]):
        state["status"] = "completed"
        state["completed_at"] = datetime.now().isoformat()
        save_state(state, state_path)
        return {"action": "completed", "message": "所有组搜索完成"}

    current_group = gs["group_order"][gs["current_group_idx"]]
    group_ops = groups.get(current_group, [])

    if gs["phase"] == "group_test":
        # 阶段 1：整组禁用测试
        test_enabled = [op for op in state["enabled_ops"] if op not in group_ops]
        test_disabled = sorted(set(state["disabled_ops"] + group_ops))

        state["current_step"] += 1
        save_state(state, state_path)

        return {
            "action": "test_disable_group",
            "group": current_group,
            "group_ops": group_ops,
            "step": state["current_step"],
            "test_enabled_ops": test_enabled,
            "test_disabled_ops": test_disabled,
            "message": f"测试整组禁用 '{current_group}' ({len(group_ops)} 个算子)",
        }

    elif gs["phase"] == "binary_search":
        # 阶段 2：组内二分定位
        bs = gs["binary_state"]
        if not bs or bs["low"] >= bs["high"]:
            # 二分搜索完成，进入下一组
            gs["group_results"][current_group] = "binary_searched"
            gs["current_group_idx"] += 1
            gs["phase"] = "group_test"
            gs["binary_state"] = None
            save_state(state, state_path)
            return get_next_action_group(state, state_path)

        mid = (bs["low"] + bs["high"]) // 2
        # 禁用前半部分 [low, mid]
        mid_ops = bs["ops"][bs["low"]:mid + 1]
        bs["mid"] = mid
        bs["mid_ops"] = mid_ops

        test_enabled = [op for op in state["enabled_ops"] if op not in mid_ops]
        test_disabled = sorted(set(state["disabled_ops"] + mid_ops))

        state["current_step"] += 1
        save_state(state, state_path)

        return {
            "action": "test_disable_binary",
            "group": current_group,
            "binary_range": f"[{bs['low']}, {mid}] of {len(bs['ops'])}",
            "test_ops": mid_ops,
            "step": state["current_step"],
            "test_enabled_ops": test_enabled,
            "test_disabled_ops": test_disabled,
            "message": f"二分搜索 '{current_group}': 测试禁用 {len(mid_ops)} 个算子 [{bs['low']}:{mid}]",
        }

    return {"action": "error", "message": f"未知阶段: {gs['phase']}"}


def get_next_action_linear(state: Dict[str, Any], state_path: Optional[str] = None) -> Dict[str, Any]:
    """线性逐个搜索的下一步操作（兼容旧模式）"""
    step = state["current_step"]
    search_ops = state.get("search_ops", state["all_ops"])

    if step >= len(search_ops):
        state["status"] = "completed"
        save_state(state, state_path)
        return {"action": "completed", "message": "所有算子已测试"}

    current_op = search_ops[step]
    state["current_op"] = current_op
    save_state(state, state_path)

    test_enabled = [op for op in state["enabled_ops"] if op != current_op]

    return {
        "action": "test_disable",
        "op": current_op,
        "step": step + 1,
        "total_steps": len(search_ops),
        "test_enabled_ops": test_enabled,
        "test_disabled_ops": state["disabled_ops"] + [current_op],
        "message": f"测试禁用算子 '{current_op}' (步骤 {step+1}/{len(search_ops)})",
    }


def get_next_action(state_path: Optional[str] = None) -> Dict[str, Any]:
    """获取下一步操作指令（自动选择搜索模式）"""
    state = load_state(state_path)

    if state["status"] == "completed":
        return {"action": "completed", "message": "优化已完成"}
    if state["status"] == "failed":
        return {"action": "failed", "message": "优化失败"}
    if state["status"] == "not_started":
        return {"action": "error", "message": "请先执行 init"}

    if state.get("search_mode") == "group":
        return get_next_action_group(state, state_path)
    else:
        return get_next_action_linear(state, state_path)


# =============================================================================
# 结果更新
# =============================================================================

def compute_min_ratio(throughputs: Dict[str, float], native_throughput: float) -> float:
    """计算多并发级别中的最小 ratio"""
    if not throughputs:
        return 0.0
    ratios = [t / native_throughput for t in throughputs.values() if native_throughput > 0]
    return min(ratios) if ratios else 0.0


def update_result(op_name: str, throughput: Optional[float] = None,
                  native_throughput: Optional[float] = None,
                  throughputs: Optional[str] = None,
                  state_path: Optional[str] = None) -> Dict[str, Any]:
    """
    更新某个算子/组禁用测试的结果。

    支持两种输入方式：
    1. 单一吞吐量: --throughput + --native-throughput
    2. 多并发吞吐量: --throughputs '{"1":800,"64":900}' + --native-throughput
       判定使用所有并发级别的最小 ratio
    """
    state = load_state(state_path)
    native_tp = native_throughput or state.get("native_throughput", 0)
    target_ratio = state["target_ratio"]

    # 计算 ratio
    if throughputs:
        tp_dict = json.loads(throughputs) if isinstance(throughputs, str) else throughputs
        ratio = compute_min_ratio(tp_dict, native_tp)
        throughput_val = min(tp_dict.values()) if tp_dict else 0
    elif throughput is not None:
        ratio = throughput / native_tp if native_tp > 0 else 0
        throughput_val = throughput
    else:
        print("ERROR: 必须提供 --throughput 或 --throughputs")
        sys.exit(1)

    log_entry = {
        "op": op_name,
        "throughput": throughput_val,
        "ratio": ratio,
        "timestamp": datetime.now().isoformat(),
    }
    if throughputs:
        log_entry["throughputs"] = json.loads(throughputs) if isinstance(throughputs, str) else throughputs

    search_mode = state.get("search_mode", "linear")

    if search_mode == "group":
        _update_group_result(state, op_name, ratio, target_ratio, log_entry)
    else:
        _update_linear_result(state, op_name, ratio, target_ratio, log_entry)

    state["search_log"].append(log_entry)
    state["current_ratio"] = ratio

    # 检查线性模式是否完成
    search_ops = state.get("search_ops", state["all_ops"])
    if search_mode == "linear" and state["current_step"] >= len(search_ops):
        state["status"] = "completed"
        state["completed_at"] = datetime.now().isoformat()

    save_state(state, state_path)

    return {
        "decision": log_entry.get("decision", "unknown"),
        "ratio": ratio,
        "enabled_ops": state["enabled_ops"],
        "disabled_ops": state["disabled_ops"],
        "progress": f"step {state['current_step']}",
        "status": state["status"],
    }


def _update_group_result(state: Dict[str, Any], op_name: str,
                         ratio: float, target_ratio: float,
                         log_entry: Dict[str, Any]):
    """处理分组搜索模式的结果更新"""
    gs = state["group_state"]
    groups = state.get("groups", {})

    if gs["current_group_idx"] >= len(gs["group_order"]):
        return

    current_group = gs["group_order"][gs["current_group_idx"]]
    group_ops = groups.get(current_group, [])

    if gs["phase"] == "group_test":
        if ratio >= target_ratio:
            # 整组禁用仍达标 → 全部禁用
            log_entry["decision"] = "group_disabled"
            log_entry["reason"] = f"整组 {current_group} 禁用后 ratio {ratio*100:.1f}% >= {target_ratio*100:.0f}%"
            for op in group_ops:
                if op in state["enabled_ops"]:
                    state["enabled_ops"].remove(op)
                if op not in state["disabled_ops"]:
                    state["disabled_ops"].append(op)
            gs["group_results"][current_group] = "all_disabled"
            gs["current_group_idx"] += 1
            print(f"  [{current_group}] 整组禁用 - {ratio*100:.1f}% >= {target_ratio*100:.0f}%")
        else:
            # 不达标 → 进入二分搜索
            log_entry["decision"] = "need_binary_search"
            log_entry["reason"] = f"整组 {current_group} 禁用后 ratio {ratio*100:.1f}% < {target_ratio*100:.0f}%"
            gs["phase"] = "binary_search"
            gs["binary_state"] = {
                "ops": group_ops,
                "low": 0,
                "high": len(group_ops) - 1,
                "mid": 0,
                "mid_ops": [],
            }
            print(f"  [{current_group}] 需要二分搜索 - {ratio*100:.1f}% < {target_ratio*100:.0f}%")

    elif gs["phase"] == "binary_search":
        bs = gs["binary_state"]
        mid = bs["mid"]
        mid_ops = bs["mid_ops"]

        if ratio >= target_ratio:
            # 禁用前半部分仍达标 → 前半部分可以禁用，继续搜索后半部分
            log_entry["decision"] = "binary_disabled_half"
            for op in mid_ops:
                if op in state["enabled_ops"]:
                    state["enabled_ops"].remove(op)
                if op not in state["disabled_ops"]:
                    state["disabled_ops"].append(op)
            bs["low"] = mid + 1
            print(f"  [{current_group}] 二分: 前半可禁用 [{bs['low']-len(mid_ops)},{mid}], "
                  f"继续搜索 [{bs['low']},{bs['high']}]")
        else:
            # 不达标 → 前半部分有关键算子，缩小搜索到前半部分
            log_entry["decision"] = "binary_kept_half"
            if mid_ops and len(mid_ops) == 1:
                # 单个算子已定位 → 保留它，继续下一段
                print(f"  [{current_group}] 二分: 定位关键算子 '{mid_ops[0]}', 保留")
                bs["low"] = mid + 1
            else:
                bs["high"] = mid
                print(f"  [{current_group}] 二分: 前半有关键算子, "
                      f"缩小到 [{bs['low']},{bs['high']}]")

        # 检查二分是否完成
        if bs["low"] > bs["high"]:
            gs["group_results"][current_group] = "binary_searched"
            gs["current_group_idx"] += 1
            gs["phase"] = "group_test"
            gs["binary_state"] = None
            print(f"  [{current_group}] 二分搜索完成")


def _update_linear_result(state: Dict[str, Any], op_name: str,
                          ratio: float, target_ratio: float,
                          log_entry: Dict[str, Any]):
    """处理线性搜索模式的结果更新"""
    if ratio >= target_ratio:
        log_entry["decision"] = "disabled"
        log_entry["reason"] = f"ratio {ratio*100:.1f}% >= target {target_ratio*100:.0f}%"
        if op_name in state["enabled_ops"]:
            state["enabled_ops"].remove(op_name)
        if op_name not in state["disabled_ops"]:
            state["disabled_ops"].append(op_name)
        print(f"  [{op_name}] DISABLED - {ratio*100:.1f}% >= {target_ratio*100:.0f}%")
    else:
        log_entry["decision"] = "kept"
        log_entry["reason"] = f"ratio {ratio*100:.1f}% < target {target_ratio*100:.0f}%"
        if op_name not in state["enabled_ops"]:
            state["enabled_ops"].append(op_name)
            state["enabled_ops"].sort()
        if op_name in state["disabled_ops"]:
            state["disabled_ops"].remove(op_name)
        print(f"  [{op_name}] KEPT - {ratio*100:.1f}% < {target_ratio*100:.0f}%")

    state["current_step"] += 1


# =============================================================================
# 算子名映射
# =============================================================================

def generate_mapping(gems_path: Optional[str] = None) -> Dict[str, Any]:
    """
    生成运行时算子名 <-> aten 算子名映射。

    优先从 flag_gems 源码的 @register 装饰器提取，
    回退到内置的静态映射表。
    """
    mapping = {
        "runtime_to_aten": dict(RUNTIME_TO_ATEN_MAP),
        "aten_to_runtime": dict(ATEN_TO_RUNTIME_MAP),
        "source": "builtin",
        "dynamic_entries": [],
    }

    # 尝试从源码提取
    search_path = gems_path
    if not search_path:
        try:
            import flag_gems
            search_path = os.path.dirname(flag_gems.__file__)
        except ImportError:
            pass

    if search_path and os.path.isdir(search_path):
        dynamic = _extract_register_decorators(search_path)
        if dynamic:
            mapping["source"] = "source_code"
            mapping["dynamic_entries"] = dynamic
            for entry in dynamic:
                rt_name = entry.get("func_name", "")
                aten_name = entry.get("aten_name", "")
                if rt_name and aten_name and rt_name != aten_name:
                    mapping["runtime_to_aten"][rt_name] = aten_name
                    mapping["aten_to_runtime"][aten_name] = rt_name

    return mapping


def _extract_register_decorators(gems_path: str) -> List[Dict[str, str]]:
    """从 flag_gems 源码中提取 @register 装饰器的映射信息"""
    entries = []
    pattern = re.compile(
        r'@(?:flag_gems\.)?register\s*\(\s*["\']([^"\']+)["\']\s*\)'
    )

    for root, dirs, files in os.walk(gems_path):
        for fname in files:
            if not fname.endswith('.py'):
                continue
            filepath = os.path.join(root, fname)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                for match in pattern.finditer(content):
                    aten_name = match.group(1)
                    # 找到紧接的 def 行
                    rest = content[match.end():]
                    def_match = re.search(r'\ndef\s+(\w+)\s*\(', rest)
                    if def_match:
                        func_name = def_match.group(1)
                        entries.append({
                            "aten_name": aten_name,
                            "func_name": func_name,
                            "file": filepath,
                        })
            except Exception:
                continue

    return entries


# =============================================================================
# 报告生成
# =============================================================================

def generate_report(state_path: Optional[str] = None) -> str:
    """生成优化报告"""
    state = load_state(state_path)

    report = []
    report.append("=" * 60)
    report.append("算子优化报告")
    report.append("=" * 60)
    report.append(f"状态: {state['status']}")
    report.append(f"搜索模式: {state.get('search_mode', 'linear')}")
    report.append(f"原生吞吐量: {state['native_throughput']:.2f} tok/s")
    report.append(f"目标比率: {state['target_ratio']*100:.0f}%")
    report.append(f"目标吞吐量: {state['native_throughput'] * state['target_ratio']:.2f} tok/s")
    report.append(f"")
    report.append(f"总算子数: {len(state['all_ops'])}")
    report.append(f"搜索范围: {len(state.get('search_ops', state['all_ops']))}")
    report.append(f"启用算子: {len(state['enabled_ops'])}")
    report.append(f"禁用算子: {len(state['disabled_ops'])}")
    report.append(f"总搜索步数: {state['current_step']}")
    report.append(f"")

    # 分组搜索结果
    gs = state.get("group_state", {})
    if gs.get("group_results"):
        report.append("分组搜索结果:")
        for gname, gresult in gs["group_results"].items():
            group_ops = state.get("groups", {}).get(gname, [])
            disabled_in_group = [op for op in group_ops if op in state["disabled_ops"]]
            report.append(f"  {gname}: {gresult} ({len(disabled_in_group)}/{len(group_ops)} 禁用)")
        report.append("")

    if state["disabled_ops"]:
        report.append("禁用的算子:")
        for op in sorted(state["disabled_ops"]):
            reason = ""
            for log in state["search_log"]:
                if log.get("op") == op and "disabled" in log.get("decision", ""):
                    reason = f"({log.get('throughput', 0):.2f} tok/s, {log.get('ratio', 0)*100:.1f}%)"
                    break
            report.append(f"  - {op} {reason}")
    else:
        report.append("无需禁用任何算子")

    report.append("")
    report.append("搜索日志:")
    for i, log in enumerate(state["search_log"]):
        tp = log.get('throughput', 0)
        r = log.get('ratio', 0)
        report.append(f"  {i+1}. {log.get('op', '?')}: {log.get('decision', '?')} - "
                       f"{tp:.2f} tok/s ({r*100:.1f}%)")

    result = "\n".join(report)
    print(result)
    return result


# =============================================================================
# 主入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="算子优化器 - 分组二分搜索最优算子集")
    subparsers = parser.add_subparsers(dest="command", help="操作命令")

    # init 子命令
    init_parser = subparsers.add_parser("init", help="初始化优化")
    init_parser.add_argument("--ops-file", required=True, help="算子列表 JSON 文件")
    init_parser.add_argument("--native-throughput", type=float, required=True, help="原生吞吐量 (tok/s)")
    init_parser.add_argument("--target-ratio", type=float, default=0.8, help="性能目标比率")
    init_parser.add_argument("--runtime-ops", help="运行时实际调用的算子列表 JSON（可选，只搜索这些算子）")
    init_parser.add_argument("--no-group-search", action="store_true", help="禁用分组二分，使用线性搜索")
    init_parser.add_argument("--state-path", help="状态文件路径")

    # next 子命令
    next_parser = subparsers.add_parser("next", help="获取下一步操作")
    next_parser.add_argument("--state-path", help="状态文件路径")

    # update 子命令
    update_parser = subparsers.add_parser("update", help="更新测试结果")
    update_parser.add_argument("--op-name", required=True, help="被测试的算子/组名")
    update_parser.add_argument("--throughput", type=float, help="禁用后的吞吐量（单一值）")
    update_parser.add_argument("--native-throughput", type=float, help="原生基线吞吐量")
    update_parser.add_argument("--throughputs", help='多并发吞吐量 JSON: {"1":800,"64":900}')
    update_parser.add_argument("--state-path", help="状态文件路径")

    # report 子命令
    report_parser = subparsers.add_parser("report", help="生成优化报告")
    report_parser.add_argument("--state-path", help="状态文件路径")

    # status 子命令
    status_parser = subparsers.add_parser("status", help="查看当前状态")
    status_parser.add_argument("--state-path", help="状态文件路径")

    # mapping 子命令
    mapping_parser = subparsers.add_parser("mapping", help="生成算子名映射表")
    mapping_parser.add_argument("--gems-path", help="flag_gems 源码路径（可选，自动探测）")
    mapping_parser.add_argument("--output", help="输出 JSON 文件路径")

    # discover 子命令
    discover_parser = subparsers.add_parser("discover", help="自动搜索算子列表文件")
    discover_parser.add_argument("--gems-path", help="flag_gems 源码路径（可选，自动探测）")
    discover_parser.add_argument("--save-ops", help="将发现的算子列表保存为 JSON 文件")

    args = parser.parse_args()

    if args.command == "init":
        init_optimization(
            args.ops_file, args.native_throughput,
            args.target_ratio,
            runtime_ops_file=args.runtime_ops,
            group_search=not args.no_group_search,
            state_path=args.state_path,
        )

    elif args.command == "next":
        action = get_next_action(args.state_path)
        print(json.dumps(action, indent=2, ensure_ascii=False))

    elif args.command == "update":
        result = update_result(
            args.op_name,
            throughput=args.throughput,
            native_throughput=args.native_throughput,
            throughputs=args.throughputs,
            state_path=args.state_path,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "report":
        generate_report(args.state_path)

    elif args.command == "status":
        state = load_state(args.state_path)
        status_info = {
            "status": state["status"],
            "search_mode": state.get("search_mode", "linear"),
            "progress": f"step {state['current_step']}",
            "total_ops": len(state["all_ops"]),
            "search_ops": len(state.get("search_ops", state["all_ops"])),
            "enabled": len(state["enabled_ops"]),
            "disabled": len(state["disabled_ops"]),
            "current_op": state.get("current_op", ""),
        }
        gs = state.get("group_state", {})
        if gs:
            status_info["group_progress"] = gs.get("group_results", {})
            idx = gs.get("current_group_idx", 0)
            order = gs.get("group_order", [])
            status_info["current_group"] = order[idx] if idx < len(order) else "done"
        print(json.dumps(status_info, indent=2, ensure_ascii=False))

    elif args.command == "mapping":
        mapping = generate_mapping(getattr(args, 'gems_path', None))
        output = json.dumps(mapping, indent=2, ensure_ascii=False)
        print(output)
        if hasattr(args, 'output') and args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f"\n映射表已保存: {args.output}")

    elif args.command == "discover":
        result = find_ops_list_file(getattr(args, 'gems_path', None))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result["found"] and args.save_ops:
            save_path = Path(args.save_ops)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(sorted(result["ops"]), f, indent=2, ensure_ascii=False)
            print(f"\n算子列表已保存: {save_path} ({result['count']} 个算子)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
