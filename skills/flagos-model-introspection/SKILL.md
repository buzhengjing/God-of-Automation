---
name: flagos-model-introspection
description: 检查模型仓库的 README 获取部署说明，包括镜像、启动命令等信息
version: 1.0.0
license: internal
triggers:
  - model introspection
  - inspect model
  - 模型检查
  - 检查部署说明
depends_on: []
provides:
  - model.name
  - model.source
  - model.readme_found
  - deployment.image
  - deployment.docker_run
  - deployment.startup_command
  - runtime.framework
---

# 模型检查 Skill

此 Skill 从模型仓库的 README 中提取部署说明，为后续环境准备和服务启动提供必要信息。

---

# 上下文集成

## 从 shared/context.yaml 读取

无（流程中的第一个 Skill）

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
  framework: <vllm|sglang>
```

---

# 工作流程

## 步骤 1 — 获取模型来源

询问用户模型来源：

- ModelScope 仓库 URL
- HuggingFace 仓库 URL
- Git 仓库 URL
- 本地已有 README 文件路径

示例输入：

```
https://modelscope.cn/models/FlagRelease/Qwen2.5-7B-Instruct
https://huggingface.co/FlagRelease/Qwen2.5-7B-Instruct
/data/models/Qwen2.5-7B-Instruct/README.md
```

结果反馈：

- 模型名称
- 来源平台

---

## 步骤 2 — 获取 README 内容

根据来源获取 README：

**ModelScope：**
```bash
# 使用 API 或浏览器获取
curl -s "https://modelscope.cn/api/v1/models/<model_id>/readme"
```

**HuggingFace：**
```bash
curl -s "https://huggingface.co/<model_id>/raw/main/README.md"
```

**本地文件：**
```bash
cat /path/to/README.md
```

结果反馈：

- README 是否存在
- README 内容预览

---

## 步骤 3 — 提取部署信息

从 README 中提取关键部署信息：

### 3.1 Docker 镜像

查找模式：
- `docker pull <image>`
- `镜像地址：<image>`
- Harbor/DockerHub 地址

### 3.2 Docker Run 命令

查找模式：
- `docker run ...`
- 包含 `--gpus`、`-v`、`--shm-size` 等参数的命令

### 3.3 服务启动命令

查找模式：
- `vllm serve ...`
- `python -m vllm.entrypoints...`
- `python -m sglang.launch_server ...`

### 3.4 模型下载命令

查找模式：
- `modelscope download ...`
- `huggingface-cli download ...`
- `git lfs clone ...`

结果反馈：

- 提取到的各项命令
- 未找到的项目（需用户补充）

---

## 步骤 4 — 确定运行时框架

根据 README 内容判断推荐的框架：

判断依据：

| 特征 | 框架 |
|------|------|
| 包含 `vllm serve` 命令 | vLLM |
| 包含 `sglang.launch_server` | SGLang |
| 镜像名包含 `vllm` | vLLM |
| 镜像名包含 `sglang` | SGLang |

结果反馈：

- 推荐框架
- 判断依据

---

## 步骤 5 — 确认并补充信息

向用户展示提取的信息，询问是否需要修改或补充：

```yaml
模型名称: Qwen2.5-7B-Instruct
来源: ModelScope
Docker 镜像: harbor.baai.ac.cn/flagrelease-public/...
Docker Run: docker run -it --gpus all ...
启动命令: vllm serve /data/model --served-model-name qwen2.5
框架: vLLM
```

用户可以：

- 确认无误
- 修改某项
- 补充缺失项

---

## 步骤 6 — 写入 context.yaml

将确认后的信息写入 `shared/context.yaml`：

```bash
# 示例写入
cat > shared/context.yaml << 'EOF'
model:
  name: "Qwen2.5-7B-Instruct"
  source: "modelscope"
  readme_found: true

deployment:
  image: "harbor.baai.ac.cn/flagrelease-public/..."
  docker_run: "docker run -it --gpus all ..."
  startup_command: "vllm serve /data/model ..."
  model_download: "modelscope download ..."

runtime:
  framework: "vllm"

metadata:
  created_by: "flagos-model-introspection"
  updated_at: "2026-03-06T12:00:00"
EOF
```

---

# 完成条件

模型检查完成的标志：

- README 已获取（或确认不存在）
- Docker 镜像地址已确定
- 服务启动命令已确定
- 运行时框架已确定
- context.yaml 已更新

---

# 缺失信息处理

如果 README 中缺少某些信息：

| 缺失项 | 处理方式 |
|--------|----------|
| Docker 镜像 | 询问用户提供，或使用默认 FlagOS 镜像 |
| 启动命令 | 由 service-startup skill 根据框架自动生成 |
| 模型下载命令 | 如模型已在服务器上则跳过 |

下一步应执行 **flagos-environment-preparation**。
