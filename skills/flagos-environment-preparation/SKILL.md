---
name: flagos-environment-preparation
description: 准备 FlagOS 推理环境，包括模型下载（可选）、Docker 镜像拉取和容器创建
version: 1.0.0
license: internal
triggers:
  - environment preparation
  - prepare environment
  - 环境准备
depends_on:
  - flagos-model-discovery
next_skill: flagos-service-startup
provides:
  - container.name
  - container.status
  - image.name
  - image.tag
  - model.local_path
  - gpu.vendor
  - gpu.count
---

# 环境准备 Skill

此 Skill 准备模型部署所需的运行时环境，包括镜像拉取和容器创建。

模型下载为可选步骤，如模型已在服务器上则自动跳过。

支持多厂商 GPU：NVIDIA、华为、海光、摩尔线程、昆仑芯、天数、沐曦、清微智能、寒武纪、平头哥。

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
model:
  name: <来自 model-introspection>
  source: <来自 model-introspection>

deployment:
  image: <来自 model-introspection>
  docker_run: <来自 model-introspection>
  model_download: <来自 model-introspection>

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
  local_path: <模型在主机上的路径>
  container_path: <模型在容器内的路径>

gpu:
  vendor: <nvidia|huawei|hygon|mthreads|kunlunxin|tianshu|metax|tsingmicro|cambricon|alibaba>
  count: <GPU 数量>
  visible_devices_env: <环境变量名>
```

---

# 工作流程

## 步骤 1 — 检测 GPU 厂商和状态

依次尝试各厂商的检测命令，确定 GPU 类型：

### GPU 检测命令表

| 厂商 | 检测命令 | 备注 |
|------|----------|------|
| NVIDIA | `nvidia-smi` | 最常见 |
| 华为 (Ascend) | `npu-smi info` | NPU |
| 海光 (Hygon) | `hy-smi` 或 `hy-smi --showpids` | DCU |
| 摩尔线程 | `mthreads-gmi` | MTT GPU |
| 昆仑芯 | `xpu-smi` | XPU |
| 天数 | `ixsmi` | |
| 沐曦 | `mx-smi` | |
| 清微智能 | `tsm_smi` 或 `source /root/.bash_profile && tsm_smi -t` | 可能需要 source 环境 |
| 寒武纪 | `cnmon` | MLU |

检测脚本示例：

```bash
# 自动检测 GPU 厂商
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

GPU_VENDOR=$(detect_gpu)
echo "检测到 GPU 厂商: $GPU_VENDOR"
```

### 指定卡的环境变量

| 厂商 | 环境变量 |
|------|----------|
| NVIDIA | `CUDA_VISIBLE_DEVICES` |
| 华为 | `ASCEND_RT_VISIBLE_DEVICES` |
| 海光 | `HIP_VISIBLE_DEVICES` |
| 摩尔线程 | `MUSA_VISIBLE_DEVICES` |
| 昆仑芯 | `XPU_VISIBLE_DEVICES` |
| 天数 | `CUDA_VISIBLE_DEVICES` |
| 沐曦 | `CUDA_VISIBLE_DEVICES` |
| 清微智能 | `TXDA_VISIBLE_DEVICES` |
| 寒武纪 | `MLU_VISIBLE_DEVICES` |
| 平头哥 | `CUDA_VISIBLE_DEVICES` |

结果反馈：

- GPU 厂商
- GPU 型号
- GPU 数量
- 显存大小

---

## 步骤 2 — 验证主机基础环境

```bash
# 检查 Docker
docker --version

# 检查磁盘空间
df -h /data

# 检查内存
free -h
```

结果反馈：

- Docker 版本
- 可用磁盘空间
- 可用内存

如果环境检查失败，提示用户解决后再继续。

---

## 步骤 3 — 检查模型是否已存在（可跳过下载）

询问用户模型路径或检查常用位置：

```bash
# 检查常用模型目录
ls -la /data/models/
ls -la /root/models/
ls -la ~/models/
```

询问用户：

"请提供模型在服务器上的路径，或输入 'download' 执行下载"

**如果模型已存在：**

验证模型文件完整性：

```bash
ls -la <model_path>/
# 应包含: config.json, tokenizer.json, *.safetensors 等
```

记录模型路径，跳过下载步骤。

**如果需要下载：**

继续步骤 4。

---

## 步骤 4 — 下载模型（可选）

使用 context.yaml 中的 `deployment.model_download` 命令，或根据来源生成：

**ModelScope：**
```bash
modelscope download \
  --model <model_repo> \
  --local_dir <model_directory>
```

**HuggingFace：**
```bash
huggingface-cli download <model_repo> \
  --local-dir <model_directory>
```

验证下载：

```bash
ls -la <model_directory>/
du -sh <model_directory>/
```

结果反馈：

- 下载状态
- 模型大小
- 文件列表

---

## 步骤 5 — 拉取 Docker 镜像

使用 context.yaml 中的 `deployment.image`：

```bash
docker pull <image>
```

验证镜像：

```bash
docker images | grep -i <image_name>
```

**如果镜像已存在：**

```bash
# 检查本地镜像
docker images | grep <image_name>
```

询问用户是否使用现有镜像或重新拉取。

结果反馈：

- 镜像名称
- 镜像大小
- 镜像 ID

---

## 步骤 6 — 创建并启动容器

### 6.1 使用 README 中的 docker run 命令

如果 context.yaml 中有 `deployment.docker_run`：

向用户展示命令，确认后执行。

### 6.2 或根据 GPU 厂商生成命令

**NVIDIA：**
```bash
docker run -itd \
  --gpus all \
  --name <container_name> \
  --shm-size 32g \
  --ulimit memlock=-1 \
  -v <host_model_path>:<container_model_path> \
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
  -p 8000:8000 \
  <image> \
  /bin/bash
```

参数说明：

| 参数 | 说明 |
|------|------|
| `--gpus all` | NVIDIA GPU（其他厂商使用 --privileged 或指定设备） |
| `--shm-size 32g` | 共享内存大小，大模型需要 |
| `--ulimit memlock=-1` | 解除内存锁定限制 |
| `-v` | 挂载模型目录 |
| `-p 8000:8000` | 端口映射 |
| `-itd` | 交互式后台运行 |

容器命名建议：

```
<model_name>_flagos
例如: qwen2.5-7b_flagos
```

---

## 步骤 7 — 创建统一工作目录

**所有后续 Skill 操作必须在此目录下进行，禁止修改镜像原有文件。**

```bash
docker exec <container_name> mkdir -p /workspace/flagos/logs \
                                       /workspace/flagos/perf \
                                       /workspace/flagos/eval \
                                       /workspace/flagos/output
```

目录结构说明：

| 目录 | 用途 | 使用 Skill |
|------|------|------------|
| `/workspace/flagos/logs` | 服务启动日志 | flagos-service-startup |
| `/workspace/flagos/perf` | 性能测试脚本和结果 | flagos-performance-testing |
| `/workspace/flagos/eval` | 精度评测脚本和结果 | flagos-eval-correctness |
| `/workspace/flagos/output` | 最终输出结果 | 所有 Skill |

---

## 步骤 8 — 验证容器状态

根据检测到的 GPU 厂商，使用对应命令验证：

```bash
# 检查容器运行状态
docker ps | grep <container_name>

# 检查容器内 GPU（根据厂商选择命令）
docker exec <container_name> <gpu_check_command>

# 检查模型挂载
docker exec <container_name> ls -la <container_model_path>

# 检查工作目录
docker exec <container_name> ls -la /workspace/flagos/
```

GPU 检查命令根据厂商：

| 厂商 | 容器内检查命令 |
|------|----------------|
| NVIDIA | `nvidia-smi` |
| 华为 | `npu-smi info` |
| 海光 | `hy-smi` |
| 摩尔线程 | `mthreads-gmi` |
| 昆仑芯 | `xpu-smi` |
| 天数 | `ixsmi` |
| 沐曦 | `mx-smi` |
| 清微智能 | `tsm_smi` |
| 寒武纪 | `cnmon` |

结果反馈：

- 容器状态（运行中/已停止）
- 容器内 GPU 可见性
- 模型目录挂载状态

---

## 步骤 9 — 更新 context.yaml

```yaml
container:
  name: "<container_name>"
  status: "running"

image:
  name: "<image_name>"
  tag: "<image_tag>"

model:
  local_path: "<host_model_path>"
  container_path: "<container_model_path>"

gpu:
  vendor: "<gpu_vendor>"
  count: <gpu_count>
  visible_devices_env: "<env_var_name>"

workspace:
  container_path: "/workspace/flagos"
  logs_dir: "/workspace/flagos/logs"
  perf_dir: "/workspace/flagos/perf"
  eval_dir: "/workspace/flagos/eval"
  output_dir: "/workspace/flagos/output"

metadata:
  updated_by: "flagos-environment-preparation"
  updated_at: "<timestamp>"
```

---

# 完成条件

环境准备成功的标志：

- GPU 厂商已识别
- 主机环境验证通过
- 模型路径已确定（下载或已存在）
- Docker 镜像已就绪
- 容器已创建并运行
- 容器内 GPU 可见
- 模型目录已正确挂载
- 统一工作目录已创建
- context.yaml 已更新

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| GPU 未检测到 | 检查驱动安装，确认设备存在 |
| 镜像拉取失败 | 检查网络，或使用 `docker load` 导入本地镜像 |
| 容器启动失败 | 检查 GPU 驱动兼容性，查看 `docker logs` |
| 模型目录为空 | 确认挂载路径正确，检查权限 |
| 容器内 GPU 不可见 | NVIDIA 检查 `--gpus all`；其他厂商检查设备挂载 |

下一步应执行 **flagos-service-startup**。
