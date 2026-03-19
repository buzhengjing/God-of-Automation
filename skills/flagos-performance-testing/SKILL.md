---
name: flagos-performance-testing
description: 三版性能基准测试（Native / Full FlagGems / Optimized FlagGems），支持快速模式、并发自动搜索（饱和自动停止）、per-test-case 超时、标准 markdown 输出格式
version: 6.0.0
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
  - flagos_full_perf.result_path
  - flagos_optimized_perf.result_path
---

# 性能测试 Skill

支持三版自动化性能测试：Native → Full FlagGems → Optimized FlagGems（如需优化），标准 markdown 三列表格输出。

**三版结果文件**：
- `native_performance.json` — Native（无 FlagGems）
- `flagos_full.json` — Full FlagGems（全量算子）
- `flagos_optimized.json` — Optimized FlagGems（≥80% 组合，如需优化才产出）

**工具脚本**（已由 setup_workspace.sh 部署到容器）:
- `benchmark_runner.py` — 性能测试（`--concurrency-search` 自动搜索+增强早停）
- `performance_compare.py` — 性能对比（`--format markdown` 标准三列表格输出）

---

## 强制约束

**只能通过 `benchmark_runner.py` 执行性能测试**，禁止直接运行 `vllm bench serve`。

**快速模式触发**：当用户说"快速测试"/"走通流程"/"smoke test"/"验证流程"时，所有 benchmark 命令自动加 `--quick`。quick 模式只跑 `prefill1_decode512` 用例，num_prompts=concurrency，并发到 256。

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

## 核心原则：三版测试 + 按需优化

新工作流按固定顺序执行三版测试：
1. **Native**（步骤⑥）— 关闭 FlagGems 的基线性能
2. **Full FlagGems**（步骤⑨）— 启用全量 FlagGems 的性能
3. **Optimized FlagGems**（步骤⑫）— 仅在 Full 不达标时，通过算子优化找到 ≥80% 的组合

**算子列表必录**：只要 FlagGems 处于启用状态，必须记录算子列表到 ops_list.json，这是算子优化的基础。

最终需要三个结果文件：
1. **native_performance.json** — Native 性能
2. **flagos_full.json** — Full FlagGems 性能
3. **flagos_optimized.json** — Optimized FlagGems 性能（仅在不达标时产出）

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

## 步骤 3：运行 Native 基线测试（步骤⑥）

此时服务已以 native 模式启动（FlagGems 关闭）。

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name native_performance \
  --output-dir /flagos-workspace/results/ \
  --mode native"
```

## 步骤 4：启用全量 FlagGems，切换到 FlagOS 模式（步骤⑦）

通过 `toggle_flaggems.py` 启用 FlagGems，重启服务。

## 步骤 5：记录算子列表（强制）

**FlagGems 启用状态下，必须先记录算子列表。**

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

## 步骤 6：运行 Full FlagGems 性能测试（步骤⑨）

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_full \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_full"
```

## 步骤 7：性能对比（步骤⑩）

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-full results/flagos_full.json \
  --output results/performance_compare.csv \
  --target-ratio 0.8 \
  --format markdown"
```

- 返回码 `0`：所有用例 ≥ 80%，Optimized = Full，跳到步骤 9
- 返回码 `1`：有不达标用例，触发步骤 8

## 步骤 8：[自动] 触发算子优化（步骤⑪）

前置条件：`ops_list.json` 已存在（步骤 5 中已记录）。

调用 `flagos-operator-replacement` 分组二分搜索。优化过程中使用已记录的算子列表作为搜索空间。

优化完成后重测（步骤⑫）：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_optimized \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_optimized"
```

## 步骤 9：三版性能对比 + 最终报告（步骤⑬）

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-optimized results/flagos_optimized.json \
  --flagos-full results/flagos_full.json \
  --output results/performance_compare_final.csv \
  --target-ratio 0.8 \
  --format markdown"
```

当 Optimized = Full（全量已达标）时，只传 `--flagos-full`，不传 `--flagos-optimized`。

## 步骤 10：写入 context.yaml

---

## benchmark_runner.py 参数

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件路径 |
| `--concurrency-search` | 自动搜索最优并发（饱和自动停止：连续2级<3% / 下降>5% / 失败） |
| `--quick` | 快速模式：只跑 early_stop=false 的用例（prefill1_decode512, 1k_input_1k_output），num_prompts=concurrency，并发到256 |
| `--output-name` | 输出文件名（不含扩展名） |
| `--output-dir` | 输出目录 |
| `--mode` | 测试模式标记 |
| `--test-case` | 运行指定测试用例 |
| `--dry-run` | 仅打印命令不执行 |

### 并发搜索停止条件

1. **连续 2 级增长 < 3%**：吞吐趋于饱和
2. **吞吐下降 > 5%**：已过拐点，继续加并发无意义
3. **请求失败 > 0**：服务过载

以上条件仅对 `early_stop: true` 的用例生效。`prefill1_decode512` 和 `1k_input_1k_output` 两个用例设置 `early_stop: false`，所有并发全跑，用于跨平台对比基准。

搜索结果中标注**最佳并发数**（吞吐峰值对应的并发级别），不区分是否提前停止。

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
| `--flagos-full` | FlagOS 全量算子性能 |
| `--output` | CSV 输出路径 |
| `--target-ratio` | 目标比率（默认 0.8） |
| `--format` | 输出格式: `text`（默认） / `markdown` |

---

## 完成条件

- 测试脚本已在容器中就绪
- **算子列表已记录**（FlagGems 启用时 ops_list.json 必须存在）
- native_performance.json 已生成
- flagos_full.json 已生成
- 对比结果已生成（performance_compare.csv）
- 性能比率已判断（≥ 80% 或触发算子优化）
- 如触发优化：flagos_optimized.json 已生成
- 最终三版对比已生成（performance_compare_final.csv）
- context.yaml 已更新
