---
name: flagos-model-discovery
description: 发现并解析模型部署配置，提取镜像、启动命令、框架等信息
version: 1.0.0
license: internal
triggers:
  - model discovery
  - discover model
  - 模型发现
  - 部署配置
depends_on: []
next_skill: flagos-environment-preparation
provides:
  - model.name
  - model.source
  - model.readme_found
  - deployment.image
  - deployment.docker_run
  - deployment.startup_command
  - deployment.model_download
  - runtime.framework
---

# 模型发现 Skill

从模型仓库获取部署配置，为后续环境准备和服务启动提供必要信息。

## 快速参考

| 输入 | 输出 |
|------|------|
| 模型仓库 URL 或本地 README 路径 | Docker 镜像、启动命令、运行框架 |

**支持的来源：** ModelScope、HuggingFace、Git、本地文件

---

# 上下文集成

## 读取

无（流程起点）

## 写入 shared/context.yaml

```yaml
model:
  name: <模型名称>
  source: <modelscope|huggingface|git|local>
  readme_found: <true|false>

deployment:
  image: <Docker 镜像地址>
  docker_run: <docker run 命令>
  startup_command: <服务启动命令>
  model_download: <模型下载命令>

runtime:
  framework: <flagscale|vllm|sglang>

metadata:
  created_by: "flagos-model-discovery"
  updated_at: <ISO 时间戳>
```

---

# 解析规则

## 信息提取模式

| 提取项 | 匹配模式 |
|--------|----------|
| Docker 镜像 | `docker pull <image>`、`镜像地址：<image>`、Harbor/DockerHub URL |
| Docker Run | `docker run ...` (含 `--gpus`、`-v`、`--shm-size` 等参数) |
| 启动命令 | `flagscale serve ...`、`vllm serve ...`、`python -m sglang.launch_server ...` |
| 模型下载 | `modelscope download ...`、`huggingface-cli download ...`、`git lfs clone ...` |

## 框架识别

按优先级顺序判断：

| 优先级 | 特征 | 框架 |
|--------|------|------|
| 1 | 命令含 `flagscale serve` 或镜像含 `flagscale` | FlagScale |
| 2 | 命令含 `vllm serve` 或镜像含 `vllm` | vLLM |
| 3 | 命令含 `sglang.launch_server` 或镜像含 `sglang` | SGLang |

> **注意：** FlagScale 是 FlagOS 推荐的统一推理框架，底层可集成 vLLM/SGLang。

---

# 工作流程

## 步骤 1 — 获取模型来源

询问用户提供以下任一输入：

```
# ModelScope
https://modelscope.cn/models/FlagRelease/Qwen2.5-7B-Instruct

# HuggingFace
https://huggingface.co/FlagRelease/Qwen2.5-7B-Instruct

# 本地文件
/data/models/Qwen2.5-7B-Instruct/README.md
```

## 步骤 2 — 获取 README

根据来源类型执行：

| 来源 | 获取方式 |
|------|----------|
| ModelScope | `curl -s "https://modelscope.cn/api/v1/models/<model_id>/readme"` |
| HuggingFace | `curl -s "https://huggingface.co/<model_id>/raw/main/README.md"` |
| 本地 | 直接读取文件 |

## 步骤 3 — 解析部署配置

按"解析规则"章节提取：
- Docker 镜像
- Docker Run 命令
- 服务启动命令
- 模型下载命令
- 运行框架

## 步骤 4 — 用户确认

展示提取结果，允许用户修改或补充：

```yaml
模型名称: Qwen2.5-7B-Instruct
来源: ModelScope
Docker 镜像: harbor.baai.ac.cn/flagrelease-public/...
Docker Run: docker run -it --gpus all ...
启动命令: flagscale serve /data/model --served-model-name qwen2.5
框架: FlagScale
```

## 步骤 5 — 写入 context.yaml

用户确认后写入 `shared/context.yaml`。

---

# 完成条件

- [ ] README 已获取（或确认不存在）
- [ ] Docker 镜像地址已确定
- [ ] 服务启动命令已确定
- [ ] 运行框架已识别
- [ ] context.yaml 已更新

---

# 异常处理

| 场景 | 处理方式 |
|------|----------|
| README 不存在 | 询问用户手动提供配置信息 |
| Docker 镜像缺失 | 询问用户提供，或使用默认 FlagOS 镜像 |
| 启动命令缺失 | 标记为空，由 `flagos-service-startup` 根据框架自动生成 |
| 模型下载命令缺失 | 跳过（模型可能已在服务器上） |
| 无法识别框架 | 询问用户选择 FlagScale/vLLM/SGLang |

---

**下一步：** `flagos-environment-preparation`
