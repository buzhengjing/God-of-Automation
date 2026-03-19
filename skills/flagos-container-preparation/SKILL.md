---
name: flagos-container-preparation
description: 多入口容器准备，支持已有容器/已有镜像/README 解析，通过 setup_workspace.sh 一次性部署所有工具
version: 4.0.0
license: internal
triggers:
  - container preparation
  - prepare container
  - 容器准备
  - 环境准备
depends_on: []
next_skill: flagos-pre-service-inspection
provides:
  - container.name
  - container.status
  - image.name
  - image.tag
  - model.name
  - model.url
  - model.local_path
  - gpu.vendor
  - gpu.count
  - workspace.host_path
  - workspace.container_path
  - entry.type
  - entry.source
---

# 容器准备 Skill（多入口）

支持三种入口场景，自动识别用户输入类型。容器就绪后，通过 `setup_workspace.sh` 一次性部署所有工具脚本。

**工具脚本**:
- `skills/flagos-container-preparation/tools/check_model_local.py` — 本地权重搜索
- `skills/flagos-container-preparation/tools/setup_workspace.sh` — 一次性部署工具

---

# 上下文集成

## 读取

无（流程起点）。用户提供以下任意一种输入：

| 入口 | 用户提供什么 | 系统做什么 |
|------|-------------|-----------|
| **已有容器** | 容器名称（或容器 ID） | 跳过创建，直接验证 |
| **已有镜像** | 镜像地址 + 模型名 + 模型路径 | docker run 创建容器 |
| **README 链接** | ModelScope/HuggingFace URL | 解析 → docker pull → docker run |

## 写入 shared/context.yaml

```yaml
entry:
  type: "<existing_container|new_container|readme_parse>"
  source: "<用户原始输入>"
model:
  name: "<模型名称>"
  url: "<模型 URL>"
  local_path: "<宿主机路径>"
  container_path: "<容器内路径>"
container:
  name: "<容器名称>"
  status: "running"
image:
  name: "<镜像名称>"
  tag: "<镜像标签>"
workspace:
  host_path: "/data/flagos-workspace/<model_name>"
  container_path: "/flagos-workspace"
gpu:
  vendor: "<nvidia|huawei|...>"
  type: "<GPU 型号>"
  count: <GPU 数量>
  visible_devices_env: "<环境变量名>"
```

---

# 工作流程

## 步骤 0 — 自动识别入口类型

根据用户输入自动判断：
- 包含 `http://` 或 `https://` → URL → 入口 3
- 包含 `/` 和 `:` 且像 registry 地址 → 镜像 → 入口 2
- 其他字符串 → 尝试作为容器名 → 入口 1

## 步骤 0.5 — 本地权重检查（自动执行）

在容器准备之前，先在宿主机搜索模型权重：

```bash
python3 skills/flagos-container-preparation/tools/check_model_local.py \
    --model "<用户输入的模型名或URL>" --output-json
```

- 找到（exit 0）→ 记录 `model.local_path`，后续 docker run 直接挂载此路径
- 未找到（exit 1）→ 继续正常流程（下载或从 README 获取路径信息）

此步骤在宿主机运行，不依赖容器。

## 入口 1 — 已有容器

```bash
docker inspect <container_name> --format '{{.State.Status}}'
docker start <container_name>  # 如果停止
```

自动检测 GPU、模型路径、创建/验证 `/flagos-workspace` 目录。

## 入口 2 — 已有镜像

1. 自动检测 GPU 厂商（nvidia-smi / npu-smi / ...）
2. 创建宿主机工作目录
3. 生成 docker run 命令（**需用户确认**）
4. 验证容器状态

## 入口 3 — README 解析

1. WebFetch 解析 URL / curl 调用 ModelScope API
2. 提取镜像地址、启动命令、模型信息
3. docker pull
4. 按入口 2 流程创建容器

## 步骤 5 — 一次性部署工具脚本

**容器创建/验证完成后，立即执行**：

```bash
bash skills/flagos-container-preparation/tools/setup_workspace.sh $CONTAINER
```

此脚本一次性完成：
1. 创建 `/flagos-workspace` 全部子目录
2. 复制所有工具脚本到容器（inspect_env.py, toggle_flaggems.py, wait_for_service.sh, benchmark_runner.py, performance_compare.py, operator_optimizer.py, operator_search.py, eval_monitor.py）
3. 安装脚本依赖（pyyaml 等）
4. 验证所有脚本可执行

## 步骤 6 — 写入 context.yaml

---

# 完成条件

- 本地权重检查已完成（check_model_local.py）
- 入口类型已自动识别
- GPU 厂商已识别
- 容器已运行
- 容器内 GPU 可见
- 模型目录已确认
- **工具脚本已通过 setup_workspace.sh 一次性部署**
- context.yaml 已更新

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| GPU 未检测到 | 检查驱动安装 |
| 镜像拉取失败 | 检查网络，或 `docker load` 导入 |
| setup_workspace.sh 失败 | 检查 Docker 容器是否运行，手动 docker cp |
| 已有容器无 /flagos-workspace | setup_workspace.sh 自动创建 |
| README 解析失败 | 手动提供镜像地址 |

下一步应执行 **flagos-pre-service-inspection**。
