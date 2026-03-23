---
name: flagos-eval-correctness
description: 自动化大模型正确性评测，支持完整/quick 双模式。完整模式：远端 FlagRelease 或本地 AIME+ERQA；quick 模式：本地 AIME25 only。含错误自动分析、算子替换重试和本地评测降级。
version: 5.0.0
triggers:
  - 精度评测
  - 正确性评测
  - accuracy test
  - eval correctness
  - AIME
  - ERQA
depends_on:
  - flagos-service-startup
next_skill: flagos-performance-testing
provides:
  - eval.request_id
  - eval.domain
  - eval.status
  - eval.results
---

# FlagOS 正确性评测 Skill

自动化评测大模型正确性，支持**完整评测**和 **quick 评测**双模式。

**双模式**：

| 模式 | 说明 |
|------|------|
| **完整评测**（默认） | 远端 FlagRelease 平台（或本地 AIME + ERQA 降级） |
| **quick 评测** | 本地 AIME25 only，跳过远端和 ERQA，快速验证精度 |

**工具脚本**（已由 setup_workspace.sh 部署到容器）:
- `eval_monitor.py` — 评测监控（提交→轮询→结果获取一体化，减少 Claude Code 思考开销）
- `eval_aime.py` — AIME 本地评测（支持 `--quick` 切换 AIME25 数据集）
- `eval_erqa.py` — ERQA 本地评测（降级方案）

**在流程中的位置**：
- 步骤④（Native）和步骤⑦（FlagOS），每次服务启动后、性能测试前执行（询问用户）

**自动化行为**：
- FlagOS 服务启动后、性能测试前，询问用户是否执行精度评测
- **迁移场景**：FlagGems 算子首次启用，精度评测可能因算子不兼容报错，自动触发步骤 D（算子报错处理闭环：检测问题算子→关闭→重启服务→重新评测）
- 支持 `${CMD_PREFIX}` 双执行模式

支持完整的错误处理闭环：
- 服务端报错（算子问题）→ 自动关闭问题算子 → 重启服务 → 重新提交评测
- 评测平台不可达 / 网络问题 → 自动降级到本地评测脚本
- 用户提供已有 `request_id` → 直接查询进度和获取结果

---

## 强制约束

**启动前互斥检查**：精度评测启动前，必须确认没有正在运行的性能测试进程。并发执行会互相抢占 GPU 资源，导致结果不可信。

```bash
# 检查是否有性能测试进程在运行（benchmark_runner.py / vllm bench）
docker exec $CONTAINER bash -c "pgrep -f 'benchmark_runner\|vllm.*bench' && echo 'BLOCKED: 性能测试运行中，等待结束' && exit 1 || echo 'OK: 无性能测试进程'"
```

如果检测到性能测试进程，**必须等待其结束后再启动精度评测**，禁止强杀测试进程。

---

# 总体流程图

```
用户触发评测
     │
     ├── 用户提供 request_id ──────────────────────────────┐
     │                                                      ↓
     │                                              步骤 B：查询与结果获取
     │                                                      │
     ↓                                                      │
步骤 A：提交远端评测任务                                     │
     │                                                      │
     ├── 提交成功 → 监控进度 ───────────────────────────────┤
     │                                                      │
     └── 提交失败（网络不可达）→ 降级到本地评测（步骤 C）    │
                                                            │
                                                            ↓
                                                     结果分析与处理
                                                            │
     ┌──────────────────────────────────────────────────────┤
     │                          │                           │
     ↓                          ↓                           ↓
  正常完成(S)            算子失败(F/OOR)              网络/平台问题
  → 输出精度报告         → 关闭问题算子              → 降级到本地评测
                         → 重启服务                     （步骤 C）
                         → 重新提交评测
                           （回到步骤 A）
```

---

# 远端评测平台 API 参考

## 平台地址

| 环境 | 地址 | 说明 |
|------|------|------|
| **公网（当前使用）** | `http://110.43.160.159:5050` | 线上环境（原 120.92.17.239 维修中） |
| 本地 | `http://127.0.0.1:5051` | 本地测试环境 |

## API 接口一览

| 接口 | 方法 | 路径 | 用途 |
|------|------|------|------|
| 提交评测 | POST | `/evaluation` | 发起评测任务，返回 request_id |
| 查询进度 | POST | `/evaluation_progress` | 查询任务执行进度 |
| 获取结果 | GET | `/evaldiffs` | 获取最终评测结果 |
| 停止评测 | POST | `/stop_evaluation` | 停止正在运行的任务 |
| 恢复评测 | POST | `/resume_evaluation` | 恢复已停止的任务 |
| 对比评测 | GET | `/evaluation_diffs` | 对比多个评测任务的差异 |

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
model:
  name: <来自 container-preparation>
  url: <来自 container-preparation>
  container_path: <来自 container-preparation>
service:
  cluster: <来自 service-startup>      # 用于判断远端评测可达性
  external_ip: <来自 service-startup>  # 用于构建 eval_url
  host: <来自 service-startup>
  port: <来自 service-startup>
  healthy: <来自 service-startup>
  gems_txt_path: <来自 service-startup>
  initial_operator_list: <来自 service-startup>
gpu:
  vendor: <来自 container-preparation>
inspection:
  flaggems_control: <来自 pre-service-inspection>
  flaggems_logic: <来自 pre-service-inspection>
```

## 写入 shared/context.yaml

```yaml
eval:
  request_id: "<远端评测任务 ID>"
  domain: "<NLP|MM>"
  mode: "<评测模式>"
  status: "<S|F|C|OOR|running|local>"
  eval_method: "<remote|local>"
  results: {}                    # 最终评测结果
```

---

# 统一工作目录

```
容器内: /flagos-workspace/
             ├── results/aime_result.json      ← 评测结果
             ├── results/erqa_result.json
             ├── results/eval_result.json       ← 远端评测结果
             ├── logs/eval_aime_progress.log    ← 评测进度日志
             ├── logs/eval_erqa_progress.log
             └── config/eval_config.yaml        ← 评测配置快照

宿主机: /data/flagos-workspace/<model_name>/  ← 实时同步
```

---

# 本地评测工具说明

本地评测脚本在远端平台不可用时作为降级方案。

## 目录结构

```
flagos-eval-correctness/
├── SKILL.md                     # 本 Skill 文件
└── tools/
    ├── config.yaml              # 评测配置文件
    ├── eval_aime.py             # AIME 评测脚本
    └── eval_erqa.py             # ERQA 评测脚本
```

## tools/eval_aime.py

AIME 数学竞赛评测脚本。加载 JSONL 格式数学题，调用模型 API，提取 `[[ANSWER]]数字[[/ANSWER]]` 格式答案，计算准确率。支持并发请求加速评测。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--output` | aime_result.json | 结果文件 |
| `--log` | eval_aime_progress.log | 进度日志 |
| `--quick` | false | quick 模式：使用 AIME25 数据集，默认全量并发 |
| `--concurrency` | quick=0(全量并发), full=1(串行) | 并发请求数，0=自动(题目数) |
| `--dry-run` | false | 测试模式 |

**并发策略**：
- `--quick` 模式默认全量并发（30 题同时请求），耗时从 30-60 分钟降至 1-3 分钟
- 完整模式默认串行（避免大量并发影响服务稳定性），可通过 `--concurrency 10` 手动加速
- vLLM 支持高并发（性能测试验证到 256），30 并发不会造成服务压力

## tools/eval_erqa.py

ERQA 具身推理评测脚本。加载 Parquet 多模态数据，调用视觉语言模型 API，提取 `[[ANSWER]]A/B/C/D[[/ANSWER]]` 格式答案，计算 8 维分类准确率。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--output` | erqa_result.json | 结果文件 |
| `--log` | eval_erqa_progress.log | 进度日志 |
| `--dry-run` | false | 测试模式 |

---

# 评测流程

## 入口判断

询问用户选择操作模式：

| 模式 | 说明 |
|------|------|
| **提交新评测（完整）** | 通过远端 API 提交新评测任务（默认） |
| **quick 评测** | 本地 AIME25 only，跳过远端和 ERQA |
| **查询已有任务** | 用户提供 request_id，查询进度或获取结果 |

**quick 评测流程**：选择 quick 后，直接跳转到步骤 C（本地评测），只运行 `eval_aime.py --quick`，跳过 ERQA。

---

## 步骤 A：提交远端评测任务（主流程）

### A0 — 服务稳定性预检（崩溃检测）

**在提交评测之前，先用一条极简 benchmark 验证服务不会崩溃。**

从 context.yaml 读取服务参数，执行：

```bash
docker exec $CONTAINER bash -c "vllm bench serve \
  --host <service_host> \
  --port <service_port> \
  --model <model_name> \
  --tokenizer <tokenizer_path> \
  --dataset-name random \
  --random-input-len 1024 \
  --random-output-len 15 \
  --num-prompts 1 \
  --endpoint /v1/completions \
  --ignore-eos \
  --trust-remote-code"
```

参数说明：
- `--random-output-len 15`：极短输出，快速完成
- `--num-prompts 1`：仅 1 条请求，耗时约几秒

**结果判断**：
- 返回码 `0` 且输出正常 → 服务稳定，继续步骤 A1
- 返回码非 `0` 或服务崩溃 → **停止评测**，跳转到步骤 D（错误处理），检查服务日志分析原因

### A1 — 确定评测参数

从 context.yaml 读取服务信息，询问用户确认或补充以下参数：

| 参数 | 来源 | 说明 |
|------|------|------|
| `eval_model` | 用户提供 | 评测唯一名称，如 `qwen2.5-7b-nv-flagos` |
| `model` | context.yaml `model.name` 或 `model.container_path` | 大模型名称（与部署一致） |
| `eval_url` | **询问用户提供本机 IP** | 服务评测接口。**必须询问用户提供本机外部 IP（非 localhost/127.0.0.1）**，否则远端评测平台无法访问。可提示用户通过 `hostname -I` 查看，然后拼接为 `http://<用户提供的IP>:<port>/v1/chat/completions` |
| `tokenizer` | 用户提供 | Tokenizer 路径，如 `Qwen/Qwen2.5-7B-Instruct` |
| `domain` | 用户选择 | `NLP`（语言模型）或 `MM`（多模态） |
| `mode` | 用户选择 | NLP: `FlagRelease`/`XLC_train`/`XLC_infer`/`Qnext`/`quickrun`；MM: `FlagRelease`/`XLC`/`EmbodiedVerse`/`RoboTrain`/`quickrun` |
| `chip` | 自动检测 | 芯片名称，如 `Nvidia-H100` |
| `api_key` | 默认 `EMPTY` | API 密钥 |
| `batch_size` | 默认 `1` | |
| `num_concurrent` | 默认 `1` | 并发数 |
| `num_retry` | 默认 `10` | 重试次数 |
| `gen_kwargs` | 可选 | 生成超参数，如 `temperature=0.6,top_k=20,max_gen_toks=16000` |
| `region` | 默认 `bj` | `bj`（大兴）或 `sz`（上庄） |
| `user_id` | 用户提供或默认 `0` | FlagEval 平台用户 ID（**整数类型**，非字符串）。若用户未提供，默认使用 `0` |
| `dry_run` | 默认 `false` | 是否仅做推理验证（少量数据） |

**eval_model 命名规范**：
- 原生版本（baseline）：`<model>-<vendor>-origin`，如 `qwen2.5-7b-nv-origin`
- FlagOS 版本：`<model>-<vendor>-flagos`，如 `qwen2.5-7b-nv-flagos`

### A1.5 — 参数预检与确认

**提交前必须完成以下检查，一次性完成，禁止逐个试错：**

1. **询问用户提供本机 IP**：
   向用户询问本机外部 IP 地址（可提示用户通过 `hostname -I` 查看）。**禁止自动执行命令获取，必须由用户确认提供**。用获取到的 IP 构建 `eval_url`，禁止使用 context 中缓存的旧 IP

2. **验证服务可达性**（用实际的 eval_url 测试）：
   ```bash
   curl -s --connect-timeout 5 http://<实时IP>:<port>/v1/models
   ```

3. **组装完整参数并展示给用户确认**：
   向用户展示完整的提交 JSON，包含所有字段和实际值，等待用户确认后再提交

4. **参数类型检查**：
   - `user_id` 必须为整数（非空字符串）
   - `batch_size`、`num_concurrent`、`num_retry` 必须为整数
   - `dry_run` 必须为布尔值

### A2 — 提交评测任务

**推荐方式：使用 eval_monitor.py 一体化提交+轮询**（减少 Claude Code 思考开销）：

```bash
# 1. 准备参数文件
cat > /flagos-workspace/eval/eval_params.json << 'PARAMS'
{
    "eval_infos": [{
        "eval_model": "<eval_model>",
        "model": "<model_name>",
        "eval_url": "<eval_url>",
        "tokenizer": "<tokenizer>",
        "api_key": "<api_key>",
        "batch_size": 1,
        "num_concurrent": 1,
        "num_retry": 10,
        "gen_kwargs": "<gen_kwargs>",
        "chip": "<chip>",
        "base_model_name": "<base_model_name>"
    }],
    "domain": "<NLP|MM>",
    "mode": "<mode>",
    "region": "<region>",
    "user_id": 0,
    "dry_run": false
}
PARAMS

# 2. 提交并自动轮询到完成
${CMD_PREFIX} python3 /flagos-workspace/scripts/eval_monitor.py submit \
  --params /flagos-workspace/eval/eval_params.json \
  --output /flagos-workspace/results/eval_result.json
```

eval_monitor.py 自动完成：提交→递增间隔轮询（60s×5 + 180s×15）→获取结果→输出 JSON。

**备选方式：手动 curl 提交**（需要更细粒度控制时）：

```bash
# NLP 评测
curl -X POST http://110.43.160.159:5050/evaluation \
-H "Content-Type: application/json" \
-d '{
    "eval_infos": [{
        "eval_model": "<eval_model>",
        "model": "<model_name>",
        "eval_url": "<eval_url>",
        "tokenizer": "<tokenizer>",
        "api_key": "<api_key>",
        "batch_size": <batch_size>,
        "num_concurrent": <num_concurrent>,
        "num_retry": <num_retry>,
        "gen_kwargs": "<gen_kwargs>",
        "chip": "<chip>",
        "base_model_name": "<base_model_name>"
    }],
    "domain": "<NLP|MM>",
    "mode": "<mode>",
    "region": "<region>",
    "user_id": <user_id>,
    "dry_run": <dry_run>
}'
```

**MM 多模态评测**（domain 为 `MM` 时）：

```bash
# MM 评测（视觉 / 具身）
curl -X POST http://110.43.160.159:5050/evaluation \
-H "Content-Type: application/json" \
-d '{
    "eval_infos": [{
        "eval_model": "<eval_model>",
        "model": "<model_name>",
        "eval_url": "<eval_url>",
        "tokenizer": "<tokenizer>",
        "api_key": "EMPTY",
        "batch_size": 1,
        "num_concurrent": 1,
        "num_retry": 10,
        "gen_kwargs": "",
        "chip": "<chip>",
        "base_model_name": "<base_model_name>"
    }],
    "domain": "MM",
    "mode": "<FlagRelease|XLC|EmbodiedVerse|RoboTrain|quickrun>",
    "region": "<region>",
    "user_id": <user_id>
}'
```

**响应处理**：

```json
{
  "err_code": 0,
  "err_msg": "...",
  "request_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "eval_tasks": [...]
}
```

- `err_code == 0`：提交成功，**记录 `request_id`**（非常重要，后续所有操作依赖此 ID）
- `err_code == 1`：提交失败，检查错误信息

**提交失败处理**：
- 网络不可达 / 连接超时 → 跳转到 **步骤 C（本地评测降级）**
- 参数错误 → 修正参数后重新提交

### A3 — 监控评测进度

使用 `request_id` 定期查询评测进度：

```bash
curl -X POST http://110.43.160.159:5050/evaluation_progress \
-H "Content-Type: application/json" \
-d '{
    "request_id": "<request_id>",
    "domain": "<NLP|MM>"
}'
```

**响应字段**：

| 字段 | 说明 |
|------|------|
| `finished` | 评测是否完成 (bool) |
| `status` | 评测状态 |
| `datasets_progress` | 数据集总体进度 |
| `running_dataset` | 当前运行的数据集 |
| `running_progress` | 当前数据集内进度 |

**轮询策略**（自适应间隔 + 最大次数限制）：
- 第 1-5 次：每 30 秒查询一次（快速确认任务已启动）
- 第 6-15 次：每 60 秒查询一次
- 第 16-30 次：每 2 分钟查询一次
- 进度 > 80% 时：自动切换到每 30 秒密集轮询（快速感知完成）
- 最多轮询 30 次（约 1 小时），超出后停止轮询
- 每次查询向用户报告进度变化（仅在进度有变化时输出，避免刷屏）
- `finished == true` 时立即跳转到 A4 获取结果
- 超出 20 次未完成 → 输出 `request_id`，告知用户稍后手动查询或重新触发评测查询

**进度查询失败处理**：
- 连续 3 次网络不可达 → 停止轮询，告知用户平台可能异常，输出 `request_id` 供后续手动查询或降级本地评测

### A4 — 获取评测结果

评测完成后，获取最终结果：

```bash
curl -X GET http://110.43.160.159:5050/evaldiffs \
-H "Content-Type: application/json" \
-d '{"request_id": "<request_id>"}'
```

**响应结构**：

```json
{
  "err_code": 0,
  "err_msg": "...",
  "eval_results": {
    "<eval_model>": {
      "status": "S",
      "details": [
        {
          "dataset": "AIME_0fewshot_@avg1",
          "status": "S",
          "accuracy": 83.33,
          "diff": 0.0
        }
      ],
      "release": true
    }
  }
}
```

**结果状态解读**：

| status | 含义 | 后续操作 |
|--------|------|----------|
| `S` | 成功 | 输出精度报告 → 完成 |
| `F` | 失败 | 分析失败原因 → 步骤 D（错误处理） |
| `C` | 已取消 | 询问用户是否恢复 |
| `OOR` | 超过重试次数 | 分析失败原因 → 步骤 D（错误处理） |

---

## 步骤 B：查询已有任务（用户提供 request_id）

用户提供已有的 `request_id` 时，直接执行查询和结果获取。

### B1 — 查询进度

```bash
curl -X POST http://110.43.160.159:5050/evaluation_progress \
-H "Content-Type: application/json" \
-d '{
    "request_id": "<user_provided_request_id>",
    "domain": "<NLP|MM>"
}'
```

向用户报告当前状态。

### B2 — 获取结果（如已完成）

```bash
curl -X GET http://110.43.160.159:5050/evaldiffs \
-H "Content-Type: application/json" \
-d '{"request_id": "<user_provided_request_id>"}'
```

### B3 — 停止任务（如用户需要）

```bash
curl -X POST http://110.43.160.159:5050/stop_evaluation \
-H "Content-Type: application/json" \
-d '{"request_id": "<request_id>"}'
```

### B4 — 恢复任务（如任务已停止）

```bash
curl -X POST http://110.43.160.159:5050/resume_evaluation \
-H "Content-Type: application/json" \
-d '{"request_id": "<request_id>"}'
```

### B5 — 对比多个评测任务

对比原生版本与 FlagOS 版本的精度差异：

```bash
curl -X GET http://110.43.160.159:5050/evaluation_diffs \
-H "Content-Type: application/json" \
-d '{"request_ids": ["<request_id_origin>", "<request_id_flagos>"]}'
```

**响应结构**：

```json
{
  "err_code": 0,
  "eval_diffs": [
    {
      "request_id": "...",
      "details": [
        {"dataset": "AIME", "base_acc": 50.0, "accuracy": 50.0, "diff": 0.0}
      ],
      "release": true
    }
  ]
}
```

结果中若发现算子导致的评测失败（status 为 F/OOR），跳转到步骤 D。

---

## 步骤 C：本地评测降级

**触发条件**：远端评测平台不可达、网络超时、连接拒绝等。

### C1 — 复制评测工具到容器

```bash
CONTAINER=<container_name>
docker cp skills/flagos-eval-correctness/tools/. $CONTAINER:/flagos-workspace/eval/
```

### C2 — 准备容器内环境

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    if [ ! -d '.venv' ]; then \
        uv venv && \
        source .venv/bin/activate && \
        uv pip install pandas pyarrow pyyaml requests; \
    fi"
```

### C3 — 配置模型连接

编辑 `/flagos-workspace/eval/config.yaml`：

```yaml
model:
  name: <model_name>           # 从 context.yaml 获取
  api_base: http://127.0.0.1:8000/v1  # 容器内服务地址
  api_key: EMPTY
```

### C3.5 — 服务稳定性预检

本地评测前同样执行崩溃检测（与步骤 A0 相同的命令），确保服务不会在评测过程中崩溃。

### C4 — 运行本地评测

**完整模式**（并行运行 AIME 和 ERQA）：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && source .venv/bin/activate && \
    nohup python eval_aime.py --output /flagos-workspace/results/aime_result.json --log /flagos-workspace/logs/eval_aime_progress.log > /dev/null 2>&1 & \
    nohup python eval_erqa.py --output /flagos-workspace/results/erqa_result.json --log /flagos-workspace/logs/eval_erqa_progress.log > /dev/null 2>&1 &"
```

**quick 模式**（AIME25 全量并发，~1-3 分钟）：
```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && source .venv/bin/activate && \
    python eval_aime.py --quick --output /flagos-workspace/results/aime_result.json --log /flagos-workspace/logs/eval_aime_progress.log"
```

**评测配置快照**（运行前保存）：
```bash
docker exec $CONTAINER cp /flagos-workspace/eval/config.yaml /flagos-workspace/config/eval_config.yaml
```

### C5 — 监控本地评测进度

```bash
# 宿主机直接查看（无需 docker exec）
tail -f /data/flagos-workspace/<model_name>/logs/eval_aime_progress.log
tail -f /data/flagos-workspace/<model_name>/logs/eval_erqa_progress.log
```

### C6 — 获取本地评测结果

```bash
cat /data/flagos-workspace/<model_name>/results/aime_result.json
cat /data/flagos-workspace/<model_name>/results/erqa_result.json
```

本地评测过程中如出现服务端报错，同样跳转到步骤 D。

---

## 步骤 D：错误处理与自动重试

### 错误分类

```
评测报错
  │
  ├── 服务端报错（算子问题）
  │     特征: CUDA error, OOM, RuntimeError, operator not supported,
  │           服务进程退出, status=F/OOR（远端结果中）
  │     → D1: 算子替换 → 重启服务 → 重新评测
  │
  └── 评测端/网络问题
        特征: timeout, connection refused, 平台 5xx, DNS 解析失败
        → D2: 降级到本地评测（步骤 C）
```

### D1 — 服务端报错处理（算子替换闭环）

**此流程可多轮迭代，直到评测通过或用户终止。**

**第 1 步：分析报错原因**

远端评测结果中发现失败：
```bash
# 检查远端返回的结果中 status 为 F 或 OOR 的数据集
# 分析 err_msg 或 details 中的错误描述
```

本地评测日志中发现失败：
```bash
# 检查服务日志
grep -iE "(CUDA|OOM|RuntimeError|operator.*not.*support|process.*exit)" \
    /data/flagos-workspace/<model_name>/output/**/*.log

# 检查评测日志
grep -iE "(error|exception|traceback)" \
    /data/flagos-workspace/<model_name>/eval/eval_*_progress.log
```

**第 2 步：整理报错报告**

向用户输出报错分析：
- 错误类型（CUDA error / OOM / 算子不支持等）
- 涉及的算子名称（从日志中提取）
- 建议关闭的算子列表

**第 3 步：触发算子替换**

调用 `flagos-operator-replacement` skill：
- 根据错误信息确定需要排除的算子
- 根据 `inspection.flaggems_control` 和 `inspection.flaggems_logic` 执行替换
- 记录替换详情

**第 4 步：重启服务**

```bash
# 停止当前服务
docker exec <container> pkill -f "vllm\|sglang"

# 等待进程退出
sleep 5

# 重新启动服务（参考 flagos-service-startup）
docker exec <container> bash -c "cd /flagos-workspace && <startup_command>"
```

验证服务健康：

```bash
curl -s http://localhost:8000/v1/models | jq .
```

**第 5 步：重新提交评测**

- 如果之前使用远端评测 → 回到 **步骤 A2** 重新提交
- 如果之前使用本地评测 → 回到 **步骤 C4** 重新运行

**迭代控制**：
- 每轮记录关闭了哪些算子
- 建议最多迭代 3 轮，超出后建议用户介入分析
- 每轮向用户报告当前状态和进展

### D2 — 评测端/网络问题处理

1. 确认是网络/平台问题而非服务端问题
2. 检查服务是否正常：
   ```bash
   curl -s http://localhost:8000/v1/models | jq .
   ```
3. 跳转到 **步骤 C（本地评测降级）**

---

# 输出格式

## 远端评测结果（来自 /evaldiffs）

```json
{
  "err_code": 0,
  "err_msg": "Get Evaluations Details Sucess!",
  "eval_results": {
    "<eval_model>": {
      "status": "S",
      "details": [
        {
          "dataset": "AIME_0fewshot_@avg1",
          "status": "S",
          "accuracy": 83.33,
          "diff": 0.0
        }
      ],
      "release": true
    }
  }
}
```

## 精度对比报告

当同时有原生版本和 FlagOS 版本的评测结果时，输出对比报告：

```
精度对比报告
=======================================
数据集          原生精度    FlagOS精度    差异
AIME            50.00%      50.00%       0.00%
ERQA            60.00%      56.50%      -3.50%
=======================================
结论: [精度对齐 / 存在差异，建议检查]
```

## 本地评测结果

与原有格式一致：

```json
{
  "err_code": 0,
  "err_msg": "Get Evaluations Details Sucess!",
  "eval_results": {
    "<MODEL_NAME>": {
      "status": "S",
      "details": [{
        "status": "S",
        "dataset": "AIME_0fewshot_@avg1",
        "accuracy": 83.33,
        "rawDetails": {}
      }]
    }
  }
}
```

---

# 故障排查

| 问题 | 类型 | 原因 | 解决方案 |
|------|------|------|----------|
| 远端提交失败 `err_code=1` | 平台 | 参数错误 | 检查 eval_infos 参数格式 |
| 连接 110.43.160.159 超时 | 网络 | 平台不可达 | 降级到本地评测（步骤 C） |
| `status: F` 算子失败 | 服务端 | 算子不兼容 | 触发算子替换 → 重启 → 重评（步骤 D1） |
| `status: OOR` 重试耗尽 | 服务端 | 服务不稳定 | 检查服务日志，可能是算子或 OOM 问题 |
| `status: C` 已取消 | 人工 | 用户或系统取消 | 使用 `/resume_evaluation` 恢复 |
| `CUDA error` | 服务端 | 算子不兼容 | 关闭问题算子 → 重启 → 重评 |
| `OOM` | 服务端 | 显存不足 | 减少 batch_size 或 tensor-parallel-size |
| 本地评测准确率为 0 | 评测端 | 答案格式问题 | 确认模型输出含 `[[ANSWER]]` |
| request_id 丢失 | 人工 | 未保存 | 无法恢复，需重新提交 |

---

# 阶段性反馈格式

每次评测完成后，必须向用户输出以下格式的总结：

```
精度评测结果
========================================
状态: 通过 / 有报错
评测项: AIME=83.3%, ERQA=60.0%
问题算子: softmax, layer_norm（从服务端报错日志提取）
建议操作: 关闭问题算子 → 重启服务 → 重新评测
已累计剔除: 2 个算子（softmax, layer_norm）
========================================
```

**反馈规则**：
- 状态为"通过"时不显示"问题算子"和"建议操作"
- 每次重新评测后更新"已累计剔除"计数
- 如果连续 3 轮仍有新算子报错，提醒用户介入

---

# 完成标准

- 评测任务已完成（远端或本地）
- 评测结果已获取（保存到 `results/`）
- 如有错误，已完成错误分析和算子替换处理
- **阶段性总结已输出给用户**
- 精度数据已记录到 context.yaml
- 评测配置快照已保存到 `config/eval_config.yaml`
- 对应 trace 文件已写入：
  - Native 评测 → `traces/05_eval_native.json`
  - Full FlagGems 评测 → `traces/08_eval_full_flagos.json`
