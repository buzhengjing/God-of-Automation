---
name: flagos-service-startup
description: 在容器内启动推理服务（支持 native/flagos 模式切换），使用 toggle_flaggems.py 和 wait_for_service.sh
version: 4.0.0
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
  - runtime.gpu_count
  - runtime.flaggems_enabled
  - runtime.framework
---

# 服务启动 Skill

支持 native/flagos 模式切换，基于 `flaggems_control` 探测结果动态决定启停方式。

**工具脚本**（已由 setup_workspace.sh 部署到容器）:
- `toggle_flaggems.py` — FlagGems 开关切换（替代 sed）
- `wait_for_service.sh` — 服务就绪检测（指数退避）

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
runtime:
  framework: <vllm|sglang>
  gpu_count: <GPU 数量>
  flaggems_enabled: true|false
```

---

# 工作流程

## 步骤 1 — 停止现有服务

```bash
docker exec $CONTAINER bash -c "pkill -f 'vllm\|sglang\|flagscale' 2>/dev/null; sleep 3"
```

## 步骤 2 — 切换 FlagGems 状态

根据启动模式调用 `toggle_flaggems.py`：

**Native 模式**（关闭 FlagGems）：
```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/toggle_flaggems.py --action disable --json
```

**FlagOS 模式**（启用 FlagGems）：
```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/toggle_flaggems.py --action enable --json
```

**如果 integration_type 为 env_var**，则通过环境变量控制（不修改代码）：
- 读取 `flaggems_control.enable_method` / `disable_method`，在启动命令前加对应环境变量。

## 步骤 3 — 启动服务

```bash
docker exec -d $CONTAINER bash -c "cd /flagos-workspace && <startup_command> > /flagos-workspace/output/startup.log 2>&1"
```

启动命令根据容器配置确定（flagscale serve / vllm serve / sglang launch_server）。

## 步骤 4 — 等待服务就绪

```bash
docker exec $CONTAINER bash -c "/flagos-workspace/scripts/wait_for_service.sh --port $PORT --model-name '$MODEL_NAME' --timeout 300"
```

自动指数退避轮询（2s, 4s, 8s, 16s, 最大 30s），超时自动分析日志。

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
| 进程启动后立即退出 | GPU 显存不足 | 减少 tensor-parallel-size |
| API 无响应 | 端口被占用 | 检查 `lsof -i:$PORT` |
| FlagGems 未生效 | toggle_flaggems.py 未正确切换 | 运行 `--action status` 检查 |
| gems.txt 未生成 | FlagGems 未启用 | 确认 toggle 状态 |
| 服务启动超时 | wait_for_service.sh 会自动诊断 | 查看超时输出的日志分析 |
