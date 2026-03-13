#!/usr/bin/env python3
"""
upgrade_component.py — 自动降级的组件升级

替代手动 git clone + pip install，支持网络检测和自动降级。

Usage（容器内执行）:
    python3 upgrade_component.py --component flaggems --branch main
    python3 upgrade_component.py --component flaggems --branch main --proxy http://10.8.36.21:17890
    python3 upgrade_component.py --component flagscale --repo https://github.com/FlagOpen/FlagScale.git

当容器内无网络时，输出 JSON 指令让 Claude Code 在宿主机完成 clone + docker cp。
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# 默认仓库地址
DEFAULT_REPOS = {
    "flaggems": "https://github.com/FlagOpen/FlagGems.git",
    "flagscale": "https://github.com/FlagOpen/FlagScale.git",
    "flagcx": "https://github.com/FlagOpen/FlagCX.git",
}

# 包名映射（pip 显示用）
PACKAGE_NAMES = {
    "flaggems": "flag-gems",
    "flagscale": "flag-scale",
    "flagcx": "flagcx",
}

# 可能需要的构建依赖
BUILD_DEPS = ["setuptools>=64.0", "scikit-build-core", "wheel"]


def run_cmd(cmd, timeout=300, env=None):
    """运行命令，返回 (returncode, stdout, stderr)"""
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, env=merged_env
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "command timed out"
    except Exception as e:
        return -1, "", str(e)


def check_network(proxy=None):
    """检测网络连通性"""
    env = {}
    if proxy:
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy

    code, out, err = run_cmd(
        "curl --connect-timeout 5 -s -o /dev/null -w '%{http_code}' https://github.com",
        timeout=10, env=env
    )
    return code == 0 and out.strip("'\"") in ["200", "301", "302"]


def get_current_version(component):
    """获取当前安装版本"""
    pkg_name = PACKAGE_NAMES.get(component, component)
    code, out, err = run_cmd(f"pip show {pkg_name} 2>/dev/null")
    if code == 0:
        for line in out.split("\n"):
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    return None


def check_build_deps(proxy=None):
    """检查并安装构建依赖"""
    env = {}
    if proxy:
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy

    missing = []
    for dep in BUILD_DEPS:
        pkg = dep.split(">=")[0].split("==")[0].replace("-", "_")
        code, _, _ = run_cmd(f"python3 -c 'import {pkg}' 2>/dev/null")
        if code != 0:
            missing.append(dep)

    if missing:
        deps_str = " ".join(f'"{d}"' for d in missing)
        code, out, err = run_cmd(f"pip install {deps_str}", env=env)
        if code != 0:
            return False, missing, err
    return True, [], ""


def clone_and_install(component, repo_url, branch, proxy=None, work_dir="/tmp"):
    """克隆仓库并安装"""
    env = {}
    if proxy:
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy

    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_path = os.path.join(work_dir, repo_name)

    # 清理旧目录
    if os.path.exists(clone_path):
        run_cmd(f"rm -rf {clone_path}")

    # 克隆
    code, out, err = run_cmd(
        f"git clone --depth 1 --branch {branch} {repo_url} {clone_path}",
        timeout=120, env=env
    )
    if code != 0:
        # branch 可能不存在，尝试不指定 branch
        if "not found" in err or "Could not find" in err:
            code, out, err = run_cmd(
                f"git clone --depth 1 {repo_url} {clone_path}",
                timeout=120, env=env
            )
        if code != 0:
            return False, f"git clone failed: {err}"

    # 安装（非 editable 模式）
    code, out, err = run_cmd(
        f"cd {clone_path} && pip install .",
        timeout=600, env=env
    )
    if code != 0:
        # 尝试 --no-build-isolation
        code, out, err = run_cmd(
            f"cd {clone_path} && pip install --no-build-isolation .",
            timeout=600, env=env
        )
        if code != 0:
            return False, f"pip install failed: {err}"

    return True, f"Successfully installed from {clone_path}"


def generate_host_instructions(component, repo_url, branch, container_name="$CONTAINER"):
    """生成宿主机执行指令（网络降级方案）"""
    repo_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
    return {
        "type": "host_fallback",
        "message": "容器内无网络，请在宿主机执行以下命令",
        "commands": [
            f"cd /tmp && git clone --depth 1 --branch {branch} {repo_url}",
            f"docker cp /tmp/{repo_name} {container_name}:/tmp/{repo_name}",
            f"docker exec {container_name} bash -c 'cd /tmp/{repo_name} && pip install .'",
        ],
        "component": component,
        "repo_url": repo_url,
        "branch": branch,
    }


def main():
    parser = argparse.ArgumentParser(description="FlagOS 组件升级工具")
    parser.add_argument("--component", required=True, choices=list(DEFAULT_REPOS.keys()) + ["custom"],
                        help="要升级的组件")
    parser.add_argument("--branch", default="main", help="Git 分支（默认 main）")
    parser.add_argument("--repo", help="仓库地址（不指定则使用默认）")
    parser.add_argument("--proxy", help="代理地址（如 http://10.8.36.21:17890）")
    parser.add_argument("--container-name", default="$CONTAINER", help="容器名（用于生成宿主机指令）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--skip-build-deps", action="store_true", help="跳过构建依赖检查")
    args = parser.parse_args()

    repo_url = args.repo or DEFAULT_REPOS.get(args.component, "")
    if not repo_url:
        print(json.dumps({"success": False, "error": f"未知组件: {args.component}，请用 --repo 指定仓库"}))
        sys.exit(1)

    result = {
        "component": args.component,
        "repo_url": repo_url,
        "branch": args.branch,
    }

    # 1. 记录当前版本
    old_version = get_current_version(args.component)
    result["previous_version"] = old_version

    # 2. 检测网络
    has_network = check_network(args.proxy)
    result["network_available"] = has_network

    if not has_network and not args.proxy:
        # 无网络且无代理 → 输出宿主机指令
        instructions = generate_host_instructions(
            args.component, repo_url, args.branch, args.container_name
        )
        result["success"] = False
        result["fallback"] = instructions
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("ERROR: 容器内无网络")
            print("请在宿主机执行以下命令：")
            for cmd in instructions["commands"]:
                print(f"  {cmd}")
        sys.exit(2)  # 特殊退出码表示需要宿主机操作

    # 3. 检查构建依赖
    if not args.skip_build_deps:
        deps_ok, missing, err = check_build_deps(args.proxy)
        if not deps_ok:
            result["success"] = False
            result["error"] = f"构建依赖安装失败: {missing}. {err}"
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(f"ERROR: {result['error']}")
            sys.exit(1)

    # 4. 克隆并安装
    success, message = clone_and_install(
        args.component, repo_url, args.branch, args.proxy
    )
    result["success"] = success
    result["message"] = message

    if success:
        new_version = get_current_version(args.component)
        result["current_version"] = new_version
        result["upgraded"] = old_version != new_version

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if success:
            print(f"升级成功: {args.component}")
            print(f"  {old_version or '未安装'} → {result.get('current_version', '?')}")
        else:
            print(f"升级失败: {message}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
