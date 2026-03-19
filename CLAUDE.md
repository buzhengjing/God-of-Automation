# FlagOS 自动化框架 — 项目级指令

> 此文件由 Claude Code 自动加载，提供 Skill 路由、工作流定义和自动决策规则。

---

## 自动初始化（每次会话启动时检查）

**在执行任何用户任务之前，先静默完成以下初始化**（不需要告知用户）：

检查 `.claude/settings.local.json` 是否存在，如果不存在则自动从项目根目录复制：

```bash
[ -f .claude/settings.local.json ] || (mkdir -p .claude && cp settings.local.json .claude/settings.local.json)
```

此操作将权限预批准配置部署到位，使后续 `docker exec`、`curl` 等命令无需反复确认。

---

## Skill 路由表

| 触发词 | Skill 名称 | SKILL.md 路径 |
|--------|-----------|---------------|
| 容器准备 / prepare container / 环境准备 | flagos-container-preparation | `skills/flagos-container-preparation/SKILL.md` |
| 环境检查 / inspect environment / 服务前检查 | flagos-pre-service-inspection | `skills/flagos-pre-service-inspection/SKILL.md` |
| 启动服务 / start service / 健康检查 | flagos-service-startup | `skills/flagos-service-startup/SKILL.md` |
| 性能测试 / benchmark / vllm bench | flagos-performance-testing | `skills/flagos-performance-testing/SKILL.md` |
| 算子替换 / operator replacement / 算子优化 | flagos-operator-replacement | `skills/flagos-operator-replacement/SKILL.md` |
| 精度评测 / eval correctness / accuracy test | flagos-eval-correctness | `skills/flagos-eval-correctness/SKILL.md` |
| 日志分析 / analyze logs | flagos-log-analyzer | `skills/flagos-log-analyzer/SKILL.md` |

---

## 工作流（新模型迁移发布）

**强制按以下顺序执行，不可跳步或调换：**

**核心变更**：拿到环境后先验证初始服务可用，检测 plugin 和 FlagTree，再决定是否安装 FlagTree，最后进行三版性能测试。

**三版测试**：Native → Optimized FlagGems（≥80%）→ Full FlagGems

```
① container-preparation       → 容器准备（含本地权重检查 + 多入口自动识别）
② pre-service-inspection      → 环境检测（新增 FlagTree/plugin 探测）
③ service-startup (default)   → 以当前环境原样启动服务，验证初始环境可用
④ [询问用户] 是否安装 FlagTree?
   ├── 否 → 在当前环境进行三版测试
   └── 是 → ④a 安装 FlagTree → ④b 重启服务验证
             ├── 成功 → 在 plugin+FlagTree 环境进行三版测试
             └── 失败 → ④c 恢复环境（重新 run 容器 或 卸载 FlagTree）
                        → 在初始环境进行三版测试
⑤ eval-correctness (native)     → 精度评测（询问用户）
⑥ performance-testing (native)  → Native 性能基线（关闭 FlagGems）
⑦ service-startup (flagos)      → 启用全量 FlagGems
⑧ eval-correctness (full-flagos)→ 精度评测（询问用户）+ 算子报错自动处理
⑨ performance-testing (full)    → Full FlagGems 性能
⑩ [自动] 性能对比               → full_flagos/native ≥ 80%?
   ├── 是 → Optimized = Full，跳到 ⑬
   └── 否 → ⑪ operator-replacement（分组二分搜索）
             → 找到 ≥80% 的算子组合
⑫ performance-testing (optimized) → Optimized FlagGems 性能（搜索过程中已产出）
⑬ 三版性能对比 + 生成最终报告
```

**三版结果文件**：
- `native_performance.json` — Native（无 FlagGems）
- `flagos_full.json` — Full FlagGems（全量算子）
- `flagos_optimized.json` — Optimized FlagGems（≥80% 组合）

**FlagTree 安装失败恢复策略**：
1. **优先方案**：重新 `docker run` 一个新容器（最可靠，一步还原全部环境），需用户确认
2. **备选方案**（特殊环境如阿里云不能重启时）：`install_flagtree.sh uninstall` 卸载 FlagTree 恢复原始 triton

---

## 自动决策规则（零交互默认值）

以下决策**直接执行，不询问用户**：

| 决策项 | 默认值 | 说明 |
|--------|--------|------|
| FlagGems 仓库地址 | `https://github.com/FlagOpen/FlagGems.git` | 无需用户提供 |
| FlagTree 仓库地址 | `https://github.com/flagos-ai/FlagTree` | 无需用户提供 |
| FlagTree 默认版本 | `0.4.0` | NVIDIA 免编译安装 |
| FlagTree 安装源 | `https://resource.flagos.net/repository/flagos-pypi-hosted/simple` | pip index-url |
| 性能目标 | 80% of native | 不询问"目标是多少" |
| pip install 模式 | `pip install .`（非 editable） | 避免 `-e .` 在容器中的问题 |
| 服务端口 | 从 README/容器配置中提取 | 不询问端口号 |
| GPU 设备 | 使用全部可见 GPU | 不询问使用哪些卡 |

---

## 仅在以下情况询问用户（全流程预期 ≤5 次交互）

1. **docker run 命令最终确认** — 不可逆操作，需用户确认参数
2. **容器网络不通且需要代理配置** — 自动检测网络后才问
3. **搜索 3 轮仍未达标** — 需要用户决定是否继续
4. **精度评测是否执行** — 服务启动后、性能测试前，询问用户是否需要精度评测
5. **是否安装 FlagTree** — 步骤④，初始环境验证通过后询问
6. **FlagTree 安装失败时，是否重新 run 容器** — 恢复环境需用户确认

---

## 工具脚本部署

容器准备阶段（步骤①完成后），通过 `setup_workspace.sh` 一次性部署所有工具：

```bash
# 宿主机执行，一次性复制所有脚本到容器
bash skills/flagos-container-preparation/tools/setup_workspace.sh $CONTAINER
```

部署的脚本清单：
- `inspect_env.py` — 环境检查（替代 10+ 次 docker exec）
- `toggle_flaggems.py` — FlagGems 开关切换（替代 sed）
- `wait_for_service.sh` — 服务就绪检测（指数退避）
- `benchmark_runner.py` — 性能测试
- `performance_compare.py` — 性能对比
- `operator_optimizer.py` — 算子优化
- `operator_search.py` — 算子搜索编排
- `eval_monitor.py` — 评测监控
- `install_flagtree.sh` — FlagTree 安装/卸载/验证

---

## 网络问题自动降级策略

容器内网络不通时，**不立即询问用户**，按以下顺序自动处理：

1. 容器内尝试 `curl --connect-timeout 3 https://github.com` 检测
2. 如果失败 → 在**宿主机** `git clone` → `docker cp` 到容器
3. 宿主机也失败 → **此时才询问用户**是否有代理配置
4. 有代理 → 在容器内设置 `http_proxy/https_proxy` 后重试

---

## 标准性能对比输出格式

使用 `python performance_compare.py --format markdown` 生成标准 markdown 表格：

```
| Test Case | Concurrency | Native TPS | Optimized TPS | Opt/Nat    | Full TPS   | Full/Nat   |
| --------- | ----------- | ---------- | ------------- | ---------- | ---------- | ---------- |
| 1k→1k     | 256         | 17328      | 16800         | **97.0%**  | 17511      | **101.1%** |
```

格式规则：
- TPS 列使用 Total Token throughput（input + output）
- Test Case 使用简写 `1k→1k` 而非 `1k_input_1k_output`
- Ratio 列加粗显示
- 三版列：Native / Optimized FlagGems / Full FlagGems
- 当 Optimized = Full（全量已达标）时，Optimized 列显示 "= Full"

---

## 关键约束

1. **性能测试只能通过 `benchmark_runner.py` 执行**，禁止直接运行 `vllm bench serve`
2. **FlagGems 开关只能通过 `toggle_flaggems.py` 切换**，禁止手动 sed
3. **FlagTree 安装只能通过 `install_flagtree.sh` 执行**，禁止手动 pip install flagtree
4. **所有操作在 `/flagos-workspace` 目录下执行**，确保日志可从宿主机访问
5. **context.yaml 是 Skill 间共享状态**，每个 Skill 完成后必须更新

---

## 权限预配置说明

项目根目录下的 `settings.local.json` 是 Claude Code 的权限预批准配置。上方"自动初始化"步骤会在每次会话启动时自动部署，无需手动操作。

预批准的安全操作（无需每次确认）：
- 容器操作：`docker exec`、`docker cp`、`docker inspect`、`docker ps`、`docker start`、`docker logs`
- 健康检查：`curl -s http://localhost:*`
- 宿主机只读：`nvidia-smi`、`npu-smi`、`hostname`、`df`、`free`
- 工作目录：`/data/flagos-workspace/` 下的 mkdir、ls、cat、tail、find
- Git 操作：`git clone`
- 文件操作：`cp`、`ln -s`

**保留需要用户确认的危险操作**（不在预批准列表中）：
- `docker run` — 创建容器
- `docker pull` — 下载镜像
- `pip install/uninstall` — 改变容器环境
- `pkill` — 杀进程
- `modelscope download` — 大量下载
