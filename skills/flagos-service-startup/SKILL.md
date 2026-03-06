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
  container_path: <来自 environment-preparation>
runtime:
  framework: <来自 model-introspection>
gpu:
  vendor: <来自 environment-preparation>
  count: <来自 environment-preparation>
  visible_devices_env: <来自 environment-preparation>
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

## 阶段一：环境检查（启动前）

### 步骤 1 — 进入容器

```bash
docker exec -it <container_name> /bin/bash
```

结果反馈：

- 成功进入容器

---

### 步骤 2 — 检查 GPU

根据 context.yaml 中的 `gpu.vendor` 使用对应检测命令：

| 厂商 | 检测命令 |
|------|----------|
| NVIDIA | `nvidia-smi` |
| 华为 (Ascend) | `npu-smi info` |
| 海光 (Hygon) | `hy-smi` |
| 摩尔线程 | `mthreads-gmi` |
| 昆仑芯 | `xpu-smi` |
| 天数 | `ixsmi` |
| 沐曦 | `mx-smi` |
| 清微智能 | `tsm_smi` 或 `source /root/.bash_profile && tsm_smi -t` |
| 寒武纪 | `cnmon` |

示例（NVIDIA）：

```bash
nvidia-smi
```

示例（华为）：

```bash
npu-smi info
```

结果反馈：

- GPU 厂商
- GPU 可见性
- GPU 数量
- 显存大小

---

### 步骤 3 — 检查运行时环境

检查关键软件包版本：

```bash
pip show torch vllm sglang flag-gems 2>/dev/null | grep -E "^(Name|Version):"
```

或详细列表：

```bash
pip list | grep -iE "(torch|vllm|sglang|flag|gems)"
```

重要软件包：

- torch
- vllm / sglang
- flag-gems

结果反馈：

- 软件包版本列表

---

### 步骤 4 — 检测 FlagGems 集成状态

**此步骤必须在启动服务前完成，决定是否启用算子替换。**

检测方法：

1. 检查 flag-gems 是否安装：

```bash
pip show flag_gems
```

2. 检查 vLLM/SGLang 是否集成了 FlagGems：

```bash
# 获取 vllm 安装路径
VLLM_PATH=$(pip show vllm | grep Location | cut -d' ' -f2)/vllm

# 搜索 gems 相关代码
grep -r "flag_gems\|gems" $VLLM_PATH --include="*.py" | head -20
```

3. 检查环境变量配置：

```bash
echo $USE_FLAGGEMS
```

结果反馈：

- FlagGems 安装状态：已安装 / 未安装
- 框架集成状态：已集成 / 未集成
- 建议：是否启用 FlagGems 算子替换

---

### 步骤 5 — 询问用户是否启用 FlagGems

根据步骤 4 的检测结果，询问用户：

**如果检测到 FlagGems 可用：**

"检测到 FlagGems 已集成，是否启用算子替换？"

选项：
1. 启用 FlagGems（推荐）
2. 不启用 FlagGems
3. 用户自定义配置

**如果未检测到 FlagGems：**

告知用户 FlagGems 不可用，将使用原生算子。

---

## 阶段二：生成并执行启动命令

### 步骤 6 — 确定启动命令

根据前面的检测结果、GPU 厂商和用户选择，生成启动命令。

### 环境变量设置

根据 GPU 厂商设置可见设备环境变量：

| 厂商 | 环境变量 | 示例 |
|------|----------|------|
| NVIDIA | `CUDA_VISIBLE_DEVICES` | `CUDA_VISIBLE_DEVICES=0,1` |
| 华为 | `ASCEND_RT_VISIBLE_DEVICES` | `ASCEND_RT_VISIBLE_DEVICES=0,1` |
| 海光 | `HIP_VISIBLE_DEVICES` | `HIP_VISIBLE_DEVICES=0,1` |
| 摩尔线程 | `MUSA_VISIBLE_DEVICES` | `MUSA_VISIBLE_DEVICES=0,1` |
| 昆仑芯 | `XPU_VISIBLE_DEVICES` | `XPU_VISIBLE_DEVICES=0,1` |
| 天数 | `CUDA_VISIBLE_DEVICES` | `CUDA_VISIBLE_DEVICES=0,1` |
| 沐曦 | `CUDA_VISIBLE_DEVICES` | `CUDA_VISIBLE_DEVICES=0,1` |
| 清微智能 | `TXDA_VISIBLE_DEVICES` | `TXDA_VISIBLE_DEVICES=0,1` |
| 寒武纪 | `MLU_VISIBLE_DEVICES` | `MLU_VISIBLE_DEVICES=0,1` |
| 平头哥 | `CUDA_VISIBLE_DEVICES` | `CUDA_VISIBLE_DEVICES=0,1` |

### 启动命令模板

**vLLM 示例（启用 FlagGems）：**

```bash
USE_FLAGGEMS=1 <VISIBLE_DEVICES_ENV>=0,1,2,3 vllm serve <model_path> \
  --served-model-name <model_name> \
  --tensor-parallel-size <gpu_count> \
  --port 8000
```

**vLLM 示例（不启用 FlagGems）：**

```bash
USE_FLAGGEMS=0 <VISIBLE_DEVICES_ENV>=0,1,2,3 vllm serve <model_path> \
  --served-model-name <model_name> \
  --tensor-parallel-size <gpu_count> \
  --port 8000
```

**SGLang 示例（启用 FlagGems）：**

```bash
USE_FLAGGEMS=1 <VISIBLE_DEVICES_ENV>=0,1,2,3 python -m sglang.launch_server \
  --model-path <model_path> \
  --port 8000
```

向用户展示生成的命令，允许用户：

- 批准
- 修改参数（如指定特定 GPU 卡）
- 完全替换

---

### 步骤 7 — 执行启动命令

用户确认后，后台执行启动命令：

```bash
nohup <startup_command> > service.log 2>&1 &
```

等待服务启动（约 30-60 秒），检查日志：

```bash
tail -f service.log
```

结果反馈：

- 启动命令
- 进程 PID

---

## 阶段三：服务验证（启动后）

### 步骤 8 — 检查进程状态

```bash
ps -ef | grep -E "vllm|sglang" | grep -v grep
```

结果反馈：

- 进程 ID
- 进程状态（运行中 / 已退出）

---

### 步骤 9 — 查询模型 API

等待服务完全启动后，查询模型列表：

```bash
curl -s http://localhost:8000/v1/models | jq .
```

结果反馈：

- API 响应状态
- 已加载模型列表

---

### 步骤 10 — 运行推理测试

发送简单推理请求验证服务：

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<model_name>",
    "messages": [{"role": "user", "content": "hello"}],
    "max_tokens": 10
  }' | jq .
```

结果反馈：

- 推理是否成功
- 响应延迟

---

### 步骤 11 — 验证 FlagGems 执行（如已启用）

如果启用了 FlagGems，检查日志确认算子替换生效：

```bash
grep -i "gems\|flag_gems" service.log | head -10
```

典型输出模式：

```
flag_gems.ops loaded
GEMS MUL
GEMS RECIPROCAL
```

结果反馈：

- FlagGems 是否实际生效

---

# 完成条件

服务启动成功的标志：

- GPU 可见且数量正确
- 运行时环境已验证
- FlagGems 状态已确认（启用/禁用）
- 服务进程正在运行
- API /v1/models 可访问
- 推理测试通过
- （如启用）FlagGems 算子替换已生效

---

# 故障排查

如果启动失败，参考 `flagos-log-analyzer` skill 进行日志分析。

常见问题：

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 进程启动后立即退出 | GPU 显存不足 | 减少 tensor-parallel-size 或使用更小模型 |
| API 无响应 | 端口被占用 | 检查 `lsof -i:8000` 并更换端口 |
| FlagGems 未生效 | 环境变量未设置 | 确认 `USE_FLAGGEMS=1` |
| 模型加载失败 | 路径错误 | 检查模型路径是否正确挂载 |
