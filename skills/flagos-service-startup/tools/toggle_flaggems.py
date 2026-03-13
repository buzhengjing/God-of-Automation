#!/usr/bin/env python3
"""
toggle_flaggems.py — 可靠的 FlagGems 开关切换

替代脆弱的 sed 行号操作，使用正则匹配 + 自动备份。

Usage:
    python3 toggle_flaggems.py --action enable    # 启用 FlagGems
    python3 toggle_flaggems.py --action disable   # 关闭 FlagGems
    python3 toggle_flaggems.py --action status    # 查看当前状态
    python3 toggle_flaggems.py --action rollback  # 回滚到备份版本
"""

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path


# FlagGems 相关的代码模式
FLAGGEMS_PATTERNS = [
    re.compile(r"^(\s*)(import flag_gems.*)$"),
    re.compile(r"^(\s*)(from flag_gems.*)$"),
    re.compile(r"^(\s*)(flag_gems\.\w+.*)$"),
]

COMMENTED_PATTERNS = [
    re.compile(r"^(\s*)#\s*(import flag_gems.*)$"),
    re.compile(r"^(\s*)#\s*(from flag_gems.*)$"),
    re.compile(r"^(\s*)#\s*(flag_gems\.\w+.*)$"),
]

BACKUP_SUFFIX = ".flaggems_backup"


def find_model_runner_files():
    """自动扫描所有 model_runner.py 文件"""
    candidates = []
    search_dirs = [
        "/usr/local/lib",
        "/usr/lib",
        "/opt",
    ]
    # 也通过 Python 路径查找
    try:
        import vllm
        vllm_path = Path(vllm.__path__[0])
        search_dirs.append(str(vllm_path.parent))
    except ImportError:
        pass
    try:
        import sglang
        sgl_path = Path(sglang.__path__[0])
        search_dirs.append(str(sgl_path.parent))
    except ImportError:
        pass

    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if not search_path.exists():
            continue
        for py_file in search_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                if "flag_gems" in content:
                    candidates.append(str(py_file))
            except (PermissionError, OSError):
                continue

    return sorted(set(candidates))


def get_file_status(filepath):
    """检查单个文件的 FlagGems 状态"""
    try:
        content = Path(filepath).read_text(encoding="utf-8")
    except Exception as e:
        return {"file": filepath, "error": str(e)}

    lines = content.split("\n")
    active_lines = []
    commented_lines = []

    for i, line in enumerate(lines, 1):
        for pat in FLAGGEMS_PATTERNS:
            if pat.match(line):
                active_lines.append({"line": i, "content": line.strip()})
                break
        for pat in COMMENTED_PATTERNS:
            if pat.match(line):
                commented_lines.append({"line": i, "content": line.strip()})
                break

    status = "unknown"
    if active_lines and not commented_lines:
        status = "enabled"
    elif commented_lines and not active_lines:
        status = "disabled"
    elif active_lines and commented_lines:
        status = "mixed"
    elif not active_lines and not commented_lines:
        status = "not_found"

    has_backup = Path(filepath + BACKUP_SUFFIX).exists()

    return {
        "file": filepath,
        "status": status,
        "active_lines": active_lines,
        "commented_lines": commented_lines,
        "has_backup": has_backup,
    }


def backup_file(filepath):
    """备份文件"""
    backup_path = filepath + BACKUP_SUFFIX
    shutil.copy2(filepath, backup_path)
    return backup_path


def disable_flaggems(filepath):
    """注释掉 FlagGems 相关代码"""
    content = Path(filepath).read_text(encoding="utf-8")
    lines = content.split("\n")
    modified = False

    new_lines = []
    for line in lines:
        commented = False
        for pat in FLAGGEMS_PATTERNS:
            match = pat.match(line)
            if match:
                indent = match.group(1)
                code = match.group(2)
                new_lines.append(f"{indent}# {code}")
                commented = True
                modified = True
                break
        if not commented:
            new_lines.append(line)

    if modified:
        backup_file(filepath)
        Path(filepath).write_text("\n".join(new_lines), encoding="utf-8")

    return modified


def enable_flaggems(filepath):
    """取消注释 FlagGems 相关代码"""
    content = Path(filepath).read_text(encoding="utf-8")
    lines = content.split("\n")
    modified = False

    new_lines = []
    for line in lines:
        uncommented = False
        for pat in COMMENTED_PATTERNS:
            match = pat.match(line)
            if match:
                indent = match.group(1)
                code = match.group(2)
                new_lines.append(f"{indent}{code}")
                uncommented = True
                modified = True
                break
        if not uncommented:
            new_lines.append(line)

    if modified:
        backup_file(filepath)
        Path(filepath).write_text("\n".join(new_lines), encoding="utf-8")

    return modified


def rollback_file(filepath):
    """从备份恢复文件"""
    backup_path = filepath + BACKUP_SUFFIX
    if not Path(backup_path).exists():
        return False
    shutil.copy2(backup_path, filepath)
    return True


def verify_change(filepath, expected_status):
    """验证修改后状态是否正确"""
    status = get_file_status(filepath)
    return status["status"] == expected_status


def main():
    parser = argparse.ArgumentParser(description="FlagGems 开关切换工具")
    parser.add_argument(
        "--action",
        required=True,
        choices=["enable", "disable", "status", "rollback"],
        help="操作类型",
    )
    parser.add_argument(
        "--files",
        nargs="*",
        help="指定文件列表（不指定则自动扫描）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 格式",
    )
    args = parser.parse_args()

    # 查找文件
    if args.files:
        files = args.files
    else:
        files = find_model_runner_files()

    if not files:
        result = {"success": False, "error": "未找到包含 flag_gems 的文件"}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("ERROR: 未找到包含 flag_gems 的文件")
        sys.exit(1)

    results = []

    if args.action == "status":
        for f in files:
            status = get_file_status(f)
            results.append(status)

    elif args.action == "disable":
        for f in files:
            before = get_file_status(f)
            if before.get("status") == "disabled":
                results.append({"file": f, "action": "skip", "reason": "already disabled"})
                continue
            modified = disable_flaggems(f)
            if modified and verify_change(f, "disabled"):
                results.append({"file": f, "action": "disabled", "success": True})
            elif not modified:
                results.append({"file": f, "action": "skip", "reason": "no active lines found"})
            else:
                results.append({"file": f, "action": "disabled", "success": False, "warning": "verification failed"})

    elif args.action == "enable":
        for f in files:
            before = get_file_status(f)
            if before.get("status") == "enabled":
                results.append({"file": f, "action": "skip", "reason": "already enabled"})
                continue
            modified = enable_flaggems(f)
            if modified and verify_change(f, "enabled"):
                results.append({"file": f, "action": "enabled", "success": True})
            elif not modified:
                results.append({"file": f, "action": "skip", "reason": "no commented lines found"})
            else:
                results.append({"file": f, "action": "enabled", "success": False, "warning": "verification failed"})

    elif args.action == "rollback":
        for f in files:
            if rollback_file(f):
                results.append({"file": f, "action": "rollback", "success": True})
            else:
                results.append({"file": f, "action": "rollback", "success": False, "reason": "no backup found"})

    # 输出
    output = {
        "action": args.action,
        "files_processed": len(results),
        "results": results,
        "timestamp": datetime.now().isoformat(),
    }

    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"\nFlagGems Toggle — {args.action}")
        print("=" * 50)
        for r in results:
            action = r.get("action", r.get("status", "?"))
            success = r.get("success", "")
            reason = r.get("reason", "")
            warning = r.get("warning", "")
            extra = ""
            if reason:
                extra = f" ({reason})"
            if warning:
                extra = f" [WARNING: {warning}]"
            if success is True:
                extra = " [OK]"
            elif success is False:
                extra = f" [FAILED]{extra}"

            # status action has different format
            if args.action == "status":
                status = r.get("status", "?")
                active = len(r.get("active_lines", []))
                commented = len(r.get("commented_lines", []))
                backup = "有备份" if r.get("has_backup") else "无备份"
                print(f"  {r['file']}")
                print(f"    状态: {status}  活跃行: {active}  注释行: {commented}  {backup}")
                for al in r.get("active_lines", []):
                    print(f"    L{al['line']}: {al['content']}")
                for cl in r.get("commented_lines", []):
                    print(f"    L{cl['line']}: {cl['content']}")
            else:
                print(f"  {r['file']} → {action}{extra}")

        print(f"\n处理文件数: {len(results)}")


if __name__ == "__main__":
    main()
