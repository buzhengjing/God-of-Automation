---
name: flagos-model-introspection
description: 检查模型仓库或目录，确定模型结构、框架兼容性和部署说明
version: 1.0.0
triggers:
  - 模型检查
  - model introspection
  - 检查模型
  - inspect model
dependencies: []
next_skill: flagos-environment-preparation
---

# FlagOS 模型检查 Skill

分析模型源以确定部署需求。

## 支持的模型来源

- ModelScope 仓库
- HuggingFace 仓库
- Git 仓库
- 本地模型目录
- 用户提供的 URL

---

## 工作流程

### 步骤 1：识别模型来源

用户应提供以下之一：

- 模型仓库 URL
- 本地模型目录
- 模型下载命令

**确定内容**：

- 来源平台
- 仓库位置
- 模型名称

**结果反馈**：

- 模型名称
- 仓库来源
- 仓库 URL

---

### 步骤 2：查找 README 或部署指南

搜索以下文件：

- README.md
- 部署文档
- 使用说明

如果 README 存在，提取：

- 模型下载命令
- Docker 镜像来源
- Docker 运行命令
- 推理启动命令

**结果反馈**：

- README 是否存在
- 可用的部署说明

---

### 步骤 3：检查模型目录

检查关键文件：

- config.json
- tokenizer.json
- model.safetensors
- pytorch_model.bin

确定模型格式。

**结果反馈**：

- 模型文件结构
- 权重格式

---

### 步骤 4：检测支持的运行时

确定兼容的框架：

- vLLM
- SGLang
- Transformers
- TGI

**判断依据**：

- vLLM 相关说明
- SGLang 相关说明
- tokenizer 配置

**结果反馈**：

- 推荐的运行时框架
- 备选运行时选项

---

## 完成标准

模型检查完成的条件：

- 模型来源已识别
- README 状态已知
- 运行时框架已确定

下一步应执行 **flagos-environment-preparation**。
