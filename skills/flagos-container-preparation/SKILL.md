---
name: flagos-container-preparation
description: 多入口容器准备，支持已有容器/已有镜像/README 解析三种入口，自动识别用户输入类型
version: 3.0.0
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

此 Skill 支持三种入口场景，自动识别用户输入类型，减少人机交互。

支持多厂商 GPU：NVIDIA、华为、海光、摩尔线程、昆仑芯、天数、沐曦、清微智能、寒武纪、平头哥。

---

# 统一工作目录

**核心设计**：所有操作在 `/flagos-workspace` 目录下进行，该目录挂载到宿主机，实现日志和结果的实时访问。

## 目录映射

```
宿主机: /data/flagos-workspace/<model_name>/
                      ↓ 挂载
容器内: /flagos-workspace/
```

## 目录结构

```
/flagos-workspace/
├── scripts/                   # 自动化脚本
│   ├── benchmark_runner.py
│   ├── performance_compare.py
│   └── operator_optimizer.py
├── logs/                      # 操作日志
├── results/                   # 性能数据
│   ├── native_performance.json
│   ├── flagos_initial.json
│   ├── flagos_optimized.json
│   ├── operator_config.json
│   ├── performance_compare.csv
│   ├── flagos_before_upgrade.json   # Scenario B only
│   └── flagos_after_upgrade.json    # Scenario B only
├── reports/                   # 报告
│   ├── env_report.md
│   ├── flag_gems_detection.md
│   └── final_report.md
├── output/                    # 服务日志
├── eval/                      # 评测结果
├── perf/                      # 兼容旧性能测试
└── shared/
    └── context.yaml
```

---

# 上下文集成

## 读取

无（流程起点）。用户提供以下任意一种输入：

| 入口 | 用户提供什么 | 系统做什么 |
|------|-------------|-----------|
| **已有容器** | 容器名称（或容器 ID） | 跳过创建，直接验证容器状态、GPU、挂载目录 |
| **已有镜像** | 镜像地址 + 模型名 + 模型路径 | docker run 创建容器 |
| **README 链接** | ModelScope/HuggingFace URL | WebFetch 解析 → 提取镜像/命令 → docker pull → docker run |

## 写入 shared/context.yaml

```yaml
entry:
  type: "<existing_container|new_container|readme_parse>"
  source: "<用户原始输入>"

model:
  name: "<模型名称>"
  url: "<用户提供的模型 URL>"
  local_path: "<模型在主机上的路径>"
  container_path: "<模型在容器内的路径>"

container:
  name: "<容器名称>"
  status: "running"

image:
  name: "<Docker 镜像名称>"
  tag: "<Docker 镜像标签>"

workspace:
  host_path: "/data/flagos-workspace/<model_name>"
  container_path: "/flagos-workspace"

gpu:
  vendor: "<nvidia|huawei|hygon|mthreads|kunlunxin|tianshu|metax|tsingmicro|cambricon|alibaba>"
  type: "<GPU 型号>"
  count: <GPU 数量>
  visible_devices_env: "<环境变量名>"

metadata:
  updated_by: "flagos-container-preparation"
  updated_at: "<timestamp>"
```

---

# 工作流程

## 步骤 0 — 自动识别入口类型

根据用户输入自动判断入口类型（减少交互）：

```
用户输入
  │
  ├── 输入看起来像容器名/ID → 自动尝试 docker inspect
  │   ├── 容器存在且运行中 → 入口1：已有容器
  │   ├── 容器存在但停止 → 自动 docker start → 入口1
  │   └── 不存在 → 提示用户确认
  │
  ├── 输入看起来像镜像地址 (含 registry/tag) → 入口2：已有镜像
  │   └── 自动询问模型名和路径（仅这两项）
  │
  └── 输入看起来像 URL (http/https) → 入口3：README 解析
      └── 自动 WebFetch → 提取所有信息 → 确认后执行
```

**判断规则**：
- 包含 `http://` 或 `https://` → URL
- 包含 `/` 和 `:` 且像 registry 地址（如 `harbor.xxx/path:tag`）→ 镜像
- 其他字符串 → 尝试作为容器名

---

## 入口 1 — 已有容器（新增）

### 步骤 1.1 — 验证容器状态

```bash
# 验证容器存在和状态
docker inspect <container_name> --format '{{.State.Status}}'

# 如果停止则启动
docker start <container_name>
```

### 步骤 1.2 — 自动检测 GPU（在容器内）

```bash
docker exec <container_name> bash -c "
  for cmd in nvidia-smi npu-smi hy-smi mthreads-gmi xpu-smi ixsmi mx-smi tsm_smi cnmon; do
    if command -v \$cmd &>/dev/null; then echo GPU_CMD=\$cmd; \$cmd; break; fi
  done
"
```

### 步骤 1.3 — 自动检测模型路径（常见挂载点扫描）

```bash
docker exec <container_name> bash -c "
  for dir in /data/models /models /workspace/models /mnt/models /flagos-workspace; do
    if [ -d \"\$dir\" ]; then echo \"FOUND: \$dir\"; ls \$dir 2>/dev/null; fi
  done
"
```

### 步骤 1.4 — 检测/创建工作目录

```bash
docker exec <container_name> bash -c "
  mkdir -p /flagos-workspace/{scripts,logs,results,reports,eval,shared,output,perf}
"
```

**关键**：已有容器可能没有 `/flagos-workspace` 挂载。如果没有：
- 在容器内直接创建 `/flagos-workspace` 目录（数据不会映射到宿主机，但流程能跑）
- 提醒用户如需宿主机访问，建议重建容器时加挂载

### 步骤 1.5 — 推导模型信息

从容器环境推导模型名和路径：
- 检查运行中的服务进程命令行参数
- 扫描常见模型目录
- 必要时询问用户确认

---

## 入口 2 — 已有镜像（现有流程优化）

### 步骤 2.1 — 接收用户输入

仅需要以下信息（自动检测的不问）：
- **镜像地址**：用户已提供
- **模型名**：询问用户
- **模型路径**：询问用户（宿主机路径）

### 步骤 2.2 — 自动检测 GPU 厂商（宿主机）

```bash
detect_gpu() {
    if command -v nvidia-smi &> /dev/null && nvidia-smi &> /dev/null; then
        echo "nvidia"
    elif command -v npu-smi &> /dev/null && npu-smi info &> /dev/null; then
        echo "huawei"
    elif command -v hy-smi &> /dev/null && hy-smi &> /dev/null; then
        echo "hygon"
    elif command -v mthreads-gmi &> /dev/null && mthreads-gmi &> /dev/null; then
        echo "mthreads"
    elif command -v xpu-smi &> /dev/null && xpu-smi &> /dev/null; then
        echo "kunlunxin"
    elif command -v ixsmi &> /dev/null && ixsmi &> /dev/null; then
        echo "tianshu"
    elif command -v mx-smi &> /dev/null && mx-smi &> /dev/null; then
        echo "metax"
    elif command -v tsm_smi &> /dev/null; then
        echo "tsingmicro"
    elif command -v cnmon &> /dev/null && cnmon &> /dev/null; then
        echo "cambricon"
    else
        echo "unknown"
    fi
}
```

### GPU 检测命令表

| 厂商 | 检测命令 | 可见设备环境变量 |
|------|----------|------------------|
| NVIDIA | `nvidia-smi` | `CUDA_VISIBLE_DEVICES` |
| 华为 (Ascend) | `npu-smi info` | `ASCEND_RT_VISIBLE_DEVICES` |
| 海光 (Hygon) | `hy-smi` | `HIP_VISIBLE_DEVICES` |
| 摩尔线程 | `mthreads-gmi` | `MUSA_VISIBLE_DEVICES` |
| 昆仑芯 | `xpu-smi` | `XPU_VISIBLE_DEVICES` |
| 天数 | `ixsmi` | `CUDA_VISIBLE_DEVICES` |
| 沐曦 | `mx-smi` | `CUDA_VISIBLE_DEVICES` |
| 清微智能 | `tsm_smi` | `TXDA_VISIBLE_DEVICES` |
| 寒武纪 | `cnmon` | `MLU_VISIBLE_DEVICES` |
| 平头哥 | - | `CUDA_VISIBLE_DEVICES` |

### 步骤 2.3 — 验证主机基础环境

```bash
docker --version
df -h /data
free -h
```

### 步骤 2.4 — 创建宿主机工作目录

```bash
WORKSPACE_HOST="/data/flagos-workspace/<model_name>"
mkdir -p ${WORKSPACE_HOST}/{scripts,logs,results,reports,eval,perf,shared}
```

### 步骤 2.5 — 生成并执行 docker run 命令

自动生成容器名：`<model_name>_flagos`

**NVIDIA：**
```bash
docker run -itd \
  --gpus all \
  --name <container_name> \
  --shm-size 32g \
  --ulimit memlock=-1 \
  -v <host_model_path>:<container_model_path> \
  -v /data/flagos-workspace/<model_name>:/flagos-workspace \
  -p 8000:8000 \
  <image> \
  /bin/bash
```

**华为 Ascend：**
```bash
docker run -itd \
  --device=/dev/davinci0 \
  --device=/dev/davinci_manager \
  --device=/dev/devmm_svm \
  --device=/dev/hisi_hdc \
  --name <container_name> \
  --shm-size 32g \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v <host_model_path>:<container_model_path> \
  -v /data/flagos-workspace/<model_name>:/flagos-workspace \
  -p 8000:8000 \
  <image> \
  /bin/bash
```

**其他厂商（通用模板）：**
```bash
docker run -itd \
  --privileged \
  --name <container_name> \
  --shm-size 32g \
  --ulimit memlock=-1 \
  -v <host_model_path>:<container_model_path> \
  -v /data/flagos-workspace/<model_name>:/flagos-workspace \
  -p 8000:8000 \
  <image> \
  /bin/bash
```

**向用户展示生成的命令，确认后执行。**（唯一需要人工确认的步骤）

### 步骤 2.6 — 验证容器状态

```bash
docker ps | grep <container_name>
docker exec <container_name> <gpu_check_command>
docker exec <container_name> ls -la <container_model_path>
docker exec <container_name> ls -la /flagos-workspace
```

---

## 入口 3 — README 解析（主要用于 Scenario B）

### 步骤 3.1 — WebFetch 解析 URL

```
使用 WebFetch 获取 URL 内容，提取：
- Docker 镜像地址
- 启动命令
- 模型名称
- 依赖信息
```

### 步骤 3.2 — docker pull

```bash
docker pull <extracted_image>
```

### 步骤 3.3 — 按入口 2 的流程创建容器

使用从 README 提取的信息，执行入口 2 的步骤 2.3 ~ 2.6。

**失败时才交互**：README 解析失败或信息不全时，再询问用户补充。

---

## 步骤 7 — 写入 context.yaml

将所有检测和创建结果写入 `shared/context.yaml`，包括新增的 `entry` 字段。

---

# 完成条件

容器准备成功的标志：

- 入口类型已自动识别并记录
- GPU 厂商已识别
- Docker 容器已运行（新建或已有）
- 容器内 GPU 可见
- 模型目录已确认
- **工作目录 `/flagos-workspace` 可用**（挂载或容器内创建）
- context.yaml 已更新（含 entry 字段）

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| GPU 未检测到 | 检查驱动安装，确认设备存在 |
| 镜像拉取失败 | 检查网络，或使用 `docker load` 导入本地镜像 |
| 容器启动失败 | 检查 GPU 驱动兼容性，查看 `docker logs` |
| 模型目录为空 | 确认挂载路径正确，检查权限 |
| 容器内 GPU 不可见 | NVIDIA 检查 `--gpus all`；其他厂商检查设备挂载 |
| 已有容器无 /flagos-workspace | 在容器内创建目录，提醒用户数据不映射到宿主机 |
| docker inspect 失败 | 容器名/ID 不正确，提示用户确认 |
| README 解析失败 | 要求用户手动提供镜像地址和模型信息 |

下一步应执行 **flagos-pre-service-inspection**。
