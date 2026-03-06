---
name: flagos-environment-preparation
description: 准备 FlagOS 推理环境，包括模型下载、Docker 镜像准备和容器创建
version: 1.0.0
license: internal
triggers:
  - environment preparation
  - prepare environment
  - 环境准备
depends_on:
  - flagos-model-introspection
provides:
  - container.name
  - container.status
  - image.name
  - image.tag
  - model.local_path
---

# 环境准备 Skill

此 Skill 准备模型部署所需的运行时环境。

不启动推理服务。

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
model:
  name: <来自 model-introspection>
  source: <来自 model-introspection>
  readme_found: <来自 model-introspection>
runtime:
  framework: <来自 model-introspection>
```

## 写入 shared/context.yaml

```yaml
container:
  name: <创建的容器名称>
  status: <running|stopped>
image:
  name: <Docker 镜像名称>
  tag: <Docker 镜像标签>
model:
  local_path: <模型存储的主机路径>
```

---

# 部署优先级

始终遵循以下顺序：

1. README 说明
2. 官方仓库说明
3. 用户提供的说明
4. 手动部署

---

# 工作流程

## 步骤 1 — 确认部署说明

检查上一步是否发现了 README。

如果存在 README：

使用提供的命令。

如果不存在 README：

向用户请求：

- 模型下载方式
- Docker 镜像来源
- 容器配置

结果反馈：

- 部署方式
- Docker 镜像来源
- 模型路径

---

## 步骤 2 — 验证主机环境

检查 GPU：

nvidia-smi

检查 Docker：

docker --version

检查 ModelScope：

modelscope --version

如果缺失则安装：

pip install modelscope

结果反馈：

- GPU 状态
- Docker 版本
- ModelScope 状态

---

## 步骤 3 — 下载模型

首选方式：

使用 README 下载命令。

否则使用 ModelScope 或用户提供的 URL。

示例：

modelscope download \
--model <model_repo> \
--local_dir <model_directory>

验证文件是否存在。

结果反馈：

- 模型路径
- 下载状态

---

## 步骤 4 — 拉取 Docker 镜像

如果 README 指定了镜像：

docker pull <image>

否则使用用户提供的镜像。

验证镜像：

docker images

结果反馈：

- 镜像名称
- 镜像标签

---

## 步骤 5 — 创建容器

如果 README 提供了 docker run 命令：

使用该命令。

否则构造容器启动命令：

docker run -it --gpus all \
--name <container_name> \
--shm-size 32g \
-v <host_model_path>:<container_model_path> \
<image> \
/bin/bash

验证容器：

docker ps

结果反馈：

- 容器名称
- 容器状态

---

# 完成条件

环境准备成功的标志：

- 模型已下载
- Docker 镜像已拉取
- 容器正在运行
