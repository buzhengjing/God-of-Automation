---
name: flagos-service-health-check
description: 验证已部署的推理服务是否可访问并正确响应
version: 1.0.0
triggers:
  - 服务验证
  - 健康检查
  - health check
  - service validation
dependencies:
  - flagos-service-startup-environment-check
next_skill: flagos-eval-correctness
---

# FlagOS 服务健康检查 Skill

验证推理服务是否正常运行。

---

## 工作流程

### 步骤 1：检查进程

```bash
ps -ef | grep vllm
```

**结果反馈**：

- 进程 ID
- 进程状态

---

### 步骤 2：查询模型 API

```bash
curl http://localhost:8000/v1/models
```

**结果反馈**：

- API 响应
- 模型标识符

---

### 步骤 3：运行推理测试

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<model_name>",
    "messages": [{"role": "user", "content": "hello"}]
  }'
```

**结果反馈**：

- 推理结果
- 延迟

---

## 完成标准

服务被认为健康的条件：

- API 可达
- 模型已列出
- 返回了推理结果

---

## 工具脚本

可使用 `tools/check_health.sh` 进行自动化检查。

```bash
bash tools/check_health.sh --host localhost --port 8000 --model <model_name>
```
