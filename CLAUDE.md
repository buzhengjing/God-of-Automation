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
| 组件升级 / flag upgrade / upgrade flaggems | flagos-flag-upgrade | `skills/flagos-flag-upgrade/SKILL.md` |
| 精度评测 / eval correctness / accuracy test | flagos-eval-correctness | `skills/flagos-eval-correctness/SKILL.md` |
| 日志分析 / analyze logs | flagos-log-analyzer | `skills/flagos-log-analyzer/SKILL.md` |

---

## 场景识别规则

收到用户指令后，**先判断场景再执行**：

| 用户指令特征 | 场景 |
|-------------|------|
| 包含 "升级" / "upgrade" / ModelScope URL / HuggingFace URL | **Scenario B**（旧模型升级） |
| 包含 "迁移" / "发布" / "新模型" / 容器名 / 镜像地址 | **Scenario A**（新模型迁移发布） |
| 不确定 | 默认 **Scenario A** |

---

## Scenario A 工作流（新模型迁移发布）

**强制按以下顺序执行，不可跳步或调换：**

```
① container-preparation     → 容器准备（含本地权重检查 + 多入口自动识别）
② pre-service-inspection    → 环境检测（一次 inspect_env.py 完成）
③ service-startup (native)  → 关闭 FlagGems，启动 native 模式
④ performance-testing       → Native 性能基线
⑤ service-startup (flagos)  → 启用 FlagGems，重启服务
⑥ performance-testing       → FlagOS 初始性能
⑦ 自动性能对比              → flagos/native ≥ 80%?
   ├── 是 → 跳到 ⑨
   └── 否 → ⑧ operator-replacement（贪心搜索）
⑨ eval-correctness           → 精度评测（询问用户是否执行）
⑩ 生成最终报告
```

## Scenario B 工作流（旧模型升级 FlagGems）

**强制按以下顺序执行 — 先测后升级：**

```
① container-preparation     → 容器准备（含本地权重检查 + 解析 README / 接入容器）
② pre-service-inspection    → 环境检测
③ service-startup (native)  → Native 模式启动
④ performance-testing       → Native 性能基线 → native_performance.json
⑤ service-startup (flagos)  → FlagOS 模式启动（升级前）
⑥ performance-testing       → 升级前 FlagOS 性能 → flagos_before_upgrade.json
⑦ flag-upgrade              → FlagGems 组件升级（默认 main 分支）
⑧ service-startup (flagos)  → 升级后 FlagOS 模式启动
⑨ performance-testing       → 升级后性能 → flagos_after_upgrade.json
⑩ 三方性能对比              → native vs before vs after
   └── 升级后 < 80% → operator-replacement
⑪ eval-correctness           → 精度评测（询问用户是否执行）
⑫ 生成最终报告
```

---

## 自动决策规则（零交互默认值）

以下决策**直接执行，不询问用户**：

| 决策项 | 默认值 | 说明 |
|--------|--------|------|
| Scenario B 升级分支 | `main` | 不询问"使用哪个分支" |
| FlagGems 仓库地址 | `https://github.com/FlagOpen/FlagGems.git` | 无需用户提供 |
| FlagScale 仓库地址 | `https://github.com/FlagOpen/FlagScale.git` | 无需用户提供 |
| FlagCX 仓库地址 | `https://github.com/FlagOpen/FlagCX.git` | 无需用户提供 |
| 性能目标 | 80% of native | 不询问"目标是多少" |
| pip install 模式 | `pip install .`（非 editable） | 避免 `-e .` 在容器中的问题 |
| 服务端口 | 从 README/容器配置中提取 | 不询问端口号 |
| GPU 设备 | 使用全部可见 GPU | 不询问使用哪些卡 |

---

## 仅在以下情况询问用户（全流程预期 ≤3 次交互）

1. **docker run 命令最终确认** — 不可逆操作，需用户确认参数
2. **容器网络不通且需要代理配置** — 自动检测网络后才问
3. **贪心搜索 3 轮仍未达标** — 需要用户决定是否继续
4. **升级后性能严重劣化（<70%）** — 需要用户确认是否回退
5. **精度评测是否执行** — 性能测试完成后，询问用户是否需要精度评测

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
- `upgrade_component.py` — 组件升级（含网络降级）
- `wait_for_service.sh` — 服务就绪检测（指数退避）
- `benchmark_runner.py` — 性能测试
- `performance_compare.py` — 性能对比
- `operator_optimizer.py` — 算子优化

---

## 网络问题自动降级策略

容器内网络不通时，**不立即询问用户**，按以下顺序自动处理：

1. 容器内尝试 `curl --connect-timeout 3 https://github.com` 检测
2. 如果失败 → 在**宿主机** `git clone` → `docker cp` 到容器
3. 宿主机也失败 → **此时才询问用户**是否有代理配置
4. 有代理 → 在容器内设置 `http_proxy/https_proxy` 后重试

---

## 标准性能对比输出格式

**Scenario B（升级场景）标准输出表格**：

```
| Test Case | Native TPS | FlagOS Before TPS | Ratio      | FlagOS After TPS | Ratio      | Best Concurrency |
| --------- | ---------- | ----------------- | ---------- | ---------------- | ---------- | ---------------- |
| 1k→1k     | 17328      | 17511             | **101.1%** | 17325            | **100.0%** | 256              |
```

格式规则：
- TPS 列使用 Total Token throughput（input + output）
- Test Case 使用简写 `1k→1k` 而非 `1k_input_1k_output`
- Ratio 列加粗显示
- 包含 Best Concurrency 列
- 使用 `python performance_compare.py --format markdown` 生成

**Scenario A 标准输出**：仅 Native / FlagOS Initial / FlagOS Optimized 三列。

---

## 关键约束

1. **性能测试只能通过 `benchmark_runner.py` 执行**，禁止直接运行 `vllm bench serve`
2. **FlagGems 开关只能通过 `toggle_flaggems.py` 切换**，禁止手动 sed
3. **所有操作在 `/flagos-workspace` 目录下执行**，确保日志可从宿主机访问
4. **context.yaml 是 Skill 间共享状态**，每个 Skill 完成后必须更新

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
