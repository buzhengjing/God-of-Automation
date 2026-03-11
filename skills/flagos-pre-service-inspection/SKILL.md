---
name: flagos-pre-service-inspection
description: 启动服务前的容器内环境全面检查，包括核心组件、flag 组件版本、FlagGems 代码逻辑分析和环境变量梳理
version: 1.0.0
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
  - inspection.core_packages
  - inspection.flag_packages
  - inspection.flaggems_control
  - inspection.flaggems_logic
  - inspection.flaggems_code_path
  - inspection.flaggems_code_lines
  - inspection.env_vars
---

# 启动服务前准备 Skill

此 Skill 在容器内执行全面的环境检查，确认核心组件和 flag 生态组件状态，并深入分析 FlagGems 代码逻辑，为后续服务启动和算子替换提供依据。

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
gpu:
  vendor: <来自 container-preparation>
```

## 写入 shared/context.yaml

```yaml
inspection:
  core_packages:                    # 核心组件版本
    torch: "<version>"
    vllm: "<version>"
    sglang: "<version>"
  flag_packages:                    # flag 生态组件版本
    flaggems: "<version>"
    flagscale: "<version>"
    flagcx: "<version>"
    vllm_plugin: "<version>"
  flaggems_control: ""              # env_var | code_comment
  flaggems_logic: ""                # unused | only_enable
  flaggems_code_path: ""            # flaggems 代码所在文件路径
  flaggems_code_lines: ""           # 相关代码行号范围
  env_vars:                         # flag 相关环境变量
    USE_FLAGGEMS: ""
    USE_FLAGOS: ""

metadata:
  updated_by: "flagos-pre-service-inspection"
  updated_at: "<timestamp>"
```

---

# 工作流程

## 步骤 1 — 核心组件检查

确认 torch、vllm/sglang 等核心推理组件已安装且版本正确。

```bash
docker exec <container> pip list | grep -iE "(torch|vllm|sglang)"
```

结果反馈：

- torch 版本
- vllm 版本（如已安装）
- sglang 版本（如已安装）
- 是否有缺失的核心组件

**如果核心组件缺失，提示用户解决后再继续。**

---

## 步骤 2 — flag/plugin 组件版本信息

检查 flag 生态系统的组件安装情况和版本。

```bash
docker exec <container> pip list | grep -iE "(flag|gems|plugin|flagscale|flagcx)"
```

记录以下组件的版本（如已安装）：

| 组件 | 包名 | 说明 |
|------|------|------|
| FlagGems | `flag-gems` / `flag_gems` | 算子替换库 |
| FlagScale | `flagscale` | 推理框架（旧版） |
| FlagCX | `flagcx` | 通信库 |
| vLLM Plugin | `vllm-plugin` / `vllm_plugin` | vLLM 插件（新版，替代 flagscale） |

结果反馈：

- 各组件版本列表
- 未安装的组件清单

**注意**：在最新版本中，`vllm_plugin` 已替换了 `flagscale`。

---

## 步骤 3 — FlagGems 代码逻辑检查（核心步骤）

此步骤深入分析 vllm/sglang 中 FlagGems 的集成方式，为后续算子替换提供关键信息。

### 3.1 定位 vllm 安装路径

```bash
docker exec <container> pip show vllm 2>/dev/null | grep Location
```

### 3.2 搜索 FlagGems 相关代码

```bash
# 进入 vllm 安装路径下的 vllm/ 子目录
VLLM_PATH=$(docker exec <container> bash -c "pip show vllm 2>/dev/null | grep Location | cut -d' ' -f2")
docker exec <container> grep -rn "gems" ${VLLM_PATH}/vllm/
```

### 3.3 分析代码逻辑

查看搜索到的相关代码片段，分析以下内容：

**控制方式判断**：

| 控制方式 | 特征 | 标记值 |
|----------|------|--------|
| 环境变量控制 | 代码中有 `os.environ.get("USE_FLAGGEMS")` 等 | `env_var` |
| 代码注释控制 | 相关代码被注释/取消注释来控制 | `code_comment` |

**算子替换逻辑判断**：

| 逻辑模式 | 特征 | 标记值 |
|----------|------|--------|
| unused 模式 | 代码中有 `unused_ops` 或排除列表 | `unused` |
| only_enable 模式 | 代码中有 `enabled_ops` 或启用列表 | `only_enable` |

### 3.4 记录分析结果

```
示例输出：
- 代码文件: /usr/lib/python3.10/site-packages/vllm/worker/model_runner.py
- 代码行号: L42-L58
- 控制方式: env_var (通过 USE_FLAGGEMS 环境变量)
- 算子逻辑: unused (使用排除列表控制不使用的算子)
```

结果反馈：

- FlagGems 代码文件路径
- 相关代码行号范围
- 控制方式（env_var / code_comment）
- 算子替换逻辑（unused / only_enable）

---

## 步骤 4 — 环境变量梳理

列出所有 flag 相关环境变量及其当前值。

```bash
docker exec <container> env | grep -iE "(flag|gems|flagos)"
```

重点关注的环境变量：

| 环境变量 | 说明 | 典型值 |
|----------|------|--------|
| `USE_FLAGGEMS` | 是否启用 FlagGems | `0` / `1` |
| `USE_FLAGOS` | 是否启用 FlagOS | `0` / `1` |
| `FLAGGEMS_LOG_LEVEL` | FlagGems 日志级别 | `INFO` / `DEBUG` |

结果反馈：

- 已设置的 flag 相关环境变量列表
- 未设置但可能需要的环境变量

---

## 步骤 5 — 写入 context.yaml

将所有检查结果汇总写入 `shared/context.yaml` 的 `inspection` 字段。

```yaml
inspection:
  core_packages:
    torch: "2.1.0"
    vllm: "0.4.0"
    sglang: ""
  flag_packages:
    flaggems: "1.0.0"
    flagscale: ""
    flagcx: "0.2.0"
    vllm_plugin: "1.0.0"
  flaggems_control: "env_var"
  flaggems_logic: "unused"
  flaggems_code_path: "/usr/lib/python3.10/site-packages/vllm/worker/model_runner.py"
  flaggems_code_lines: "L42-L58"
  env_vars:
    USE_FLAGGEMS: "1"
    USE_FLAGOS: "1"
```

---

# 完成条件

环境检查成功的标志：

- 核心组件（torch、vllm/sglang）已确认安装
- flag 组件版本已记录
- FlagGems 代码逻辑已分析（控制方式、算子逻辑）
- 环境变量已梳理
- context.yaml 已更新 `inspection` 字段

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| torch 未安装 | 镜像可能有问题，建议更换镜像或手动安装 |
| vllm/sglang 都未安装 | 确认镜像是否为推理镜像 |
| FlagGems 未安装 | 可通过 `flagos-flag-upgrade` 安装 |
| grep 未找到 gems 代码 | 当前框架可能未集成 FlagGems，记录为不可用 |
| 环境变量未设置 | 启动服务时需手动设置 |

下一步应执行 **flagos-service-startup**。
