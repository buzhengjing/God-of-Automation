---
name: flagos-service-startup
description: 在容器内启动推理服务（支持 default/native/flagos 模式切换），使用 toggle_flaggems.py 和 wait_for_service.sh
version: 5.0.0
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
  - service.healthy
  - service.model_id
  - service.log_path
  - service.gems_txt_path
  - service.initial_operator_list
  - service.max_model_len
  - runtime.gpu_count
  - runtime.flaggems_enabled
  - runtime.framework
  - runtime.thinking_model
  - environment.initial_env_verified
  - environment.flagtree_env_verified
---

# 服务启动 Skill

支持 default/native/flagos 三种模式，基于 `flaggems_control` 探测结果动态决定启停方式。

**启动模式**：
- **default** — 不修改任何 FlagGems 状态，以容器现有配置原样启动。用于步骤③验证初始环境可用性。
- **native** — 关闭 FlagGems，纯原生环境。
- **flagos** — 启用全量 FlagGems。

**工具脚本**（已由 setup_workspace.sh 部署到容器）:
- `toggle_flaggems.py` — FlagGems 开关切换（替代 sed）
- `wait_for_service.sh` — 服务就绪检测（指数退避）
- `install_flagtree.sh` — FlagTree 安装/卸载/验证

---

# 统一工作目录

所有服务启动操作在 `/flagos-workspace` 目录下执行。

```
容器内: /flagos-workspace/output/ ← 服务日志
宿主机: /data/flagos-workspace/<model_name>/output/ ← 实时同步
```

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
model:
  name: <来自 container-preparation>
  container_path: <来自 container-preparation>
execution:
  cmd_prefix: <来自 pre-service-inspection>
flaggems_control:
  enable_method: <来自 pre-service-inspection>
  disable_method: <来自 pre-service-inspection>
  integration_type: <来自 pre-service-inspection>
```

## 写入 shared/context.yaml

```yaml
service:
  cluster: <集群标识>
  external_ip: <宿主机 IP>
  host: <服务主机>
  port: <服务端口>
  healthy: true|false
  model_id: <模型标识符>
  log_path: <日志路径>
  gems_txt_path: <gems.txt 路径>
  initial_operator_list: [...]
  max_model_len: <服务实际的 max_model_len>
runtime:
  framework: <vllm|sglang>
  gpu_count: <GPU 数量>
  flaggems_enabled: true|false
  thinking_model: true|false            # 是否为 thinking model（传递给后续评测 Skill）
```

---

# 工作流程

## 步骤 1 — 停止现有服务

```bash
docker exec $CONTAINER bash -c "pkill -f 'vllm\|sglang\|flagscale' 2>/dev/null; sleep 3"
```

## 步骤 2 — 切换 FlagGems 状态

根据启动模式调用 `toggle_flaggems.py`：

**Default 模式**（不修改任何状态）：
不调用 `toggle_flaggems.py`，直接跳到步骤 3。用于步骤③验证初始环境可用性。

**Native 模式**（关闭 FlagGems）：

非 plugin 场景：
```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/toggle_flaggems.py --action disable --json
```

Plugin 场景：
```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/toggle_flaggems.py --action disable --integration-type plugin --json
```
这会生成 `/flagos-workspace/env_config.sh`（内含 `VLLM_FL_PREFER_ENABLED=false`），启动服务前 source 此文件。

**FlagOS 模式**（启用 FlagGems）：

非 plugin 场景：
```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/toggle_flaggems.py --action enable --json
```

Plugin 场景：
```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/toggle_flaggems.py --action enable --integration-type plugin --json
```

**如果 integration_type 为 env_var**，则通过环境变量控制（不修改代码）：
- 读取 `flaggems_control.enable_method` / `disable_method`，在启动命令前加对应环境变量。

## 步骤 3 — 启动服务

**非 plugin 场景**：
```bash
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && <startup_command> > /flagos-workspace/output/startup.log 2>&1"
```

**Plugin 场景**（带环境变量）：
```bash
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && source /flagos-workspace/env_config.sh && <startup_command> > /flagos-workspace/output/startup.log 2>&1"
```

启动命令根据容器配置确定（flagscale serve / vllm serve / sglang launch_server）。

### max_model_len 决策规则

`--max-model-len` 直接决定模型单次请求能处理的最大 token 数。**如果设置过小，评测端请求的 `max_tokens` 会被服务端截断，导致推理不完整。**

**决策逻辑**：

1. **判断是否为 thinking model**：
   - 模型名包含 `Qwen3` / `QwQ` / `DeepSeek-R1` / `DeepSeek-R2` → thinking model
   - 其他 → 标准模型

2. **根据模型类型选择 max_model_len**：

| 模型类型 | 推荐 max_model_len | 原因 |
|---------|-------------------|------|
| Thinking model | **32768** 或更高 | thinking chain 需要 30000+ tokens，需留余量给 prompt |
| 标准 LLM（性能测试） | **8192** | 性能测试使用固定 input/output 长度，够用即可 |
| 标准 LLM（精度评测） | **8192** | 非 thinking 模型的评测 max_tokens=8192 |

3. **显存约束**：
   - `max_model_len` 越大，vLLM 预分配的 KV cache 显存越多
   - 如果 GPU 显存不足导致 OOM，优先降低 `max_model_len`
   - Thinking model 最低不应低于 **16384**（否则推理链严重截断）

4. **具体参数**：

```bash
# Thinking model（如 Qwen3-8B）
vllm serve <model_path> --max-model-len 32768 ...

# 标准模型（性能测试场景）
vllm serve <model_path> --max-model-len 8192 ...

# 显存不足时的降级
vllm serve <model_path> --max-model-len 16384 ...  # thinking model 最低线
```

5. **验证**：启动后 `wait_for_service.sh` 会输出实际的 `max_model_len`，确认与预期一致。如果评测场景需要 `max_tokens=30000`，则 `max_model_len` 必须 > 30000 + prompt_tokens。

## 步骤 4 — 等待服务就绪

```bash
docker exec $CONTAINER bash -c "/flagos-workspace/scripts/wait_for_service.sh --port $PORT --model-name '$MODEL_NAME' --timeout 300"
```

自动指数退避轮询（2s, 4s, 8s, 16s, 最大 30s），超时自动分析日志。

**启动后校验**：检查 `wait_for_service.sh` 输出的 `max_model_len`：
- 如果是 thinking model 且 `max_model_len < 32768` → 警告，建议重启并加大 `--max-model-len`
- 如果 `max_model_len < 8192` → 评测可能出问题，必须修正

## 步骤 5 — 服务验证

```bash
curl -s http://localhost:$PORT/v1/models | python3 -m json.tool
curl -s http://localhost:$PORT/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "<model_name>", "messages": [{"role": "user", "content": "hello"}], "max_tokens": 10}'
```

## 步骤 6 — 探测宿主机 IP 和输出连接信息

```
============================================================
服务连接信息
============================================================
<集群, IP, 服务端口, 模型名称>
评测接口: http://${EXTERNAL_IP}:${PORT}/v1/chat/completions
启动模式: native / flagos
============================================================
```

## 步骤 7 — 检查 gems.txt（flagos 模式时）

```bash
docker exec $CONTAINER find / -name "gems.txt" 2>/dev/null
docker exec $CONTAINER cat <gems_txt_path>
```

## 步骤 8 — 写入 context.yaml

写入 `environment` 字段（步骤③ default 模式时）：
```yaml
environment:
  initial_env_verified: true    # 步骤③通过后设为 true
  has_plugin: <from inspection>
  has_flagtree: <from flagtree.installed>
```

---

# FlagTree 安装验证流程（步骤④b）

当用户选择安装 FlagTree 后，需要重启服务验证：

## 1. 安装 FlagTree

```bash
docker exec $CONTAINER bash /flagos-workspace/scripts/install_flagtree.sh install --vendor $GPU_VENDOR --version 0.4.0
```

## 2. 验证安装

```bash
docker exec $CONTAINER bash /flagos-workspace/scripts/install_flagtree.sh verify
```

## 3. 重启服务（default 模式）

停止现有服务 → 启动（不修改 FlagGems 状态）→ 等待就绪 → API 验证

## 4. 判断结果

- **成功**：写入 `environment.flagtree_env_verified: true`，`environment.flagtree_installed_by_us: true`
- **失败**：触发恢复流程

---

# FlagTree 安装失败恢复（步骤④c）

**优先方案**：重新 `docker run` 新容器
- 使用 context.yaml 中的 `image` 信息重新创建
- 需要用户确认（docker run 属于危险操作）
- 重新执行步骤①②③

**备选方案**（特殊环境如阿里云不能重建容器）：
```bash
docker exec $CONTAINER bash /flagos-workspace/scripts/install_flagtree.sh uninstall
```
- 卸载 FlagTree 恢复原始 triton
- 验证服务能否正常启动
- 写入 `environment.flagtree_env_verified: false`

---

# 失败恢复

如果 flagos 模式启动失败：
1. 保存失败日志
2. 自动切回 Native 验证
3. Native 也失败 → 报告环境问题；Native 成功 → 确认是 FlagGems 问题

---

# 完成条件

- 启动模式已确认（native / flagos）
- 服务进程正在运行
- API /v1/models 可访问
- 推理测试通过
- 已输出服务连接信息
- gems.txt 已检查（flagos 模式）
- context.yaml 已更新

---

# 故障排查

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 进程启动后立即退出 | GPU 显存不足 | 减少 tensor-parallel-size 或降低 max-model-len |
| API 无响应 | 端口被占用 | 检查 `lsof -i:$PORT` |
| FlagGems 未生效 | toggle_flaggems.py 未正确切换 | 运行 `--action status` 检查 |
| gems.txt 未生成 | FlagGems 未启用 | 确认 toggle 状态 |
| 服务启动超时 | wait_for_service.sh 会自动诊断 | 查看超时输出的日志分析 |
| Thinking model 评测分数异常低 | max_model_len 过小，推理链被截断 | 重启服务，加大 `--max-model-len` 至 32768+ |
| OOM: max_model_len 过大 | KV cache 显存预分配超限 | 降低 max-model-len（thinking model 最低 16384） |
