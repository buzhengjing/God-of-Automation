---
name: flagos-eval-comprehensive
description: 基于 EvalScope 的全类型模型正确性评测，支持 LLM/VL/Omni/Robotics/ImageGen 五大类模型自动化评测，新增 quick 模式（迁移流程用）
version: 2.0.0
triggers:
  - 精度评测
  - quick 评测
  - 本地评测
  - 综合评测
  - 全面评测
  - comprehensive eval
  - evalscope
  - AIME
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

## 支持的模型类型与 Benchmark

| 模型类型 | Benchmark 数量 | 核心 Benchmark |
|---------|--------------|---------------|
| **LLM** | 11 | MMLU, AIME24, AIME25, GPQA-Diamond, MUSR, LiveBench, MATH-500, MMLU-Pro, TheoremQA, GSM8K, CEVAL |
| **VL** | 11 | MMMU, CMMMU, MMMU-Pro, Blink, OCRBench, MathVision, CII-Bench, MM-Vet v2, MathVista, Video-MME |
| **Omni** | 14+ | LLM 基准 + VL 基准组合（inherit 自动合并） |
| **Robotics** | 12 | SAT, All-Angles, Where2Place, Blink_ev, RoboSpatial, EgoPlan2, ERQA, CV-Bench, EmbSpatial, VSI-Bench, EmbodiedVerse, MAPE |
| **ImageGen** | 1 | 定性评估辅助 |

---

## Quick 模式（迁移流程用）

迁移流程步骤⑤⑧使用本 Skill 进行精度评测，支持 quick 和全量两种模式。

| 模式 | 命令参数 | 运行的 Benchmark | 用途 |
|------|---------|-----------------|------|
| **Quick** | `--quick` | 仅 `quick: true` 的 benchmark（当前为 AIME25） | 迁移筛查阶段，并发校验 + 快速验证精度 |
| **全量** | 无额外参数 | 该模型类型的全部必测 + 可选 benchmark | 正式评测阶段 |

**Quick 模式与全量模式的区别仅在于数据集选择不同，其他逻辑（配置、执行、报告）完全一致。**

**Quick 模式并发校验**：EvalScope 以 `eval_batch_size`（默认 64）并发发送请求后，自动扫描每条 prediction 结果进行校验：
- **空返回检测**：model_output 为空、无 choices、content 为空白
- **Thinking 模式检测**：thinking 模型的输出必须包含 reasoning 块（`<think>` 标签）
- **上下文溢出检测**：stop_reason=length 或错误信息含 context length 关键词
- 校验失败时，eval_report.json 中对应 benchmark 的 `status` 标记为 `"F"`，`rawDetails.validation` 包含详细问题列表

Quick 模式运行命令：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python eval_orchestrator.py --config config.yaml --quick"
```

Quick 模式 + Preflight：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python eval_orchestrator.py --config config.yaml --quick --preflight"
```

**迁移流程中的精度评测规则**：
- 步骤⑤（Native 精度）：询问用户是否执行，quick 模式下可跳过
- 步骤⑧（FlagGems 精度）：**必须执行，不可跳过**（即使 quick 模式也必须执行，因为开启 FlagGems 后必须验证算子兼容性和精度）

**扩展 Quick benchmark**：在 `benchmark_registry.yaml` 中为需要的 benchmark 添加 `quick: true` 字段即可，编排器会自动识别。

---

## 强制执行流程（按步骤顺序，不可跳步）

**执行评测前必须确认以下前置条件均已满足**：
- 容器已创建且运行中（`flagos-container-preparation` 已完成）
- 模型服务已启动并通过健康检查（`flagos-service-startup` 已完成）
- API 地址可达（`curl <api_base>/v1/models` 返回正常）

### 步骤 1：复制评测工具到容器

将本 Skill 的 `tools/` 目录完整复制到容器工作目录：

```bash
CONTAINER=<container_name>
docker cp skills/flagos-eval-comprehensive/tools/. $CONTAINER:/flagos-workspace/eval/
```

**验证**：确认关键文件已到位：
```bash
docker exec $CONTAINER ls /flagos-workspace/eval/eval_orchestrator.py
```

### 步骤 2：安装评测依赖

```bash
docker exec $CONTAINER bash -c "pip install evalscope pandas pyarrow pyyaml requests"
```

按需安装可选依赖：
- VLMEvalKit 后端：`pip install evalscope[vlmeval]`
- Robotics 自研评测：确认 `datasets/` 下对应数据集已就位

### 步骤 3：配置 config.yaml

编辑 `/flagos-workspace/eval/config.yaml`，**必须逐项检查**：

| 字段 | 要求 | 说明 |
|------|------|------|
| `model.name` | **必填** | 必须与 `/v1/models` 返回的 model id 完全一致 |
| `model.type` | **必填** | `LLM` / `VL` / `Omni` / `Robotics` / `ImageGen` |
| `model.api_base` | **必填** | OpenAI 兼容 API 地址，如 `http://localhost:9010/v1` |
| `model.api_key` | 可选 | 默认 `EMPTY` |
| `generation_config.max_tokens` | 重要 | 不得超过 `模型max_model_len - 8192`，脚本会自动查询并调整 |
| `generation_config.temperature` | 重要 | 标准评测用 `0.0`；thinking 模型用 `0.6` |
| `evalscope.dataset_dir` | 推荐 | 预下载缓存路径，避免运行时在线下载 |

**thinking 模型特殊配置**：
```yaml
generation_config:
  max_tokens: 30000
  temperature: 0.6
  top_p: 0.95
  top_k: 20

dataset_filters:
  remove_until: "</think>"
```

### 步骤 4：Benchmark 选择与数据集预下载

**推荐方式 — 一站式选择器**（交互选择 + 自动下载 + 启动评测）：

```bash
# 交互式
docker exec -it $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml"

# 非交互：仅必测项
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml --auto"

# 非交互：全选
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml --select all"

# 仅下载不评测
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python benchmark_selector.py --config config.yaml --auto --no-eval"
```

**手动预下载**：
```bash
# 按模型类型
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache"

# 指定 benchmark
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python dataset_prefetch.py --model-type LLM --benchmarks mmlu,aime24 --cache-dir datasets/evalscope_cache"

# 检查缓存状态
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache --status"
```

> 使用 HuggingFace 镜像源：`--source huggingface --hf-mirror https://hf-mirror.com`

### 步骤 5：Preflight 预检（推荐）

**正式评测前必须执行 preflight 预检**，用极小样本（limit=2）快速验证所有 benchmark 的可运行性：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python eval_orchestrator.py --config config.yaml --preflight"
```

Preflight 验证内容：
- API 连通性（模型服务是否响应）
- 参数合法性（max_tokens 是否超限、API 格式是否正确）
- 数据集可用性（本地缓存或在线下载是否正常）
- 执行器依赖（evalscope / vlmeval / custom 脚本是否可加载）

Preflight 行为：
- 每个 benchmark 使用 `limit=2` 运行，输出到 `outputs/preflight/` 子目录
- **任一 benchmark 失败即中止**，打印 `[ABORT]` 和失败详情
- 全部通过后打印 `[PASS]`，自动进入全量评测
- 不污染正式评测结果目录

**预检失败时**：根据 `[FAIL]` 输出定位问题：
| 常见失败原因 | 排查方法 |
|-------------|---------|
| API 连接超时 | 检查 `model.api_base`，确认服务已启动 |
| max_tokens 超限 | 降低 `generation_config.max_tokens` |
| 数据集下载失败 | 先运行 `dataset_prefetch.py` 预下载 |
| evalscope 未安装 | `pip install evalscope` |
| 自研脚本找不到 | 确认 `custom_eval/` 目录已完整复制 |

### 步骤 6：运行正式评测

**全量评测（带 preflight）**：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    nohup python eval_orchestrator.py --config config.yaml --preflight > /dev/null 2>&1 &"
```

**全量评测（跳过 preflight，仅当已确认环境无误时）**：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    nohup python eval_orchestrator.py --config config.yaml > /dev/null 2>&1 &"
```

**其他运行方式**：

```bash
# 仅 EvalScope 原生 benchmark（跳过自研脚本）
python eval_orchestrator.py --config config.yaml --skip-custom

# 仅必测项
python eval_orchestrator.py --config config.yaml --skip-optional

# 指定 benchmark
python eval_orchestrator.py --config config.yaml --benchmarks mmlu,aime24,gpqa_diamond

# 从选择配置文件运行
python eval_orchestrator.py --config config.yaml --selection benchmark_selection.json

# 并行执行（谨慎使用，需确认 GPU 显存充足）
python eval_orchestrator.py --config config.yaml --parallel 3

# 小样本调试
python eval_orchestrator.py --config config.yaml --limit 5

# Dry-run（仅查看执行计划，不实际运行）
python eval_orchestrator.py --config config.yaml --dry-run
```

### 步骤 7：监控评测进度

```bash
# 全局进度（实时）
tail -f /data/flagos-workspace/<model_name>/eval/eval_progress.log

# 检查进程
docker exec $CONTAINER ps aux | grep "eval_\|evalscope"
```

### 步骤 8：获取与验证结果

```bash
# JSON 汇总报告
cat /data/flagos-workspace/<model_name>/eval/eval_report.json

# Markdown 可读报告
cat /data/flagos-workspace/<model_name>/eval/eval_report.md
```

**结果验证检查清单**：
- [ ] `eval_report.json` 存在且 `err_code == 0`
- [ ] 所有必测 benchmark 的 `status` 均为 `"S"`
- [ ] 失败的 benchmark 已记录原因（`rawDetails.error`）
- [ ] `eval_report.md` 可读报告已生成

---

## 统一工作目录

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
             │   ├── preflight/           ← Preflight 预检输出（独立隔离）
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

## 工具说明

### tools/eval_orchestrator.py — 主编排器（核心入口）

读取配置和注册表，按模型类型筛选 benchmark，调度三种执行器（evalscope / vlmeval / custom），收集结果并生成报告。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--registry` | benchmark_registry.yaml | Benchmark 注册表 |
| `--benchmarks` | 无（全部） | 指定运行的 benchmark，逗号分隔 |
| `--selection` | 无 | 从 benchmark_selector 生成的选择配置文件读取 |
| `--skip-custom` | false | 跳过自研 benchmark，仅运行 EvalScope 原生 |
| `--skip-optional` | false | 跳过可选 benchmark，仅运行必测 |
| `--parallel` | 1 | 并行执行的 benchmark 数量 |
| `--limit` | 无 | 限制每个 benchmark 的样本数（调试用） |
| `--preflight` | false | 正式评测前用 limit=2 快速验证所有 benchmark |
| `--dry-run` | false | 仅打印执行计划，不实际运行 |
| `--quick` | false | Quick 模式：只跑 registry 中 quick=true 的 benchmark |
| `--log` | eval_progress.log | 进度日志 |

**参数优先级**：`--dry-run` > `--preflight` > `--quick` > 正式执行。

**config.yaml 关键字段**：
```yaml
model:
  name: <模型名称>           # 必填
  type: <模型类型>           # LLM / VL / Omni / Robotics / ImageGen
  api_base: <API地址>        # OpenAI 兼容 API
  api_key: <API密钥>         # 可选，默认 EMPTY
  thinking: false            # 是否为 thinking model（true/false/不设置=自动检测）
```

**内部执行流程**：
1. 加载 config.yaml 和 benchmark_registry.yaml
2. 根据 `model.type` 解析 benchmark 列表（处理 inherit、去重）
3. 应用过滤（`--benchmarks` / `--selection` / `--skip-custom` / `--skip-optional`）
4. 若 `--dry-run`：打印计划并退出
5. 若 `--preflight`：逐个 benchmark 用 limit=2 运行，任一失败即中止
6. 正式执行：逐个（或并行）运行 benchmark，调度对应 runner
7. 汇总结果，调用 report_generator 生成 JSON + Markdown 报告

### tools/evalscope_runner.py — EvalScope 执行器

封装 EvalScope `TaskConfig` + `run_task` 调用。

关键行为：
- 自动查询 `/v1/models` 获取 `max_model_len`，动态调整 `max_tokens`（预留 8K 给 prompt）
- 支持 `dataset_dir` 本地缓存（离线评测）
- 支持 `dataset_filters`（thinking 模型过滤 `</think>` 前内容）
- 结果解析：将 EvalScope Report 对象转为 dict，递归提取 score

**关键字段**（benchmark_registry.yaml）：
- `thinking: true/false` — 控制 thinking model 在该 benchmark 上是否启用 thinking 模式
- `reference_scores` — 官方参考分数（用于报告中自动对比）

### tools/vlmeval_runner.py — VLMEvalKit 执行器

VL benchmark 执行器。当模型通过 API 部署时，自动 fallback 到 evalscope 原生后端。

### tools/benchmark_selector.py — 一站式选择器

交互式 Benchmark 选择 → 自动下载数据集 → 启动评测的完整流水线。

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

### tools/dataset_prefetch.py — 数据集预下载

从 benchmark_registry.yaml 解析所有 evalscope runner 的 benchmark，预下载数据集到本地缓存。

关键特性：
- 自动检测 EvalScope adapter 加载模式（reformat_subset / split_as_subset / normal）
- 精确计算缓存路径，与 EvalScope 运行时一致
- 支持 `--status` 检查缓存完整性
- 支持 ModelScope 和 HuggingFace 双数据源

### tools/report_generator.py — 报告生成器

汇总所有 benchmark 结果，生成：
- `eval_report.json`：标准化 JSON 报告（`err_code` / `eval_results` / `details`）
- `eval_report.md`：可读 Markdown 报告（总览表格 + 详细结果 + 失败信息）
- 支持多报告合并（`merge_reports`）

### tools/utils.py — 共享工具库

提供：配置加载、ProgressLogger 日志器、OpenAI 兼容 API 调用（文本 + 多模态）、答案提取（数值 / 选择题）、结果格式构建、Prompt 模板。

### tools/config.yaml — 主配置文件

定义模型信息、EvalScope 框架参数、生成配置、自研评测配置、Robotics 数据集路径、输出路径。

### tools/benchmark_registry.yaml — Benchmark 注册表

定义每种模型类型的必测/可选 benchmark 列表。每个 benchmark 指定：
- `name`：EvalScope / VLMEvalKit 中的标识名
- `runner`：执行器类型（evalscope / vlmeval / custom）
- `display_name`：报告中显示的名称
- `args`：benchmark 特定参数（如 `few_shot_num`）
- `script`：自研脚本路径（custom runner 使用）

---

## 三种执行器调度规则

| runner 类型 | 调度到 | 适用场景 |
|------------|--------|---------|
| `evalscope` | `evalscope_runner.py` → EvalScope TaskConfig | 原生支持的 benchmark（MMLU、AIME 等） |
| `vlmeval` | `vlmeval_runner.py` → VLMEvalKit 或 fallback | VL benchmark（API 部署时 fallback 到 evalscope） |
| `custom` | 动态加载 `custom_eval/eval_*.py` | 自研评测脚本（LiveBench、TheoremQA、Robotics 等） |

自研脚本约定：
- 导出 `evaluate_*()` 函数
- 签名：`(config, logger=..., limit=..., [benchmark=..., dataset_path=...]) -> detail dict`
- 返回标准 detail dict（`status` / `dataset` / `accuracy` / `rawDetails`）

---

## 输出格式

### eval_report.json

```json
{
  "err_code": 0,
  "err_msg": "Get Evaluations Details Success!",
  "eval_results": {
    "<MODEL_NAME>": {
      "status": "S",
      "details": [
        {"status": "S", "dataset": "MMLU_5shot", "accuracy": 83.5, "rawDetails": {}, "duration_seconds": 120.5},
        {"status": "S", "dataset": "AIME24_0shot", "accuracy": 70.0, "rawDetails": {}, "duration_seconds": 45.3},
        {"status": "F", "dataset": "LiveBench", "accuracy": 0.0, "rawDetails": {"error": "..."}, "duration_seconds": 5.1}
      ]
    }
  },
  "total_duration_seconds": 3600.0
}
```

**err_code 含义**：
| 值 | 含义 |
|----|------|
| 0 | 全部成功 |
| 1 | 全部失败 |
| 2 | 部分成功（`Partial: X ok, Y failed`） |

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
| `API_ERROR` / 连接超时 | API 不可达或超时 | 检查 `model.api_base`，确认服务已启动，增大 `timeout` |
| `max_tokens exceeds model context` | max_tokens 超过模型上下文长度 | 脚本会自动调整；也可手动降低 `generation_config.max_tokens` |
| `Dataset download failed` | 网络或 ModelScope 认证 | 先运行 `dataset_prefetch.py` 预下载，或检查网络/`modelscope login` |
| benchmark 结果为空 | 模型类型配置错误 | 检查 `model.type` 字段与实际模型匹配 |
| VLMEvalKit 报错 | 未安装 vlmeval 扩展 | `pip install evalscope[vlmeval]` |
| Preflight 某项失败 | 配置/环境/数据集问题 | 根据 `[FAIL]` 输出定位具体 benchmark 的错误信息 |
| 自研脚本 `No evaluate_* function` | 脚本缺少约定函数 | 确认脚本导出 `evaluate_*()` 函数 |
| `--selection` 和 `--benchmarks` 冲突 | 两个参数互斥 | 只使用其中一个 |

---

## 完成标准

- [ ] 步骤 1-3 配置完成，`config.yaml` 各必填字段已正确设置
- [ ] 步骤 4 数据集已预下载（`dataset_prefetch.py --status` 全部 cached）
- [ ] 步骤 5 Preflight 预检通过（`[PASS] All benchmarks passed preflight`）
- [ ] 步骤 6 eval_orchestrator.py 执行完毕
- [ ] 步骤 8 eval_report.json 已生成且 `err_code == 0`
- [ ] 所有必测 benchmark 的 `status` 均为 `"S"`
- [ ] eval_report.md 可读报告已生成
- [ ] context.yaml 已更新评测结果（Skill 间共享状态）
