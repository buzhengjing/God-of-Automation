#!/usr/bin/env bash
# setup_workspace.sh — 一次性工作区初始化
#
# 在容器准备阶段一次性完成：创建目录、复制脚本、安装依赖。
# 替代每个阶段各自 docker cp 的重复操作。
#
# Usage:
#   bash skills/flagos-container-preparation/tools/setup_workspace.sh <container_name>
#   bash skills/flagos-container-preparation/tools/setup_workspace.sh RoboBrain2.0-7B_flagos

set -euo pipefail

CONTAINER="${1:?用法: $0 <container_name>}"

# 项目根目录（此脚本所在位置的上三级）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

echo "=========================================="
echo "FlagOS 工作区初始化"
echo "=========================================="
echo "  容器: ${CONTAINER}"
echo "  项目: ${PROJECT_ROOT}"
echo ""

# 1. 创建容器内目录结构
echo "[1/4] 创建目录结构..."
docker exec "${CONTAINER}" bash -c "
    mkdir -p /flagos-workspace/{scripts,logs,results,reports,eval,perf/config,shared,output,traces,config}
"
echo "  目录创建完成"

# 2. 复制所有脚本到容器
echo "[2/4] 复制脚本到容器..."

SCRIPTS_COPIED=0

# 环境检查脚本
if [ -f "${PROJECT_ROOT}/skills/flagos-pre-service-inspection/tools/inspect_env.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-pre-service-inspection/tools/inspect_env.py" \
        "${CONTAINER}:/flagos-workspace/scripts/inspect_env.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ inspect_env.py"
fi

# FlagGems 开关切换
if [ -f "${PROJECT_ROOT}/skills/flagos-service-startup/tools/toggle_flaggems.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-service-startup/tools/toggle_flaggems.py" \
        "${CONTAINER}:/flagos-workspace/scripts/toggle_flaggems.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ toggle_flaggems.py"
fi

# 服务就绪检测
if [ -f "${PROJECT_ROOT}/skills/flagos-service-startup/tools/wait_for_service.sh" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-service-startup/tools/wait_for_service.sh" \
        "${CONTAINER}:/flagos-workspace/scripts/wait_for_service.sh"
    docker exec "${CONTAINER}" chmod +x /flagos-workspace/scripts/wait_for_service.sh
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ wait_for_service.sh"
fi

# 性能测试
if [ -f "${PROJECT_ROOT}/skills/flagos-performance-testing/tools/benchmark_runner.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-performance-testing/tools/benchmark_runner.py" \
        "${CONTAINER}:/flagos-workspace/scripts/benchmark_runner.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ benchmark_runner.py"
fi

# 性能对比
if [ -f "${PROJECT_ROOT}/skills/flagos-performance-testing/tools/performance_compare.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-performance-testing/tools/performance_compare.py" \
        "${CONTAINER}:/flagos-workspace/scripts/performance_compare.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ performance_compare.py"
fi

# 算子优化
if [ -f "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/operator_optimizer.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/operator_optimizer.py" \
        "${CONTAINER}:/flagos-workspace/scripts/operator_optimizer.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ operator_optimizer.py"
fi

# 算子搜索编排
if [ -f "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/operator_search.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/operator_search.py" \
        "${CONTAINER}:/flagos-workspace/scripts/operator_search.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ operator_search.py"
fi

# 算子配置生成（Plugin 场景）
if [ -f "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/apply_op_config.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/apply_op_config.py" \
        "${CONTAINER}:/flagos-workspace/scripts/apply_op_config.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ apply_op_config.py"
fi

# 算子快速诊断
if [ -f "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/diagnose_ops.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-operator-replacement/tools/diagnose_ops.py" \
        "${CONTAINER}:/flagos-workspace/scripts/diagnose_ops.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ diagnose_ops.py"
fi

# 性能测试配置
if [ -d "${PROJECT_ROOT}/skills/flagos-performance-testing/config" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-performance-testing/config/." \
        "${CONTAINER}:/flagos-workspace/perf/config/"
    echo "  ✓ perf/config/"
fi

# 评测脚本（已统一到 eval-comprehensive）
for eval_script in "${PROJECT_ROOT}"/skills/flagos-eval-comprehensive/tools/eval_*.py; do
    if [ -f "$eval_script" ]; then
        docker cp "$eval_script" "${CONTAINER}:/flagos-workspace/scripts/"
        echo "  ✓ $(basename "$eval_script")"
        SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    fi
done

# TP 推算脚本
if [ -f "${PROJECT_ROOT}/skills/flagos-service-startup/tools/calc_tp_size.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-service-startup/tools/calc_tp_size.py" \
        "${CONTAINER}:/flagos-workspace/scripts/calc_tp_size.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ calc_tp_size.py"
fi

# 评测配置模板（不存在则跳过）
if [ -f "${PROJECT_ROOT}/skills/flagos-eval-comprehensive/tools/config.yaml" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-eval-comprehensive/tools/config.yaml" \
        "${CONTAINER}:/flagos-workspace/eval/config.yaml"
    echo "  ✓ eval/config.yaml (评测配置模板)"
fi

# GPQA Diamond 快速精度评测
if [ -f "${PROJECT_ROOT}/skills/flagos-eval-comprehensive/tools/fast_gpqa.py" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-eval-comprehensive/tools/fast_gpqa.py" \
        "${CONTAINER}:/flagos-workspace/eval/fast_gpqa.py"
    SCRIPTS_COPIED=$((SCRIPTS_COPIED + 1))
    echo "  ✓ eval/fast_gpqa.py"
fi
if [ -f "${PROJECT_ROOT}/skills/flagos-eval-comprehensive/tools/fast_gpqa_config.yaml" ]; then
    docker cp "${PROJECT_ROOT}/skills/flagos-eval-comprehensive/tools/fast_gpqa_config.yaml" \
        "${CONTAINER}:/flagos-workspace/eval/fast_gpqa_config.yaml"
    echo "  ✓ eval/fast_gpqa_config.yaml"
fi

echo "  共复制 ${SCRIPTS_COPIED} 个脚本"

# 2.5. 确保 context.yaml 存在
if ! docker exec "${CONTAINER}" test -f /flagos-workspace/shared/context.yaml 2>/dev/null; then
    if [ -f "${PROJECT_ROOT}/shared/context.yaml" ]; then
        docker cp "${PROJECT_ROOT}/shared/context.yaml" "${CONTAINER}:/flagos-workspace/shared/context.yaml"
        echo "  ✓ shared/context.yaml (从模板创建)"
    else
        docker exec "${CONTAINER}" bash -c "echo '# FlagOS context' > /flagos-workspace/shared/context.yaml"
        echo "  ✓ shared/context.yaml (空文件)"
    fi
fi

# 3. 安装脚本依赖（如需要）
echo "[3/4] 检查脚本依赖..."
docker exec "${CONTAINER}" bash -c "
    PATH=/opt/conda/bin:\$PATH python3 -c 'import yaml' 2>/dev/null || PATH=/opt/conda/bin:\$PATH pip install pyyaml -q 2>/dev/null || true
"
echo "  依赖检查完成"

# 4. 验证
echo "[4/4] 验证部署..."
SCRIPT_COUNT=$(docker exec "${CONTAINER}" bash -c "ls /flagos-workspace/scripts/*.py /flagos-workspace/scripts/*.sh 2>/dev/null | wc -l")
echo "  容器内脚本数: ${SCRIPT_COUNT}"
docker exec "${CONTAINER}" ls -la /flagos-workspace/scripts/ 2>/dev/null || true

echo ""
echo "=========================================="
echo "工作区初始化完成"
echo "=========================================="
echo "  容器: ${CONTAINER}"
echo "  脚本目录: /flagos-workspace/scripts/"
echo "  结果目录: /flagos-workspace/results/"
echo "  报告目录: /flagos-workspace/reports/"
echo "=========================================="
