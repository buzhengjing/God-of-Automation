#!/usr/bin/env bash
# install_flagtree.sh — FlagTree 安装/卸载/验证
#
# FlagTree 是统一 Triton 编译器，替换 triton 包（import triton 仍然生效）
# 参考: https://github.com/flagos-ai/FlagTree
#
# Usage:
#   install_flagtree.sh install [--vendor nvidia] [--version 0.4.0]
#   install_flagtree.sh uninstall
#   install_flagtree.sh verify

set -euo pipefail

ACTION="${1:?Usage: $0 install|uninstall|verify}"
shift || true

# 默认值
VENDOR="${VENDOR:-nvidia}"
VERSION="${VERSION:-0.4.0}"

# 解析参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --vendor) VENDOR="$2"; shift 2 ;;
        --version) VERSION="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

BACKUP_DIR="/tmp/flagtree_backup"

case "$ACTION" in
    install)
        echo "=========================================="
        echo "FlagTree 安装"
        echo "=========================================="
        echo "  厂商: ${VENDOR}"
        echo "  版本: ${VERSION}"
        echo ""

        # 备份原始 triton 信息
        mkdir -p "$BACKUP_DIR"
        python3 -c "import triton; print(triton.__version__)" > "${BACKUP_DIR}/triton_version" 2>/dev/null || echo "" > "${BACKUP_DIR}/triton_version"
        pip show triton 2>/dev/null > "${BACKUP_DIR}/triton_pip_info" || true
        echo "  原始 triton 版本: $(cat "${BACKUP_DIR}/triton_version")"

        case "$VENDOR" in
            nvidia)
                echo "[1/2] 卸载原始 triton..."
                pip uninstall -y triton 2>/dev/null || true

                echo "[2/2] 安装 FlagTree ${VERSION}..."
                pip install "flagtree==${VERSION}" \
                    --index-url=https://resource.flagos.net/repository/flagos-pypi-hosted/simple \
                    --trusted-host=resource.flagos.net
                ;;
            *)
                # 非 NVIDIA：源码编译
                echo "[1/3] 安装构建依赖..."
                apt-get update -qq && apt-get install -y -qq zlib1g-dev libxml2-dev 2>/dev/null || true

                echo "[2/3] 克隆 FlagTree..."
                if [ -d /tmp/FlagTree ]; then
                    rm -rf /tmp/FlagTree
                fi
                git clone https://github.com/flagos-ai/FlagTree.git /tmp/FlagTree

                echo "[3/3] 编译安装 (backend=${VENDOR})..."
                cd /tmp/FlagTree
                export FLAGTREE_BACKEND="${VENDOR}"
                pip install -r python/requirements.txt 2>/dev/null || true
                cd python && pip install . --no-build-isolation -v
                ;;
        esac

        echo ""
        echo "安装完成，执行验证..."
        "$0" verify
        ;;

    uninstall)
        echo "=========================================="
        echo "FlagTree 卸载"
        echo "=========================================="

        echo "[1/2] 卸载 flagtree..."
        pip uninstall -y flagtree 2>/dev/null || true

        echo "[2/2] 恢复原始 triton..."
        ORIG_VER=""
        if [ -f "${BACKUP_DIR}/triton_version" ]; then
            ORIG_VER=$(cat "${BACKUP_DIR}/triton_version")
        fi
        if [ -n "$ORIG_VER" ]; then
            echo "  恢复 triton==${ORIG_VER}"
            pip install "triton==${ORIG_VER}"
        else
            echo "  无备份版本信息，安装最新 triton"
            pip install triton
        fi

        echo ""
        echo "卸载完成，验证状态..."
        "$0" verify
        ;;

    verify)
        echo "=========================================="
        echo "FlagTree 状态检查"
        echo "=========================================="
        python3 -c "
import json

result = {}

# 检查 triton
try:
    import triton
    result['triton_version'] = getattr(triton, '__version__', 'unknown')
    result['triton_installed'] = True
except ImportError:
    result['triton_installed'] = False
    result['triton_version'] = ''

# 检查 flagtree
try:
    import flagtree
    result['flagtree_installed'] = True
    result['flagtree_version'] = getattr(flagtree, '__version__', 'unknown')
    result['backend'] = getattr(flagtree, 'backend', '')
except ImportError:
    result['flagtree_installed'] = False
    result['flagtree_version'] = ''
    result['backend'] = ''

print(json.dumps(result, indent=2))

# 人类可读输出
print()
print(f\"  triton: {'v' + result['triton_version'] if result['triton_installed'] else 'NOT INSTALLED'}\")
print(f\"  flagtree: {'v' + result['flagtree_version'] if result['flagtree_installed'] else 'NOT INSTALLED'}\")
if result.get('backend'):
    print(f\"  backend: {result['backend']}\")
"
        ;;

    *)
        echo "Unknown action: $ACTION"
        echo "Usage: $0 install|uninstall|verify"
        exit 1
        ;;
esac
