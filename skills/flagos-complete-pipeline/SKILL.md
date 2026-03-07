---
name: flagos-complete-pipeline
description: 端到端完整工作流，从模型检查到模型发布的全流程编排
version: 1.0.0
triggers:
  - 完整流程
  - 端到端
  - complete pipeline
  - full workflow
  - 全流程
dependencies: []
next_skill: null
---

# FlagOS 完整流水线编排器

端到端编排从模型检查到模型发布的完整工作流。

---

## 工作流程概览

```
模型检查 → 环境准备 → 服务启动 → 服务验证 → 精度评测 → 性能评测 → 镜像打包 → 模型发布
```

---

## 详细步骤

| 阶段 | 步骤 | Skill | 可选 |
|------|------|-------|------|
| 部署 | 1 | flagos-model-introspection | 否 |
| 部署 | 2 | flagos-environment-preparation | 否 |
| 部署 | 3 | flagos-service-startup-environment-check | 否 |
| 部署 | 4 | flagos-service-health-check | 否 |
| 评测 | 5 | flagos-eval-correctness | 是 |
| 评测 | 6 | flagos-performance-testing | 是 |
| 发布 | 7 | flagos-image-package-upload | 是 |
| 发布 | 8 | flagos-model-release | 是 |

---

## 阶段说明

### 阶段 1：部署（必选）

执行 `flagos-full-deployment` 完成基础部署：

- 模型结构检查
- 环境准备（模型下载、镜像拉取、容器启动）
- 服务启动
- 健康检查

### 阶段 2：评测（可选）

根据需求选择执行：

- **精度评测**：`flagos-eval-correctness`
  - AIME 数学竞赛测试
  - ERQA 具身推理测试

- **性能评测**：`flagos-performance-testing`
  - 吞吐量测试
  - 延迟测试（TTFT、TPOT）

### 阶段 3：发布（可选）

根据需求选择执行：

- **镜像打包上传**：`flagos-image-package-upload`
  - 收集环境信息
  - 构建 Docker 镜像
  - 推送到 Harbor

- **模型发布**：`flagos-model-release`
  - 准备 README
  - 上传到 HuggingFace
  - 上传到 ModelScope

---

## 辅助工具

在任意阶段遇到问题时可使用：

- **日志分析**：`flagos-log-analyzer`
  - 诊断启动失败
  - 分析运行时错误
  - 检测 FlagGems 集成状态

---

## 状态管理

完整流水线状态记录在 `pipeline_state.json`：

```json
{
  "pipeline_id": "uuid",
  "started_at": "2026-03-07T10:00:00",
  "current_stage": "evaluation",
  "stages": {
    "deployment": {
      "status": "completed",
      "skills": ["model-introspection", "environment-preparation", "service-startup", "health-check"]
    },
    "evaluation": {
      "status": "in_progress",
      "skills": ["eval-correctness"]
    },
    "release": {
      "status": "pending",
      "skills": []
    }
  }
}
```

---

## 快速开始

### 完整流程

```
用户：执行完整流程
系统：依次执行所有步骤
```

### 仅部署

```
用户：执行完整部署
系统：执行步骤 1-4
```

### 仅评测

```
用户：执行精度评测和性能评测
系统：执行步骤 5-6（需先完成部署）
```

### 仅发布

```
用户：打包镜像并发布模型
系统：执行步骤 7-8（需先完成部署）
```

---

## 完成标准

完整流水线成功的条件：

- 所有必选步骤已完成
- 所有选择执行的可选步骤已完成
- 最终状态已记录

---

## 中断恢复

流水线支持断点续跑：

1. 检查 `pipeline_state.json` 获取当前状态
2. 从上次中断的步骤继续执行
3. 无需重复已完成的步骤
