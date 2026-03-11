---
name: flagos-service-startup
description: 在容器内启动推理服务、验证服务健康状态，并检查 gems.txt 算子列表
version: 2.0.0
license: internal
triggers:
  - service startup
  - start service
  - 启动服务
  - health check
  - 健康检查
depends_on:
  - flagos-pre-service-inspection
next_skill: flagos-eval-correctness
provides:
  - service.host
  - service.port
  - service.process_id
  - service.healthy
  - service.model_id
  - service.log_path
  - service.gems_txt_path
  - service.initial_operator_list
  - runtime.gpu_count
  - runtime.flaggems_enabled
---

# 服务启动 Skill

此 Skill 在容器内生成并执行服务启动命令、验证服务健康状态，并在启动后检查 gems.txt 获取初始算子列表。

**前提条件**：已完成 `flagos-pre-service-inspection` 环境检查。

---

# 统一工作目录

**重要**：所有服务启动操作必须在 `/flagos-workspace` 目录下执行，确保日志生成到宿主机可访问的位置。

```
容器内: /flagos-workspace/          ← 启动服务的工作目录
             │
             └── output/            ← 服务启动后自动生成
                 └── <服务名>/
                     └── serve/
                         └── *.log  ← 服务日志

宿主机: /data/flagos-workspace/<model_name>/output/  ← 实时同步，可直接访问
```

**宿主机实时监控日志**：
```bash
# 查找日志文件
find /data/flagos-workspace/<model_name>/output -name "*.log"

# 实时查看
tail -f /data/flagos-workspace/<model_name>/output/**/*.log
```

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
model:
  name: <来自 container-preparation>
  url: <来自 container-preparation>
  container_path: <来自 container-preparation>
workspace:
  host_path: <来自 container-preparation>
  container_path: "/flagos-workspace"
gpu:
  vendor: <来自 container-preparation>
  count: <来自 container-preparation>
  visible_devices_env: <来自 container-preparation>
inspection:
  core_packages: <来自 pre-service-inspection>
  flag_packages: <来自 pre-service-inspection>
  flaggems_control: <来自 pre-service-inspection>
  env_vars: <来自 pre-service-inspection>
```

## 写入 shared/context.yaml

```yaml
service:
  host: <服务主机，通常为 localhost>
  port: <服务端口，通常为 8000>
  process_id: <运行中服务的 PID>
  healthy: <true|false>
  model_id: <API 响应中的模型标识符>
  log_path: <服务日志路径>
  gems_txt_path: <gems.txt 文件路径>
  initial_operator_list: [...]
runtime:
  gpu_count: <可见 GPU 数量>
  flaggems_enabled: <true|false>
```

---

# 工作流程

## 阶段一：生成并执行启动命令

### 步骤 1 — 确定启动命令

根据 `inspection` 中的环境检查结果、GPU 厂商和用户选择，生成启动命令。

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

### 步骤 2 — 执行启动命令

**重要**：必须先 `cd` 到工作目录，确保 `output/` 日志目录生成在挂载路径下。

用户确认后，后台执行启动命令：

```bash
# 在容器内的工作目录下启动服务
docker exec <container_name> bash -c "cd /flagos-workspace && <startup_command>"
```

**完整示例（vLLM）**：

```bash
docker exec <container_name> bash -c "cd /flagos-workspace && USE_FLAGGEMS=1 CUDA_VISIBLE_DEVICES=0,1,2,3 vllm serve <model_path> --served-model-name <model_name> --tensor-parallel-size 4 --port 8000"
```

等待服务启动（约 30-60 秒），**在宿主机直接查看日志**：

```bash
# 查找生成的日志文件
find /data/flagos-workspace/<model_name>/output -name "*.log"

# 实时查看日志（无需 docker exec）
tail -f /data/flagos-workspace/<model_name>/output/**/*.log
```

结果反馈：

- 启动命令
- 进程 PID
- **日志文件路径（宿主机）**

---

## 阶段二：服务验证

### 步骤 3 — 检查进程状态

```bash
docker exec <container_name> ps -ef | grep -E "vllm|sglang" | grep -v grep
```

结果反馈：

- 进程 ID
- 进程状态（运行中 / 已退出）

---

### 步骤 4 — 查询模型 API

等待服务完全启动后，查询模型列表：

```bash
curl -s http://localhost:8000/v1/models | jq .
```

结果反馈：

- API 响应状态
- 已加载模型列表

---

### 步骤 5 — 运行推理测试

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

### 步骤 6 — 验证 FlagGems 执行（如已启用）

如果启用了 FlagGems，**在宿主机**检查日志确认算子替换生效：

```bash
# 在宿主机直接查看日志（无需 docker exec）
grep -ri "gems\|flag_gems" /data/flagos-workspace/<model_name>/output/ | head -10
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

## 阶段三：检查 gems.txt（启动后）

### 步骤 7 — 查找并读取 gems.txt

服务启动后，FlagGems 会生成 gems.txt 文件，记录实际使用的算子列表。

```bash
# 在容器内查找 gems.txt
docker exec <container_name> find / -name "gems.txt" 2>/dev/null

# 查看内容
docker exec <container_name> cat <gems_txt_path>
```

记录初始算子列表，为后续算子替换工作提供依据。

结果反馈：

- gems.txt 文件路径
- 初始算子列表

---

### 步骤 8 — 写入 context.yaml

将服务信息和 gems.txt 结果写入 context.yaml。

---

# 完成条件

服务启动成功的标志：

- 服务进程正在运行
- **日志文件已生成在 `/flagos-workspace/output/` 目录**
- **宿主机可直接访问日志文件**
- API /v1/models 可访问
- 推理测试通过
- （如启用）FlagGems 算子替换已生效
- **gems.txt 已检查，初始算子列表已记录**
- context.yaml 已更新

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
| gems.txt 未生成 | FlagGems 未启用或版本不支持 | 确认 FlagGems 已启用，检查版本 |
