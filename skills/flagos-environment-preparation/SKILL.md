---
name: flagos-environment-preparation
description: 准备 FlagOS 推理环境，包括模型下载、Docker 镜像准备和容器创建
version: 1.0.0
triggers:
  - 环境准备
  - 下载模型
  - 拉取镜像
  - 启动容器
  - environment preparation
dependencies:
  - flagos-model-introspection
next_skill: flagos-service-startup-environment-check
---

# FlagOS 环境准备 Skill

准备模型部署所需的运行时环境，不启动推理服务。

---

## 部署优先级

始终按此顺序：

1. README 说明
2. 官方仓库说明
3. 用户提供的说明
4. 手动部署

---

## 工作流程

### 步骤 1：确认部署说明

检查上一步是否发现了 README。

**如果 README 存在**：

使用提供的命令。

**如果 README 不存在**：

向用户请求：

- 模型下载方式
- Docker 镜像来源
- 容器配置

**结果反馈**：

- 部署方式
- Docker 镜像来源
- 模型路径

---

### 步骤 2：验证主机环境

**检查 GPU**：

```bash
nvidia-smi
```

**检查 Docker**：

```bash
docker --version
```

**检查 ModelScope**：

```bash
modelscope --version
```

如果缺失则安装：

```bash
pip install modelscope
```

**结果反馈**：

- GPU 状态
- Docker 版本
- ModelScope 状态

---

### 步骤 3：下载模型

**首选方式**：

使用 README 下载命令。

否则使用 ModelScope 或用户提供的 URL。

**示例**：

```bash
modelscope download \
  --model <model_repo> \
  --local_dir <model_directory>
```

验证文件是否存在。

**结果反馈**：

- 模型路径
- 下载状态

---

### 步骤 4：拉取 Docker 镜像

**如果 README 指定了镜像**：

```bash
docker pull <image>
```

否则使用用户提供的镜像。

**验证镜像**：

```bash
docker images
```

**结果反馈**：

- 镜像名称
- 镜像标签

---

### 步骤 5：创建容器

**如果 README 提供了 docker run 命令**：

使用该命令。

**否则构建容器启动命令**：

```bash
docker run -it --gpus all \
  --name <container_name> \
  --shm-size 32g \
  -v <host_model_path>:<container_model_path> \
  <image> \
  /bin/bash
```

**验证容器**：

```bash
docker ps
```

**结果反馈**：

- 容器名称
- 容器状态

---

## 完成标准

环境准备成功的条件：

- 模型已下载
- Docker 镜像已拉取
- 容器正在运行
