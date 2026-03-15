---
name: flagos-eval-comprehensive
description: 基于 EvalScope 的全类型模型正确性评测，支持 LLM/VL/Omni/Robotics/ImageGen 五大类模型自动化评测
version: 1.0.0
triggers:
  - 综合评测
  - 全面评测
  - comprehensive eval
  - evalscope
  - benchmark
  - 精度评测
depends_on:
  - flagos-service-startup
next_skill: flagos-performance-testing
provides:
  - eval_results
  - eval_report
---

# FlagOS 综合评测 Skill

基于 EvalScope 框架，自动化评测大模型在各类 benchmark 上的正确性。根据模型类型自动选择对应的评测基准集，支持 5 大类模型共 30+ 个 benchmark。

---

# 支持的模型类型与 Benchmark

| 模型类型 | Benchmark 数量 | 核心 Benchmark |
|---------|--------------|---------------|
| **LLM** | 10 | MMLU, AIME, GPQA-Diamond, LiveBench, MUSR, MATH-500, MMLU-Pro, TheoremQA, GSM8K, CEVAL |
| **VL** | 11 | MMMU, CMMMU, MMMU-Pro(std+vis), MM-Vet v2, OCRBench, MathVision, CII-Bench, Blink, MathVista, Video-MME |
| **Omni** | 14+ | LLM 基准 + VL 基准组合 |
| **Robotics** | 11 | SAT, All-Angles, Where2Place, Blink_ev, RoboSpatial, EgoPlan2, ERQA, CV-Bench, EmbSpatial, VSI-Bench, EmbodiedVerse |
| **ImageGen** | 1 | 定性评估辅助 |

---

# 统一工作目录

```
容器内: /flagos-workspace/eval/
             ├── config.yaml              ← 评测配置
             ├── benchmark_registry.yaml  ← Benchmark 注册表
             ├── benchmark_selector.py    ← 交互式选择+下载+评测
             ├── benchmark_selection.json ← 选择配置（自动生成）
             ├── dataset_prefetch.py      ← 数据集预下载脚本
             ├── eval_orchestrator.py     ← 主编排器
             ├── evalscope_runner.py      ← EvalScope 执行器
             ├── vlmeval_runner.py        ← VLMEvalKit 执行器
             ├── custom_eval/             ← 自研评测脚本
             ├── utils.py                 ← 共享工具
             ├── report_generator.py      ← 报告生成
             ├── datasets/                ← 数据集缓存
             │   └── evalscope_cache/     ← 预下载的 EvalScope 数据集
             ├── outputs/                 ← 评测输出目录
             │   ├── evalscope/           ← EvalScope 原生输出
             │   └── custom/              ← 自研脚本输出
             ├── eval_report.json         ← 最终汇总报告
             ├── eval_report.md           ← 可读 Markdown 报告
             └── eval_progress.log        ← 全局进度日志

宿主机: /data/flagos-workspace/<model_name>/eval/  ← 实时同步
```

**宿主机监控**：
```bash
tail -f /data/flagos-workspace/<model_name>/eval/eval_progress.log
cat /data/flagos-workspace/<model_name>/eval/eval_report.json
```

---

## 目录结构

```
flagos-eval-comprehensive/
├── SKILL.md
└── tools/
    ├── config.yaml                # 主配置文件
    ├── benchmark_registry.yaml    # Benchmark 注册表
    ├── benchmark_selector.py      # 交互式选择 + 自动下载 + 评测启动
    ├── dataset_prefetch.py        # 数据集预下载脚本（离线支持）
    ├── eval_orchestrator.py       # 主编排器
    ├── evalscope_runner.py        # EvalScope 原生执行器
    ├── vlmeval_runner.py          # VLMEvalKit 后端执行器
    ├── report_generator.py        # 报告生成器
    ├── utils.py                   # 共享工具库
    └── custom_eval/               # 自研评测脚本
        ├── eval_livebench.py
        ├── eval_theoremqa.py
        ├── eval_cii_bench.py
        ├── eval_mm_vet.py
        ├── eval_video_mme.py
        ├── eval_robotics.py
        ├── eval_mape.py
        └── eval_image_gen.py
```

---

## 工具说明

### tools/config.yaml

主配置文件，定义模型信息和评测参数。

**关键字段**：

```yaml
model:
  name: <模型名称>           # 必填
  type: <模型类型>           # LLM / VL / Omni / Robotics / ImageGen
  api_base: <API地址>        # OpenAI 兼容 API
  api_key: <API密钥>         # 可选，默认 EMPTY
  thinking: false            # 是否为 thinking model（true/false/不设置=自动检测）

evalscope:
  dataset_dir: <缓存路径>     # 预下载缓存目录（离线评测用）
  eval_batch_size: 64        # 并行评测 batch 大小
  stream: true               # 流式输出
  timeout: 60000             # 超时（毫秒）

# 标准模式生成配置（non-thinking benchmarks 使用）
generation_config:
  max_tokens: 8192
  temperature: 0.0

# Thinking 模式生成配置（model.thinking=true 且 benchmark.thinking=true 时使用）
thinking_generation_config:
  max_tokens: 30000
  temperature: 0.6
  top_p: 0.95
  top_k: 20
```

### tools/benchmark_registry.yaml

定义每种模型类型对应的必测和可选 benchmark 列表，以及每个 benchmark 的执行器类型（evalscope / vlmeval / custom）、参数和 thinking 配置。

**关键字段**：
- `thinking: true/false` — 控制 thinking model 在该 benchmark 上是否启用 thinking 模式
- `reference_scores` — 官方参考分数（用于报告中自动对比）

### tools/benchmark_selector.py

一站式 Benchmark 选择器：推荐展示 → 交互选择 → 自动下载数据集 → 启动评测。

**功能**：
- 根据模型类型展示推荐的 benchmark 列表（分必测/可选）
- 终端交互式选择（输入序号切换勾选状态）
- 确认后自动调用 `dataset_prefetch.py` 下载所选数据集
- 保存选择配置到 `benchmark_selection.json`
- 自动启动 `eval_orchestrator.py --selection benchmark_selection.json`

**参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--registry` | 同目录 benchmark_registry.yaml | Benchmark 注册表 |
| `--auto` | false | 非交互：自动选择必测项，直接下载+评测 |
| `--select` | 无 | 非交互：`all` 全选，`required` 仅必测 |
| `--no-eval` | false | 下载数据集后不启动评测 |
| `--save-only` | false | 仅保存选择配置，不下载不评测 |
| `--output` | benchmark_selection.json | 选择配置输出路径 |
| `--limit` | 无 | 传递给 eval_orchestrator 的样本数限制 |
| `--parallel` | 1 | 传递给 eval_orchestrator 的并行度 |

### tools/eval_orchestrator.py

主编排器，核心入口。

**功能**：
- 读取模型配置和 benchmark 注册表
- 根据模型类型筛选 benchmark 列表
- 调度 evalscope / vlmeval / custom 执行器
- 支持并行执行
- 收集结果并调用报告生成器

**参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--benchmarks` | 无（全部） | 指定运行的 benchmark，逗号分隔 |
| `--selection` | 无 | 从 benchmark_selector 生成的选择配置文件读取 |
| `--skip-custom` | false | 跳过自研 benchmark，仅运行 EvalScope 原生 |
| `--skip-optional` | false | 跳过可选 benchmark，仅运行必测 |
| `--parallel` | 1 | 并行执行的 benchmark 数量 |
| `--limit` | 无 | 限制每个 benchmark 的样本数（调试用） |
| `--dry-run` | false | 仅打印执行计划，不实际运行 |
| `--log` | eval_progress.log | 进度日志 |

---

## 评测流程

### 步骤 1：复制评测工具到容器工作目录

```bash
CONTAINER=<container_name>
docker cp skills/flagos-eval-comprehensive/tools/. $CONTAINER:/flagos-workspace/eval/
```

### 步骤 2：安装依赖

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    pip install evalscope pandas pyarrow pyyaml requests"
```

> 如需 VLMEvalKit 后端：`pip install evalscope[vlmeval]`

### 步骤 2.5：一站式 Benchmark 选择 + 数据集下载（推荐）

使用 `benchmark_selector.py` 交互式选择 benchmark，自动下载数据集并启动评测：

```bash
# 推荐方式：交互式选择 + 自动下载 + 评测
docker exec -it $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml"

# 非交互：仅必测项，自动下载+评测
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml --auto"

# 非交互：全选
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml --select all"

# 仅下载数据集，不启动评测
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml --auto --no-eval"
```

也可以手动预下载数据集：

```bash
# 预下载指定 benchmark 数据集
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python dataset_prefetch.py --model-type LLM --benchmarks mmlu,aime24 --cache-dir datasets/evalscope_cache"

# 预下载某类型全部数据集
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache"

# 检查缓存状态
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache --status"
```

> 使用 HuggingFace 镜像源：`--source huggingface --hf-mirror https://hf-mirror.com`

### 步骤 3：配置模型

编辑 `/flagos-workspace/eval/config.yaml`：

```bash
cat /data/flagos-workspace/<model_name>/eval/config.yaml
```

**配置检查清单**：
- [ ] `model.name` 正确
- [ ] `model.type` 与模型类型匹配（LLM/VL/Omni/Robotics/ImageGen）
- [ ] `model.api_base` 可达
- [ ] thinking 模型配置（见下方 Thinking Model 决策指南）

### 步骤 4：运行评测

**全量评测**：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    nohup python eval_orchestrator.py --config config.yaml > /dev/null 2>&1 &"
```

**仅 EvalScope 原生 benchmark**：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    nohup python eval_orchestrator.py --config config.yaml --skip-custom > /dev/null 2>&1 &"
```

**指定 benchmark**：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python eval_orchestrator.py --config config.yaml --benchmarks mmlu,aime24,gpqa_diamond"
```

**Dry-run（查看执行计划）**：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python eval_orchestrator.py --config config.yaml --dry-run"
```

### 步骤 5：监控进度

```bash
# 全局进度
tail -f /data/flagos-workspace/<model_name>/eval/eval_progress.log

# 检查进程
docker exec $CONTAINER ps aux | grep "eval_\|evalscope"
```

### 步骤 6：获取结果

```bash
# JSON 汇总报告
cat /data/flagos-workspace/<model_name>/eval/eval_report.json

# Markdown 可读报告
cat /data/flagos-workspace/<model_name>/eval/eval_report.md
```

---

## 输出格式

### eval_report.json

```json
{
  "err_code": 0,
  "err_msg": "Get Evaluations Details Sucess!",
  "eval_results": {
    "<MODEL_NAME>": {
      "status": "S",
      "details": [
        {"status": "S", "dataset": "MMLU_5shot", "accuracy": 83.5, "rawDetails": {}},
        {"status": "S", "dataset": "AIME_0fewshot_@avg1", "accuracy": 70.0, "rawDetails": {}},
        {"status": "S", "dataset": "GPQA_Diamond_0shot", "accuracy": 71.2, "rawDetails": {}},
        ...
      ]
    }
  }
}
```

---

## Thinking Model 决策指南

### 什么是 thinking model

Thinking model 是指经过训练能够在回答前进行长链推理的模型（输出中包含 `<think>...</think>` 块）。典型代表：Qwen3 系列、QwQ 系列、DeepSeek-R1/R2 系列。

这类模型在使用正确的推理参数时，能在数学、科学、多步推理等任务上显著提升表现。

### 自动检测机制

编排器 `eval_orchestrator.py` 会自动处理 thinking model：

1. **模型层面检测**：根据 `model.thinking` 字段或模型名自动识别
   - 显式设置 `model.thinking: true` → 强制启用
   - 显式设置 `model.thinking: false` → 强制关闭
   - 未设置 → 自动检测模型名（匹配 `qwen3`, `qwq`, `deepseek-r1` 等）

2. **Benchmark 层面控制**：每个 benchmark 在 `benchmark_registry.yaml` 中有 `thinking` 字段
   - `thinking: true` — 当模型支持 thinking 时，该 benchmark 使用 thinking 配置
   - `thinking: false` — 该 benchmark 始终使用标准配置

3. **两者结合**：只有**模型是 thinking model** 且 **benchmark.thinking=true** 时，才使用 thinking 配置

### Per-Benchmark 配置差异

| 配置项 | 标准模式 | Thinking 模式 | 说明 |
|--------|---------|--------------|------|
| `temperature` | 0.0 | 0.6 | thinking 需要采样多样性启动思考链 |
| `max_tokens` | 8192 | 30000 | thinking chain 需要大量 token 空间 |
| `top_p` | 1.0 | 0.95 | 配合 temperature 使用 |
| `dataset_filters` | 无 | `remove_until: "</think>"` | 答案提取前过滤思考内容 |

### 哪些 Benchmark 使用 thinking

| Benchmark | thinking | 原因 |
|-----------|----------|------|
| MMLU | false | 多选题，不需要长推理链，thinking 会大幅增加 token 消耗但收益有限 |
| AIME24/25 | **true** | 竞赛数学，必须充分推理 |
| GPQA Diamond | **true** | 研究生级别科学推理 |
| MUSR | **true** | 多步推理 |
| MATH-500 | **true** | 数学推理 |
| GSM8K | false | 小学数学，标准模式即可 |
| MMLU-Pro | false | 多选题 |
| CEVAL | false | 多选题 |

### 智能体决策指导

**配置 `config.yaml` 时的决策规则**：

1. **判断模型是否为 thinking model**：
   - 查看模型名或官方文档，确认模型是否具备 thinking 能力
   - 如果确定是 → 设置 `model.thinking: true`
   - 如果确定不是 → 设置 `model.thinking: false`（或不设置，自动检测会处理）
   - 如果不确定 → 不设置，依赖自动检测

2. **不需要手动修改 `generation_config`**：
   - 编排器会根据 benchmark 的 `thinking` 字段自动切换配置
   - `config.yaml` 中的 `generation_config` 作为标准模式基线
   - `thinking_generation_config` 作为 thinking 模式参数

3. **可以覆盖 benchmark 的 thinking 设置**：
   - 如果认为某个 benchmark 的 `thinking` 字段不合适，直接修改 `benchmark_registry.yaml`
   - 例如：如果发现 MMLU 在 thinking 模式下效果更好，可以改为 `thinking: true`

4. **新增 benchmark 时**：
   - 需要深度推理的（数学、科学、多步逻辑）→ `thinking: true`
   - 多选/知识记忆为主的 → `thinking: false`

---

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `evalscope not found` | 未安装 evalscope | `pip install evalscope` |
| `API_ERROR` | API 超时或连接失败 | 检查 api_base，已内置重试 |
| `Dataset download failed` | 网络或 ModelScope 认证 | 先运行 `dataset_prefetch.py` 预下载，或检查网络/`modelscope login` |
| benchmark 结果为空 | 模型类型配置错误 | 检查 `model.type` 字段 |
| VLMEvalKit 报错 | 未安装 vlmeval 扩展 | `pip install evalscope[vlmeval]` |

---

## 完成标准

- eval_orchestrator.py 执行完毕
- eval_report.json 已生成且 err_code == 0
- 所有必测 benchmark 的 status 均为 "S"
- eval_report.md 可读报告已生成
