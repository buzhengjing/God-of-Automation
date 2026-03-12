#!/usr/bin/env python3
"""
算子优化器 — 贪心搜索最优算子集

通过逐个禁用 FlagGems 算子并重新测试性能，找到使 FlagOS 性能 >= 目标比率（默认 80% native）的最优算子组合。

核心算法：
1. 从全部算子开始
2. 逐个尝试禁用每个算子
3. 禁用后如果仍达标（>= target_ratio），则该算子可以被禁用
4. 禁用后如果不达标，则恢复该算子
5. 输出最终的 enabled/disabled 算子列表

注意：此脚本设计为被 Claude Code 调用，不直接执行 benchmark。
它生成配置文件和操作指令，由 Claude Code 执行实际的服务重启和 benchmark。

Usage:
    python operator_optimizer.py --ops-file /path/to/ops_list.json \
                                  --native-throughput 1000.0 \
                                  --target-ratio 0.8

    python operator_optimizer.py --init \
                                  --ops-file /path/to/ops_list.json

    python operator_optimizer.py --update \
                                  --op-name softmax \
                                  --throughput 850.0 \
                                  --native-throughput 1000.0
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


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
        "enabled_ops": [],
        "disabled_ops": [],
        "native_throughput": 0.0,
        "target_ratio": 0.8,
        "current_ratio": 0.0,
        "search_log": [],
        "status": "not_started",  # not_started | in_progress | completed | failed
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
# 初始化
# =============================================================================

def init_optimization(ops_file: str, native_throughput: float,
                      target_ratio: float = 0.8,
                      state_path: Optional[str] = None) -> Dict[str, Any]:
    """
    初始化优化状态。

    Args:
        ops_file: 算子列表 JSON 文件路径
        native_throughput: 原生性能基线吞吐量 (tok/s)
        target_ratio: 性能目标比率
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

    state = {
        "all_ops": sorted(all_ops),
        "enabled_ops": sorted(all_ops),
        "disabled_ops": [],
        "native_throughput": native_throughput,
        "target_ratio": target_ratio,
        "current_ratio": 0.0,
        "search_log": [],
        "status": "in_progress",
        "current_step": 0,
        "current_op": all_ops[0] if all_ops else "",
        "created_at": datetime.now().isoformat(),
    }

    save_state(state, state_path)
    print(f"优化已初始化: {len(all_ops)} 个算子, 目标比率 {target_ratio*100:.0f}%")
    print(f"原生吞吐量: {native_throughput:.2f} tok/s")
    print(f"目标吞吐量: {native_throughput * target_ratio:.2f} tok/s")

    return state


# =============================================================================
# 贪心搜索步骤
# =============================================================================

def get_next_action(state_path: Optional[str] = None) -> Dict[str, Any]:
    """
    获取下一步操作指令。

    返回一个 action dict，Claude Code 根据此指令执行实际操作：
    - action: "disable_op" | "restore_op" | "completed" | "failed"
    - op: 算子名
    - config: 当前应使用的算子配置
    """
    state = load_state(state_path)

    if state["status"] == "completed":
        return {"action": "completed", "message": "优化已完成"}

    if state["status"] == "failed":
        return {"action": "failed", "message": "优化失败"}

    step = state["current_step"]
    all_ops = state["all_ops"]

    if step >= len(all_ops):
        state["status"] = "completed"
        save_state(state, state_path)
        return {"action": "completed", "message": "所有算子已测试"}

    current_op = all_ops[step]
    state["current_op"] = current_op
    save_state(state, state_path)

    # 生成禁用当前算子后的配置
    test_enabled = [op for op in state["enabled_ops"] if op != current_op]

    return {
        "action": "test_disable",
        "op": current_op,
        "step": step + 1,
        "total_steps": len(all_ops),
        "test_enabled_ops": test_enabled,
        "test_disabled_ops": state["disabled_ops"] + [current_op],
        "message": f"测试禁用算子 '{current_op}' (步骤 {step+1}/{len(all_ops)})",
    }


def update_result(op_name: str, throughput: float, native_throughput: float,
                  state_path: Optional[str] = None) -> Dict[str, Any]:
    """
    更新某个算子禁用测试的结果。

    Args:
        op_name: 被测试禁用的算子名
        throughput: 禁用该算子后的吞吐量
        native_throughput: 原生基线吞吐量
    """
    state = load_state(state_path)

    ratio = throughput / native_throughput if native_throughput > 0 else 0
    target_ratio = state["target_ratio"]

    log_entry = {
        "op": op_name,
        "throughput": throughput,
        "ratio": ratio,
        "timestamp": datetime.now().isoformat(),
    }

    if ratio >= target_ratio:
        # 禁用此算子仍达标 → 保持禁用
        log_entry["decision"] = "disabled"
        log_entry["reason"] = f"ratio {ratio*100:.1f}% >= target {target_ratio*100:.0f}%"

        if op_name in state["enabled_ops"]:
            state["enabled_ops"].remove(op_name)
        if op_name not in state["disabled_ops"]:
            state["disabled_ops"].append(op_name)

        print(f"  [{op_name}] DISABLED - {throughput:.2f} tok/s ({ratio*100:.1f}%) >= {target_ratio*100:.0f}%")
    else:
        # 禁用后不达标 → 恢复此算子
        log_entry["decision"] = "kept"
        log_entry["reason"] = f"ratio {ratio*100:.1f}% < target {target_ratio*100:.0f}%"

        if op_name not in state["enabled_ops"]:
            state["enabled_ops"].append(op_name)
            state["enabled_ops"].sort()
        if op_name in state["disabled_ops"]:
            state["disabled_ops"].remove(op_name)

        print(f"  [{op_name}] KEPT - {throughput:.2f} tok/s ({ratio*100:.1f}%) < {target_ratio*100:.0f}%")

    state["search_log"].append(log_entry)
    state["current_ratio"] = ratio
    state["current_step"] += 1

    # 检查是否完成
    if state["current_step"] >= len(state["all_ops"]):
        state["status"] = "completed"
        state["completed_at"] = datetime.now().isoformat()

    save_state(state, state_path)

    return {
        "decision": log_entry["decision"],
        "enabled_ops": state["enabled_ops"],
        "disabled_ops": state["disabled_ops"],
        "progress": f"{state['current_step']}/{len(state['all_ops'])}",
        "status": state["status"],
    }


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
    report.append(f"原生吞吐量: {state['native_throughput']:.2f} tok/s")
    report.append(f"目标比率: {state['target_ratio']*100:.0f}%")
    report.append(f"目标吞吐量: {state['native_throughput'] * state['target_ratio']:.2f} tok/s")
    report.append(f"")
    report.append(f"总算子数: {len(state['all_ops'])}")
    report.append(f"启用算子: {len(state['enabled_ops'])}")
    report.append(f"禁用算子: {len(state['disabled_ops'])}")
    report.append(f"")

    if state["disabled_ops"]:
        report.append("禁用的算子:")
        for op in state["disabled_ops"]:
            # 查找搜索日志中的原因
            reason = ""
            for log in state["search_log"]:
                if log["op"] == op and log["decision"] == "disabled":
                    reason = f"({log['throughput']:.2f} tok/s, {log['ratio']*100:.1f}%)"
                    break
            report.append(f"  - {op} {reason}")
    else:
        report.append("无需禁用任何算子")

    report.append("")
    report.append("搜索日志:")
    for i, log in enumerate(state["search_log"]):
        report.append(f"  {i+1}. {log['op']}: {log['decision']} - "
                       f"{log['throughput']:.2f} tok/s ({log['ratio']*100:.1f}%)")

    result = "\n".join(report)
    print(result)
    return result


# =============================================================================
# 主入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="算子优化器 - 贪心搜索最优算子集")
    subparsers = parser.add_subparsers(dest="command", help="操作命令")

    # init 子命令
    init_parser = subparsers.add_parser("init", help="初始化优化")
    init_parser.add_argument("--ops-file", required=True, help="算子列表 JSON 文件")
    init_parser.add_argument("--native-throughput", type=float, required=True, help="原生吞吐量 (tok/s)")
    init_parser.add_argument("--target-ratio", type=float, default=0.8, help="性能目标比率")
    init_parser.add_argument("--state-path", help="状态文件路径")

    # next 子命令
    next_parser = subparsers.add_parser("next", help="获取下一步操作")
    next_parser.add_argument("--state-path", help="状态文件路径")

    # update 子命令
    update_parser = subparsers.add_parser("update", help="更新测试结果")
    update_parser.add_argument("--op-name", required=True, help="被测试的算子名")
    update_parser.add_argument("--throughput", type=float, required=True, help="禁用后的吞吐量")
    update_parser.add_argument("--native-throughput", type=float, required=True, help="原生基线吞吐量")
    update_parser.add_argument("--state-path", help="状态文件路径")

    # report 子命令
    report_parser = subparsers.add_parser("report", help="生成优化报告")
    report_parser.add_argument("--state-path", help="状态文件路径")

    # status 子命令
    status_parser = subparsers.add_parser("status", help="查看当前状态")
    status_parser.add_argument("--state-path", help="状态文件路径")

    args = parser.parse_args()

    if args.command == "init":
        init_optimization(args.ops_file, args.native_throughput,
                          args.target_ratio, args.state_path)

    elif args.command == "next":
        action = get_next_action(args.state_path)
        print(json.dumps(action, indent=2, ensure_ascii=False))

    elif args.command == "update":
        result = update_result(args.op_name, args.throughput,
                               args.native_throughput, args.state_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "report":
        generate_report(args.state_path)

    elif args.command == "status":
        state = load_state(args.state_path)
        print(json.dumps({
            "status": state["status"],
            "progress": f"{state['current_step']}/{len(state['all_ops'])}",
            "enabled": len(state["enabled_ops"]),
            "disabled": len(state["disabled_ops"]),
            "current_op": state.get("current_op", ""),
        }, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
