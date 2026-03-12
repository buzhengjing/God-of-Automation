---
name: flagos-service-startup
description: 在容器内启动推理服务（支持 native/flagos 模式切换），验证服务健康状态，并检查 gems.txt 算子列表
version: 3.0.0
license: internal
triggers:
  - service startup
  - start service
  - 启动服务
  - health check
  - 健康检查
depends_on:
  - flagos-pre-service-inspection
next_skill: flagos-performance-testing
provides:
  - service.cluster
  - service.external_ip
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
  - runtime.framework
---

# 服务启动 Skill

此 Skill 在容器内生成并执行服务启动命令、验证服务健康状态，并在启动后检查 gems.txt 获取初始算子列表。

**新增能力**：
- 支持 **native 模式**（关闭 FlagGems）和 **flagos 模式**（启用 FlagGems）切换
- 基于 `flaggems_control` 探测结果动态决定启停方式（不再硬编码）
- 支持 `${CMD_PREFIX}` 双执行模式
- 失败恢复：FlagOS 启动失败自动切回 Native 验证

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
execution:
  mode: <来自 pre-service-inspection>
  cmd_prefix: <来自 pre-service-inspection>
inspection:
  core_packages: <来自 pre-service-inspection>
  flag_packages: <来自 pre-service-inspection>
  flaggems_control: <来自 pre-service-inspection>
  env_vars: <来自 pre-service-inspection>
flaggems_control:
  enable_method: <来自 pre-service-inspection>
  disable_method: <来自 pre-service-inspection>
  integration_type: <来自 pre-service-inspection>
```

## 写入 shared/context.yaml

```yaml
service:
  cluster: <集群/机房标识>
  external_ip: <宿主机外部 IP>
  host: <服务主机，通常为 localhost>
  port: <服务端口，通常为 8000>
  process_id: <运行中服务的 PID>
  healthy: <true|false>
  model_id: <API 响应中的模型标识符>
  log_path: <服务日志路径>
  gems_txt_path: <gems.txt 文件路径>
  initial_operator_list: [...]
runtime:
  framework: <vllm|sglang>
  gpu_count: <可见 GPU 数量>
  flaggems_enabled: <true|false>
```

---

# 工作流程

## 步骤 0 — 确定启动模式

此 Skill 可被多次调用，每次可能以不同模式启动：

| 启动模式 | 说明 | 触发场景 |
|----------|------|----------|
| **native** | 关闭 FlagGems，原生性能基线 | Scenario A 步骤④ |
| **flagos** | 启用 FlagGems，FlagOS 性能测试 | Scenario A 步骤⑤ |
| **default** | 按容器原始配置启动 | 单次启动或不指定模式时 |

调用方应指明启动模式（如 "以 native 模式启动" 或 "以 flagos 模式启动"）。

---

## 阶段一：生成并执行启动命令

### 步骤 1 — 停止现有服务（如有）

```bash
${CMD_PREFIX} bash -c "pkill -f 'vllm\|sglang' 2>/dev/null; sleep 3"
```

### 步骤 2 — 根据模式构建 FlagGems 环境变量

**不再硬编码 `USE_FLAGGEMS=0/1`**，而是读取 `flaggems_control.enable_method` 和 `disable_method`：

#### Native 模式（关闭 FlagGems）

读取 `flaggems_control.disable_method`，根据值执行：

| disable_method | 操作 |
|----------------|------|
| `env:USE_FLAGGEMS=0` | 在启动命令前加 `USE_FLAGGEMS=0` |
| `env:USE_FLAGOS=0` | 在启动命令前加 `USE_FLAGOS=0` |
| `env:<VAR>=<VAL>` | 在启动命令前加对应环境变量 |
| `uninstall` | `pip uninstall flag-gems -y`（极端情况） |
| `script:<path>` | 执行指定脚本 |
| `plugin:disable` | `pip uninstall vllm-plugin-FL -y` 或设置环境变量 |
| 其他/unknown | 报告无法自动切换，需人工介入 |

#### FlagOS 模式（启用 FlagGems）

读取 `flaggems_control.enable_method`，根据值执行：

| enable_method | 操作 |
|---------------|------|
| `env:USE_FLAGGEMS=1` | 在启动命令前加 `USE_FLAGGEMS=1` |
| `env:USE_FLAGOS=1` | 在启动命令前加 `USE_FLAGOS=1` |
| `env:<VAR>=<VAL>` | 在启动命令前加对应环境变量 |
| `auto` | 插件自动启用，无需额外操作 |
| `script:<path>` | 执行指定脚本 |
| 其他/unknown | 报告无法自动切换，需人工介入 |

### 步骤 3 — 确定启动命令

根据 `inspection` 中的环境检查结果、GPU 厂商和启动模式，生成启动命令。

#### 环境变量设置

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

#### 启动命令模板

**vLLM（native 模式）：**

```bash
<FLAGGEMS_DISABLE_ENV> <VISIBLE_DEVICES_ENV>=0,1,2,3 vllm serve <model_path> \
  --served-model-name <model_name> \
  --tensor-parallel-size <gpu_count> \
  --port 8000
```

**vLLM（flagos 模式）：**

```bash
<FLAGGEMS_ENABLE_ENV> <VISIBLE_DEVICES_ENV>=0,1,2,3 vllm serve <model_path> \
  --served-model-name <model_name> \
  --tensor-parallel-size <gpu_count> \
  --port 8000
```

**SGLang 同理**，将 `vllm serve` 替换为 `python -m sglang.launch_server --model-path`。

向用户展示生成的命令，允许用户：
- 批准
- 修改参数（如指定特定 GPU 卡）
- 完全替换

---

### 步骤 4 — 执行启动命令

**重要**：必须先 `cd` 到工作目录，确保 `output/` 日志目录生成在挂载路径下。

```bash
${CMD_PREFIX} bash -c "cd /flagos-workspace && <startup_command>"
```

等待服务启动（约 30-60 秒），查看日志：

```bash
# 宿主机模式：直接查看日志
find /data/flagos-workspace/<model_name>/output -name "*.log"
tail -f /data/flagos-workspace/<model_name>/output/**/*.log

# 容器内模式：直接查看
find /flagos-workspace/output -name "*.log"
tail -f /flagos-workspace/output/**/*.log
```

---

## 阶段二：服务验证

### 步骤 5 — 检查进程状态

```bash
${CMD_PREFIX} ps -ef | grep -E "vllm|sglang" | grep -v grep
```

### 步骤 6 — 查询模型 API

```bash
curl -s http://localhost:8000/v1/models | jq .
```

### 步骤 7 — 运行推理测试

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<model_name>",
    "messages": [{"role": "user", "content": "hello"}],
    "max_tokens": 10
  }' | jq .
```

### 步骤 8 — 验证 FlagGems 执行（flagos 模式时）

如果以 flagos 模式启动，检查日志确认算子替换生效：

```bash
grep -ri "gems\|flag_gems" /data/flagos-workspace/<model_name>/output/ | head -10
```

---

## 阶段二补充：输出服务连接信息（必须执行）

### 步骤 8.5 — 探测宿主机 IP 和集群信息

服务验证通过后，**必须**探测并输出服务连接信息，供用户判断远端评测可达性。

**探测宿主机外部 IP**：

```bash
# 优先读取常见云厂商的 metadata 接口
EXTERNAL_IP=$(curl -s --connect-timeout 2 http://metadata.tencentyun.com/latest/meta-data/public-ipv4 2>/dev/null)

if [ -z "$EXTERNAL_IP" ]; then
    EXTERNAL_IP=$(curl -s --connect-timeout 2 http://100.100.100.200/latest/meta-data/eip 2>/dev/null)  # 阿里云
fi

if [ -z "$EXTERNAL_IP" ]; then
    EXTERNAL_IP=$(curl -s --connect-timeout 2 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null)  # AWS/通用
fi

if [ -z "$EXTERNAL_IP" ]; then
    # 降级：使用宿主机网卡 IP（非 127/docker 的第一个 IP）
    EXTERNAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
fi

echo "EXTERNAL_IP=$EXTERNAL_IP"
```

**探测集群/机房标识**（自动推断，无需用户提供）：

```bash
# 通过 IP 段、hostname 或云厂商 metadata 推断
CLUSTER=""

# 尝试从 hostname 推断
HOSTNAME=$(hostname)
if echo "$HOSTNAME" | grep -qiE "tencent|qcloud|tx"; then
    CLUSTER="腾讯云"
elif echo "$HOSTNAME" | grep -qiE "ali|aliyun|ecs"; then
    CLUSTER="阿里云"
elif echo "$HOSTNAME" | grep -qiE "huawei|hw"; then
    CLUSTER="华为云"
fi

# 尝试从 metadata 推断地域
REGION=$(curl -s --connect-timeout 2 http://metadata.tencentyun.com/latest/meta-data/placement/zone 2>/dev/null)
if [ -z "$REGION" ]; then
    REGION=$(curl -s --connect-timeout 2 http://100.100.100.200/latest/meta-data/region-id 2>/dev/null)
fi

if [ -n "$REGION" ]; then
    CLUSTER="${CLUSTER}${REGION}"
fi

# 如果无法自动推断，留空（后续由用户补充）
echo "CLUSTER=$CLUSTER"
```

### 步骤 8.6 — 输出服务连接信息摘要

**服务验证通过后，必须以如下格式输出连接信息**：

```
============================================================
服务连接信息（用于远端评测可达性判断）
============================================================
<集群, IP, 服务端口, 模型名称>
<${CLUSTER}, ${EXTERNAL_IP}, ${PORT}, ${MODEL_NAME}>

示例: <腾讯云北京, 172.21.16.14, 9010, Qwen/Qwen3.5-35B-A3B>
============================================================
评测接口: http://${EXTERNAL_IP}:${PORT}/v1/chat/completions
启动模式: native / flagos
FlagGems: 已启用 / 已关闭
============================================================
```

**关键**：
- 如果 `CLUSTER` 为空，提示用户补充集群/机房信息
- 如果 `EXTERNAL_IP` 是内网地址（10.x / 172.16-31.x / 192.168.x），提醒用户远端评测平台可能无法直接访问，需确认网络连通性
- 将 `cluster` 和 `external_ip` 写入 context.yaml 的 `service` 字段

---

## 阶段三：失败恢复（新增）

### 步骤 9 — FlagOS 启动失败自动恢复

如果 flagos 模式启动失败：

1. **保存失败日志**：
   ```bash
   ${CMD_PREFIX} bash -c "cp /flagos-workspace/output/**/*.log /flagos-workspace/logs/flagos_startup_fail_$(date +%s).log 2>/dev/null"
   ```

2. **自动切回 Native 验证**：
   ```bash
   # 以 native 模式重启，验证是 FlagGems 问题还是环境问题
   ${CMD_PREFIX} bash -c "pkill -f 'vllm\|sglang' 2>/dev/null; sleep 3"
   # 重新以 native 模式启动
   ```

3. **判断结果**：
   - Native 也失败 → 报告环境问题，需人工介入
   - Native 成功 → 确认是 FlagGems 问题，触发算子优化

---

## 阶段四：检查 gems.txt（启动后）

### 步骤 10 — 查找并读取 gems.txt

服务启动后，FlagGems 会生成 gems.txt 文件，记录实际使用的算子列表。

```bash
${CMD_PREFIX} find / -name "gems.txt" 2>/dev/null
${CMD_PREFIX} cat <gems_txt_path>
```

### 步骤 11 — 写入 context.yaml

将服务信息和 gems.txt 结果写入 context.yaml。

---

# 完成条件

服务启动成功的标志：

- **启动模式已确认（native / flagos / default）**
- 服务进程正在运行
- **日志文件已生成在 `/flagos-workspace/output/` 目录**
- API /v1/models 可访问
- 推理测试通过
- （如 flagos 模式）FlagGems 算子替换已生效
- **已输出服务连接信息 `<集群, IP, 服务端口, 模型名称>`**
- **gems.txt 已检查，初始算子列表已记录**
- context.yaml 已更新（含 cluster、external_ip）
- **runtime.flaggems_enabled 正确反映当前状态**

---

# 故障排查

如果启动失败，参考 `flagos-log-analyzer` skill 进行日志分析。

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 进程启动后立即退出 | GPU 显存不足 | 减少 tensor-parallel-size 或使用更小模型 |
| API 无响应 | 端口被占用 | 检查 `lsof -i:8000` 并更换端口 |
| FlagGems 未生效 | 启用方法不正确 | 检查 flaggems_control.enable_method |
| 模型加载失败 | 路径错误 | 检查模型路径是否正确挂载 |
| gems.txt 未生成 | FlagGems 未启用或版本不支持 | 确认 FlagGems 已启用，检查版本 |
| flagos 模式启动失败 | 算子兼容问题 | 自动切回 native 验证 → 触发算子优化 |
| 无法关闭 FlagGems | disable_method 不适用 | 检查 flaggems_control，可能需要 uninstall |
