---
name: flagos-service-startup-environment-check
description: 启动模型推理服务并检查运行时环境，包括 GPU 状态、框架版本和 FlagGems 集成
version: 1.0.0
triggers:
  - 启动服务
  - 部署模型
  - start service
  - deploy model
dependencies:
  - flagos-environment-preparation
next_skill: flagos-service-health-check
---

# FlagOS 服务启动与环境检查 Skill

在运行的容器内启动推理服务并验证运行时环境。

---

## 工作流程

### 步骤 1：进入容器

```bash
docker exec -it <container_name> /bin/bash
```

**结果反馈**：

- 容器进入成功

---

### 步骤 2：检查 GPU

```bash
nvidia-smi
```

**结果反馈**：

- GPU 可见性
- GPU 数量

---

### 步骤 3：检查运行时环境

**检查软件包**：

```bash
pip list
```

**重要软件包**：

- torch
- vllm
- sglang
- flaggems

**结果反馈**：

- 软件包版本

---

### 步骤 4：检测 FlagGems 集成

**查找框架路径**：

```bash
pip show vllm
```

找到安装目录。

**搜索 gems**：

```bash
grep gems -rn ./
```

确定是否存在 FlagGems 支持。

不要修改代码。

**结果反馈**：

- 检测到的框架
- FlagGems 集成状态

---

### 步骤 5：确定启动命令

**如果 README 提供了启动命令**：

向用户展示命令。

询问用户：

"是否使用 README 中的启动命令？"

**可能的结果**：

1. 使用 README 命令
2. 用户提供自定义命令
3. 没有可用命令

---

### 步骤 6：生成启动命令（如果需要）

如果没有启动命令，根据框架生成。

**vLLM 示例**：

```bash
vllm serve <model_path> \
  --served-model-name <model_name>
```

**SGLang 示例**：

```bash
python -m sglang.launch_server \
  --model-path <model_path>
```

向用户展示生成的命令。

允许用户：

- 批准
- 修改
- 替换

仅在用户确认后执行命令。

**结果反馈**：

- 最终启动命令
- 进程状态

---

## 完成标准

服务启动成功的条件：

- 运行时环境已验证
- 启动命令已确定
- 服务进程已启动
