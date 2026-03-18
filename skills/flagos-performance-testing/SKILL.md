---
name: flagos-performance-testing
description: 性能基准测试，支持 native/flagos 对比、先导测试、并发自动搜索增强早停、per-test-case 超时、标准 markdown 输出格式
version: 5.0.0
triggers:
  - 性能测试
  - benchmark
  - vllm bench
  - 吞吐量测试
  - performance test
depends_on:
  - flagos-service-startup
next_skill: null
provides:
  - native_perf.result_path
  - native_perf.output_throughput
  - native_perf.total_throughput
  - flagos_perf.initial_path
  - flagos_perf.optimized_path
---

# 性能测试 Skill

支持自动化的 native vs FlagOS 性能对比，先导测试快速评估，并发搜索+增强早停，标准 markdown 表格输出。

**工具脚本**（已由 setup_workspace.sh 部署到容器）:
- `benchmark_runner.py` — 性能测试（`--concurrency-search` 自动搜索+增强早停）
- `performance_compare.py` — 性能对比（`--format markdown` 标准表格输出）

---

## 强制约束

**只能通过 `benchmark_runner.py` 执行性能测试**，禁止直接运行 `vllm bench serve`。

**快速模式触发**：当用户说"快速测试"/"走通流程"/"smoke test"/"验证流程"时，所有 benchmark 命令自动加 `--quick`。

---

# Triton Cache 保护

**警告**：在算子替换后重启服务时，Triton JIT cache 可能导致旧的 kernel 被使用。

```bash
# 清除 Triton cache（在每次算子配置变更后）
${CMD_PREFIX} rm -rf ~/.triton/cache/ 2>/dev/null
${CMD_PREFIX} rm -rf /tmp/triton_cache/ 2>/dev/null
```

**何时需要清除**：
- 算子替换后重启服务前
- FlagGems 升级后重启服务前
- 性能测试结果异常时排查

---

# Plugin 场景的算子覆盖率检查

当 `vllm_plugin_installed=true` 时，在性能测试前检查算子覆盖率：

```bash
# 检查 FlagGems 实际覆盖了多少 aten 算子
${CMD_PREFIX} python3 -c "
import json
try:
    import flag_gems
    flag_gems.enable()
    ops = list(flag_gems.all_registered_ops()) if hasattr(flag_gems, 'all_registered_ops') else []
    print(json.dumps({'covered_ops': len(ops), 'ops': sorted(ops)}))
except Exception as e:
    print(json.dumps({'error': str(e)}))
"
```

如果覆盖率很低（< 20 个算子），FlagOS 加速效果可能有限，应在报告中注明。

---

# 工作流程

## 核心原则：环境感知 + 算子列表必录

**性能测试的执行顺序取决于当前环境中 FlagGems 是否已启用**，而非固定的 native → flagos 顺序。
这样可以减少不必要的服务重启，先测当前状态，再切换测另一状态。

**强制规则：只要 FlagGems 处于启用状态，就必须记录算子列表**。算子列表是后续算子优化的基础，不可遗漏。

最终需要三个结果：
1. **Native 性能**（不启用 FlagGems）
2. **FlagOS 性能**（启用 FlagGems，未优化）
3. **FlagOS 优化后性能**（通过算子替换达到 ≥ 80% native）— 仅在不达标时需要

## 步骤 1：同步配置

从 `shared/context.yaml` 读取服务信息，写入 `/flagos-workspace/perf/config/perf_config.yaml`。

**per-test-case 超时配置**：在 perf_config.yaml 中为不同用例设置不同超时：

```yaml
test_matrix:
  - name: 1k_input_1k_output
    input_len: 1024
    output_len: 1024
    timeout: 600        # 默认 600s 足够
  - name: 32k_input_1k_output
    input_len: 32768
    output_len: 1024
    timeout: 1800       # 32k 输入需要更长时间
  - name: 1k_input_4k_output
    input_len: 1024
    output_len: 4096
    timeout: 900        # 长输出需要更多时间
```

## 步骤 2：判断当前 FlagGems 状态

从 `shared/context.yaml` 的 `flaggems_control.integration_type` 和 `inspection` 字段判断当前环境中 FlagGems 是否已启用。

判断依据（按优先级）：
1. `flaggems_control.enable_method` 是否为 `auto`（plugin 自动启用）
2. 环境变量 `USE_FLAGGEMS=1` / `USE_FLAGOS=1`
3. 代码中是否有 `flag_gems.enable()` 被调用
4. 服务启动日志中是否有 FlagGems 相关输出

```
当前状态判定:
  ├── FlagGems 已启用 → 走路径 A（先测 FlagOS）
  └── FlagGems 未启用 → 走路径 B（先测 Native）
```

---

## 路径 A：FlagGems 已启用（先 FlagOS → 后 Native）

### 步骤 A3：记录算子列表（强制）

**FlagGems 启用状态下，必须先记录算子列表，这是不可或缺的。**

```bash
${CMD_PREFIX} python3 -c "
import json, flag_gems
flag_gems.enable()
ops = list(flag_gems.all_registered_ops()) if hasattr(flag_gems, 'all_registered_ops') else list(flag_gems.all_ops())
with open('/flagos-workspace/results/ops_list.json', 'w') as f:
    json.dump(sorted(ops), f, indent=2)
print(f'已记录 {len(ops)} 个算子到 ops_list.json')
"
```

将算子列表写入 context.yaml：
```yaml
service:
  initial_operator_list: [<算子列表>]
  operator_count: <数量>
```

### 步骤 A4：运行 FlagOS 性能测试（当前状态，无需切换）

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_initial \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_initial"
```

### 步骤 A5：关闭 FlagGems，切换到 Native 模式

通过 `toggle_flaggems.py` 关闭 FlagGems，重启服务。

### 步骤 A6：运行 Native 基线测试

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name native_performance \
  --output-dir /flagos-workspace/results/ \
  --mode native"
```

### 步骤 A7：跳转到步骤 7（对比 + 优化决策）

---

## 路径 B：FlagGems 未启用（先 Native → 后 FlagOS）

### 步骤 B3：运行 Native 基线测试（当前状态，无需切换）

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name native_performance \
  --output-dir /flagos-workspace/results/ \
  --mode native"
```

### 步骤 B4：启用 FlagGems，切换到 FlagOS 模式

通过 `toggle_flaggems.py` 启用 FlagGems，重启服务。

### 步骤 B5：记录算子列表（强制）

**FlagGems 刚启用，必须立即记录算子列表。**

```bash
${CMD_PREFIX} python3 -c "
import json, flag_gems
flag_gems.enable()
ops = list(flag_gems.all_registered_ops()) if hasattr(flag_gems, 'all_registered_ops') else list(flag_gems.all_ops())
with open('/flagos-workspace/results/ops_list.json', 'w') as f:
    json.dump(sorted(ops), f, indent=2)
print(f'已记录 {len(ops)} 个算子到 ops_list.json')
"
```

### 步骤 B6：运行 FlagOS 性能测试

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_initial \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_initial"
```

### 步骤 B7：跳转到步骤 7（对比 + 优化决策）

---

## 步骤 7：性能对比（标准 markdown 格式）

无论走路径 A 还是 B，此时已有 `native_performance.json` 和 `flagos_initial.json`。

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-initial results/flagos_initial.json \
  --output results/performance_compare.csv \
  --target-ratio 0.8 \
  --format markdown"
```

- 返回码 `0`：所有用例 ≥ 80%，跳到步骤 9
- 返回码 `1`：有不达标用例，触发步骤 8

## 步骤 8：[自动] 触发算子优化

前置条件：`ops_list.json` 已存在（步骤 A3 或 B5 中已记录）。

调用 `flagos-operator-replacement` 分组二分搜索。优化过程中使用已记录的算子列表作为搜索空间。

优化完成后重测：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_optimized \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_optimized"
```

## 步骤 9：写入 context.yaml

---

## Scenario B 专用

### 升级前测试

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_before_upgrade \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_before_upgrade"
```

### 升级后测试

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_after_upgrade \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_after_upgrade"
```

### 升级前后对比（标准 markdown 格式）

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-before results/flagos_before_upgrade.json \
  --flagos-after results/flagos_after_upgrade.json \
  --output results/performance_compare.csv \
  --format markdown"
```

输出格式：
```
| Test Case | Native TPS | FlagOS Before TPS | Ratio      | FlagOS After TPS | Ratio      | Best Concurrency |
| --------- | ---------- | ----------------- | ---------- | ---------------- | ---------- | ---------------- |
| 1k→1k     | 17328      | 17511             | **101.1%** | 17325            | **100.0%** | 256              |
```

---

## benchmark_runner.py 参数

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件路径 |
| `--concurrency-search` | 自动搜索最优并发（增强早停：连续2级<3% / 下降>5% / 失败） |
| `--quick` | 快速模式：num_prompts=concurrency，并发取前3+末1，用于流程验证 |
| `--output-name` | 输出文件名（不含扩展名） |
| `--output-dir` | 输出目录 |
| `--mode` | 测试模式标记 |
| `--test-case` | 运行指定测试用例 |
| `--dry-run` | 仅打印命令不执行 |

### 并发搜索增强早停条件

1. **连续 2 级增长 < 3%**：吞吐趋于饱和
2. **吞吐下降 > 5%**：已过拐点，继续加并发无意义
3. **请求失败 > 0**：服务过载

### 最低样本量

并发搜索阶段每级样本量：`max(concurrency, 100)`，避免低并发时样本不足导致结果波动。

### per-test-case 超时

从配置文件 `test_matrix[].timeout` 字段读取，默认 600s。长序列用例（如 32k 输入）可设置 1800s。

## performance_compare.py 参数

| 参数 | 说明 |
|------|------|
| `--native` | 原生性能 JSON（必填） |
| `--flagos-initial` | FlagOS 初始性能 |
| `--flagos-optimized` | FlagOS 优化后性能 |
| `--flagos-before` | 升级前性能（Scenario B） |
| `--flagos-after` | 升级后性能（Scenario B） |
| `--output` | CSV 输出路径 |
| `--target-ratio` | 目标比率（默认 0.8） |
| `--format` | 输出格式: `text`（默认） / `markdown` |

---

## 完成条件

- 测试脚本已在容器中就绪
- 当前 FlagGems 状态已判断（环境感知）
- **算子列表已记录**（FlagGems 启用时 ops_list.json 必须存在）
- native_performance.json 已生成
- flagos_initial.json 已生成
- 对比结果已生成（performance_compare.csv）
- 性能比率已判断（≥ 80% 或触发算子优化）
- 如触发优化：flagos_optimized.json 已生成
- context.yaml 已更新
