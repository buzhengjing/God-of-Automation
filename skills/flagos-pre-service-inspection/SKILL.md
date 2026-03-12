---
name: flagos-pre-service-inspection
description: 启动服务前的容器内环境全面检查，包括执行模式检测、核心组件、flag 组件版本、FlagGems 深度探测（多维度）、环境变量梳理和报告生成
version: 3.0.0
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
  - inspection.flaggems_logic
  - inspection.flaggems_code_path
  - inspection.flaggems_code_lines
  - inspection.flaggems_capabilities
  - inspection.vendor_config_path
  - inspection.vllm_plugin_installed
  - inspection.plugin_has_dispatch
  - inspection.env_vars
  - flaggems_control.enable_method
  - flaggems_control.disable_method
  - flaggems_control.integration_type
---

# 启动服务前准备 Skill

此 Skill 在容器内执行全面的环境检查，确认核心组件和 flag 生态组件状态，并深入分析 FlagGems 集成方式（多维度探测），为后续服务启动和算子替换提供依据。

**新增能力**：
- 执行模式检测（宿主机 / 容器内）
- 深度 FlagGems 多维度探测（不预设集成模式）
- 推导 FlagGems 启用/关闭方法
- 生成 `env_report.md` 和 `flag_gems_detection.md` 报告

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
  flaggems_control: ""              # env_var | code_comment | plugin | auto
  flaggems_logic: ""                # unused | only_enable
  flaggems_code_path: ""
  flaggems_code_lines: ""
  flaggems_capabilities: []
  vendor_config_path: ""
  vllm_plugin_installed: false
  plugin_has_dispatch: false
  env_vars:
    USE_FLAGGEMS: ""
    USE_FLAGOS: ""

flaggems_control:
  enable_method: ""           # 如何启用 FlagGems
  disable_method: ""          # 如何关闭 FlagGems
  integration_type: ""        # 集成方式

metadata:
  updated_by: "flagos-pre-service-inspection"
  updated_at: "<timestamp>"
```

---

# 工作流程

## 步骤 0 — 执行模式检测（新增）

检测 Claude Code 运行在宿主机还是容器内，确定命令前缀：

```bash
# 检测是否在容器内
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    EXEC_MODE="container"   # Claude Code 在容器内，直接执行
    CMD_PREFIX=""
else
    EXEC_MODE="host"        # Claude Code 在宿主机，通过 docker exec
    CMD_PREFIX="docker exec <container>"
fi
```

将结果写入 context.yaml：

```yaml
execution:
  mode: "<host|container>"
  cmd_prefix: "<CMD_PREFIX>"
```

**后续所有命令统一使用 `${CMD_PREFIX}` 前缀**，确保在两种模式下都能正确执行。

---

## 步骤 1 — 核心组件检查

确认 torch、vllm/sglang 等核心推理组件已安装且版本正确。

```bash
${CMD_PREFIX} pip list | grep -iE "(torch|vllm|sglang)"
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
${CMD_PREFIX} pip list | grep -iE "(flag|gems|plugin|flagscale|flagcx)"
```

记录以下组件的版本（如已安装）：

| 组件 | 包名 | 说明 |
|------|------|------|
| FlagGems | `flag-gems` / `flag_gems` | 算子替换库 |
| FlagScale | `flagscale` | 推理框架（旧版） |
| FlagCX | `flagcx` | 通信库 |
| vLLM Plugin | `vllm-plugin` / `vllm_plugin` | vLLM 插件（新版，替代 flagscale） |

---

## 步骤 3 — FlagGems 深度探测（核心步骤）

**设计原则**：**不预设任何固定的 FlagGems 集成模式**。现实中 FlagGems 可能通过以下任意方式集成：

| 集成方式 | 特征 |
|----------|------|
| 环境变量 `USE_FLAGGEMS=1` | vllm/sglang 源码中检查环境变量 |
| vllm-plugin-FL 插件自动加载 | pyproject.toml 的 entry_points 注册 |
| 代码中直接 import flag_gems | 源码硬编码 |
| 注释/取消注释控制 | 代码块被注释掉 |
| 启动脚本中控制 | shell 脚本里有条件判断 |
| 配置文件控制 | YAML/JSON 配置文件中有开关 |

### 3.1 定位 vllm 安装路径

```bash
${CMD_PREFIX} pip show vllm 2>/dev/null | grep Location
```

### 3.2 搜索 FlagGems 相关代码（保留，用于定位集成入口）

```bash
VLLM_PATH=$(${CMD_PREFIX} bash -c "pip show vllm 2>/dev/null | grep Location | cut -d' ' -f2")
${CMD_PREFIX} grep -rn "gems" ${VLLM_PATH}/vllm/
```

### 3.3 分析代码逻辑（保留，兼容旧版本场景）

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

### 3.4 运行时能力探测（已有，保留）

在容器内执行探测脚本，让 Python 运行时报告 FlagGems 和 vllm-plugin-FL 的实际能力：

```bash
${CMD_PREFIX} python3 -c "
import json, importlib

result = {
    'flaggems_installed': False,
    'capabilities': [],
    'enable_signature': '',
    'vendor_config_path': '',
    'vllm_plugin_installed': False,
    'plugin_has_dispatch': False,
    'probe_error': ''
}

# --- 探测 FlagGems ---
try:
    import flag_gems
    result['flaggems_installed'] = True
    import inspect

    # 探测 enable() 签名
    if hasattr(flag_gems, 'enable'):
        sig = inspect.signature(flag_gems.enable)
        result['enable_signature'] = str(sig)
        params = list(sig.parameters.keys())
        if 'unused' in params:
            result['capabilities'].append('enable_unused')

    # 探测 only_enable()
    if hasattr(flag_gems, 'only_enable'):
        result['capabilities'].append('only_enable')

    # 探测 YAML 配置支持
    if hasattr(flag_gems, 'config'):
        cfg = flag_gems.config
        if hasattr(cfg, 'resolve_user_setting'):
            result['capabilities'].append('yaml_config')
        if hasattr(cfg, 'get_default_enable_config'):
            result['capabilities'].append('vendor_default')
            try:
                path = cfg.get_default_enable_config()
                result['vendor_config_path'] = str(path) if path else ''
            except Exception:
                pass

    # 探测算子查询接口
    if hasattr(flag_gems, 'all_registered_ops'):
        result['capabilities'].append('query_ops')
    elif hasattr(flag_gems, 'all_ops'):
        result['capabilities'].append('query_ops_legacy')

    # 探测 use_gems 上下文管理器
    if hasattr(flag_gems, 'use_gems'):
        sig = inspect.signature(flag_gems.use_gems)
        params = list(sig.parameters.keys())
        if 'include' in params or 'exclude' in params:
            result['capabilities'].append('use_gems_filter')

except ImportError:
    pass
except Exception as e:
    result['probe_error'] = str(e)

# --- 探测 vllm-plugin-FL ---
try:
    import vllm_fl
    result['vllm_plugin_installed'] = True
    try:
        from vllm_fl.dispatch import OpManager
        result['plugin_has_dispatch'] = True
    except ImportError:
        pass
except ImportError:
    pass

print(json.dumps(result, indent=2))
"
```

### 3.5 多维度 FlagGems 集成方式探测（新增）

在已有运行时探测基础上，新增多维度深度探测：

```bash
# === 探测维度1：环境变量检查 ===
${CMD_PREFIX} env | grep -iE "(flag|gems|flagos|use_flag)"

# === 探测维度2：vllm-plugin-FL 入口点检查 ===
${CMD_PREFIX} python3 -c "
import pkg_resources
for ep in pkg_resources.iter_entry_points('vllm.general_plugins'):
    print(f'plugin: {ep.name} = {ep}')
for ep in pkg_resources.iter_entry_points('vllm.platform_plugins'):
    print(f'platform: {ep.name} = {ep}')
" 2>/dev/null

# === 探测维度3：代码级扫描（不依赖特定变量名） ===
${CMD_PREFIX} bash -c "
  # 扫描 vllm 安装目录中所有 gems 相关代码
  VLLM_PATH=\$(python3 -c 'import vllm; print(vllm.__path__[0])' 2>/dev/null)
  if [ -n \"\$VLLM_PATH\" ]; then
    grep -rn 'flag_gems\|flaggems\|use_gems\|enable.*gems\|import.*gems' \$VLLM_PATH/ 2>/dev/null
  fi

  # 扫描 sglang 安装目录
  SGL_PATH=\$(python3 -c 'import sglang; print(sglang.__path__[0])' 2>/dev/null)
  if [ -n \"\$SGL_PATH\" ]; then
    grep -rn 'flag_gems\|flaggems\|use_gems\|enable.*gems\|import.*gems' \$SGL_PATH/ 2>/dev/null
  fi
"

# === 探测维度4：启动脚本扫描 ===
${CMD_PREFIX} bash -c "
  find /usr/local/bin /opt /root -name '*.sh' -exec grep -l 'gems\|flagos\|flag_gems' {} \; 2>/dev/null
"

# === 探测维度5：配置文件扫描 ===
${CMD_PREFIX} bash -c "
  find / -maxdepth 4 -name '*.yaml' -o -name '*.yml' -o -name '*.json' 2>/dev/null | \
    xargs grep -l 'gems\|flagos' 2>/dev/null | head -20
"
```

### 3.6 推导 FlagGems 启用/关闭方法（新增）

综合 3.3~3.5 的探测结果，推导 FlagGems 的启用/关闭方法。**此步骤结果是后续 service-startup 切换 native/flagos 模式的核心依据。**

**推导规则**（按优先级）：

| 探测结果 | enable_method | disable_method | integration_type |
|----------|---------------|----------------|------------------|
| 发现 `USE_FLAGGEMS` 环境变量被引用 | `env:USE_FLAGGEMS=1` | `env:USE_FLAGGEMS=0` | `env_var` |
| 发现 `USE_FLAGOS` 环境变量被引用 | `env:USE_FLAGOS=1` | `env:USE_FLAGOS=0` | `env_var` |
| 发现 vllm-plugin-FL 入口点注册 | `auto`（插件自动启用） | `env:USE_FLAGGEMS=0` 或 `pip uninstall vllm-plugin-FL` | `plugin` |
| 发现代码中直接 import flag_gems | 分析代码确定控制方式 | 分析代码确定关闭方式 | `code_import` |
| 发现启动脚本中有控制逻辑 | `script:<脚本路径>` | `script:<脚本路径>` | `script` |
| 发现配置文件中有开关 | 修改配置文件 | 修改配置文件 | `config_file` |
| 无法确定 | 报告需人工分析 | 报告需人工分析 | `unknown` |

---

## 步骤 4 — 环境变量梳理

列出所有 flag 相关环境变量及其当前值。

```bash
${CMD_PREFIX} env | grep -iE "(flag|gems|flagos)"
```

重点关注的环境变量：

| 环境变量 | 说明 | 典型值 |
|----------|------|--------|
| `USE_FLAGGEMS` | 是否启用 FlagGems | `0` / `1` |
| `USE_FLAGOS` | 是否启用 FlagOS | `0` / `1` |
| `FLAGGEMS_LOG_LEVEL` | FlagGems 日志级别 | `INFO` / `DEBUG` |

---

## 步骤 5 — 写入 context.yaml

将所有检查结果汇总写入 `shared/context.yaml`，包括：
- `execution` 字段（执行模式）
- `inspection` 字段（组件版本、探测结果）
- `flaggems_control` 字段（启用/关闭方法）

---

## 步骤 6 — 生成报告（新增）

### env_report.md

在 `/flagos-workspace/reports/env_report.md`（或宿主机对应路径）生成环境报告：

```markdown
# 环境检测报告

## 执行模式
- Claude Code 位置: host / container
- 命令前缀: <CMD_PREFIX>

## 核心组件
| 组件 | 版本 | 状态 |
|------|------|------|
| torch | x.x.x | 已安装 |
| vllm | x.x.x | 已安装 |
| sglang | - | 未安装 |

## Flag 生态组件
| 组件 | 版本 | 状态 |
|------|------|------|
| flag-gems | x.x.x | 已安装 |
| vllm-plugin-FL | x.x.x | 已安装 |
| flagcx | x.x.x | 已安装 |

## GPU 信息
- 厂商: <vendor>
- 型号: <type>
- 数量: <count>

## 环境变量
- USE_FLAGGEMS: <value>
- USE_FLAGOS: <value>
```

### flag_gems_detection.md

在 `/flagos-workspace/reports/flag_gems_detection.md` 生成 FlagGems 检测报告：

```markdown
# FlagGems 检测报告

## 安装状态
- flag-gems: 已安装 / 版本 x.x.x
- vllm-plugin-fl: 已安装 / 版本 x.x.x

## 集成方式
- 检测到的集成方式: [env_var / plugin_entrypoint / code_import / ...]
- 控制开关: USE_FLAGGEMS 环境变量 / 无（自动启用）

## 运行时能力
- capabilities: [enable_unused, only_enable, yaml_config, ...]

## FlagGems 启用/关闭方法
- 启用: <enable_method>
- 关闭: <disable_method>

## 已注册算子
- 算子总数: N
- 算子列表: [...]
```

**关键**：`启用/关闭方法` 是后续 service-startup 切换 native/flagos 模式的依据，必须从实际探测中得出，不能硬编码。

---

# 完成条件

环境检查成功的标志：

- **执行模式已检测（host / container）**
- 核心组件（torch、vllm/sglang）已确认安装
- flag 组件版本已记录
- FlagGems 代码逻辑已分析（控制方式、算子逻辑）
- **FlagGems 运行时能力已探测（flaggems_capabilities）**
- **FlagGems 多维度集成方式已探测**
- **FlagGems 启用/关闭方法已推导并写入 flaggems_control**
- **vllm-plugin-FL 安装和调度状态已记录**
- 环境变量已梳理
- context.yaml 已更新
- **env_report.md 和 flag_gems_detection.md 已生成**

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| torch 未安装 | 镜像可能有问题，建议更换镜像或手动安装 |
| vllm/sglang 都未安装 | 确认镜像是否为推理镜像 |
| FlagGems 未安装 | 可通过 `flagos-flag-upgrade` 安装 |
| grep 未找到 gems 代码 | 当前框架可能未集成 FlagGems，记录为不可用 |
| 环境变量未设置 | 启动服务时需手动设置 |
| 探测脚本报错 | 检查 `probe_error` 字段，可能是 FlagGems 版本过旧或安装不完整 |
| capabilities 为空列表 | FlagGems 可能版本过旧，算子替换将降级到源码修改模式 |
| 无法推导启用/关闭方法 | 标记 integration_type 为 unknown，后续步骤需人工介入 |

下一步应执行 **flagos-service-startup**。
