# eval_orchestrator.py 使用手册

> 面向评测操作人员的实用手册。涵盖所有命令用法、典型场景、调试技巧和日志解读。
> 如需了解代码原理和架构设计，请阅读 `PROJECT_GUIDE.md`。

---

## 目录

- [1. 快速开始](#1-快速开始)
- [2. 命令参考](#2-命令参考)
  - [2.1 eval_orchestrator.py](#21-eval_orchestratorpy)
  - [2.2 benchmark_selector.py](#22-benchmark_selectorpy)
  - [2.3 dataset_prefetch.py](#23-dataset_prefetchpy)
  - [2.4 evalscope_runner.py](#24-evalscope_runnerpy)
  - [2.5 vlmeval_runner.py](#25-vlmeval_runnerpy)
  - [2.6 report_generator.py](#26-report_generatorpy)
- [3. 典型使用场景](#3-典型使用场景)
- [4. Preflight 预检详解](#4-preflight-预检详解)
- [5. 调试指南](#5-调试指南)
- [6. 日志解读](#6-日志解读)
- [7. config.yaml 配置速查](#7-configyaml-配置速查)
- [8. 常见报错与解决](#8-常见报错与解决)

---

## 1. 快速开始

```bash
# 假设已在容器内 /flagos-workspace/eval/ 目录下

# 第一步：确认模型服务可用
curl http://localhost:9010/v1/models

# 第二步：编辑 config.yaml（改模型名、类型、API 地址）
vi config.yaml

# 第三步：预检 + 全量评测（推荐的标准流程）
python eval_orchestrator.py --config config.yaml --preflight
```

30 秒内预检完成。如果全部 `[OK]`，自动进入全量评测。如果有 `[FAIL]`，修完再跑。

---

## 2. 命令参考

### 2.1 eval_orchestrator.py

主编排器，所有评测的入口。

```
python eval_orchestrator.py [选项]
```

#### 全部参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--config` | 文件路径 | `config.yaml` | 主配置文件 |
| `--registry` | 文件路径 | `benchmark_registry.yaml` | Benchmark 注册表 |
| `--benchmarks` | 逗号分隔 | 无（全部） | 只运行指定的 benchmark |
| `--selection` | 文件路径 | 无 | 从 `benchmark_selector` 生成的 JSON 文件读取 benchmark 列表 |
| `--skip-custom` | 开关 | false | 跳过所有自研 benchmark（仅跑 EvalScope 原生） |
| `--skip-optional` | 开关 | false | 跳过可选 benchmark（仅跑必测项） |
| `--parallel` | 整数 | 1 | 并行执行的 benchmark 数量 |
| `--limit` | 整数 | 无 | 每个 benchmark 最多跑多少条样本 |
| `--preflight` | 开关 | false | 正式评测前用 limit=2 快速验证所有 benchmark |
| `--dry-run` | 开关 | false | 只打印执行计划，不实际运行 |
| `--log` | 文件路径 | `eval_progress.log` | 进度日志路径 |

#### 参数优先级

```
--dry-run > --preflight > 正常执行
```

- `--dry-run` 和 `--preflight` 同时传：只执行 dry-run（打印计划），preflight 不执行
- `--preflight` 单独传：先 preflight，通过后自动进入全量评测
- 都不传：直接全量评测

#### 参数互斥

- `--benchmarks` 和 `--selection` 不能同时使用（报错退出）

#### 命令速查表

```bash
# ─── 查看与规划 ──────────────────────────────────────────
# 查看将要执行哪些 benchmark（不实际运行）
python eval_orchestrator.py --config config.yaml --dry-run

# 查看 LLM 必测项的执行计划
python eval_orchestrator.py --config config.yaml --skip-custom --skip-optional --dry-run

# ─── 预检 ────────────────────────────────────────────────
# 预检所有 benchmark（limit=2 快速验证，通过后自动全量评测）
python eval_orchestrator.py --config config.yaml --preflight

# 仅预检、不进入全量评测（配合 limit 使 preflight 成为"只检不测"）
# 注意：没有单独的"只预检"开关，但可以 Ctrl+C 在 [PASS] 后中断
# 或者用 --limit 2 直接跑极小样本来代替：
python eval_orchestrator.py --config config.yaml --limit 2

# ─── 全量评测 ─────────────────────────────────────────────
# 标准全量评测
python eval_orchestrator.py --config config.yaml

# 带预检的全量评测（推荐）
python eval_orchestrator.py --config config.yaml --preflight

# 后台运行（长时间评测用）
nohup python eval_orchestrator.py --config config.yaml --preflight > /dev/null 2>&1 &

# ─── 筛选 benchmark ──────────────────────────────────────
# 只跑指定的几个
python eval_orchestrator.py --config config.yaml --benchmarks mmlu,aime24,gpqa_diamond

# 只跑必测项（跳过可选）
python eval_orchestrator.py --config config.yaml --skip-optional

# 只跑 EvalScope 原生（跳过自研脚本）
python eval_orchestrator.py --config config.yaml --skip-custom

# 只跑 EvalScope 原生的必测项
python eval_orchestrator.py --config config.yaml --skip-custom --skip-optional

# 从选择配置文件运行（benchmark_selector 生成的）
python eval_orchestrator.py --config config.yaml --selection benchmark_selection.json

# ─── 调试 ─────────────────────────────────────────────────
# 小样本调试（每个 benchmark 只跑 5 条）
python eval_orchestrator.py --config config.yaml --limit 5

# 只跑一个 benchmark 的小样本
python eval_orchestrator.py --config config.yaml --benchmarks mmlu --limit 3

# 并行执行（需确认 GPU 显存和模型并发能力足够）
python eval_orchestrator.py --config config.yaml --parallel 3

# 自定义日志路径
python eval_orchestrator.py --config config.yaml --log /tmp/my_eval.log
```

---

### 2.2 benchmark_selector.py

一站式选择器：选择 benchmark → 下载数据集 → 启动评测。

```bash
# 交互式选择（终端 UI 勾选）
python benchmark_selector.py --config config.yaml

# 非交互：自动选必测项，直接下载+评测
python benchmark_selector.py --config config.yaml --auto

# 非交互：全选
python benchmark_selector.py --config config.yaml --select all

# 仅必测
python benchmark_selector.py --config config.yaml --select required

# 只下载数据集，不启动评测
python benchmark_selector.py --config config.yaml --auto --no-eval

# 只保存选择配置，不下载不评测
python benchmark_selector.py --config config.yaml --auto --save-only

# 传递参数给 eval_orchestrator
python benchmark_selector.py --config config.yaml --auto --limit 5 --parallel 2
```

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件路径 |
| `--registry` | 注册表路径 |
| `--auto` | 自动选择必测项 |
| `--select all\|required` | 非交互选择范围 |
| `--no-eval` | 下载完不评测 |
| `--save-only` | 只保存选择 JSON |
| `--output` | 选择配置输出路径（默认 `benchmark_selection.json`） |
| `--limit` | 传给 eval_orchestrator 的样本限制 |
| `--parallel` | 传给 eval_orchestrator 的并行度 |

---

### 2.3 dataset_prefetch.py

数据集预下载工具。评测前先把数据集下到本地，避免运行时在线下载。

```bash
# 查看某类型需要的数据集列表
python dataset_prefetch.py --model-type LLM --list

# 查看缓存状态（哪些已下载、哪些缺失）
python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache --status

# 下载 LLM 的全部数据集
python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache

# 只下载指定 benchmark
python dataset_prefetch.py --model-type LLM --benchmarks mmlu,aime24 --cache-dir datasets/evalscope_cache

# 下载所有模型类型
python dataset_prefetch.py --model-type All --cache-dir datasets/evalscope_cache

# 使用 HuggingFace 源 + 镜像
python dataset_prefetch.py --model-type LLM --source huggingface --hf-mirror https://hf-mirror.com

# 强制重新下载（覆盖缓存）
python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache --force
```

| 参数 | 说明 |
|------|------|
| `--model-type` | `LLM` / `VL` / `Omni` / `Robotics` / `ImageGen` / `All` |
| `--cache-dir` | 缓存目录（默认 `~/.cache/evalscope`） |
| `--registry` | 注册表路径 |
| `--source` | `modelscope`（默认）/ `huggingface` |
| `--hf-mirror` | HuggingFace 镜像地址 |
| `--benchmarks` | 只下载指定 benchmark，逗号分隔 |
| `--list` | 只列出需要下载的数据集 |
| `--status` | 检查缓存状态 |
| `--force` | 强制重新下载 |
| `--max-retries` | 下载重试次数（默认 3） |

---

### 2.4 evalscope_runner.py

EvalScope 执行器，可单独运行某个 EvalScope benchmark（调试用）。

```bash
# 单独跑一个 benchmark
python evalscope_runner.py --config config.yaml --benchmark mmlu

# 限制样本数
python evalscope_runner.py --config config.yaml --benchmark aime24 --limit 5
```

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件 |
| `--benchmark` | benchmark 名称（**必填**） |
| `--limit` | 样本数限制 |

输出：JSON 格式的 detail 结果（直接打印到 stdout）。

---

### 2.5 vlmeval_runner.py

VLMEvalKit 执行器，可单独运行 VL benchmark（调试用）。

```bash
# 单独跑 VL benchmark
python vlmeval_runner.py --config config.yaml --datasets mmmu

# 多个数据集
python vlmeval_runner.py --config config.yaml --datasets mmmu,cmmmu --limit 5
```

| 参数 | 说明 |
|------|------|
| `--config` | 配置文件 |
| `--datasets` | 数据集名称，逗号分隔（**必填**） |
| `--limit` | 样本数限制 |

> 注意：API 部署的模型会 fallback 到 evalscope 原生后端执行。

---

### 2.6 report_generator.py

报告生成器，可合并多个报告文件。

```bash
# 合并多个报告
python report_generator.py --input report1.json report2.json --output-dir ./merged

# 指定模型信息
python report_generator.py --input report1.json --model-name MyModel --model-type VL
```

| 参数 | 说明 |
|------|------|
| `--input` | 一个或多个 JSON 报告文件 |
| `--output-dir` | 输出目录 |
| `--model-name` | 模型名称 |
| `--model-type` | 模型类型 |

---

## 3. 典型使用场景

### 场景 A：首次评测一个新模型

完整的推荐流程：

```bash
# 1. 确认模型服务正常
curl http://localhost:9010/v1/models
# 应返回包含模型名称的 JSON

# 2. 编辑配置（修改 model.name、model.type、model.api_base）
vi config.yaml

# 3. 查看执行计划
python eval_orchestrator.py --config config.yaml --dry-run
# 确认 benchmark 列表是否符合预期

# 4. 预下载数据集（推荐，避免评测时等待下载）
python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache
# 确认 config.yaml 中 evalscope.dataset_dir 指向此缓存目录

# 5. 预检 + 全量评测
python eval_orchestrator.py --config config.yaml --preflight

# 6. 查看结果
cat eval_report.json | python -m json.tool
cat eval_report.md
```

### 场景 B：只需要跑几个指定的 benchmark

```bash
# 指定 benchmark 名称（name 字段，不是 display_name）
python eval_orchestrator.py --config config.yaml --benchmarks mmlu,aime24,gpqa_diamond

# 先预检再跑
python eval_orchestrator.py --config config.yaml --benchmarks mmlu,aime24 --preflight
```

### 场景 C：评测 thinking 模型（DeepSeek-R1 等）

```yaml
# config.yaml 修改为：
generation_config:
  max_tokens: 30000
  temperature: 0.6
  top_p: 0.95
  top_k: 20

dataset_filters:
  remove_until: "</think>"
```

```bash
# thinking 模型的 max_tokens 通常需要更大，脚本会自动查询模型的 max_model_len 并调整
python eval_orchestrator.py --config config.yaml --preflight
```

### 场景 D：离线环境（无外网）

```bash
# 在有网的机器上预下载
python dataset_prefetch.py --model-type LLM --cache-dir /path/to/cache

# 将缓存目录复制到离线机器
scp -r /path/to/cache user@offline:/flagos-workspace/eval/datasets/evalscope_cache

# 在离线机器上修改 config.yaml
# evalscope.dataset_dir: "datasets/evalscope_cache"

# 评测（不会尝试联网下载）
python eval_orchestrator.py --config config.yaml --preflight
```

### 场景 E：评测失败了一部分，想只重跑失败的

```bash
# 1. 查看哪些失败了
cat eval_report.json | python -c "
import json, sys
data = json.load(sys.stdin)
for model, info in data['eval_results'].items():
    for d in info['details']:
        if d['status'] == 'F':
            print(f\"  FAIL: {d['dataset']} - {d.get('rawDetails', {}).get('error', 'unknown')}\")"

# 2. 从 benchmark_registry.yaml 中找到失败项的 name（注意是 name 不是 display_name）
# 例如 display_name "MMLU_5shot" 对应 name "mmlu"

# 3. 只重跑失败的
python eval_orchestrator.py --config config.yaml --benchmarks mmlu,livebench

# 4. 合并报告
python report_generator.py --input eval_report.json eval_report_retry.json --output-dir ./merged
```

### 场景 F：在容器外（宿主机）操作

```bash
CONTAINER=my_container

# 复制工具到容器
docker cp skills/flagos-eval-comprehensive/tools/. $CONTAINER:/flagos-workspace/eval/

# 在容器内执行评测
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    python eval_orchestrator.py --config config.yaml --preflight"

# 后台评测
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    nohup python eval_orchestrator.py --config config.yaml --preflight > /dev/null 2>&1 &"

# 宿主机监控进度
tail -f /data/flagos-workspace/eval/eval_progress.log

# 查看结果
cat /data/flagos-workspace/eval/eval_report.json
```

---

## 4. Preflight 预检详解

### 什么是 Preflight

Preflight 在正式评测前，用极小样本（limit=2）快速跑一遍所有 benchmark。目的是**提前发现配置和环境问题**，而不是等全量评测跑了几个小时才报错。

### Preflight 检测的问题

| 检测项 | 能发现的问题 |
|--------|------------|
| API 连通性 | 模型服务未启动、端口错误、API 地址错误 |
| 参数合法性 | max_tokens 超过模型上下文长度、temperature 不合法 |
| 数据集可用性 | 本地缓存不存在、在线下载失败、数据集格式不匹配 |
| 依赖完整性 | evalscope 未安装、自研脚本文件不存在、evaluate_* 函数缺失 |
| 模型基本能力 | 模型是否能正常返回响应（不超时、不返回空） |

### Preflight 的输出

```
============================================================
Preflight Check (limit=2)
============================================================
  Preflight: MMLU_5shot ...
--------------------------------------------------
>>> Running: MMLU_5shot (runner=evalscope)
[EvalScope] Starting mmlu ...
[EvalScope] mmlu completed successfully
<<< MMLU_5shot: accuracy=100.0, status=S, duration=8.52s
  [OK] MMLU_5shot
  Preflight: AIME24_0shot ...
  ...
  [OK] AIME24_0shot
  Preflight: LiveBench ...
  [FAIL] LiveBench: Connection refused
[ABORT] Preflight failed. Fix errors above before running full evaluation.
```

- **`[OK]`**：该 benchmark 能正常运行（accuracy 不重要，只看是否报错）
- **`[FAIL]`**：该 benchmark 运行失败，后面跟着错误原因
- **`[PASS]`**：所有 benchmark 均通过 → 自动开始全量评测
- **`[ABORT]`**：有 benchmark 失败 → 中止，不进入全量评测

### Preflight 输出目录

预检结果保存在 `outputs/preflight/`，和正式评测的 `outputs/evalscope/` 等目录完全隔离，不会污染正式结果。

### Preflight 的返回值

失败时返回：
```json
{"preflight": false, "error": "Preflight check failed"}
```

成功时：继续执行全量评测，最终返回正常的评测报告。

---

## 5. 调试指南

### 5.1 由粗到细的调试流程

```bash
# 第一步：确认配置正确
python eval_orchestrator.py --config config.yaml --dry-run

# 第二步：单个 benchmark 小样本
python eval_orchestrator.py --config config.yaml --benchmarks mmlu --limit 2

# 第三步：单个 runner 直接测试
python evalscope_runner.py --config config.yaml --benchmark mmlu --limit 2

# 第四步：全量预检
python eval_orchestrator.py --config config.yaml --preflight

# 第五步：全量评测
python eval_orchestrator.py --config config.yaml
```

### 5.2 确认 API 连通性

```bash
# 检查模型列表
curl http://localhost:9010/v1/models

# 检查 chat 接口
curl http://localhost:9010/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "YOUR_MODEL_NAME", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 10}'
```

如果 curl 超时或报错，问题在模型服务而不是评测脚本。

### 5.3 确认数据集缓存

```bash
# 查看缓存状态
python dataset_prefetch.py --model-type LLM --cache-dir datasets/evalscope_cache --status

# 预期输出：
#   ✓ mmlu                 | 2/2 cached, 0 missing, 0 corrupt
#   ✗ livebench            | 0/1 cached, 1 missing, 0 corrupt
```

如果显示 missing 或 corrupt，重新下载：

```bash
python dataset_prefetch.py --model-type LLM --benchmarks mmlu --cache-dir datasets/evalscope_cache --force
```

### 5.4 调试自研脚本

自研脚本都支持单独运行：

```bash
# TheoremQA
python custom_eval/eval_theoremqa.py --config config.yaml --limit 3

# Robotics 的某个子 benchmark
python custom_eval/eval_robotics.py --config config.yaml --benchmark erqa --limit 3

# LiveBench
python custom_eval/eval_livebench.py --config config.yaml --limit 3
```

### 5.5 max_tokens 问题

这是最常见的评测错误。`evalscope_runner.py` 会自动查询模型的 `max_model_len` 并调整：

```
[WARN] max_tokens 30000 exceeds model context 16384, adjusting to 8192
```

如果你在日志里看到这条 WARN，说明自动调整生效了。如果还是报错，手动修改 config.yaml：

```yaml
generation_config:
  max_tokens: 4096  # 保守值
```

### 5.6 并行评测的注意事项

```bash
# 并行度 = 同时运行的 benchmark 数
python eval_orchestrator.py --config config.yaml --parallel 3
```

**风险**：
- 多个 benchmark 同时发请求给模型，可能导致 OOM 或超时
- 日志会交错（多个 benchmark 的日志混在一起）
- 建议先串行跑通一遍再考虑并行

---

## 6. 日志解读

### 6.1 日志文件位置

默认 `eval_progress.log`，可通过 `--log` 参数或 `config.yaml` 中 `output.progress_log` 修改。

### 6.2 日志格式

每行格式：`[时间戳] 内容`

```
[2026-03-16 14:30:01] ============================================================
[2026-03-16 14:30:01] Evaluation Orchestrator
[2026-03-16 14:30:01] ============================================================
[2026-03-16 14:30:01] Model: Qwen2-72B
[2026-03-16 14:30:01] Type: LLM
[2026-03-16 14:30:01] Benchmarks to run: 5
[2026-03-16 14:30:01]   - MMLU_5shot (runner=evalscope)
[2026-03-16 14:30:01]   - AIME24_0shot (runner=evalscope)
...
```

### 6.3 关键日志标记

| 标记 | 含义 | 后续动作 |
|------|------|---------|
| `>>> Running: XXX` | 开始执行某个 benchmark | 等待 |
| `<<< XXX: accuracy=N, status=S` | benchmark 执行完成 | 成功 |
| `[ERROR] XXX failed: ...` | benchmark 执行报错 | 检查错误详情 |
| `[WARN] max_tokens ... adjusting` | max_tokens 自动调整 | 正常，无需处理 |
| `[EvalScope] Starting XXX` | EvalScope 开始运行 | 等待 |
| `[EvalScope] XXX completed` | EvalScope 运行完成 | 成功 |
| `Preflight: XXX ...` | 开始预检某个 benchmark | 等待 |
| `[OK] XXX` | 预检通过 | 继续 |
| `[FAIL] XXX: ...` | 预检失败 | 查看错误原因 |
| `[PASS] All benchmarks passed` | 全部预检通过 | 自动进入全量评测 |
| `[ABORT] Preflight failed` | 预检有失败项 | 修复后重试 |
| `Evaluation Complete` | 全部评测结束 | 查看报告 |
| `Success: N, Failed: M` | 最终统计 | 确认 Failed=0 |
| `Total duration: Ns` | 总耗时 | 参考 |

### 6.4 实时监控

```bash
# 实时查看日志
tail -f eval_progress.log

# 只看关键信息（过滤）
tail -f eval_progress.log | grep -E "(>>>|<<<|ERROR|FAIL|PASS|ABORT|Complete)"

# 统计进度（已完成/总数）
grep -c "<<<" eval_progress.log
```

---

## 7. config.yaml 配置速查

### 7.1 必须正确的字段

```yaml
model:
  name: "Qwen2-72B"                    # 必须与 /v1/models 返回的 id 一致
  type: "LLM"                          # LLM / VL / Omni / Robotics / ImageGen
  api_base: "http://localhost:9010/v1"  # 模型 API 地址
```

**如何确认 model.name 正确**：

```bash
curl -s http://localhost:9010/v1/models | python -c "
import json, sys
data = json.load(sys.stdin)
for m in data.get('data', []):
    print(m['id'])"
```

输出的就是应该填入 `model.name` 的值。

### 7.2 按场景选择的配置

| 场景 | temperature | max_tokens | 额外配置 |
|------|------------|------------|---------|
| 标准评测 | 0.0 | 4096~30000 | 无 |
| thinking 模型 | 0.6 | 30000 | `dataset_filters.remove_until: "</think>"` |
| 调试 | 0.0 | 4096 | 配合 `--limit 5` |

### 7.3 evalscope 配置说明

```yaml
evalscope:
  dataset_hub: "modelscope"        # 或 "huggingface"
  dataset_dir: "datasets/evalscope_cache"  # 预下载缓存路径
  eval_batch_size: 64              # 并行请求数（调小可降低模型压力）
  stream: true                     # 流式输出
  timeout: 60000                   # 单请求超时（毫秒）
```

- `dataset_dir` 配置后，EvalScope 优先从本地加载数据，不联网
- `eval_batch_size` 过大可能导致模型 OOM，出问题时调到 8 或 16
- `timeout` 对 thinking 模型可能需要调大（推理时间长）

---

## 8. 常见报错与解决

### 8.1 启动阶段

| 报错 | 原因 | 解决 |
|------|------|------|
| `[ERROR] Failed to load config: config.yaml` | 配置文件不存在或 YAML 语法错误 | 检查文件路径和 YAML 格式 |
| `[ERROR] Failed to load registry: benchmark_registry.yaml` | 注册表不存在 | 确认文件已复制到工作目录 |
| `[ERROR] --selection and --benchmarks are mutually exclusive` | 两个参数冲突 | 只用其中一个 |

### 8.2 Preflight / 执行阶段

| 报错 | 原因 | 解决 |
|------|------|------|
| `evalscope not installed` | 缺少 evalscope 包 | `pip install evalscope` |
| `Connection refused` / `Connection error` | 模型服务未启动或地址错误 | `curl` 检查 API 地址 |
| `max_tokens exceeds model context` | 自动调整生效（WARN 级别） | 通常无需处理，脚本已自动降低 |
| `Request timeout` | 模型推理太慢 | 增大 `evalscope.timeout`，或减小 `eval_batch_size` |
| `Dataset download failed` | 网络问题 | 先用 `dataset_prefetch.py` 预下载 |
| `No evaluate_* function in XXX` | 自研脚本缺少约定的入口函数 | 检查脚本是否有 `evaluate_xxx()` 函数 |
| `Script not found: XXX` | 自研脚本文件不存在 | 检查 `custom_eval/` 目录是否完整 |
| `Unknown runner: XXX` | 注册表中 runner 字段值不合法 | 只能是 `evalscope` / `vlmeval` / `custom` |

### 8.3 结果阶段

| 问题 | 原因 | 解决 |
|------|------|------|
| `err_code: 1` | 所有 benchmark 都失败 | 查看 details 里每个的 error 信息 |
| `err_code: 2` | 部分失败 | 只需修复失败的，成功的不用重跑 |
| `accuracy: 0.0, status: S` | benchmark 运行成功但未能提取到分数 | 查看 rawDetails 里的原始数据 |
| eval_report.json 不存在 | eval_orchestrator 中途崩溃 | 查看 eval_progress.log 的最后几行 |

### 8.4 性能问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 评测非常慢 | eval_batch_size 太大导致排队 | 调小 `eval_batch_size` |
| GPU OOM | 并行评测压力过大 | `--parallel 1` 串行执行 |
| 单个 benchmark 卡住不动 | 模型服务无响应 | 检查模型服务日志 |

---

## 附录：benchmark name 对照表

在命令行使用 `--benchmarks` 时需要填写 **name**（不是 display_name）：

| name（命令行用） | display_name（报告显示） | 类型 | runner |
|-----------------|------------------------|------|--------|
| `mmlu` | MMLU_5shot | LLM | evalscope |
| `aime24` | AIME24_0shot | LLM | evalscope |
| `aime25` | AIME25_0shot | LLM | evalscope |
| `gpqa_diamond` | GPQA_Diamond_0shot | LLM | evalscope |
| `musr` | MUSR_0shot | LLM | evalscope |
| `livebench` | LiveBench | LLM | custom |
| `math_500` | MATH-500_0shot | LLM | evalscope |
| `mmlu_pro` | MMLU-Pro_0shot | LLM | evalscope |
| `theoremqa` | TheoremQA | LLM | custom |
| `gsm8k` | GSM8K | LLM | evalscope |
| `ceval` | CEVAL | LLM | evalscope |
| `mmmu` | MMMU_val | VL | evalscope |
| `cmmmu` | CMMMU_val | VL | evalscope |
| `mmmu_pro` | MMMU_Pro | VL | evalscope |
| `blink` | Blink_val | VL | evalscope |
| `ocr_bench` | OCRBench | VL | evalscope |
| `math_vision` | MathVision | VL | evalscope |
| `cii_bench` | CII-Bench | VL | custom |
| `mm_vet_v2` | MM-Vet_v2 | VL | custom |
| `math_vista` | MathVista | VL | evalscope |
| `video_mme` | Video-MME | VL | custom |
| `erqa` | ERQA | Robotics | custom |
| `sat` | SAT | Robotics | custom |
| `all_angles` | All-Angles_Bench | Robotics | custom |
| `where2place` | Where2Place | Robotics | custom |
| `blink_ev` | Blink_val_ev | Robotics | custom |
| `robospatial` | RoboSpatial-Home | Robotics | custom |
| `egoplan2` | EgoPlan-Bench2 | Robotics | custom |
| `cv_bench` | CV-Bench | Robotics | custom |
| `embspatial` | EmbSpatial-Bench | Robotics | custom |
| `vsi_bench` | VSI-Bench | Robotics | custom |
| `embodiedverse` | EmbodiedVerse-Open | Robotics | custom |
| `mape` | MAPE | Robotics | custom |
| `image_gen_qualitative` | Image_Gen_Qualitative | ImageGen | custom |

---

*最后更新: 2026-03-16*
