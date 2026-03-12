---
name: flagos-operator-replacement
description: 算子替换与优化工具，支持被动排除（评测报错）和主动贪心搜索优化（性能驱动），根据运行时探测自动选择最优替换方式
version: 3.0.0
license: internal
triggers:
  - operator replacement
  - replace operator
  - 算子替换
  - gems replace
  - 算子优化
  - operator optimize
depends_on: []
provides:
  - operator_replacement.replaced_operators
  - operator_replacement.replacement_mode
  - operator_replacement.final_gems_txt
  - operator_replacement.config_file_path
  - operator_replacement.available_ops
  - operator_replacement.rollback_info
  - optimization.target_ratio
  - optimization.current_ratio
  - optimization.enabled_ops
  - optimization.disabled_ops
  - optimization.operator_config_path
  - optimization.search_log
---

# 算子替换与优化 Skill

独立工具，可在任何阶段按需调用。支持两种模式：

1. **被动排除模式**：根据评测报错信息排除问题算子（沿用 Layer 1-4 分层降级）
2. **主动优化模式**（新增）：贪心搜索最优算子集，使 FlagOS 性能 ≥ 目标比率

**核心设计**：FlagGems / vllm-plugin-FL 处于持续迭代中，本 skill 不硬编码任何特定 API，而是根据 `pre-service-inspection` 探测到的 `flaggems_capabilities` 自动选择最优操作方式，逐层降级保证稳定性。

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
gpu:
  vendor: <来自 container-preparation>
execution:
  mode: <来自 pre-service-inspection>
  cmd_prefix: <来自 pre-service-inspection>
inspection:
  flaggems_control: <来自 pre-service-inspection>
  flaggems_logic: <来自 pre-service-inspection>
  flaggems_code_path: <来自 pre-service-inspection>
  flaggems_code_lines: <来自 pre-service-inspection>
  flaggems_capabilities: <来自 pre-service-inspection>
  vendor_config_path: <来自 pre-service-inspection>
  vllm_plugin_installed: <来自 pre-service-inspection>
  plugin_has_dispatch: <来自 pre-service-inspection>
service:
  gems_txt_path: <来自 service-startup>
  initial_operator_list: <来自 service-startup>
native_perf:
  output_throughput: <来自 performance-testing>
flaggems_control:
  enable_method: <来自 pre-service-inspection>
  disable_method: <来自 pre-service-inspection>
```

## 写入 shared/context.yaml

```yaml
operator_replacement:
  replaced_operators: []
  replacement_mode: ""
  final_gems_txt: ""
  config_file_path: ""
  available_ops: []
  rollback_info: ""

optimization:
  target_ratio: 0.8
  current_ratio: <当前性能比>
  enabled_ops: [<最终启用的算子列表>]
  disabled_ops: [<最终禁用的算子列表>]
  operator_config_path: "/flagos-workspace/results/operator_config.json"
  search_log: [<搜索历史>]
```

---

# 两种触发方式

| 触发方式 | 场景 | 模式 |
|----------|------|------|
| 评测报错 | eval-correctness 发现算子问题 | **被动排除**（Layer 1-4） |
| 性能不达标 | performance-testing 发现 FlagOS < 80% native | **主动贪心搜索** |

---

# 模式一：被动排除（沿用）

## 分层降级策略

根据 `flaggems_capabilities` 从最优方案逐层降级：

```
Layer 1 (最优): YAML 配置文件     ← 需要 capabilities 含 yaml_config
Layer 2:        only_enable API   ← 需要 capabilities 含 only_enable
Layer 3:        enable(unused=)   ← 需要 capabilities 含 enable_unused
Layer 4 (兜底): 源码直接修改       ← 任何版本都能用，但最脆弱
```

| Layer | 所需能力 | 操作方式 | 稳定性 | 回滚难度 |
|-------|----------|----------|--------|----------|
| 1 | `yaml_config` | 写入/修改 YAML 配置文件 | 最高 | 删除文件 |
| 2 | `only_enable` | 修改启动入口的 API 调用 | 高 | 改回原调用 |
| 3 | `enable_unused` | 修改 enable() 的 unused 参数 | 中 | 删除参数 |
| 4 | 无（兜底） | 修改源码中的算子列表 | 低 | 用备份还原 |

## 步骤 1 — 查询当前可用算子

```bash
${CMD_PREFIX} python3 -c "
import json
ops = []
error = ''

try:
    import flag_gems
    flag_gems.enable()

    if hasattr(flag_gems, 'all_registered_ops'):
        ops = list(flag_gems.all_registered_ops())
    elif hasattr(flag_gems, 'all_ops'):
        ops = list(flag_gems.all_ops())
    else:
        try:
            import flag_gems.ops as ops_module
            ops = [name for name in dir(ops_module) if not name.startswith('_')]
        except ImportError:
            error = 'unable to enumerate ops'
except ImportError:
    error = 'flag_gems not installed'
except Exception as e:
    error = str(e)

print(json.dumps({'registered_ops': sorted(ops), 'count': len(ops), 'error': error}, indent=2))
"
```

## 步骤 2 — 确定需要替换的算子

| 来源 | 说明 |
|------|------|
| 评测报错 | 服务端 CUDA error、算子不支持等报错 → 排除问题算子 |
| 用户指定 | 用户明确指定需要替换/排除的算子 |
| 日志分析 | `flagos-log-analyzer` 识别出的问题算子 |

## 步骤 3 — 选择操作层级并执行

### Layer 1：YAML 配置文件（capabilities 含 `yaml_config`）

```bash
GEMS_PATH=$(${CMD_PREFIX} python3 -c "
import flag_gems, os
print(os.path.dirname(flag_gems.__file__))
")

${CMD_PREFIX} python3 -c "
import os
config_dir = '${GEMS_PATH}/runtime/backend/_<vendor>'
os.makedirs(config_dir, exist_ok=True)
config_path = os.path.join(config_dir, 'enable_configs.yaml')

content = '''exclude:
  - <problem_operator_1>
  - <problem_operator_2>
'''

with open(config_path, 'w') as f:
    f.write(content)
print('配置已写入:', config_path)
"
```

**回滚方式**：`${CMD_PREFIX} rm <config_file_path>`

### Layer 2：only_enable API（capabilities 含 `only_enable` 但无 `yaml_config`）

修改 FlagGems 启动入口代码，将 `enable()` 调用替换为 `only_enable(include=[...])`。

**先备份 → 展示 diff → 确认后执行**。

### Layer 3：enable(unused=) API（capabilities 含 `enable_unused` 但无 `only_enable`）

在现有 `enable()` 调用中添加 `unused` 参数。

### Layer 4：源码直接修改（兜底）

**先完整读取 → 理解结构 → 展示 diff → 确认后执行 → 验证**。

## 步骤 4 — 报告替换详情并提醒重启

---

# 模式二：主动贪心搜索（新增）

## 触发条件

`performance-testing` 对比结果显示 FlagOS 性能 < 80% native。

## 工作流程

### 步骤 O1 — 复制优化器到容器

```bash
docker cp skills/flagos-operator-replacement/operator_optimizer.py \
  $CONTAINER:/flagos-workspace/scripts/
```

### 步骤 O2 — 导出当前算子列表

```bash
${CMD_PREFIX} python3 -c "
import json, flag_gems
flag_gems.enable()
ops = list(flag_gems.all_registered_ops()) if hasattr(flag_gems, 'all_registered_ops') else list(flag_gems.all_ops())
with open('/flagos-workspace/results/ops_list.json', 'w') as f:
    json.dump(sorted(ops), f, indent=2)
print(f'导出 {len(ops)} 个算子')
"
```

### 步骤 O3 — 初始化优化器

```bash
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py init \
  --ops-file /flagos-workspace/results/ops_list.json \
  --native-throughput <native_perf.output_throughput> \
  --target-ratio 0.8
```

### 步骤 O4 — 迭代搜索循环

**每轮操作**：

```
1. 获取下一步操作:
   ${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py next

2. 根据返回的 test_enabled_ops，应用算子配置:
   - 使用 Layer 1-4 降级策略应用配置

3. 重启服务（flagos 模式）

4. 运行快速 benchmark:
   ${CMD_PREFIX} python3 /flagos-workspace/scripts/benchmark_runner.py \
     --config /flagos-workspace/perf/config/perf_config.yaml \
     --test-case 1k_input_1k_output \
     --output-name optimize_step_N \
     --output-dir /flagos-workspace/results/

5. 提取吞吐量并更新优化器:
   ${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py update \
     --op-name <当前测试的算子名> \
     --throughput <测试吞吐量> \
     --native-throughput <native_perf.output_throughput>

6. 检查状态，继续或结束
```

### 步骤 O5 — 生成优化报告

```bash
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py report
```

### 步骤 O6 — 应用最终配置

使用优化器输出的最终 `enabled_ops` 列表，通过 Layer 1-4 策略应用配置。

### 步骤 O7 — 验证最终性能

重启服务后运行完整 benchmark 验证优化后性能。

## 搜索限制

- 默认最多遍历所有算子一轮
- 贪心搜索 3 轮仍未达标时，询问用户是否继续
- 每轮保存进度，支持断点续搜

---

# 写入 context.yaml

```yaml
operator_replacement:
  replaced_operators:
    - name: "softmax"
      reason: "optimization: ratio 95% without it"
      action: "disabled"
  replacement_mode: "yaml_config"
  final_gems_txt: "/path/to/gems.txt"
  config_file_path: "/path/to/enable_configs.yaml"
  available_ops: [...]
  rollback_info: "rm /path/to/enable_configs.yaml"

optimization:
  target_ratio: 0.8
  current_ratio: 0.85
  enabled_ops: [<最终启用列表>]
  disabled_ops: [<最终禁用列表>]
  operator_config_path: "/flagos-workspace/results/operator_config.json"
  search_log:
    - op: "softmax"
      decision: "disabled"
      throughput: 950.0
      ratio: 0.95
```

---

# 完成条件

## 被动排除模式
- 当前可用算子已查询
- 需要替换的算子已确定
- 操作层级已根据 capabilities 自动选择
- 替换操作已执行
- 替换详情（含回滚方式）已报告给用户
- context.yaml 已更新
- 已提醒用户重启服务

## 主动优化模式
- 算子列表已导出
- 优化器已初始化
- 贪心搜索已完成（或用户终止）
- 最终算子配置已应用
- 验证 benchmark 确认达标
- operator_config.json 已保存
- context.yaml 已更新 optimization 字段

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| gems.txt 不存在 | 服务可能未启动过，先执行 `flagos-service-startup` |
| 代码路径不存在 | 重新执行 `flagos-pre-service-inspection` 更新路径 |
| 替换后服务仍报错 | 检查报错的算子是否全部被排除，可能需要多轮替换 |
| capabilities 为空 | FlagGems 版本过旧，将自动降级到 Layer 4（源码修改） |
| 贪心搜索中途服务挂掉 | 保存进度 → 恢复上一个可用配置 → 支持断点继续 |
| 优化后仍不达标 | 检查是否有硬件限制，报告给用户 |
| YAML 配置写入后不生效 | 确认 FlagGems 启动时使用了 `resolve_user_setting()` |

---

# 失败恢复

1. **算子优化中途失败**：`operator_optimizer.py` 自动保存进度到 `operator_config.json`
2. **恢复搜索**：下次调用 `next` 自动从上次位置继续
3. **回退到可用配置**：应用 `operator_config.json` 中 `enabled_ops` 的上一个快照
