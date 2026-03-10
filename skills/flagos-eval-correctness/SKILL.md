---
name: flagos-eval-correctness
description: 自动化大模型正确性评测流程，支持 AIME（数学竞赛）和 ERQA（具身推理）数据集
version: 1.1.0
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
---

# FlagOS 正确性评测 Skill

自动化评测大模型在 AIME 和 ERQA 数据集上的正确性。

---

# 统一工作目录

**重要**：所有评测操作在 `/flagos-workspace/eval` 目录下执行，结果和日志生成到宿主机可访问的位置。

```
容器内: /flagos-workspace/eval/
             ├── aime_result.json      ← 评测结果
             ├── erqa_result.json
             ├── eval_aime_progress.log ← 进度日志
             └── eval_erqa_progress.log

宿主机: /data/flagos-workspace/<model_name>/eval/  ← 实时同步
```

**宿主机实时监控**：
```bash
# 查看评测进度（无需 docker exec）
tail -f /data/flagos-workspace/<model_name>/eval/eval_aime_progress.log
tail -f /data/flagos-workspace/<model_name>/eval/eval_erqa_progress.log

# 查看评测结果
cat /data/flagos-workspace/<model_name>/eval/aime_result.json
cat /data/flagos-workspace/<model_name>/eval/erqa_result.json
```

---

## 目录结构

```
flagos-eval-correctness/
├── SKILL.md                     # 本 Skill 文件
└── tools/
    ├── config.yaml              # 评测配置文件
    ├── eval_aime.py             # AIME 评测脚本
    └── eval_erqa.py             # ERQA 评测脚本
```

---

## 工具说明

### tools/config.yaml

评测配置文件，定义模型参数和数据集路径。

**关键字段**：

```yaml
model:
  name: <模型名称>           # 必填：模型ID
  api_base: <API地址>        # 必填：OpenAI兼容API地址
  api_key: <API密钥>         # 可选：默认EMPTY

inference:
  temperature: 0             # 推理温度
  max_tokens: 2048           # 最大token数

evaluation:
  aime_samples: 30           # AIME样本数上限
  erqa_samples: 400          # ERQA样本数上限

datasets:
  aime_path: datasets/AIME   # AIME数据集相对路径
  erqa_path: datasets/ERQA   # ERQA数据集相对路径
```

### tools/eval_aime.py

AIME 数学竞赛评测脚本。

**功能**：

- 加载 AIME 数学题（JSONL格式）
- 调用模型 API 生成答案
- 提取 `[[ANSWER]]数字[[/ANSWER]]` 格式的答案
- 计算整体准确率

**参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--output` | aime_result.json | 结果文件 |
| `--log` | eval_aime_progress.log | 进度日志 |
| `--dry-run` | false | 测试模式 |

### tools/eval_erqa.py

ERQA 具身推理评测脚本。

**功能**：

- 加载 ERQA 多模态数据（Parquet格式，含图片）
- 调用视觉语言模型 API
- 提取 `[[ANSWER]]A/B/C/D[[/ANSWER]]` 格式的答案
- 计算 8 个维度的分类准确率 + Token 统计

**参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | config.yaml | 配置文件 |
| `--output` | erqa_result.json | 结果文件 |
| `--log` | eval_erqa_progress.log | 进度日志 |
| `--dry-run` | false | 测试模式 |

---

## 评测流程

### 步骤 1：复制评测工具到容器工作目录

```bash
# 在宿主机执行
CONTAINER=<container_name>
WORKSPACE_HOST="/data/flagos-workspace/<model_name>"

# 复制评测工具到工作目录
docker cp skills/flagos-eval-correctness/tools/. $CONTAINER:/flagos-workspace/eval/
```

### 步骤 2：准备容器内环境

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && \
    if [ ! -d '.venv' ]; then \
        uv venv && \
        source .venv/bin/activate && \
        uv pip install pandas pyarrow pyyaml requests; \
    fi"
```

### 步骤 3：配置模型

读取并按需修改 `/flagos-workspace/eval/config.yaml`：

```bash
# 宿主机直接查看和编辑
cat /data/flagos-workspace/<model_name>/eval/config.yaml
```

**配置检查清单**：

- [ ] `model.name` 是否正确
- [ ] `model.api_base` 是否可达（容器内通常为 `http://127.0.0.1:8000/v1`）
- [ ] `datasets.aime_path` 和 `datasets.erqa_path` 是否存在

### 步骤 4：运行评测

**在容器的工作目录下执行**：

**单独运行 AIME**：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && source .venv/bin/activate && nohup python eval_aime.py > /dev/null 2>&1 &"
```

**单独运行 ERQA**：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && source .venv/bin/activate && nohup python eval_erqa.py > /dev/null 2>&1 &"
```

**并行运行两个评测**：

```bash
docker exec $CONTAINER bash -c "cd /flagos-workspace/eval && source .venv/bin/activate && nohup python eval_aime.py > /dev/null 2>&1 & nohup python eval_erqa.py > /dev/null 2>&1 &"
```

### 步骤 5：监控进度（宿主机直接访问）

```bash
# 无需 docker exec，宿主机直接查看
tail -f /data/flagos-workspace/<model_name>/eval/eval_aime_progress.log
tail -f /data/flagos-workspace/<model_name>/eval/eval_erqa_progress.log

# 检查进程状态
docker exec $CONTAINER ps aux | grep "eval_"
```

### 步骤 6：获取结果（宿主机直接访问）

```bash
# 无需 docker exec，宿主机直接查看
cat /data/flagos-workspace/<model_name>/eval/aime_result.json
cat /data/flagos-workspace/<model_name>/eval/erqa_result.json
```

---

## 输出格式

### AIME 结果

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

### ERQA 结果

```json
{
  "err_code": 0,
  "err_msg": "Get Evaluations Details Sucess!",
  "eval_results": {
    "<MODEL_NAME>": {
      "status": "S",
      "details": [{
        "status": "S",
        "dataset": "ERQA",
        "accuracy": 80.0,
        "rawDetails": {
          "Other": 75.0,
          "Pointing": 82.5,
          "Task Reasoning": 78.0,
          "Action Reasoning": 81.0,
          "State Estimation": 79.5,
          "Spatial Reasoning": 83.0,
          "Multi-view Reasoning": 77.0,
          "Trajectory Reasoning": 84.0,
          "accuracy": 80.0,
          "average_tokens": 510.0,
          "average_prompt_tokens": 500.0,
          "average_completion_tokens": 10.0
        }
      }]
    }
  }
}
```

---

## 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `API_ERROR` | API超时或连接失败 | 检查api_base，已内置3次重试 |
| 准确率为0 | 答案格式提取失败 | 确认模型输出含`[[ANSWER]]` |
| 文件找不到 | 路径配置错误 | 检查datasets路径是否正确 |
| 进程无响应 | 资源不足或死锁 | `ps aux \| grep eval_` 检查 |

---

## 完成标准

评测完成的条件：

- 评测脚本执行完毕
- 结果文件已生成
- 准确率数据已记录