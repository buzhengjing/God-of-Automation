# 性能测试 Skill

vLLM 模型性能基准测试工具，支持多种输入/输出长度组合的自动化测试。

## 目录结构

```
Performance_Testing/
├── skill.md                      # Skill 定义文件（触发条件、工作流程）
├── README.md                     # 本文档
│
├── config/                       # 配置目录（Agent 可修改）
│   ├── perf_config.yaml          # 主配置文件
│   ├── schema.json               # 配置校验 JSON Schema
│   └── examples/                 # 配置示例
│       ├── metax_c500.yaml       # MetaX C500 GPU 配置示例
│       └── mthreads_s4000.yaml   # Moore Threads S4000 配置示例
│
├── src/                          # 源代码（只读）
│   ├── __init__.py
│   ├── perf.py                   # 主入口程序
│   ├── runner.py                 # Benchmark 执行器
│   ├── parser.py                 # 输出解析器
│   └── reporter.py               # 结果报告生成器
│
├── lib/                          # 工具库（只读）
│   ├── __init__.py
│   ├── config_loader.py          # 配置加载与校验
│   ├── env_detector.py           # 容器环境自动检测
│   └── validators.py             # 参数验证器
│
├── scripts/                      # 可执行脚本
│   ├── run_benchmark.sh          # 一键运行脚本
│   ├── detect_env.sh             # 环境检测脚本
│   └── generate_report.py        # Markdown 报告生成
│
├── templates/                    # 模板文件
│   ├── config_template.yaml      # 配置文件模板
│   └── report_template.md        # 报告模板
│
├── output/                       # 输出目录（自动生成）
│   └── .gitkeep
│
└── tests/                        # 单元测试
    ├── test_parser.py            # 解析器测试
    └── test_config.py            # 配置加载测试
```

## 模块说明

### 配置模块 (`config/`)

| 文件 | 说明 |
|------|------|
| `perf_config.yaml` | 测试参数配置（连接信息从 `shared/context.yaml` 读取） |
| `schema.json` | JSON Schema 定义，用于校验配置文件格式正确性 |
| `examples/*.yaml` | 不同硬件平台的配置示例 |

**配置架构说明：**

```
shared/context.yaml          ← 上游 skill 写入连接信息
    │
    ├── service.host/port    # vLLM 服务地址
    └── model.tokenizer_path # tokenizer 路径
          │
          ↓
config/perf_config.yaml      ← 本 skill 配置测试参数
    │
    ├── test_matrix          # 测试用例
    ├── concurrency          # 并发级别
    └── output               # 输出配置
```

**perf_config.yaml 结构：**

```yaml
# 注意: 连接信息从 shared/context.yaml 读取

test_matrix:      # 测试矩阵（输入/输出长度组合）
  - name: "1k_input_1k_output"
    input_len: 1024
    output_len: 1024
    enabled: true
  # ... 更多组合

concurrency:      # 并发配置
  levels: [1, 2, 4, 8, 16, 32, 64, 128, 256]
  final_num_prompts: 1000

benchmark:        # Benchmark 固定参数
  dataset_name: "random"
  endpoint: "/v1/completions"

output:           # 输出配置
  dir: "./output"
  format: "json"
```

### 源代码模块 (`src/`)

| 文件 | 职责 |
|------|------|
| `perf.py` | **主入口** - 解析命令行参数，协调各模块执行测试流程 |
| `runner.py` | **执行器** - 构建 vLLM bench 命令，执行并发测试 |
| `parser.py` | **解析器** - 从 benchmark 输出中提取关键性能指标 |
| `reporter.py` | **报告器** - 将结果保存为 JSON/CSV 格式 |

**核心流程：**

```
perf.py (入口)
    │
    ├─→ config_loader.py (加载配置)
    │
    ├─→ runner.py (执行测试)
    │       │
    │       └─→ parser.py (解析输出)
    │
    └─→ reporter.py (保存结果)
```

### 工具库模块 (`lib/`)

| 文件 | 职责 |
|------|------|
| `config_loader.py` | 加载 `shared/context.yaml` + `perf_config.yaml`，合并为完整配置 |
| `env_detector.py` | 运行时自动采集环境信息（GPU、vLLM 版本等）写入结果 metadata |
| `validators.py` | 参数校验工具（IP、端口、路径等） |

### 脚本模块 (`scripts/`)

| 脚本 | 用途 | 使用方式 |
|------|------|----------|
| `run_benchmark.sh` | 一键运行完整测试 | `bash scripts/run_benchmark.sh` |
| `generate_report.py` | 从 JSON 结果生成 Markdown 报告 | `python scripts/generate_report.py output/xxx.json` |

## 快速开始

### 1. 确认连接信息

确保 `shared/context.yaml` 已包含正确的服务连接信息（由上游 skill 写入）：

```yaml
service:
  host: "10.1.15.35"
  port: 8000

model:
  tokenizer_path: "/nfs/Qwen3-4B"
```

### 2. 修改测试参数（可选）

编辑 `config/perf_config.yaml`：

- `test_matrix`: 启用/禁用特定测试用例
- `concurrency.levels`: 自定义并发级别

### 3. 运行测试

```bash
# 方式一：使用脚本
bash scripts/run_benchmark.sh

# 方式二：直接运行
python -m src.perf --config config/perf_config.yaml

# 方式三：只运行特定测试
python -m src.perf --config config/perf_config.yaml --test-case 1k_input_1k_output

# 方式四：预览模式（不实际执行）
python -m src.perf --config config/perf_config.yaml --dry-run
```

### 4. 查看结果

```bash
# 查看输出文件
ls output/

# 生成 Markdown 报告
python scripts/generate_report.py output/benchmark_20260305_103000.json -o report.md
```

## 测试矩阵

默认配置包含以下 4 种输入/输出长度组合：

| 测试名称 | 输入长度 | 输出长度 |
|----------|----------|----------|
| 1k_input_1k_output | 1024 | 1024 |
| 4k_input_1k_output | 4096 | 1024 |
| 16k_input_1k_output | 16384 | 1024 |
| 32k_input_1k_output | 32768 | 1024 |

每个测试用例会执行以下并发级别：
- 并发 1, 2, 4, 8, 16, 32, 64, 128, 256（各运行对应数量的 prompts）
- 最终测试：1000 prompts，无并发限制

## 采集指标

| 指标类别 | 具体指标 |
|----------|----------|
| 吞吐量 | Request throughput (req/s), Output token throughput (tok/s), Total token throughput (tok/s) |
| 首 Token 延迟 (TTFT) | Mean, Median, P99 |
| Token 间延迟 (TPOT) | Mean, Median, P99 |
| Token 间隔延迟 (ITL) | Mean, Median, P99 |
| 统计信息 | Successful/Failed requests, Benchmark duration, Total tokens |

## 输出格式

### JSON 输出结构

```json
{
  "metadata": {
    "timestamp": "2026-03-05T10:30:00",
    "version": "1.0.0",
    "config": { ... }
  },
  "results": {
    "1k_input_1k_output": {
      "concurrency_1": {
        "Successful requests": 1,
        "Output token throughput (tok/s)": 456.78,
        "Mean TTFT (ms)": 125.67,
        ...
      },
      "concurrency_2": { ... },
      ...
      "max": { ... }
    },
    "4k_input_1k_output": { ... }
  }
}
```

## Agent 集成指南

### 文件权限

| 类型 | 路径 | Agent 权限 |
|------|------|------------|
| 配置文件 | `config/perf_config.yaml` | **可修改** |
| 共享上下文 | `shared/context.yaml` | 只读（由上游写入） |
| 源代码 | `src/*` | 只读 |
| 工具库 | `lib/*` | 只读 |
| 脚本 | `scripts/*` | 只读 |
| 模板 | `templates/*` | 只读 |

### Agent 工作流程

1. **确认连接**: 检查 `shared/context.yaml` 是否已包含服务连接信息
2. **配置修改**: 按需修改 `config/perf_config.yaml` 测试参数
3. **执行测试**: 运行 `python -m src.perf --config config/perf_config.yaml`
4. **结果收集**: 从 `output/` 目录读取结果文件

### 配置校验

系统会自动根据 `config/schema.json` 校验配置，确保：
- 必填字段完整
- 数据类型正确
- 数值范围合法

## 依赖项

```
pyyaml>=6.0
```

## 运行测试

```bash
# 运行解析器测试
python tests/test_parser.py

# 运行配置测试
python tests/test_config.py
```

## 常见问题

### Q: 如何只运行部分测试用例？

在 `config/perf_config.yaml` 中将不需要的测试用例设置 `enabled: false`：

```yaml
test_matrix:
  - name: "1k_input_1k_output"
    enabled: true
  - name: "32k_input_1k_output"
    enabled: false  # 禁用此测试
```

### Q: 如何修改并发级别？

修改 `config/perf_config.yaml` 中的 `concurrency.levels`：

```yaml
concurrency:
  levels: [1, 4, 16, 64, 256]  # 自定义并发级别
  final_num_prompts: 500
```

### Q: 测试超时怎么办？

单个 benchmark 命令默认超时 600 秒。如需修改，请编辑 `src/runner.py` 中的 `timeout` 参数。

## 版本历史

- **v1.0.0** - 初始版本
  - 支持 4 种输入/输出长度组合
  - 自动环境检测
  - JSON/CSV 输出格式
  - 配置 Schema 校验
