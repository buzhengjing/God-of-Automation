---
name: flagos-eval-correctness
description: 自动化大模型正确性评测，优先使用远端 FlagEval 平台 API，支持错误自动分析、算子替换重试和本地评测降级。集成到双场景流程中作为可选步骤。
version: 3.1.0
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

自动化评测大模型正确性，**优先通过远端 FlagEval 平台 API 提交评测任务**。

**在双场景流程中的位置**：
- **Scenario A**：步骤⑧，可选步骤（默认跳过，用户可提前指定执行）
- **Scenario B**：步骤⑦，可选步骤

**自动化行为**：
- 默认跳过精度评测（除非用户明确要求）
- 如果在流程开始时用户指定了要做精度评测，则自动执行
- 支持 `${CMD_PREFIX}` 双执行模式

支持完整的错误处理闭环：
- 服务端报错（算子问题）→ 自动关闭问题算子 → 重启服务 → 重新提交评测
- 评测平台不可达 / 网络问题 → 自动降级到本地评测脚本
- 用户提供已有 `request_id` → 直接查询进度和获取结果

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
容器内: /flagos-workspace/eval/
             ├── aime_result.json      ← 评测结果（本地评测时生成）
             ├── erqa_result.json
             ├── eval_aime_progress.log
             └── eval_erqa_progress.log

宿主机: /data/flagos-workspace/<model_name>/eval/  ← 实时同步
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

AIME 数学竞赛评测脚本。加载 JSONL 格式数学题，调用模型 API，提取 `[[ANSWER]]数字[[/ANSWER]]` 格式答案，计算准确率。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--output` | aime_result.json | 结果文件 |
| `--log` | eval_aime_progress.log | 进度日志 |
| `--dry-run` | false | 测试模式 |

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
| **提交新评测** | 通过远端 API 提交新评测任务（默认） |
| **查询已有任务** | 用户提供 request_id，查询进度或获取结果 |

---

## 步骤 A：提交远端评测任务（主流程）

### A1 — 确定评测参数

从 context.yaml 读取服务信息，询问用户确认或补充以下参数：

| 参数 | 来源 | 说明 |
|------|------|------|
| `eval_model` | 用户提供 | 评测唯一名称，如 `qwen2.5-7b-nv-flagos` |
| `model` | context.yaml `model.name` 或 `model.container_path` | 大模型名称（与部署一致） |
| `eval_url` | context.yaml `service.external_ip`:`service.port` | 服务评测接口，如 `http://<external_ip>:8000/v1/chat/completions`。**必须使用 `external_ip`（非 localhost）**，否则远端评测平台无法访问 |
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
| `user_id` | 用户提供 | FlagEval 平台用户 ID |
| `dry_run` | 默认 `false` | 是否仅做推理验证（少量数据） |

**eval_model 命名规范**：
- 原生版本（baseline）：`<model>-<vendor>-origin`，如 `qwen2.5-7b-nv-origin`
- FlagOS 版本：`<model>-<vendor>-flagos`，如 `qwen2.5-7b-nv-flagos`

### A2 — 提交评测任务

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
    "user_id": "<user_id>",
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
    "user_id": "<user_id>"
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

**轮询策略**：
- 每 60 秒查询一次进度
- 向用户报告进度变化
- `finished == true` 时跳转到 A4 获取结果

**进度查询失败处理**：
- 连续 3 次网络不可达 → 告知用户平台可能异常，建议稍后手动查询或降级本地评测

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

### C4 — 运行本地评测

```bash
# 并行运行 AIME 和 ERQA
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && source .venv/bin/activate && \
    nohup python eval_aime.py > /dev/null 2>&1 & \
    nohup python eval_erqa.py > /dev/null 2>&1 &"
```

### C5 — 监控本地评测进度

```bash
# 宿主机直接查看（无需 docker exec）
tail -f /data/flagos-workspace/<model_name>/eval/eval_aime_progress.log
tail -f /data/flagos-workspace/<model_name>/eval/eval_erqa_progress.log
```

### C6 — 获取本地评测结果

```bash
cat /data/flagos-workspace/<model_name>/eval/aime_result.json
cat /data/flagos-workspace/<model_name>/eval/erqa_result.json
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

# 完成标准

评测完成的条件：

- 评测任务已提交并完成（远端或本地）
- request_id 已记录（远端评测时）
- 评测结果已获取
- 如有错误，已完成自动错误分析和处理（算子替换/降级）
- 精度数据已记录到 context.yaml
- 如有原生和 FlagOS 双版本结果，已输出对比报告
