#!/usr/bin/env python3
"""
算子搜索编排脚本 — 自动化完整搜索循环

将 算子优化器(next) → toggle FlagGems → 重启服务 → benchmark → 更新结果(update) 的完整循环
封装为一次脚本调用，避免 Claude Code 在搜索循环中消耗思考 token。

此脚本在**容器内**运行，直接调用各工具脚本。

Usage:
    # 运行完整搜索循环（直到搜索完成或达到最大轮次）
    python operator_search.py run \
        --state-path /flagos-workspace/results/operator_config.json \
        --perf-config /flagos-workspace/perf/config/perf_config.yaml \
        --service-startup-cmd "bash /flagos-workspace/scripts/start_service.sh" \
        --max-rounds 20

    # 只运行一轮搜索
    python operator_search.py step \
        --state-path /flagos-workspace/results/operator_config.json \
        --perf-config /flagos-workspace/perf/config/perf_config.yaml \
        --service-startup-cmd "bash /flagos-workspace/scripts/start_service.sh"

    # 查看当前状态
    python operator_search.py status --state-path /flagos-workspace/results/operator_config.json
"""

import sys

# IO 缓冲修复
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
else:
    import functools
    print = functools.partial(print, flush=True)

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# =============================================================================
# 配置
# =============================================================================

DEFAULT_STATE_PATH = "/flagos-workspace/results/operator_config.json"
DEFAULT_PERF_CONFIG = "/flagos-workspace/perf/config/perf_config.yaml"
DEFAULT_TOGGLE_SCRIPT = "/flagos-workspace/scripts/toggle_flaggems.py"
DEFAULT_BENCHMARK_SCRIPT = "/flagos-workspace/scripts/benchmark_runner.py"
DEFAULT_OPTIMIZER_SCRIPT = "/flagos-workspace/scripts/operator_optimizer.py"
DEFAULT_WAIT_SCRIPT = "/flagos-workspace/scripts/wait_for_service.sh"

SERVICE_STOP_CMD = "pkill -f 'vllm\\|sglang'"
SERVICE_WAIT_TIMEOUT = 300  # 秒


# =============================================================================
# 工具函数
# =============================================================================

def run_cmd(cmd: str, timeout: int = 600, check: bool = True) -> subprocess.CompletedProcess:
    """执行命令并实时输出"""
    print(f"  $ {cmd}")
    proc = subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True
    )
    output_lines = []
    for line in proc.stdout:
        output_lines.append(line)
        print(f"    | {line.rstrip()}")
    proc.wait()
    result = subprocess.CompletedProcess(
        cmd, proc.returncode,
        stdout="".join(output_lines),
        stderr=""
    )
    if check and proc.returncode != 0:
        print(f"  WARN: 命令返回码 {proc.returncode}")
    return result


def load_json(path: str) -> Dict[str, Any]:
    """加载 JSON 文件"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data: Any, path: str):
    """保存 JSON 文件"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# =============================================================================
# 搜索步骤
# =============================================================================

def get_next_action(state_path: str, optimizer_script: str) -> Dict[str, Any]:
    """调用 operator_optimizer.py next 获取下一步操作"""
    result = run_cmd(
        f"python {optimizer_script} next --state-path {state_path}",
        check=False
    )
    try:
        # 从输出中提取 JSON
        output = result.stdout.strip()
        # 找到第一个 { 和最后一个 }
        start = output.index('{')
        end = output.rindex('}') + 1
        return json.loads(output[start:end])
    except (ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: 解析 next 输出失败: {e}")
        return {"action": "error", "message": str(e)}


def apply_operator_config(enabled_ops: List[str], toggle_script: str,
                          gems_txt_path: Optional[str] = None) -> bool:
    """应用算子配置 — 通过 toggle_flaggems.py 更新 gems.txt"""
    if not gems_txt_path:
        print("  WARN: 未指定 gems_txt_path，跳过算子配置")
        return True

    # 写入临时算子列表
    tmp_ops = "/tmp/search_ops.json"
    save_json(enabled_ops, tmp_ops)

    # 写入 gems.txt
    print(f"  写入 {len(enabled_ops)} 个算子到 {gems_txt_path}")
    with open(gems_txt_path, 'w', encoding='utf-8') as f:
        for op in sorted(enabled_ops):
            f.write(f"{op}\n")

    return True


def restart_service(stop_cmd: str, startup_cmd: str,
                    wait_script: str, wait_timeout: int = SERVICE_WAIT_TIMEOUT) -> bool:
    """重启服务：停止 → 启动 → 等待就绪"""
    print("\n[重启服务]")

    # 清除 Triton cache
    print("  清除 Triton cache...")
    run_cmd("rm -rf ~/.triton/cache/ 2>/dev/null", check=False)
    run_cmd("rm -rf /tmp/triton_cache/ 2>/dev/null", check=False)

    # 停止
    print("  停止服务...")
    run_cmd(stop_cmd, check=False)
    time.sleep(5)

    # 启动
    print("  启动服务...")
    run_cmd(startup_cmd, check=False)

    # 等待就绪
    print(f"  等待服务就绪 (最多 {wait_timeout}s)...")
    result = run_cmd(
        f"bash {wait_script} --timeout {wait_timeout}",
        timeout=wait_timeout + 30,
        check=False
    )
    if result.returncode != 0:
        print("  ERROR: 服务启动失败")
        return False

    print("  服务就绪")
    return True


def run_benchmark_quick(perf_config: str, benchmark_script: str,
                        output_name: str = "search_benchmark") -> Dict[str, Any]:
    """运行快速 benchmark（用于搜索阶段）"""
    print("\n[运行 Benchmark]")

    output_dir = "/flagos-workspace/results"
    result = run_cmd(
        f"python {benchmark_script} "
        f"--config {perf_config} "
        f"--quick "
        f"--output-name {output_name} "
        f"--output-dir {output_dir} "
        f"--mode search",
        timeout=600,
        check=False
    )

    # 解析结果
    output_path = f"{output_dir}/{output_name}.json"
    try:
        data = load_json(output_path)
        results = data.get("results", {})

        # 提取吞吐量
        throughputs = {}
        for tc_name, tc_results in results.items():
            if not isinstance(tc_results, dict):
                continue
            meta = tc_results.get("_search_meta", {})
            best_tp = meta.get("best_throughput", 0)
            if best_tp > 0:
                throughputs[tc_name] = best_tp

        return {"success": True, "throughputs": throughputs, "results": results}
    except Exception as e:
        print(f"  ERROR: 解析 benchmark 结果失败: {e}")
        return {"success": False, "error": str(e)}


def update_optimizer_result(state_path: str, optimizer_script: str,
                            op_name: str, throughputs: Dict[str, float],
                            native_throughput: float) -> Dict[str, Any]:
    """调用 operator_optimizer.py update 更新结果"""
    tp_json = json.dumps(throughputs)
    result = run_cmd(
        f"python {optimizer_script} update "
        f"--op-name {op_name} "
        f"--throughputs '{tp_json}' "
        f"--native-throughput {native_throughput} "
        f"--state-path {state_path}",
        check=False
    )
    try:
        output = result.stdout.strip()
        start = output.index('{')
        end = output.rindex('}') + 1
        return json.loads(output[start:end])
    except (ValueError, json.JSONDecodeError):
        return {"error": "parse failed"}


# =============================================================================
# 主搜索循环
# =============================================================================

def run_search_step(state_path: str, perf_config: str,
                    service_startup_cmd: str,
                    gems_txt_path: Optional[str] = None,
                    optimizer_script: str = DEFAULT_OPTIMIZER_SCRIPT,
                    benchmark_script: str = DEFAULT_BENCHMARK_SCRIPT,
                    toggle_script: str = DEFAULT_TOGGLE_SCRIPT,
                    wait_script: str = DEFAULT_WAIT_SCRIPT) -> Dict[str, Any]:
    """执行单轮搜索步骤"""

    # 1. 获取下一步操作
    print("\n" + "=" * 60)
    print(f"[搜索步骤] {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)

    action = get_next_action(state_path, optimizer_script)
    action_type = action.get("action", "error")

    if action_type in ("completed", "failed", "error"):
        print(f"\n搜索结束: {action.get('message', action_type)}")
        return action

    print(f"\n操作: {action.get('message', action_type)}")

    # 2. 应用算子配置
    test_enabled = action.get("test_enabled_ops", [])
    if not apply_operator_config(test_enabled, toggle_script, gems_txt_path):
        return {"action": "error", "message": "算子配置应用失败"}

    # 3. 重启服务
    if not restart_service(SERVICE_STOP_CMD, service_startup_cmd, wait_script):
        return {"action": "error", "message": "服务重启失败"}

    # 4. 运行 benchmark
    bench_result = run_benchmark_quick(perf_config, benchmark_script,
                                       f"search_step_{action.get('step', 0)}")

    if not bench_result.get("success"):
        return {"action": "error", "message": f"Benchmark 失败: {bench_result.get('error', '?')}"}

    # 5. 更新结果
    state = load_json(state_path)
    native_tp = state.get("native_throughput", 0)
    throughputs = bench_result.get("throughputs", {})

    op_name = action.get("group", action.get("op", "unknown"))
    update = update_optimizer_result(
        state_path, optimizer_script,
        op_name, throughputs, native_tp
    )

    print(f"\n[步骤完成] decision={update.get('decision', '?')}, "
          f"ratio={update.get('ratio', 0)*100:.1f}%")

    return {
        "action": action_type,
        "step": action.get("step", 0),
        "op_name": op_name,
        "decision": update.get("decision", "?"),
        "ratio": update.get("ratio", 0),
        "status": update.get("status", "?"),
    }


def run_full_search(state_path: str, perf_config: str,
                    service_startup_cmd: str,
                    max_rounds: int = 20,
                    gems_txt_path: Optional[str] = None,
                    **kwargs) -> Dict[str, Any]:
    """运行完整搜索循环"""
    print(f"\n{'#' * 60}")
    print(f"# 算子搜索开始 (最多 {max_rounds} 轮)")
    print(f"{'#' * 60}\n")

    search_log = []
    start_time = time.time()

    for round_num in range(1, max_rounds + 1):
        print(f"\n{'=' * 60}")
        print(f"第 {round_num}/{max_rounds} 轮")
        print(f"{'=' * 60}")

        result = run_search_step(
            state_path, perf_config, service_startup_cmd,
            gems_txt_path=gems_txt_path, **kwargs
        )

        search_log.append(result)

        if result.get("action") in ("completed", "failed", "error"):
            break

    elapsed = time.time() - start_time
    total_rounds = len(search_log)

    # 最终状态
    try:
        state = load_json(state_path)
    except Exception:
        state = {}

    summary = {
        "total_rounds": total_rounds,
        "elapsed_seconds": round(elapsed),
        "elapsed_display": f"{int(elapsed // 60)}m{int(elapsed % 60)}s",
        "final_status": state.get("status", "unknown"),
        "enabled_ops": len(state.get("enabled_ops", [])),
        "disabled_ops": len(state.get("disabled_ops", [])),
        "disabled_list": state.get("disabled_ops", []),
        "search_log": search_log,
    }

    print(f"\n{'#' * 60}")
    print(f"# 搜索完成: {total_rounds} 轮, 耗时 {summary['elapsed_display']}")
    print(f"# 状态: {summary['final_status']}")
    print(f"# 启用: {summary['enabled_ops']}, 禁用: {summary['disabled_ops']}")
    if summary["disabled_list"]:
        print(f"# 禁用列表: {', '.join(summary['disabled_list'])}")
    print(f"{'#' * 60}\n")

    # 保存摘要
    summary_path = str(Path(state_path).parent / "search_summary.json")
    save_json(summary, summary_path)
    print(f"搜索摘要已保存: {summary_path}")

    return summary


# =============================================================================
# 主入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="算子搜索编排 — 自动化完整搜索循环")

    subparsers = parser.add_subparsers(dest="command", help="操作命令")

    # 公共参数
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-path", default=DEFAULT_STATE_PATH, help="优化器状态文件")
    common.add_argument("--perf-config", default=DEFAULT_PERF_CONFIG, help="性能测试配置")
    common.add_argument("--service-startup-cmd", required=True, help="服务启动命令")
    common.add_argument("--gems-txt-path", help="gems.txt 路径（可选，用于写入算子列表）")
    common.add_argument("--optimizer-script", default=DEFAULT_OPTIMIZER_SCRIPT)
    common.add_argument("--benchmark-script", default=DEFAULT_BENCHMARK_SCRIPT)
    common.add_argument("--toggle-script", default=DEFAULT_TOGGLE_SCRIPT)
    common.add_argument("--wait-script", default=DEFAULT_WAIT_SCRIPT)

    # run — 完整搜索
    run_parser = subparsers.add_parser("run", parents=[common], help="运行完整搜索循环")
    run_parser.add_argument("--max-rounds", type=int, default=20, help="最大搜索轮次")

    # step — 单步搜索
    step_parser = subparsers.add_parser("step", parents=[common], help="运行单轮搜索")

    # status — 查看状态
    status_parser = subparsers.add_parser("status", help="查看搜索状态")
    status_parser.add_argument("--state-path", default=DEFAULT_STATE_PATH)

    args = parser.parse_args()

    if args.command == "run":
        result = run_full_search(
            args.state_path, args.perf_config,
            args.service_startup_cmd,
            max_rounds=args.max_rounds,
            gems_txt_path=args.gems_txt_path,
            optimizer_script=args.optimizer_script,
            benchmark_script=args.benchmark_script,
            toggle_script=args.toggle_script,
            wait_script=args.wait_script,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "step":
        result = run_search_step(
            args.state_path, args.perf_config,
            args.service_startup_cmd,
            gems_txt_path=args.gems_txt_path,
            optimizer_script=args.optimizer_script,
            benchmark_script=args.benchmark_script,
            toggle_script=args.toggle_script,
            wait_script=args.wait_script,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "status":
        try:
            state = load_json(args.state_path)
            info = {
                "status": state.get("status"),
                "search_mode": state.get("search_mode"),
                "current_step": state.get("current_step"),
                "enabled": len(state.get("enabled_ops", [])),
                "disabled": len(state.get("disabled_ops", [])),
                "disabled_list": state.get("disabled_ops", []),
            }
            gs = state.get("group_state", {})
            if gs:
                idx = gs.get("current_group_idx", 0)
                order = gs.get("group_order", [])
                info["current_group"] = order[idx] if idx < len(order) else "done"
                info["group_results"] = gs.get("group_results", {})
            print(json.dumps(info, indent=2, ensure_ascii=False))
        except FileNotFoundError:
            print(json.dumps({"error": f"状态文件不存在: {args.state_path}"}))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
