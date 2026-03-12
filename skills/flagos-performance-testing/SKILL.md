---
name: flagos-performance-testing
description: 性能基准测试，支持 native/flagos 对比、并发自动搜索早停、自动性能判断和算子优化触发
version: 3.0.0
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

支持自动化的 native vs FlagOS 性能对比流程，包括：
- 并发级别自动搜索 + 早停（吞吐增长 < 3% 时停止）
- 自动性能对比判断（是否 ≥ 80% native）
- 性能不达标时自动触发算子优化

---

# 统一工作目录

```
容器内: /flagos-workspace/
    ├── scripts/
    │   ├── benchmark_runner.py       # 性能测试脚本（重构版）
    │   └── performance_compare.py    # 性能对比脚本
    ├── results/
    │   ├── native_performance.json   # 原生性能基线
    │   ├── flagos_initial.json       # FlagOS 初始性能
    │   ├── flagos_optimized.json     # FlagOS 优化后性能
    │   └── performance_compare.csv   # 对比报告
    └── perf/
        └── config/
            └── perf_config.yaml      # 测试配置

宿主机: /data/flagos-workspace/<model_name>/  ← 实时同步
```

---

## 文件结构

```
flagos-performance-testing/
├── SKILL.md                  # 本文件
├── benchmark_runner.py       # 测试入口（重构版，含并发搜索+早停）
├── performance_compare.py    # 性能对比工具
├── perf.py                   # 旧版入口（保留兼容）
├── config/
│   └── perf_config.yaml      # 测试配置（可编辑）
└── output/                   # 旧版结果输出
```

---

## ⚠️ 强制约束

**你必须且只能通过以下方式执行性能测试：**

```bash
python benchmark_runner.py --config config/perf_config.yaml [options]
# 或兼容旧版：
python perf.py --config config/perf_config.yaml
```

**绝对禁止：**
- ❌ 直接运行 `vllm bench serve` 或任何其他基准测试命令
- ❌ 自行编写测试脚本或代码
- ❌ 绕过 benchmark_runner.py 执行测试

**唯一允许的操作：**
- ✅ 修改 `config/perf_config.yaml` 调整测试参数
- ✅ 运行 `benchmark_runner.py` 及其参数
- ✅ 运行 `performance_compare.py` 对比结果

---

## 自动化执行流程

### 步骤 1：复制脚本到容器工作目录

```bash
CONTAINER=<container_name>

# 复制测试脚本到 scripts 目录
docker cp skills/flagos-performance-testing/benchmark_runner.py $CONTAINER:/flagos-workspace/scripts/
docker cp skills/flagos-performance-testing/performance_compare.py $CONTAINER:/flagos-workspace/scripts/

# 复制配置到 perf 目录（兼容旧结构）
docker cp skills/flagos-performance-testing/config/. $CONTAINER:/flagos-workspace/perf/config/

# 创建结果目录
docker exec $CONTAINER mkdir -p /flagos-workspace/results
```

### 步骤 2：同步配置信息

从 `shared/context.yaml` 读取以下字段，填充到 `/flagos-workspace/perf/config/perf_config.yaml`：

| context.yaml 字段 | perf_config.yaml 字段 |
|-------------------|----------------------|
| `service.host` | `server.host` |
| `service.port` | `server.port` |
| `model.name` 或 `model.container_path` | `model.name` |
| `model.tokenizer_path` 或 `model.container_path` | `model.tokenizer_path` |

**注意**：容器内服务地址通常为 `127.0.0.1` 或 `localhost`

### 步骤 3：调整测试矩阵（如需要）

根据模型的 `max_model_len` 禁用超出范围的测试用例：

```yaml
test_matrix:
  - name: "1k_input_1k_output"
    enabled: true
  - name: "16k_input_1k_output"
    enabled: false  # 如果 max_model_len < 16384
```

### 步骤 4：运行 Native 性能基线测试

**前提**：服务已以 native 模式启动（参考 flagos-service-startup）。

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name native_performance \
  --output-dir /flagos-workspace/results/ \
  --mode native"
```

将结果写入 context.yaml：

```yaml
native_perf:
  result_path: "/flagos-workspace/results/native_performance.json"
  output_throughput: <从结果中提取最优值>
  total_throughput: <从结果中提取最优值>
```

### 步骤 5：运行 FlagOS 初始性能测试

**前提**：服务已以 flagos 模式重启（参考 flagos-service-startup）。

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_initial \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_initial"
```

### 步骤 6：运行性能对比

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-initial results/flagos_initial.json \
  --output results/performance_compare.csv \
  --target-ratio 0.8"
```

**自动判断结果**：
- 返回码 `0`：所有测试用例的 FlagOS/Native 比率 ≥ 80%，**跳到步骤 8**
- 返回码 `1`：存在不达标的测试用例，**触发步骤 7 算子优化**

### 步骤 7：[自动] 触发算子优化（如需要）

当性能不达标时，自动触发 `flagos-operator-replacement` 的贪心搜索优化模式。

优化完成后，重启服务并运行 FlagOS 优化后性能测试：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_optimized \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_optimized"
```

运行最终对比（包含优化后结果）：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-initial results/flagos_initial.json \
  --flagos-optimized results/flagos_optimized.json \
  --output results/performance_compare.csv \
  --target-ratio 0.8"
```

### 步骤 8：写入 context.yaml 并生成报告

```yaml
flagos_perf:
  initial_path: "/flagos-workspace/results/flagos_initial.json"
  optimized_path: "/flagos-workspace/results/flagos_optimized.json"  # 如有优化
```

---

## Scenario B 专用步骤

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

### 升级前后对比

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-before results/flagos_before_upgrade.json \
  --flagos-after results/flagos_after_upgrade.json \
  --output results/performance_compare.csv"
```

---

## benchmark_runner.py 参数说明

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件路径 |
| `--test-case` | 运行指定测试用例 |
| `--dry-run` | 仅打印命令不执行 |
| `--concurrency-search` | **自动搜索最优并发级别，吞吐增长 < 3% 时早停** |
| `--output-name` | 指定输出文件名（不含扩展名） |
| `--output-dir` | 指定输出目录（默认 /flagos-workspace/results/） |
| `--mode` | 测试模式标记（native/flagos_initial/flagos_optimized） |

## performance_compare.py 参数说明

| 参数 | 说明 |
|------|------|
| `--native` | 原生性能结果 JSON 路径（必填） |
| `--flagos-initial` | FlagOS 初始性能结果 |
| `--flagos-optimized` | FlagOS 优化后性能结果 |
| `--flagos-before` | FlagOS 升级前性能结果（Scenario B） |
| `--flagos-after` | FlagOS 升级后性能结果（Scenario B） |
| `--output` | CSV 输出路径 |
| `--target-ratio` | 性能目标比率（默认 0.8） |

---

## 配置说明

`config/perf_config.yaml` 与旧版完全兼容，包含完整配置。

---

## 输出指标

- Request throughput (req/s)
- Output token throughput (tok/s) — **主要对比指标**
- Total Token throughput (tok/s)
- TTFT: Mean/Median/P99 (ms)
- TPOT: Mean/Median/P99 (ms)
- ITL: Mean/Median/P99 (ms)

---

## 失败恢复

1. **Benchmark 失败**：保存日志 → 自动重试 1 次 → 仍失败跳过当前 case
2. **服务在测试中挂掉**：检测错误 → 重启服务 → 从失败的 case 继续

---

## 完成条件

- 测试脚本和配置已复制到容器
- Native 性能基线已测试（如 Scenario A）
- FlagOS 性能已测试
- 对比结果 `performance_compare.csv` 已生成
- 性能比率已判断（≥ 80% 或已触发优化）
- context.yaml 已更新 `native_perf` 和 `flagos_perf`
