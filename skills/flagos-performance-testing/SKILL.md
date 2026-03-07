---
name: flagos-performance-testing
description: vLLM 模型性能基准测试工具，支持多种输入/输出长度组合
version: 1.0.0
triggers:
  - 性能评测
  - 性能测试
  - benchmark
  - vllm bench
  - throughput test
  - TTFT test
  - TPOT test
  - latency test
dependencies:
  - flagos-service-health-check
next_skill: flagos-image-package-upload
---

# FlagOS 性能测试 Skill

自动化 vLLM 模型性能基准测试，支持多种输入/输出长度组合。

---

## 触发条件

- 用户请求模型性能测试
- 用户提及 benchmark、吞吐量或延迟测试
- 用户需要测试不同的输入/输出长度组合

---

## Agent 工作流

### 步骤 1：配置

仅修改 `config/perf_config.yaml`，根据 `config/schema.json` 验证。

**关键配置项**：

- `server.host` / `server.port`: 服务端点
- `model.name` / `model.tokenizer_path`: 模型设置
- `test_matrix`: 启用/禁用特定测试用例

### 步骤 2：执行测试

```bash
python -m src.perf --config config/perf_config.yaml
```

或使用便捷脚本：

```bash
bash scripts/run_benchmark.sh
```

### 步骤 3：收集结果

结果自动保存到带时间戳的 `output/` 目录。

---

## 文件权限

### 可修改（Agent 可编辑）

- `config/perf_config.yaml` - 主配置文件

### 只读（Agent 不可编辑）

- `src/*` - 源代码
- `lib/*` - 库模块
- `scripts/*` - 可执行脚本
- `templates/*` - 模板文件

---

## 测试矩阵（默认）

| 测试用例 | 输入长度 | 输出长度 |
|----------|----------|----------|
| 1k_input_1k_output | 1024 | 1024 |
| 4k_input_1k_output | 4096 | 1024 |
| 16k_input_1k_output | 16384 | 1024 |
| 32k_input_1k_output | 32768 | 1024 |

---

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

---

## 关键指标

- Request throughput (req/s) - 请求吞吐量
- Output token throughput (tok/s) - 输出 token 吞吐量
- Total token throughput (tok/s) - 总 token 吞吐量
- Mean/Median/P99 TTFT (ms) - 首 token 时间
- Mean/Median/P99 TPOT (ms) - 每 token 时间
- Mean/Median/P99 ITL (ms) - token 间延迟

---

## 使用示例

1. 更新配置：
   ```bash
   # 编辑 config/perf_config.yaml 设置正确的 host/port/model
   ```

2. 运行基准测试：
   ```bash
   python -m src.perf --config config/perf_config.yaml
   ```

3. 查看结果：
   ```bash
   ls output/
   cat output/benchmark_YYYYMMDD_HHMMSS.json
   ```

---

## 完成标准

性能测试完成的条件：

- 所有测试用例执行完毕
- 结果文件已生成
- 关键指标已记录
