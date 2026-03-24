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
| 综合评测 / comprehensive eval / 本地评测 / quick 评测 / evalscope | flagos-eval-comprehensive | `skills/flagos-eval-comprehensive/SKILL.md` |
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
⑤ eval-comprehensive (native)    → 精度评测（询问用户，quick 模式可跳过）
⑥ performance-testing (native)   → Native 性能基线（关闭 FlagGems）
⑦ service-startup (flagos)       → 启用全量 FlagGems
⑧ eval-comprehensive (full-flagos)→ 精度评测（**必须执行，不可跳过**）+ 算子报错自动处理
⑨ performance-testing (full)    → Full FlagGems 性能
⑩ [自动] 性能对比               → full_flagos/native ≥ 80%?
   ├── 是 → Optimized = Full，跳到 ⑬
   └── 否 → ⑪ operator-replacement（分组二分搜索）
             → 找到 ≥80% 的算子组合
⑫ performance-testing (optimized) → Optimized FlagGems 性能（搜索过程中已产出）
⑬ 三版性能对比 + 生成最终报告
```

### Quick 模式与正式评测（二阶段）

流程支持两种执行模式，用户在流程开始前选择：

**Quick 模式**（筛查阶段）：
- 全 ①-⑬ 步骤完整执行，流程和算子替换逻辑**与标准模式完全一致**
- 区别仅在于：性能测试用 `--strategy quick`（只跑 prefill1_decode512），精度评测用 `--quick`（AIME25 only）
- 目标：验证流程可走通 + 快速筛查算子问题（启动崩溃、eval 报错、精度不达标、性能不达标）
- 算子搜索内部始终用 quick benchmark，与外层模式无关
- **精度评测规则**：步骤⑤（Native 精度）可跳过；步骤⑧（FlagGems 精度）**绝对不能跳过**，因为开启 FlagGems 后必须验证算子兼容性和精度

**正式评测**（复测阶段）：
- Quick 筛查完毕、算子问题已修复后，从步骤⑤或⑥开始复测
- 性能测试切换为 `fast`（饱和即停）或 `comprehensive`（全跑）
- 精度评测切换为完整模式（AIME + ERQA 或远端 FlagRelease）
- 跳过 ①②③④，直接复用已修复的环境和算子配置
- 产出正式的三版结果文件用于最终报告

**三版结果文件**（均位于 `results/` 目录下）：
- `results/native_performance.json` — Native（无 FlagGems）
- `results/flagos_full.json` — Full FlagGems（全量算子）
- `results/flagos_optimized.json` — Optimized FlagGems（≥80% 组合）

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
| FlagTree 默认版本 | 按后端自动选择（NVIDIA 默认 `0.5.0rc1`） | `install_flagtree.sh list-vendors` 查看全部 |
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
4. **精度评测是否执行** — 仅步骤⑤（Native 精度）询问用户，quick 模式下可跳过；步骤⑧（FlagGems 精度）**强制执行不询问**
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
- `diagnose_ops.py` — 算子快速诊断（崩溃日志解析、精度分组测试、性能热点预扫描）
- `eval_monitor.py` — 评测监控
- `install_flagtree.sh` — FlagTree 安装/卸载/验证

---

## 宿主机工作目录结构

宿主机 `/data/flagos-workspace/<model>/` 挂载到容器 `/flagos-workspace`，统一使用四个子目录：

```
/data/flagos-workspace/<model>/          ← 挂载到容器 /flagos-workspace
├── results/                              # 最终交付物
│   ├── native_performance.json
│   ├── flagos_full.json
│   ├── flagos_optimized.json             # 仅不达标时产出
│   ├── ops_list.json
│   ├── performance_compare.csv           # 首次对比
│   ├── performance_compare_final.csv     # 最终三版对比
│   ├── aime_result.json
│   ├── erqa_result.json                  # quick 模式无此文件
│   └── eval_result.json                  # 远端评测结果
│
├── traces/                               # 每步留痕（JSON）
│   ├── 01_container_preparation.json
│   ├── 02_environment_inspection.json
│   ├── 03_service_startup_default.json
│   ├── 04_flagtree_installation.json     # 可选
│   ├── 05_eval_native.json               # 可选
│   ├── 06_perf_native.json
│   ├── 07_service_startup_flagos.json
│   ├── 08_eval_full_flagos.json          # 可选
│   ├── 09_perf_full_flagos.json
│   ├── 10_performance_compare.json
│   ├── 11_operator_replacement.json      # 仅不达标时
│   ├── 12_perf_optimized.json            # 仅不达标时
│   └── 13_final_report.json
│
├── logs/                                 # 运行日志
│   ├── startup_default.log
│   ├── startup_native.log
│   ├── startup_flagos.log
│   ├── eval_aime_progress.log
│   └── eval_erqa_progress.log
│
└── config/                               # 使用的配置快照
    ├── perf_config.yaml
    ├── eval_config.yaml
    └── context_snapshot.yaml             # 流程结束时的完整 context
```

目录创建时机：容器准备阶段由 `setup_workspace.sh` 自动创建。

---

## Trace 留痕规范

**强制规则**：每个 Skill 完成后，Claude 必须在 `traces/` 下写入对应步骤的 trace JSON 文件。

### Trace JSON 统一格式

```json
{
  "step": "01_container_preparation",
  "title": "容器准备",
  "timestamp_start": "2026-03-20T15:30:00",
  "timestamp_end": "2026-03-20T15:32:00",
  "duration_seconds": 120,
  "status": "success | failed | skipped",
  "actions": [
    {
      "action": "docker_run",
      "command": "docker run -d --name xxx --gpus all ...",
      "timestamp": "2026-03-20T15:30:05",
      "status": "success",
      "output_summary": "Container abc123 started"
    }
  ],
  "result_files": ["results/native_performance.json"],
  "context_updates": {
    "container.name": "xxx",
    "gpu.count": 8
  }
}
```

**字段说明**：
- `actions[]`: 该步骤中执行的每个关键操作
- `command`: 实际执行的完整命令字符串
- `output_summary`: 关键输出摘要（不是全量 stdout）
- `result_files`: 该步骤产出的结果文件路径（相对于工作目录）
- `context_updates`: 该步骤写入 context.yaml 的字段

### 每步 trace 记录内容

| 步骤 | trace 文件 | 记录的 actions |
|------|-----------|----------------|
| ①容器准备 | `01_container_preparation.json` | docker run 命令（含完整参数）、setup_workspace 部署结果 |
| ②环境检测 | `02_environment_inspection.json` | inspect_env.py 命令、关键输出（包版本、FlagGems 控制方式、FlagTree 状态） |
| ③初始启动 | `03_service_startup_default.json` | 启动命令、env vars、健康检查结果、端口 |
| ④FlagTree | `04_flagtree_installation.json` | install_flagtree.sh 命令、安装结果、verify 输出 |
| ⑤精度native | `05_eval_native.json` | 评测方式(remote/local/quick)、提交参数/命令、精度结果 |
| ⑥性能native | `06_perf_native.json` | benchmark_runner.py 命令（含 --strategy）、用例列表、峰值吞吐 |
| ⑦启动flagos | `07_service_startup_flagos.json` | toggle 命令、启动命令、ops_list 记录命令、健康检查 |
| ⑧精度full | `08_eval_full_flagos.json` | 同⑤ |
| ⑨性能full | `09_perf_full_flagos.json` | 同⑥ |
| ⑩性能对比 | `10_performance_compare.json` | compare 命令、对比结果摘要（达标/不达标）、返回码 |
| ⑪算子替换 | `11_operator_replacement.json` | 搜索策略、每轮测试命令、禁用算子列表、最终性能比 |
| ⑫性能optimized | `12_perf_optimized.json` | 同⑥ |
| ⑬最终报告 | `13_final_report.json` | 三版对比命令、最终对比表格、结论 |

### Trace 写入方式

由 Claude 编排层通过 shell heredoc 写 JSON 到容器内 `/flagos-workspace/traces/` 目录，例如：

```bash
docker exec $CONTAINER bash -c "cat > /flagos-workspace/traces/01_container_preparation.json << 'TRACE_EOF'
{...trace JSON...}
TRACE_EOF"
```

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
- TPS 列使用 Total token throughput（input + output）
- Test Case 使用简写 `1k→1k` 而非 `1k_input_1k_output`
- Ratio 列加粗显示
- 三版列：Native / Optimized FlagGems / Full FlagGems
- 当 Optimized = Full（全量已达标）时，Optimized 列显示 "= Full"

---

## 最终报告格式

流程结束时（步骤⑬）必须输出完整的迁移发布报告：

**交付物清单**：
- `results/` — 性能/精度结果文件
- `traces/` — 全流程执行留痕
- `logs/` — 服务和评测运行日志
- `config/context_snapshot.yaml` — 流程结束时的完整 context 快照

```
FlagOS 迁移发布报告
========================================
模型: <model_name>
GPU: <gpu_count>x <gpu_type>
容器: <container_name>

算子状态:
  全量算子: XX 个
  最终启用: XX 个
  剔除算子: <op1>, <op2>, ...
  剔除原因:
    - <op1>: 精度评测报错 (CUDA error)
    - <op2>: 性能拖慢 (禁用后 +XX%)

精度评测:
  AIME: XX.X%  ERQA: XX.X%
  状态: 通过 / 有问题

性能对比:
| Test Case | Conc | Native TPS | Optimized TPS | Opt/Nat   | Full TPS | Full/Nat  |
| --------- | ---- | ---------- | ------------- | --------- | -------- | --------- |
| 1k→1k     | 256  | XXXXX      | XXXXX         | **XX.X%** | XXXXX    | **XX.X%** |

结论: FlagOS Optimized 达标(≥80%) / 不达标
========================================
```

---

## 关键约束

1. **性能测试只能通过 `benchmark_runner.py` 执行**，禁止直接运行 `vllm bench serve`
2. **FlagGems 开关只能通过 `toggle_flaggems.py` 切换**，禁止手动 sed
3. **FlagTree 安装只能通过 `install_flagtree.sh` 执行**，禁止手动 pip install flagtree
4. **所有操作在 `/flagos-workspace` 目录下执行**，产出文件按类型分目录：`results/`（交付物）、`traces/`（留痕）、`logs/`（日志）、`config/`（配置快照）
5. **context.yaml 是 Skill 间共享状态**，每个 Skill 完成后必须更新
6. **每个 Skill 完成后必须写入对应的 trace JSON**，记录实际执行的命令、参数和关键输出
7. **禁止添加 SKILL.md 未记录的 vLLM/sglang 启动参数**（如 `--enforce-eager`、`--disable-log-stats` 等），遇到启动问题应分析日志找根因，而非猜测参数绕过
8. **精度评测和性能测试严禁同时进行**。必须等一个完全结束后再启动另一个。并发执行会互相抢占 GPU 资源，导致两边结果都不可信。启动前必须检查是否有正在运行的评测/测试进程
9. **算子列表以 `flaggems_enable_oplist.txt` 为唯一权威来源**。每次服务启动后必须检查该文件（默认 `/tmp/flaggems_enable_oplist.txt`）：
   - **文件存在且有内容** → FlagGems 实际在运行，以此文件内容作为当前生效的算子列表
   - **文件不存在或为空** → FlagGems 未启用，不依赖任何缓存的算子列表
   - 每次 FlagGems 重新启动都会**重新生成**此文件，内容反映 blacklist 等配置生效后的实际结果
   - 如果启动模式为 native 但文件残留 → 是上次 flagos 的旧数据，不可作为当前算子列表
   - 所有后续操作（算子替换、搜索、性能对比、报告生成）中的"当前算子列表"均以此文件为准

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
