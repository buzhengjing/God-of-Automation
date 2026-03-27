---
name: flagos-eval-comprehensive
description: 基于 EvalScope 的模型精度评测，主模式为 GPQA Diamond 快速评测（自动适配所有模型），同时保留全量评测能力
version: 3.0.0
triggers:
  - 精度评测
  - quick 评测
  - 本地评测
  - 综合评测
  - 全面评测
  - comprehensive eval
  - evalscope
  - GPQA
  - fast gpqa
depends_on:
  - flagos-service-startup
next_skill: flagos-performance-testing
provides:
  - eval_results
  - eval_report
---

# FlagOS 精度评测 Skill

主模式：**GPQA Diamond 快速评测** — 一条命令跑完，自动适配所有模型（thinking/non-thinking），自动探测吞吐选并发，力求最佳精度和效率。

---

## 快速评测（主模式）

### 核心特性

- **自动适配所有模型**：自动检测 thinking model（Qwen3/QwQ/DeepSeek-R1/R2），设置对应的 temperature/filters
- **自动 max_tokens**：查询 `/v1/models` 获取 `max_model_len`，计算 `max_tokens = clamp(max_model_len - 8192, 4096, 32768)`，解决长输出模型（如 Qwen3-Coder-Next）精度被截断的问题
- **自动选并发**：探测阶段跑 1 题测耗时，≤5s 选 32 并发，>5s 选 16 并发
- **数据集预加载**：探测计时前先下载数据集，确保探测结果不含下载时间

### 使用方式

**步骤 1：复制工具到容器**

```bash
CONTAINER=<container_name>
docker cp skills/flagos-eval-comprehensive/tools/fast_gpqa.py $CONTAINER:/flagos-workspace/eval/fast_gpqa.py
docker cp skills/flagos-eval-comprehensive/tools/fast_gpqa_config.yaml $CONTAINER:/flagos-workspace/eval/fast_gpqa_config.yaml
```

**步骤 2：安装依赖**

```bash
docker exec $CONTAINER pip install evalscope pyyaml requests
```

如使用 ModelScope 数据源（默认）：
```bash
docker exec $CONTAINER pip install modelscope
```

**步骤 3：配置**

编辑容器内 `/flagos-workspace/eval/fast_gpqa_config.yaml`：

```yaml
model:
  name: ""                              # 必填，与 /v1/models 返回的 id 一致
  api_base: "http://localhost:8000/v1"  # 必填，OpenAI 兼容 API 地址
  api_key: "EMPTY"                      # 可选

dataset_dir: ""                         # 可选，预下载缓存目录
dataset_hub: "modelscope"               # modelscope 或 huggingface
```

仅 2 个必填字段，其余全部自动。

**步骤 4：运行评测**

```bash
# 方式一：使用配置文件
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python fast_gpqa.py --config fast_gpqa_config.yaml"

# 方式二：命令行参数（无需改配置文件）
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python fast_gpqa.py --model-name Qwen3-8B --api-base http://localhost:8000/v1"

# 命令行参数覆盖配置文件
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python fast_gpqa.py --config fast_gpqa_config.yaml --model-name Qwen3-30B-A3B"
```

### 输出

终端打印 + `gpqa_result.json`：

```
============================================================
  GPQA Diamond 快速评测结果
============================================================
  模型:     Qwen3-30B-A3B
  模式:     thinking (temperature=0.6, max_tokens=24576)
  并发:     32
  题数:     198
  得分:     61.11%
  耗时:     10m 25s
  报告:     gpqa_result.json
============================================================
```

### 自动决策逻辑

| 决策项 | 逻辑 |
|--------|------|
| max_tokens | 查询 `/v1/models` → `max_model_len - 8192`，clamp 到 [4096, 32768]，失败 fallback 16384 |
| temperature | thinking model → 0.6；standard → 0.0 |
| top_p | thinking → 0.95；standard → 1.0 |
| dataset_filters | thinking → `remove_until: </think>`；standard → 无 |
| eval_batch_size | 探测 1 题耗时 ≤5s → 32；>5s → 16；探测失败 → 16 |
| few_shot | 始终 0-shot |
| stream | 始终开启 |

### Thinking 模型检测规则

模型名（不区分大小写）包含以下关键词即判定为 thinking model：
- `qwen3`、`qwq`、`deepseek-r1`、`deepseek-r2`

---

## 迁移流程中的用法

迁移流程步骤⑤（Native 精度）和步骤⑧（FlagGems 精度）使用本 Skill。

**步骤⑤ — Native 精度**（可选，询问用户）：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python fast_gpqa.py --config fast_gpqa_config.yaml"
```

**步骤⑧ — FlagGems 精度**（强制执行，不可跳过）：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python fast_gpqa.py --config fast_gpqa_config.yaml"
```

结果文件 `gpqa_result.json` 复制到 `results/` 对应位置：
```bash
docker exec $CONTAINER cp /flagos-workspace/eval/gpqa_result.json /flagos-workspace/results/gpqa_native.json
# 或
docker exec $CONTAINER cp /flagos-workspace/eval/gpqa_result.json /flagos-workspace/results/gpqa_flagos.json
```

---

## 工具文件

```
tools/
├── fast_gpqa.py              ← 快速 GPQA Diamond 评测（主入口）
├── fast_gpqa_config.yaml     ← 快速评测配置模板
├── eval_orchestrator.py      ← 全量评测编排器（保留，按需使用）
├── evalscope_runner.py       ← EvalScope 执行器（保留）
├── config.yaml               ← 全量评测配置（保留）
├── benchmark_registry.yaml   ← Benchmark 注册表（保留）
└── datasets/evalscope_cache/ ← 数据集缓存
```

### tools/fast_gpqa.py — 快速 GPQA Diamond 评测（核心）

单文件约 470 行，包含完整的 GPQA Diamond 评测流程：

1. 加载配置 / 解析 CLI 参数
2. 验证 API 可达性
3. 查询 `/v1/models` → 自动计算 max_tokens
4. 检测 thinking model → 设置 generation_config
5. 预加载数据集 → 探测 1 题测耗时 → 选并发
6. 正式评测 198 题
7. 解析结果 → 输出 JSON 报告 + 终端打印

| CLI 参数 | 说明 |
|----------|------|
| `--config` | 配置文件路径 |
| `--model-name` | 模型名称（覆盖 config） |
| `--api-base` | API 地址（覆盖 config） |
| `--api-key` | API 密钥（覆盖 config） |
| `--dataset-dir` | 数据集缓存目录（覆盖 config） |

---

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `evalscope not found` | 未安装 | `pip install evalscope` |
| API 不可达 | 服务未启动或地址错误 | 检查 `--api-base`，确认 `curl <api_base>/models` 正常 |
| 精度异常低 | max_tokens 不够 | 脚本自动计算，检查日志中 `max_tokens` 值是否合理 |
| 探测选并发偏保守 | 首次运行含数据集下载 | 已内置预加载逻辑，第二次运行会准确 |
| model_id 含 `/` 报路径错误 | 模型名是路径格式 | 已内置 sanitize 逻辑，自动取最后一段 |
| 双时间戳目录 | EvalScope 内部追加 | 已设 `no_timestamp=True` |

---

## 完成标准

- [ ] `fast_gpqa.py` 和 `fast_gpqa_config.yaml` 已复制到容器
- [ ] evalscope 已安装
- [ ] config 中 `model.name` 和 `model.api_base` 已正确设置
- [ ] API 连通性检查通过
- [ ] 评测完成，`gpqa_result.json` 已生成
- [ ] score 字段有值（非 null）
- [ ] 结果已复制到 `results/` 目录
- [ ] context.yaml 已更新评测结果
