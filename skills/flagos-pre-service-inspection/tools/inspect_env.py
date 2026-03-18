#!/usr/bin/env python3
"""
inspect_env.py — 合并环境检查脚本

一次运行完成全部环境检查，替代原来 10+ 次 docker exec 串行执行。
输出结构化 JSON，可直接写入 context.yaml。

Usage:
    python3 inspect_env.py --output-json    # 输出 JSON（供程序读取）
    python3 inspect_env.py --report         # 输出人类可读报告
    python3 inspect_env.py                  # 同时输出 JSON 和报告
"""

import argparse
import importlib
import inspect
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd, timeout=30):
    """运行 shell 命令并返回 stdout"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout.strip()
    except Exception:
        return ""


def check_execution_mode():
    """检测是否在容器内运行"""
    if os.path.exists("/.dockerenv"):
        return "container"
    try:
        with open("/proc/1/cgroup", "r") as f:
            if "docker" in f.read():
                return "container"
    except Exception:
        pass
    return "host"


def check_core_packages():
    """检查核心组件版本"""
    packages = {}
    for pkg_name, import_name in [("torch", "torch"), ("vllm", "vllm"), ("sglang", "sglang")]:
        try:
            mod = importlib.import_module(import_name)
            packages[pkg_name] = getattr(mod, "__version__", "installed")
        except ImportError:
            packages[pkg_name] = None
    # torch CUDA version
    try:
        import torch
        packages["torch_cuda"] = torch.version.cuda if hasattr(torch.version, "cuda") else None
    except Exception:
        packages["torch_cuda"] = None
    return packages


def check_flag_packages():
    """检查 flag 生态组件版本"""
    packages = {}
    for pkg_name, import_name in [
        ("flaggems", "flag_gems"),
        ("flagscale", "flag_scale"),
        ("flagcx", "flagcx"),
        ("vllm_plugin", "vllm_fl"),
    ]:
        try:
            mod = importlib.import_module(import_name)
            packages[pkg_name] = getattr(mod, "__version__", "installed")
        except ImportError:
            packages[pkg_name] = None
    return packages


def probe_flaggems_capabilities():
    """探测 FlagGems 运行时能力"""
    result = {
        "flaggems_installed": False,
        "capabilities": [],
        "enable_signature": "",
        "enable_params": [],
        "vendor_config_path": "",
        "vllm_plugin_installed": False,
        "plugin_has_dispatch": False,
        "probe_error": "",
        "gpu_compute_capability": "",
        "gpu_arch": "",
        "plugin_env_vars": {},
    }

    # GPU compute capability 探测
    try:
        import torch
        if torch.cuda.is_available():
            major, minor = torch.cuda.get_device_capability(0)
            result["gpu_compute_capability"] = f"{major}.{minor}"
            result["gpu_arch"] = f"sm_{major}{minor}"
    except Exception:
        pass

    # Plugin dispatch 环境变量探测
    for var in ["VLLM_FL_FLAGOS_WHITELIST", "VLLM_FL_PREFER_ENABLED",
                "VLLM_USE_DEEP_GEMM", "VLLM_FL_DISPATCH_MODE"]:
        val = os.environ.get(var)
        if val is not None:
            result["plugin_env_vars"][var] = val

    # 探测 FlagGems
    try:
        import flag_gems

        result["flaggems_installed"] = True

        # enable() 签名
        if hasattr(flag_gems, "enable"):
            sig = inspect.signature(flag_gems.enable)
            result["enable_signature"] = str(sig)
            params = list(sig.parameters.keys())
            result["enable_params"] = params
            if "unused" in params:
                result["capabilities"].append("enable_unused")

        # only_enable()
        if hasattr(flag_gems, "only_enable"):
            result["capabilities"].append("only_enable")

        # use_gems 上下文管理器
        if hasattr(flag_gems, "use_gems"):
            result["capabilities"].append("use_gems")
            try:
                sig = inspect.signature(flag_gems.use_gems)
                params = list(sig.parameters.keys())
                if "include" in params or "exclude" in params:
                    result["capabilities"].append("use_gems_filter")
            except Exception:
                pass

        # YAML 配置支持
        if hasattr(flag_gems, "config"):
            cfg = flag_gems.config
            if hasattr(cfg, "resolve_user_setting"):
                result["capabilities"].append("yaml_config")
            if hasattr(cfg, "get_default_enable_config"):
                result["capabilities"].append("vendor_default")
                try:
                    path = cfg.get_default_enable_config()
                    result["vendor_config_path"] = str(path) if path else ""
                except Exception:
                    pass

        # 算子查询接口
        if hasattr(flag_gems, "all_registered_ops"):
            result["capabilities"].append("query_ops")
        elif hasattr(flag_gems, "all_ops"):
            result["capabilities"].append("query_ops_legacy")

    except ImportError:
        pass
    except Exception as e:
        result["probe_error"] = str(e)

    # 探测 vllm-plugin-FL
    try:
        import vllm_fl

        result["vllm_plugin_installed"] = True
        try:
            from vllm_fl.dispatch import OpManager
            result["plugin_has_dispatch"] = True
        except ImportError:
            pass
    except ImportError:
        pass

    return result


def scan_flaggems_integration():
    """多维度扫描 FlagGems 集成方式"""
    integration = {
        "env_vars": {},
        "code_locations": [],
        "entry_points": [],
        "startup_scripts": [],
        "integration_type": "unknown",
        "enable_method": "",
        "disable_method": "",
    }

    # 维度1：环境变量检查
    for var in ["USE_FLAGGEMS", "USE_FLAGOS", "FLAGGEMS_LOG_LEVEL", "ENABLE_FLAGGEMS"]:
        val = os.environ.get(var)
        if val is not None:
            integration["env_vars"][var] = val

    # 维度2：vllm/sglang 代码扫描
    for framework in ["vllm", "sglang"]:
        try:
            mod = importlib.import_module(framework)
            fw_path = mod.__path__[0]
            output = run_cmd(
                f"grep -rn 'flag_gems\\|flaggems\\|use_gems\\|enable.*gems\\|import.*gems' {fw_path}/ 2>/dev/null"
            )
            if output:
                for line in output.strip().split("\n"):
                    if line:
                        integration["code_locations"].append(line)
        except (ImportError, Exception):
            pass

    # 维度3：入口点扫描
    try:
        import pkg_resources
        for group in ["vllm.general_plugins", "vllm.platform_plugins"]:
            for ep in pkg_resources.iter_entry_points(group):
                integration["entry_points"].append(f"{group}: {ep.name} = {ep}")
    except Exception:
        pass

    # 维度4：启动脚本扫描
    output = run_cmd(
        "find /usr/local/bin /opt /root -name '*.sh' -exec grep -l 'gems\\|flagos\\|flag_gems' {} \\; 2>/dev/null"
    )
    if output:
        integration["startup_scripts"] = [s for s in output.strip().split("\n") if s]

    # 推导集成方式
    _derive_integration_methods(integration)

    return integration


def _derive_integration_methods(integration):
    """根据扫描结果推导 FlagGems 启用/关闭方法"""
    code_locs = integration["code_locations"]
    env_vars = integration["env_vars"]
    entry_points = integration["entry_points"]

    # 优先级1：环境变量控制
    for var in ["USE_FLAGGEMS", "USE_FLAGOS"]:
        if var in env_vars:
            integration["integration_type"] = "env_var"
            integration["enable_method"] = f"env:{var}=1"
            integration["disable_method"] = f"env:{var}=0"
            return
    # 检查代码中是否引用了这些环境变量
    for loc in code_locs:
        for var in ["USE_FLAGGEMS", "USE_FLAGOS"]:
            if var in loc:
                integration["integration_type"] = "env_var"
                integration["enable_method"] = f"env:{var}=1"
                integration["disable_method"] = f"env:{var}=0"
                return

    # 优先级2：插件入口点
    if entry_points:
        integration["integration_type"] = "plugin"
        integration["enable_method"] = "auto"
        integration["disable_method"] = "env:USE_FLAGGEMS=0"
        return

    # 优先级3：代码中直接 import
    if code_locs:
        # 解析具体的代码位置
        import_locs = []
        for loc in code_locs:
            match = re.match(r"^(.+):(\d+):(.+)$", loc)
            if match:
                filepath, lineno, content = match.groups()
                if "import flag_gems" in content or "flag_gems.enable" in content:
                    import_locs.append({"file": filepath, "line": int(lineno), "content": content.strip()})

        if import_locs:
            integration["integration_type"] = "code_import"
            # 提供代码文件列表供 toggle_flaggems.py 使用
            files = list(set(loc["file"] for loc in import_locs))
            integration["enable_method"] = f"code:uncomment:{json.dumps(files)}"
            integration["disable_method"] = f"code:comment:{json.dumps(files)}"
            integration["code_import_details"] = import_locs
            return

    # 优先级4：启动脚本
    if integration["startup_scripts"]:
        integration["integration_type"] = "script"
        integration["enable_method"] = f"script:{integration['startup_scripts'][0]}"
        integration["disable_method"] = f"script:{integration['startup_scripts'][0]}"
        return

    # 无法确定
    integration["integration_type"] = "unknown"
    integration["enable_method"] = "unknown"
    integration["disable_method"] = "unknown"


def check_env_vars():
    """列出所有 flag 相关环境变量"""
    result = {}
    for key, val in os.environ.items():
        if re.search(r"flag|gems|flagos", key, re.IGNORECASE):
            result[key] = val
    return result


def collect_all():
    """收集全部检查结果"""
    exec_mode = check_execution_mode()
    core = check_core_packages()
    flag = check_flag_packages()
    capabilities = probe_flaggems_capabilities()
    integration = scan_flaggems_integration()
    env_vars = check_env_vars()

    return {
        "execution": {
            "mode": exec_mode,
        },
        "inspection": {
            "core_packages": core,
            "flag_packages": flag,
            "flaggems_capabilities": capabilities["capabilities"],
            "flaggems_enable_signature": capabilities["enable_signature"],
            "flaggems_enable_params": capabilities["enable_params"],
            "vendor_config_path": capabilities["vendor_config_path"],
            "vllm_plugin_installed": capabilities["vllm_plugin_installed"],
            "plugin_has_dispatch": capabilities["plugin_has_dispatch"],
            "probe_error": capabilities["probe_error"],
            "gpu_compute_capability": capabilities["gpu_compute_capability"],
            "gpu_arch": capabilities["gpu_arch"],
            "plugin_env_vars": capabilities["plugin_env_vars"],
            "env_vars": env_vars,
        },
        "flaggems_control": {
            "integration_type": integration["integration_type"],
            "enable_method": integration["enable_method"],
            "disable_method": integration["disable_method"],
            "code_locations": integration["code_locations"],
            "entry_points": integration["entry_points"],
            "startup_scripts": integration["startup_scripts"],
        },
    }


def output_json(data):
    """输出 JSON 格式"""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def output_report(data):
    """输出人类可读报告"""
    insp = data["inspection"]
    ctrl = data["flaggems_control"]

    report = []
    report.append("=" * 60)
    report.append("环境检测报告")
    report.append("=" * 60)

    report.append(f"\n## 执行模式: {data['execution']['mode']}")

    report.append("\n## 核心组件")
    report.append(f"  {'组件':<15} {'版本':<20} {'状态'}")
    report.append(f"  {'-'*15} {'-'*20} {'-'*10}")
    for pkg, ver in insp["core_packages"].items():
        if pkg == "torch_cuda":
            continue
        status = "已安装" if ver else "未安装"
        report.append(f"  {pkg:<15} {str(ver or '-'):<20} {status}")
    cuda_ver = insp["core_packages"].get("torch_cuda")
    if cuda_ver:
        report.append(f"  {'CUDA':<15} {cuda_ver:<20} {'已安装'}")

    report.append("\n## Flag 生态组件")
    report.append(f"  {'组件':<15} {'版本':<20} {'状态'}")
    report.append(f"  {'-'*15} {'-'*20} {'-'*10}")
    for pkg, ver in insp["flag_packages"].items():
        status = "已安装" if ver else "未安装"
        report.append(f"  {pkg:<15} {str(ver or '-'):<20} {status}")

    report.append("\n## FlagGems 集成分析")
    report.append(f"  集成方式:    {ctrl['integration_type']}")
    report.append(f"  启用方法:    {ctrl['enable_method']}")
    report.append(f"  关闭方法:    {ctrl['disable_method']}")
    report.append(f"  运行时能力:  {', '.join(insp['flaggems_capabilities']) or '无'}")
    if insp["flaggems_enable_signature"]:
        report.append(f"  enable() 签名: {insp['flaggems_enable_signature']}")

    if insp.get("gpu_compute_capability"):
        report.append(f"  GPU Compute:    {insp['gpu_compute_capability']} ({insp.get('gpu_arch', '')})")

    if insp.get("plugin_env_vars"):
        report.append(f"  Plugin 环境变量:")
        for k, v in insp["plugin_env_vars"].items():
            report.append(f"    {k}={v}")

    if ctrl["code_locations"]:
        report.append("\n  代码级扫描结果:")
        for loc in ctrl["code_locations"][:10]:
            report.append(f"    {loc}")

    if insp["env_vars"]:
        report.append("\n## 环境变量")
        for k, v in insp["env_vars"].items():
            report.append(f"  {k}={v}")
    else:
        report.append("\n## 环境变量: 无 flag 相关环境变量")

    if insp["probe_error"]:
        report.append(f"\n## 探测错误: {insp['probe_error']}")

    report.append("\n" + "=" * 60)
    print("\n".join(report))


def main():
    parser = argparse.ArgumentParser(description="FlagOS 环境检查合并脚本")
    parser.add_argument("--output-json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--report", action="store_true", help="输出人类可读报告")
    args = parser.parse_args()

    data = collect_all()

    if args.output_json:
        output_json(data)
    elif args.report:
        output_report(data)
    else:
        # 默认都输出
        output_json(data)
        print("\n---\n")
        output_report(data)


if __name__ == "__main__":
    main()
