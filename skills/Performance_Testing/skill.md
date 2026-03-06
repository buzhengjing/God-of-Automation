---
name: performance-testing
description: vLLM 模型性能基准测试工具
version: 1.0.0
license: internal
triggers:
  - 性能测试
  - benchmark
  - vllm bench
  - 吞吐量测试
  - TTFT 测试
  - TPOT 测试
  - 延迟测试
depends_on:
  - flagos-service-startup
provides:
  - benchmark.results
  - benchmark.timestamp
---

# 性能测试 Skill

## 概述

自动化 vLLM 模型性能基准测试，支持多种输入/输出长度组合。

## 触发条件

- 用户请求模型性能测试
- 用户提及 benchmark、吞吐量或延迟测试
- 用户需要测试不同的输入/输出长度组合

## Agent 工作流程

### 步骤 1: 配置

**连接信息从 `shared/context.yaml` 读取**（由上游 skill 写入）：
- `service.host` / `service.port`: 服务地址
- `model.tokenizer_path`: Tokenizer 路径

**测试参数在 `config/perf_config.yaml` 配置**：
- `test_matrix`: 启用/禁用测试用例
- `concurrency`: 并发级别
- `output`: 输出配置

### 步骤 2: 执行测试

```bash
python -m src.perf --config config/perf_config.yaml
```

或使用便捷脚本：
```bash
bash scripts/run_benchmark.sh
```

### 步骤 3: 收集结果

结果自动保存到 `output/` 目录，带有时间戳。

## 文件权限

### 可修改（Agent 可编辑）
- `config/perf_config.yaml` - 主配置文件

### 只读（Agent 不可编辑）
- `src/*` - 源代码
- `lib/*` - 库模块
- `scripts/*` - 可执行脚本
- `templates/*` - 模板文件

## 测试矩阵（默认）

| 测试用例 | 输入长度 | 输出长度 |
|----------|----------|----------|
| 1k_input_1k_output | 1024 | 1024 |
| 4k_input_1k_output | 4096 | 1024 |
| 16k_input_1k_output | 16384 | 1024 |
| 32k_input_1k_output | 32768 | 1024 |

## 输出格式

```json
{
  "metadata": {
    "timestamp": "2026-03-05T10:30:00",
    "config_snapshot": { ... }
  },
  "results": {
    "1k_input_1k_output": {
      "concurrency_1": { ... },
      "concurrency_2": { ... },
      "max": { ... }
    }
  }
}
```

## 采集指标

- 请求吞吐量 (req/s)
- 输出 Token 吞吐量 (tok/s)
- 总 Token 吞吐量 (tok/s)
- 首 Token 延迟 TTFT: Mean/Median/P99 (ms)
- Token 间延迟 TPOT: Mean/Median/P99 (ms)
- Token 间隔延迟 ITL: Mean/Median/P99 (ms)

## 使用示例

1. 确认 `shared/context.yaml` 已包含服务连接信息

2. 按需修改 `config/perf_config.yaml` 测试参数

3. 运行基准测试：
   ```bash
   python -m src.perf --config config/perf_config.yaml
   ```

4. 查看结果：
   ```bash
   ls output/
   cat output/benchmark_YYYYMMDD_HHMMSS.json
   ```
