---
name: flagos-pre-service-inspection
description: 启动服务前的容器内环境全面检查，通过 inspect_env.py 一次完成全部检测
version: 5.0.0
license: internal
triggers:
  - pre-service inspection
  - inspect environment
  - 服务前检查
  - 环境检查
depends_on:
  - flagos-container-preparation
next_skill: flagos-service-startup
provides:
  - execution.mode
  - execution.cmd_prefix
  - inspection.core_packages
  - inspection.flag_packages
  - inspection.flaggems_control
  - flaggems_control.enable_method
  - flaggems_control.disable_method
  - flaggems_control.integration_type
---

# 启动服务前准备 Skill

通过 `inspect_env.py` 一次 docker exec 完成全部环境检查（替代原来 10+ 次串行调用），输出结构化 JSON。

**工具脚本**: `skills/flagos-pre-service-inspection/tools/inspect_env.py`（已由 setup_workspace.sh 部署到容器）

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
gpu:
  vendor: <来自 container-preparation>
entry:
  type: <来自 container-preparation>
```

## 写入 shared/context.yaml

```yaml
execution:
  mode: "<host|container>"
  cmd_prefix: "<''|'docker exec <container>'>"
inspection:
  core_packages:
    torch: "<version>"
    vllm: "<version>"
    sglang: "<version>"
  flag_packages:
    flaggems: "<version>"
    flagscale: "<version>"
    flagcx: "<version>"
    vllm_plugin: "<version>"
  flaggems_capabilities: []
  env_vars: {}
flaggems_control:
  enable_method: ""
  disable_method: ""
  integration_type: ""
```

---

# 工作流程

## 步骤 1 — 运行环境检查脚本（一步完成）

```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/inspect_env.py --output-json
```

此命令一次性完成：
- 执行模式检测（host / container）
- 核心组件版本检查（torch, vllm, sglang）
- flag 生态组件版本（flaggems, flagscale, flagcx, vllm_plugin）
- FlagGems 运行时能力探测（capabilities, enable_signature 等）
- FlagGems 多维度集成方式探测（环境变量/代码扫描/入口点/启动脚本）
- 推导 enable/disable 方法
- 环境变量梳理

## 步骤 2 — 解析 JSON 结果并写入 context.yaml

从 JSON 输出中提取字段，写入 `shared/context.yaml` 的 `execution`、`inspection`、`flaggems_control` 字段。

同时写入 `environment` 字段：
```yaml
environment:
  has_plugin: <vllm_plugin_installed>
```

## 步骤 3 — 生成报告

```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/inspect_env.py --report
```

将报告内容分别保存到：
- `/flagos-workspace/reports/env_report.md` — 环境检测报告
- `/flagos-workspace/reports/flag_gems_detection.md` — FlagGems 检测报告

---

# 完成条件

- 执行模式已检测（host / container）
- 核心组件（torch、vllm/sglang）已确认安装
- flag 组件版本已记录
- FlagGems 集成方式已探测（integration_type）
- FlagGems 启用/关闭方法已推导（enable_method / disable_method）
- context.yaml 已更新（含 environment 字段）
- 报告已生成
- `traces/02_environment_inspection.json` 已写入（记录 inspect_env.py 命令、关键输出）

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| torch 未安装 | 镜像可能有问题，建议更换镜像或手动安装 |
| vllm/sglang 都未安装 | 确认镜像是否为推理镜像 |
| FlagGems 未安装 | 确认镜像是否包含 FlagGems，或手动安装 |
| inspect_env.py 不存在 | 运行 `setup_workspace.sh` 重新部署 |
| capabilities 为空列表 | FlagGems 版本过旧，算子替换降级到源码修改模式 |
| integration_type 为 unknown | 标记为 unknown，后续步骤需人工介入 |

下一步应执行 **flagos-service-startup**（default 模式，验证初始环境可用性）。
