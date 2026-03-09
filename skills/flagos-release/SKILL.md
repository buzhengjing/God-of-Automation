---
name: flagos-release
description: 打包并发布 FlagOS Docker 镜像和模型到仓库（Harbor、HuggingFace、ModelScope）
version: 1.0.0
license: internal
triggers:
  - release
  - image upload
  - package image
  - model release
  - upload model
  - 发布
  - 镜像上传
  - 模型发布
depends_on:
  - flagos-performance-testing
next_skill: null
provides:
  - image.registry_url
  - image.upload_timestamp
  - release.huggingface_url
  - release.modelscope_url
---

# 发布 Skill

此 Skill 打包并发布 FlagOS 产物：

- **Docker 镜像** → Harbor 仓库
- **模型文件** → HuggingFace 和 ModelScope

用户可以选择仅发布镜像、仅发布模型或两者都发布。

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 environment-preparation>
model:
  name: <来自 model-introspection>
  local_path: <来自 environment-preparation>
service:
  healthy: <来自 service-startup>
runtime:
  flaggems_enabled: <来自 service-startup>
```

## 写入 shared/context.yaml

```yaml
image:
  registry_url: <推送镜像的 Harbor URL>
  upload_timestamp: <YYMMDDHHMM>
release:
  huggingface_url: <HuggingFace 模型 URL>
  modelscope_url: <ModelScope 模型 URL>
```

---

# 工作流程选项

询问用户要执行哪种发布类型：

1. **仅镜像** — 打包并推送 Docker 镜像到 Harbor
2. **仅模型** — 上传模型到 HuggingFace 和 ModelScope
3. **完整发布** — 镜像和模型都发布

---

# 部分 A — Docker 镜像发布

## 步骤 A1 — 收集环境信息

收集镜像命名所需的软件和硬件版本。

命令：

```bash
# FlagOS 软件包
pip show flagtree flaggems flagscale flagcx

# Python 和 PyTorch
python -V
python -c "import torch;print(torch.__version__)"

# CUDA 和驱动
nvcc -V
nvidia-smi
```

结果反馈：

- 环境版本表

---

## 步骤 A2 — 构建 Docker 镜像

将运行中的容器提交为 Docker 镜像。

```bash
docker commit <container_name> flagos:<timestamp>
```

结果反馈：

- 本地 Docker 镜像已创建

---

## 步骤 A3 — 标记并推送镜像

镜像命名格式：

```
harbor.baai.ac.cn/flagrelease-public/flagrelease-<vendor>-release-model_<model_name>-tree_<ver>-gems_<ver>-scale_<ver>-cx_<ver>-python_<ver>-torch_<ver>-pcp_<cuda>-gpu_<gpu>-arc_<arch>-driver_<driver>:<tag>
```

规则：

- 模型名称必须小写
- 如果版本包含 "+"，替换为 "-"
- tag = 上传时间戳（YYMMDDHHMM）

命令：

```bash
docker tag flagos:<timestamp> <full_image_name>
docker login harbor.baai.ac.cn
docker push <full_image_name>
```

结果反馈：

- 已发布镜像 URL

---

# 部分 B — 模型发布

## 步骤 B1 — 准备 README

上传前填写 README 模板。

所需信息：

- 模型名称
- 基准测试结果
- Docker 镜像 URL
- 启动命令
- 环境版本

---

## 步骤 B2 — 上传到 HuggingFace

```bash
hf auth login
hf upload FlagRelease/<model-name> /data/<model-dir> --repo-type model
```

结果反馈：

- HuggingFace 模型 URL

---

## 步骤 B3 — 上传到 ModelScope

```bash
modelscope upload FlagRelease/<model-name> /data/<model-dir> --token <token>
```

结果反馈：

- ModelScope 模型 URL

---

# 完成条件

发布成功的标志：

**镜像发布：**
- 环境信息已收集
- Docker 镜像已提交
- 镜像已标记并推送到 Harbor

**模型发布：**
- README 已准备
- 模型已上传到 HuggingFace
- 模型已上传到 ModelScope
