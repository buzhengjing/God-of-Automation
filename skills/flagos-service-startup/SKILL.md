---
name: flagos-service-startup
description: 启动模型推理服务，验证运行时环境，并验证服务健康状态
version: 1.0.0
license: internal
triggers:
  - service startup
  - start service
  - 启动服务
  - health check
  - 健康检查
depends_on:
  - flagos-environment-preparation
provides:
  - service.host
  - service.port
  - service.process_id
  - service.healthy
  - service.model_id
  - runtime.gpu_count
  - runtime.flaggems_enabled
---

# 服务启动 Skill

此 Skill 在运行的容器内启动推理服务，验证运行时环境，并验证服务健康状态。

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 environment-preparation>
model:
  name: <来自 model-introspection>
  local_path: <来自 environment-preparation>
runtime:
  framework: <来自 model-introspection>
```

## 写入 shared/context.yaml

```yaml
service:
  host: <服务主机，通常为 localhost>
  port: <服务端口，通常为 8000>
  process_id: <运行中服务的 PID>
  healthy: <true|false>
  model_id: <API 响应中的模型标识符>
runtime:
  gpu_count: <可见 GPU 数量>
  flaggems_enabled: <true|false>
```

---

# 工作流程

## 步骤 1 — 进入容器

docker exec -it <container_name> /bin/bash

结果反馈：

- 成功进入容器

---

## 步骤 2 — 检查 GPU

nvidia-smi

结果反馈：

- GPU 可见性
- GPU 数量

---

## 步骤 3 — 检查运行时环境

检查软件包：

pip list

重要软件包：

- torch
- vllm
- sglang
- flaggems

结果反馈：

- 软件包版本

---

## 步骤 4 — 检测 FlagGems 集成

定位框架路径。

示例：

pip show vllm

查找安装目录。

搜索 gems：

grep gems -rn ./

确定是否存在 FlagGems 支持。

不要修改代码。

结果反馈：

- 检测到的框架
- FlagGems 集成状态

---

## 步骤 5 — 确定启动命令

如果 README 提供了启动命令：

向用户展示命令。

询问用户：

"是否使用 README 中的启动命令？"

可能的结果：

1. 使用 README 命令
2. 用户提供自定义命令
3. 无可用命令

---

## 步骤 6 — 生成启动命令（如需要）

如果没有启动命令，则根据框架生成。

vLLM 示例：

vllm serve <model_path> \
--served-model-name <model_name>

SGLang 示例：

python -m sglang.launch_server \
--model-path <model_path>

向用户展示生成的命令。

允许用户：

- 批准
- 修改
- 替换

仅在用户确认后执行命令。

结果反馈：

- 最终启动命令
- 进程状态

---

## 步骤 7 — 检查进程

ps -ef | grep vllm

结果反馈：

- 进程 ID
- 进程状态

---

## 步骤 8 — 查询模型 API

从 shared/context.yaml 读取 `service.host` 和 `service.port`，然后：

curl http://${service.host}:${service.port}/v1/models

结果反馈：

- API 响应
- 模型标识符

---

## 步骤 9 — 运行推理测试

从 shared/context.yaml 读取 `model.name`，然后：

curl http://${service.host}:${service.port}/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
"model":"${model.name}",
"messages":[{"role":"user","content":"hello"}]
}'

结果反馈：

- 推理结果
- 延迟

---

# 完成条件

服务启动成功的标志：

- 已进入容器
- GPU 可见
- 运行时环境已验证
- 服务进程正在运行
- API 可访问
- 模型已列出
- 推理结果已返回
