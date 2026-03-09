---
name: performance-testing
description: vLLM 模型性能基准测试工具
version: 2.0.0
triggers:
  - 性能测试
  - benchmark
  - vllm bench
  - 吞吐量测试
depends_on:
  - flagos-service-startup
---

# 性能测试 Skill

## 强制约束

1. **禁止自行编写测试代码** - 只能使用 `perf.py`
2. **只能修改配置** - 仅 `config/perf_config.yaml` 可编辑
3. **禁止创建新文件** - 不得创建任何 .py/.sh 脚本

## 文件结构

```
Performance_Testing/
├── SKILL.md              # 本文件
├── perf.py               # 测试入口（只读）
├── config/
│   └── perf_config.yaml  # 测试配置（可编辑）
└── output/               # 结果输出
```

## 使用方法

```bash
# 运行所有测试
python perf.py

# 指定配置文件
python perf.py --config config/perf_config.yaml

# 运行单个测试用例
python perf.py --test-case 1k_input_1k_output

# 仅打印命令不执行
python perf.py --dry-run
```

## 配置说明

连接信息从 `shared/context.yaml` 自动读取：
- `service.host` / `service.port`
- `model.name` / `model.tokenizer_path`

测试参数在 `config/perf_config.yaml` 配置：
- `test_matrix`: 测试用例列表
- `concurrency.levels`: 并发级别
- `output`: 输出配置

## 输出指标

- Request throughput (req/s)
- Output token throughput (tok/s)
- TTFT: Mean/Median/P99 (ms)
- TPOT: Mean/Median/P99 (ms)
- ITL: Mean/Median/P99 (ms)
