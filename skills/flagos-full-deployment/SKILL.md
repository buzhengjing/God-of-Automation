---
name: flagos-full-deployment
description: 执行完整的模型部署流程，包括模型检查、环境准备、服务启动和服务验证
version: 1.0.0
triggers:
  - 完整部署
  - full deployment
  - 一键部署
  - deploy model
dependencies: []
next_skill: null
---

# FlagOS 完整部署编排器

编排完整的模型部署流水线。

---

## 工作流程

按顺序执行以下 skill：

| 步骤 | Skill | 说明 |
|------|-------|------|
| 1 | flagos-model-introspection | 检查模型结构和部署需求 |
| 2 | flagos-environment-preparation | 准备运行环境（下载模型、拉取镜像、启动容器）|
| 3 | flagos-service-startup-environment-check | 启动推理服务 |
| 4 | flagos-service-health-check | 验证服务健康状态 |

---

## 执行方式

### 自动执行

触发 `flagos-full-deployment` 后，系统将自动按顺序执行上述 skill。

### 手动执行

也可以逐个触发单独的 skill：

```
1. /flagos-model-introspection
2. /flagos-environment-preparation
3. /flagos-service-startup-environment-check
4. /flagos-service-health-check
```

---

## 状态跟踪

每个步骤完成后记录状态到 `deployment_state.json`：

```json
{
  "model_introspection": {
    "status": "completed",
    "timestamp": "2026-03-07T10:00:00",
    "result": { ... }
  },
  "environment_preparation": {
    "status": "completed",
    "timestamp": "2026-03-07T10:15:00",
    "result": { ... }
  },
  "service_startup": {
    "status": "in_progress",
    "timestamp": "2026-03-07T10:30:00"
  },
  "health_check": {
    "status": "pending"
  }
}
```

---

## 完成标准

部署成功的条件：

- 模型已检查
- 容器正在运行
- 服务已启动
- API 正常响应

---

## 故障处理

如果某个步骤失败：

1. 检查失败步骤的日志
2. 使用 `flagos-log-analyzer` 诊断问题
3. 修复问题后从失败步骤继续
