---
name: flagos-operator-replacement
description: 算子替换与优化工具，支持被动排除（评测报错）和主动分组二分搜索优化（性能驱动），支持 plugin 两层替换架构，算子列表自动发现，全自动搜索编排
version: 5.0.0
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
2. **主动优化模式**：分组二分搜索最优算子集，使 FlagOS 性能 ≥ 目标比率

**工具脚本**（已由 setup_workspace.sh 部署到容器）:
- `operator_optimizer.py` — 算子优化器（分组二分搜索、算子列表自动发现、映射表生成）
- `operator_search.py` — 搜索编排（完整的 next→toggle→restart→benchmark→update 自动循环）

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
  gpu_compute_capability: <来自 pre-service-inspection>
  gpu_arch: <来自 pre-service-inspection>
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

# GPU 架构预检

在开始算子替换之前，检查 GPU 架构信息（来自 inspect_env.py 的 `gpu_compute_capability` 和 `gpu_arch`）。

| GPU 架构 | Compute Capability | 已知限制 |
|----------|-------------------|----------|
| sm_80 (A100) | 8.0 | FlagGems 完整支持 |
| sm_89 (L40S/4090) | 8.9 | 部分算子可能不支持 |
| sm_90 (H100/H800) | 9.0 | DeepGemm 可用 |
| sm_70 (V100) | 7.0 | Triton 支持有限，多数算子不可用 |

**如果 `gpu_arch` 为 sm_70 或更低，警告用户 FlagGems 支持有限，算子问题可能较多。**

---

# Plugin 场景的两层替换架构

当 `vllm_plugin_installed=true` 且 `plugin_has_dispatch=true` 时，算子替换涉及**两层**：

```
┌─────────────────────────────────────────┐
│ Layer A: flag_gems 层                    │
│   gems.txt → 控制哪些算子被注册          │
│   位置: flag_gems 包内部                 │
│   修改: toggle_flaggems.py / YAML 配置   │
├─────────────────────────────────────────┤
│ Layer B: vllm_fl dispatch 层             │
│   whitelist / dispatch 逻辑              │
│   位置: vllm_fl/dispatch/               │
│   控制: VLLM_FL_FLAGOS_WHITELIST 环境变量│
│   或修改 dispatch 源码                    │
└─────────────────────────────────────────┘
```

## 算子列表自动发现

**不硬编码 gems.txt**，而是自动搜索 flag_gems 源码目录下记录算子列表的 txt 文件。`operator_optimizer.py discover` 子命令完成自动发现：

```bash
# 自动搜索 flaggems 中的算子列表文件
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py discover

# 搜索并保存为 JSON
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py discover \
  --save-ops /flagos-workspace/results/ops_list.json
```

发现逻辑：
1. 定位 flag_gems 安装目录（`import flag_gems; flag_gems.__file__`）
2. 遍历所有 `.txt` 文件
3. 通过内容特征识别算子列表（每行一个短标识符，与已知算子名有交集）
4. 返回匹配度最高的文件及解析出的算子列表

找到的算子列表文件就是运行时实际加载的算子清单，是算子替换的标准：
1. 从该列表中移除问题算子
2. 重写该文件（或等效的配置方式）
3. 重启服务使生效

## 修复 vllm_fl 代码的操作模板

当 dispatch 层也需要修改时（通常是 whitelist 方式）：

```bash
# 方式 1：通过环境变量控制 whitelist
# 将需要保留的算子用逗号分隔
export VLLM_FL_FLAGOS_WHITELIST="addmm,bmm,mm,linear,..."

# 方式 2：修改 dispatch 源码（备份 → 修改 → 验证）
${CMD_PREFIX} cp /path/to/vllm_fl/dispatch/ops.py /path/to/vllm_fl/dispatch/ops.py.bak
# 然后注释掉问题算子的 dispatch 注册
```

---

# 运行时算子名映射

FlagGems 注册的算子名（运行时函数名）与 PyTorch aten 算子名不完全一致。`operator_optimizer.py mapping` 子命令可以生成完整映射。

常见不一致项：

| 运行时函数名 | aten 算子名 | 说明 |
|-------------|------------|------|
| `arange_start` | `arange.start` | 点号变下划线 |
| `arange_start_step` | `arange.start_step` | 同上 |
| `add_scalar` | `add.Scalar` | 大小写 + 点号 |
| `fill_scalar_` | `fill_.Scalar` | 下划线位置不同 |
| `sort_stable` | `sort.stable` | 点号变下划线 |
| `to_copy` | `_to_copy` | 前缀下划线 |

```bash
# 生成映射表
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py mapping \
  --output /flagos-workspace/results/op_mapping.json
```

---

# 已知问题模式库

从实战中沉淀的 5 个高频问题模式，优先检查：

## 模式 1：SM 架构不支持

**症状**：`CUDA error: no kernel image is available for execution on the device`
**原因**：Triton kernel 未编译对应 SM 架构
**修复**：禁用报错算子，检查 `gpu_arch` 是否在 FlagGems 支持列表中

## 模式 2：算子参数不匹配

**症状**：`RuntimeError: xxx() got an unexpected keyword argument`
**原因**：FlagGems 实现的算子签名与 PyTorch 版本不一致
**修复**：禁用该算子

## 模式 3：精度问题导致 NaN

**症状**：输出中出现 NaN 或 Inf，精度评测失败
**原因**：FlagGems 算子在特定输入下精度不足
**修复**：禁用该算子，通常涉及 `softmax`、`layer_norm`、`rms_norm`

## 模式 4：DeepGemm 兼容性

**症状**：`VLLM_USE_DEEP_GEMM=1` 时启动崩溃
**原因**：DeepGemm 与某些 FlagGems 算子冲突
**修复**：设置 `VLLM_USE_DEEP_GEMM=0` 或禁用冲突算子

## 模式 5：dispatch 层遗漏

**症状**：gems.txt 中已移除算子但仍被调用
**原因**：vllm_fl dispatch 层有独立的算子注册，未同步修改
**修复**：同时修改 flag_gems 层和 dispatch 层（见两层替换架构）

---

# 两种触发方式

| 触发方式 | 场景 | 模式 |
|----------|------|------|
| 评测报错 | eval-correctness 发现算子问题 | **被动排除**（Layer 1-4） |
| 性能不达标 | performance-testing 发现 FlagOS < 80% native | **主动分组二分搜索** |

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
| 已知模式库 | 对照上方 5 个已知模式快速定位 |
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

## 步骤 4 — Plugin 场景：同步修改 dispatch 层

如果 `plugin_has_dispatch=true`，在修改 flag_gems 层后还需同步 dispatch 层：

```bash
# 检查 dispatch 层的算子注册
${CMD_PREFIX} grep -rn "register\|dispatch" /path/to/vllm_fl/dispatch/ 2>/dev/null | head -20

# 通过环境变量或源码修改同步禁用
```

## 步骤 5 — 报告替换详情并提醒重启

---

# 模式二：主动分组二分搜索

## 触发条件

`performance-testing` 对比结果显示 FlagOS 性能 < 80% native。

## 搜索策略

**分组二分搜索**（替代旧版逐个遍历）：

```
算子按功能分为 5 组：
  compute: addmm, mm, bmm, linear, matmul, ...
  memory:  copy_, zero_, zeros, ones, full, fill_scalar_, ...
  math:    cos, sin, pow_scalar, exp, log, sqrt, relu, gelu, silu, ...
  index:   gather, scatter, scatter_add_0, index, embedding, ...
  reduce:  cumsum, sort, argmax, sum, mean, softmax, layer_norm, rms_norm, ...
  other:   未归类算子

搜索流程：
  1. 整组禁用 → benchmark
     ├── 仍 ≥ 80% → 整组全禁用，跳过组内搜索 ✓
     └── < 80% → 组内二分定位关键算子
  2. 二分搜索：禁用前半 → benchmark → 缩小范围
  3. 预计搜索轮次：5 组 × ~3 轮 = ~15 轮（vs 旧版 38 轮）
```

## 工作流程

### 步骤 O1 — 复制优化器到容器

```bash
docker cp skills/flagos-operator-replacement/operator_optimizer.py \
  $CONTAINER:/flagos-workspace/scripts/
docker cp skills/flagos-operator-replacement/operator_search.py \
  $CONTAINER:/flagos-workspace/scripts/
```

### 步骤 O2 — 自动发现并导出算子列表

```bash
# 自动发现算子列表文件并保存
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py discover \
  --save-ops /flagos-workspace/results/ops_list.json
```

如果自动发现失败，回退到 API 枚举：

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

### 步骤 O2.5 — [可选] 获取运行时算子列表

如果有运行时 profiling 数据（如 torch.profiler trace），提取实际调用的算子：

```bash
# 运行时算子列表保存为 JSON
${CMD_PREFIX} python3 -c "
import json
# 从 profiler trace 或日志中提取
runtime_ops = [...]  # 实际调用的算子
with open('/flagos-workspace/results/runtime_ops.json', 'w') as f:
    json.dump(runtime_ops, f, indent=2)
"
```

### 步骤 O3 — 初始化优化器

```bash
# 基本模式（搜索全量算子）
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py init \
  --ops-file /flagos-workspace/results/ops_list.json \
  --native-throughput <native_perf.output_throughput> \
  --target-ratio 0.8

# 或：仅搜索运行时算子（减少搜索空间）
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py init \
  --ops-file /flagos-workspace/results/ops_list.json \
  --runtime-ops /flagos-workspace/results/runtime_ops.json \
  --native-throughput <native_perf.output_throughput> \
  --target-ratio 0.8

# 或：使用线性搜索（兼容旧模式）
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py init \
  --ops-file /flagos-workspace/results/ops_list.json \
  --native-throughput <native_perf.output_throughput> \
  --no-group-search
```

### 步骤 O4 — 运行搜索循环

**推荐方式：使用 operator_search.py 全自动搜索**（减少 Claude Code 思考开销）：

```bash
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_search.py run \
  --state-path /flagos-workspace/results/operator_config.json \
  --perf-config /flagos-workspace/perf/config/perf_config.yaml \
  --service-startup-cmd "bash /flagos-workspace/scripts/start_service.sh" \
  --gems-txt-path ${GEMS_TXT_PATH} \
  --max-rounds 20
```

脚本自动完成：next→应用算子配置→清除Triton cache→重启服务→等待就绪→quick benchmark→更新结果→循环。

**备选方式：手动逐步搜索**（需要更细粒度控制时使用）：

```
1. 获取下一步操作:
   ${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py next

2. 根据返回的 test_enabled_ops，应用算子配置

3. 清除 Triton cache + 重启服务

4. 运行快速 benchmark:
   ${CMD_PREFIX} python3 /flagos-workspace/scripts/benchmark_runner.py \
     --config /flagos-workspace/perf/config/perf_config.yaml \
     --quick --output-name optimize_step_N --output-dir /flagos-workspace/results/

5. 更新优化器:
   ${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py update \
     --op-name <名称> --throughputs '{"1":800,"64":900,"256":850}' \
     --native-throughput <native_perf.output_throughput>

6. 检查状态，继续或结束
```

### 步骤 O5 — 生成优化报告

```bash
${CMD_PREFIX} python3 /flagos-workspace/scripts/operator_optimizer.py report
```

### 步骤 O6 — 应用最终配置

使用优化器输出的最终 `enabled_ops` 列表，通过 Layer 1-4 策略应用配置。

Plugin 场景需同步修改 dispatch 层。

### 步骤 O7 — 验证最终性能

重启服务后运行完整 benchmark 验证优化后性能。

## 搜索限制

- 分组二分搜索：预计 15 轮左右完成
- 线性搜索：遍历搜索范围内所有算子一轮
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
  search_mode: "group"
  enabled_ops: [<最终启用列表>]
  disabled_ops: [<最终禁用列表>]
  operator_config_path: "/flagos-workspace/results/operator_config.json"
  search_log:
    - op: "memory"
      decision: "group_disabled"
      throughput: 950.0
      ratio: 0.95
    - op: "compute"
      decision: "need_binary_search"
      throughput: 700.0
      ratio: 0.70
```

---

# 完成条件

## 被动排除模式
- 当前可用算子已查询
- 需要替换的算子已确定
- 已对照已知问题模式库
- GPU 架构已检查
- 操作层级已根据 capabilities 自动选择
- 替换操作已执行（含 dispatch 层同步）
- 替换详情（含回滚方式）已报告给用户
- context.yaml 已更新
- 已提醒用户重启服务

## 主动优化模式
- 算子列表已导出
- 优化器已初始化（分组二分或线性）
- 搜索已完成（或用户终止）
- 最终算子配置已应用（含 dispatch 层）
- 验证 benchmark 确认达标
- operator_config.json 已保存
- context.yaml 已更新 optimization 字段

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| gems.txt 不存在 | 服务可能未启动过，先执行 `flagos-service-startup` |
| 代码路径不存在 | 重新执行 `flagos-pre-service-inspection` 更新路径 |
| 替换后服务仍报错 | 检查是否 dispatch 层未同步修改（模式 5） |
| capabilities 为空 | FlagGems 版本过旧，将自动降级到 Layer 4（源码修改） |
| 贪心搜索中途服务挂掉 | 保存进度 → 恢复上一个可用配置 → 支持断点继续 |
| 优化后仍不达标 | 检查是否有硬件限制（gpu_arch），报告给用户 |
| YAML 配置写入后不生效 | 确认 FlagGems 启动时使用了 `resolve_user_setting()` |
| 运行时算子名不匹配 | 使用 `mapping` 子命令生成映射表，确认名称对应关系 |
| sm_70/sm_75 大量算子失败 | GPU 架构过旧，建议减少 FlagGems 算子使用范围 |

---

# 失败恢复

1. **算子优化中途失败**：`operator_optimizer.py` 自动保存进度到 `operator_config.json`
2. **恢复搜索**：下次调用 `next` 自动从上次位置继续
3. **回退到可用配置**：应用 `operator_config.json` 中 `enabled_ops` 的上一个快照
4. **dispatch 层回退**：从 `.bak` 备份文件还原
