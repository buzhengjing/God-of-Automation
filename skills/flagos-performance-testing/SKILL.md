---
name: flagos-performance-testing
description: 性能基准测试，支持 native/flagos 对比、并发自动搜索早停、标准 markdown 输出格式
version: 4.0.0
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

支持自动化的 native vs FlagOS 性能对比，并发搜索+早停，标准 markdown 表格输出。

**工具脚本**（已由 setup_workspace.sh 部署到容器）:
- `benchmark_runner.py` — 性能测试（`--concurrency-search` 自动搜索+早停）
- `performance_compare.py` — 性能对比（`--format markdown` 标准表格输出）

---

## 强制约束

**只能通过 `benchmark_runner.py` 执行性能测试**，禁止直接运行 `vllm bench serve`。

---

# 工作流程

## 步骤 1：同步配置

从 `shared/context.yaml` 读取服务信息，写入 `/flagos-workspace/perf/config/perf_config.yaml`。

## 步骤 2：运行 Native 基线测试

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name native_performance \
  --output-dir /flagos-workspace/results/ \
  --mode native"
```

## 步骤 3：运行 FlagOS 性能测试

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_initial \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_initial"
```

## 步骤 4：性能对比（标准 markdown 格式）

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/performance_compare.py \
  --native results/native_performance.json \
  --flagos-initial results/flagos_initial.json \
  --output results/performance_compare.csv \
  --target-ratio 0.8 \
  --format markdown"
```

- 返回码 `0`：所有用例 ≥ 80%，跳到步骤 6
- 返回码 `1`：有不达标用例，触发步骤 5

## 步骤 5：[自动] 触发算子优化

调用 `flagos-operator-replacement` 贪心搜索，优化后重测：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace && python scripts/benchmark_runner.py \
  --config perf/config/perf_config.yaml \
  --concurrency-search \
  --output-name flagos_optimized \
  --output-dir /flagos-workspace/results/ \
  --mode flagos_optimized"
```

## 步骤 6：写入 context.yaml

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
| `--concurrency-search` | 自动搜索最优并发（增长<3%时早停） |
| `--output-name` | 输出文件名（不含扩展名） |
| `--output-dir` | 输出目录 |
| `--mode` | 测试模式标记 |

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
- 性能基线已测试
- 对比结果已生成
- 性能比率已判断
- context.yaml 已更新
