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
- `calc_tp_size.py` — TP 自动推算（根据模型大小和 GPU 显存）
- `toggle_flaggems.py` — FlagGems 开关切换（替代 sed）
- `wait_for_service.sh` — 服务就绪检测（指数退避）
- `install_flagtree.sh` — FlagTree 安装/卸载/验证

---

# 统一工作目录

所有服务启动操作在 `/flagos-workspace` 目录下执行。

```
容器内: /flagos-workspace/logs/ ← 服务日志（按模式命名）
  startup_default.log  — 步骤③ default 模式
  startup_native.log   — 步骤⑥ native 模式
  startup_flagos.log   — 步骤⑦ flagos 模式
宿主机: /data/flagos-workspace/<model_name>/logs/ ← 实时同步
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
# 推荐方式：docker restart 确保资源完全释放（避免僵尸进程占用显存）
docker restart $CONTAINER
sleep 5
```

备选方式（仅当不能重启容器时）：
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
输出 JSON 包含 `env_vars` 和 `env_inline` 字段，在启动命令中使用 `env_inline` 作为内联前缀。

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

## 步骤 2.5 — TP 自动推算

在启动服务前，自动推算最小可用 `--tensor-parallel-size`：

```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/calc_tp_size.py --model-path $MODEL_PATH --json
```

输出示例：
```json
{
  "recommended_tp": 1,
  "gpu_count": 8,
  "gpu_memory_gb": 80.0,
  "model_size_gb": 15.2,
  "estimated_required_gb": 18.2,
  "reason": "模型 15.2GB，单卡 80GB 显存充足，推荐 TP=1"
}
```

**使用规则**：
- 读取 `recommended_tp` 作为 `${TP_SIZE}` 的值
- 如果脚本执行失败（退出码非 0），fallback 到 GPU 总数
- 如果推荐 TP 启动后 OOM，自动翻倍重试（TP×2），直到 GPU 总数

将推荐值写入 context.yaml 的 `runtime.tp_size` 和 `runtime.tp_reason`。

## 步骤 3 — 启动服务

**非 plugin 场景**：
```bash
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && <startup_command> > /flagos-workspace/logs/startup_<mode>.log 2>&1"
```

**Plugin 场景**（内联环境变量前缀）：
```bash
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && PATH=/opt/conda/bin:\$PATH <env_inline> <startup_command> > /flagos-workspace/logs/startup_<mode>.log 2>&1"
```

其中 `<mode>` 为 `default`、`native` 或 `flagos`，`<env_inline>` 来自 `toggle_flaggems.py --json` 输出的 `env_inline` 字段。

### Plugin 场景 vllm 服务启动模板

Plugin 环境下服务启动命令统一使用标准 vllm 格式，FlagGems 控制通过**内联环境变量**注入，与启动命令分离。

```bash
vllm serve ${MODEL_PATH} \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --served-model-name ${MODEL_NAME} \
    --tensor-parallel-size ${TP_SIZE} \
    --max-num-batched-tokens ${MAX_BATCHED_TOKENS:-16384} \
    --max-num-seqs ${MAX_NUM_SEQS:-256} \
    --max-model-len ${MAX_MODEL_LEN:-8192} \
    --trust-remote-code
```

**可选参数**（按需添加）：

| 参数 | 场景 | 示例 |
|------|------|------|
| `--pipeline-parallel-size` | 多机或超大模型 | `--pipeline-parallel-size 2` |
| `--gpu-memory-utilization` | 需限制显存占用 | `--gpu-memory-utilization 0.8` |
| `--reasoning-parser` | Thinking model | `--reasoning-parser qwen3` |

**四种模式启动方式**：

```bash
# Default（不修改环境，原样启动）
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && PATH=/opt/conda/bin:\$PATH vllm serve ... > /flagos-workspace/logs/startup_default.log 2>&1"

# Native（关闭 FlagGems）
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && PATH=/opt/conda/bin:\$PATH USE_FLAGGEMS=0 VLLM_FL_PREFER_ENABLED=false vllm serve ... > /flagos-workspace/logs/startup_native.log 2>&1"

# FlagOS Full（全量 FlagGems）
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && PATH=/opt/conda/bin:\$PATH USE_FLAGGEMS=1 VLLM_FL_PREFER_ENABLED=true vllm serve ... > /flagos-workspace/logs/startup_flagos.log 2>&1"

# FlagOS Optimized（自定义 blacklist）
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && PATH=/opt/conda/bin:\$PATH USE_FLAGGEMS=1 VLLM_FL_PREFER_ENABLED=true VLLM_FL_FLAGOS_BLACKLIST='mm,softmax' vllm serve ... > /flagos-workspace/logs/startup_flagos.log 2>&1"
```

四种模式差异仅在内联环境变量前缀（由 `toggle_flaggems.py` 或 `apply_op_config.py` 的 JSON 输出中的 `env_inline` 提供）。

**模板使用规则**：
- 具体参数值从容器 README / 用户输入 / context.yaml 获取
- `--served-model-name` 默认使用模型目录名
- `--tensor-parallel-size` 默认使用 `calc_tp_size.py` 的推荐值（基于模型大小和单卡显存自动推算），fallback 到 GPU 总数
- 业务环境变量（`VLLM_USE_MODELSCOPE` 等）按需在 docker exec 中追加，不写入模板

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
# Native 模式 / Default 模式
docker exec $CONTAINER bash -c "/flagos-workspace/scripts/wait_for_service.sh --port $PORT --model-name '$MODEL_NAME' --timeout 300"

# FlagGems 模式（CUDA graph 编译慢，需更长超时）
docker exec $CONTAINER bash -c "/flagos-workspace/scripts/wait_for_service.sh --port $PORT --model-name '$MODEL_NAME' --timeout 600"
```

自动轮询（2s→4s→5s 快速收敛，最大间隔 5s），超时自动分析日志。

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

## 步骤 7 — 记录算子列表（flagos 模式时，强制）

FlagGems 启用状态下，**必须记录算子列表**，这是后续算子优化的搜索空间来源。

```bash
# 自动发现并保存算子列表
docker exec $CONTAINER python3 /flagos-workspace/scripts/operator_optimizer.py discover \
  --save-ops /flagos-workspace/results/ops_list.json

# 检查运行时 gems.txt
docker exec $CONTAINER find / -name "gems.txt" 2>/dev/null
```

**反馈输出**：
```
FlagGems 已启用，记录算子列表：XX 个算子
算子列表已保存: /flagos-workspace/results/ops_list.json
gems.txt 路径: /path/to/gems.txt
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
docker exec $CONTAINER bash /flagos-workspace/scripts/install_flagtree.sh install --vendor $GPU_VENDOR
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

**⚠️ 强制规则**：FlagTree 安装失败后，禁止在当前容器上继续任何操作（环境已被污染）。
必须立即执行以下恢复流程，然后从步骤③重新开始。

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
- 对应 trace 文件已写入：
  - default 模式 → `traces/03_service_startup_default.json`
  - native 模式（步骤⑥前）→ 记录在 `traces/06_perf_native.json` 的 actions 中
  - flagos 模式 → `traces/07_service_startup_flagos.json`

---

# 故障排查

| 症状 | 可能原因 | 解决方案 |
|------|----------|----------|
| 进程启动后立即退出 | GPU 显存不足 | 自动将 TP 翻倍重试（TP×2），或降低 max-model-len |
| API 无响应 | 端口被占用 | 检查 `lsof -i:$PORT` |
| FlagGems 未生效 | toggle_flaggems.py 未正确切换 | 运行 `--action status` 检查 |
| gems.txt 未生成 | FlagGems 未启用 | 确认 toggle 状态 |
| 服务启动超时 | wait_for_service.sh 会自动诊断 | 查看超时输出的日志分析 |
| Thinking model 评测分数异常低 | max_model_len 过小，推理链被截断 | 重启服务，加大 `--max-model-len` 至 32768+ |
| OOM: max_model_len 过大 | KV cache 显存预分配超限 | 降低 max-model-len（thinking model 最低 16384） |
