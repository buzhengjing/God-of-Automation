---
name: flagos-model-introspection
description: 检查模型仓库或目录，确定模型结构、框架兼容性和可用的部署说明
version: 1.0.0
license: internal
triggers:
  - model introspection
  - inspect model
  - 模型检查
depends_on: []
provides:
  - model.name
  - model.source
  - model.path
  - model.readme_found
  - runtime.framework
---

# 模型检查 Skill

此 Skill 在部署前分析模型来源。

支持的来源包括：

- ModelScope 仓库
- HuggingFace 仓库
- Git 仓库
- 本地模型目录
- 用户提供的 URL

目标是在环境准备前了解模型结构和部署要求。

---

# 上下文集成

## 从 shared/context.yaml 读取

无（通常是流程中的第一个 Skill）

## 写入 shared/context.yaml

```yaml
model:
  name: <检测到的模型名称>
  source: <modelscope|huggingface|git|local>
  path: <仓库 URL 或本地路径>
  readme_found: <true|false>
runtime:
  framework: <vllm|sglang|transformers|tgi>
```

---

# 工作流程

## 步骤 1 — 识别模型来源

用户应提供以下之一：

- 模型仓库 URL
- 本地模型目录
- 模型下载命令

确定：

- 来源平台
- 仓库位置
- 模型名称

结果反馈：

- 模型名称
- 仓库来源
- 仓库 URL

---

## 步骤 2 — 查找 README 或部署指南

搜索：

README.md
部署文档
使用说明

如果存在 README，提取：

- 模型下载命令
- Docker 镜像来源
- Docker run 命令
- 推理启动命令

结果反馈：

- 是否检测到 README
- 可用的部署说明

---

## 步骤 3 — 检查模型目录

检查关键文件如：

config.json
tokenizer.json
model.safetensors
pytorch_model.bin

确定模型格式。

结果反馈：

- 模型文件结构
- 权重格式

---

## 步骤 4 — 检测支持的运行时

确定兼容的框架。

典型框架：

- vLLM
- SGLang
- Transformers
- TGI

判断依据：

- 是否存在 vLLM 说明
- 是否存在 SGLang 说明
- Tokenizer 配置

结果反馈：

- 推荐的运行时框架
- 备选运行时选项

---

# 完成条件

模型检查完成的标志：

- 模型来源已识别
- README 状态已知
- 运行时框架已确定

下一步应执行 **flagos-environment-preparation**。
