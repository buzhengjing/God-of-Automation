---
name: performance-testing
description: vLLM 模型性能基准测试工具
version: 2.1.0
triggers:
  - 性能测试
  - benchmark
  - vllm bench
  - 吞吐量测试
depends_on:
  - flagos-eval-correctness
next_skill: flagos-release
---

# 性能测试 Skill

---

# 统一工作目录

**重要**：所有性能测试在 `/flagos-workspace/perf` 目录下执行，结果生成到宿主机可访问的位置。

```
容器内: /flagos-workspace/perf/
             ├── perf.py
             ├── config/
             │   └── perf_config.yaml
             └── output/
                 └── benchmark_*.json  ← 测试结果

宿主机: /data/flagos-workspace/<model_name>/perf/  ← 实时同步
```

**宿主机查看结果**：
```bash
# 无需 docker exec，宿主机直接查看
ls /data/flagos-workspace/<model_name>/perf/output/
cat /data/flagos-workspace/<model_name>/perf/output/benchmark_*.json
```

---

## ⚠️ 强制约束（必须严格遵守）

**你必须且只能通过以下方式执行性能测试：**

```bash
python perf.py --config config/perf_config.yaml
```

**绝对禁止：**
- ❌ 直接运行 `vllm bench serve` 或任何其他基准测试命令
- ❌ 自行编写测试脚本或代码
- ❌ 创建任何 .py/.sh 文件
- ❌ 绕过 perf.py 执行测试

**唯一允许的操作：**
- ✅ 修改 `config/perf_config.yaml` 调整测试参数
- ✅ 运行 `python perf.py` 及其参数

**违反上述约束将导致测试结果无效。**

---

## 文件结构

```
flagos-performance-testing/
├── SKILL.md              # 本文件
├── perf.py               # 测试入口（只读）
├── config/
│   └── perf_config.yaml  # 测试配置（可编辑）
└── output/               # 结果输出
```

---

## 执行流程

### 步骤 1：复制测试工具到容器工作目录

```bash
# 在宿主机执行
CONTAINER=<container_name>

# 复制测试脚本和配置到工作目录
docker cp skills/flagos-performance-testing/perf.py $CONTAINER:/flagos-workspace/perf/
docker cp skills/flagos-performance-testing/config/. $CONTAINER:/flagos-workspace/perf/config/
```

### 步骤 2：同步配置信息

从 `shared/context.yaml` 读取以下字段，填充到 `/flagos-workspace/perf/config/perf_config.yaml`：

| context.yaml 字段 | perf_config.yaml 字段 |
|-------------------|----------------------|
| `service.host` | `server.host` |
| `service.port` | `server.port` |
| `model.name` 或 `model.container_path` | `model.name` |
| `model.tokenizer_path` 或 `model.container_path` | `model.tokenizer_path` |

**可直接在宿主机编辑配置**：

```bash
# 宿主机直接编辑（无需 docker exec）
vim /data/flagos-workspace/<model_name>/perf/config/perf_config.yaml
```

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

### 步骤 4：在容器内执行测试

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/perf && python perf.py --config config/perf_config.yaml"
```

**其他运行选项：**

```bash
# 运行单个测试用例
docker exec $CONTAINER bash -c "cd /flagos-workspace/perf && python perf.py --test-case 1k_input_1k_output"

# 仅打印命令不执行（调试用）
docker exec $CONTAINER bash -c "cd /flagos-workspace/perf && python perf.py --dry-run"
```

### 步骤 5：获取测试结果（宿主机直接访问）

```bash
# 无需 docker cp，宿主机直接查看
ls /data/flagos-workspace/<model_name>/perf/output/
cat /data/flagos-workspace/<model_name>/perf/output/benchmark_*.json
```

---

## 配置说明

`config/perf_config.yaml` 包含完整配置：

```yaml
# 服务连接（必填，从 context.yaml 同步）
server:
  host: "127.0.0.1"
  port: 8000

model:
  name: "/path/to/model"
  tokenizer_path: "/path/to/model"

# 测试矩阵
test_matrix:
  - name: "1k_input_1k_output"
    input_len: 1024
    output_len: 1024
    enabled: true

# 并发级别
concurrency:
  levels: [1, 2, 4, 8, 16, 32, 64, 128, 256]
  final_num_prompts: 1000
```

---

## 输出指标

- Request throughput (req/s)
- Output token throughput (tok/s)
- TTFT: Mean/Median/P99 (ms)
- TPOT: Mean/Median/P99 (ms)
- ITL: Mean/Median/P99 (ms)

---

## 完成条件

- 测试脚本和配置已复制到容器
- `perf.py` 执行完成
- 结果文件已生成在 `output/` 目录
- 结果已复制回宿主机
