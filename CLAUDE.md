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
| 精度评测 / eval correctness / accuracy test / 远端评测 / FlagRelease / flageval / 综合评测 / comprehensive eval / 本地评测 / quick 评测 / evalscope / GPQA | flagos-eval-comprehensive | `skills/flagos-eval-comprehensive/SKILL.md` |
| 日志分析 / analyze logs | flagos-log-analyzer | `skills/flagos-log-analyzer/SKILL.md` |

---

## 工作流（新模型迁移发布）

**强制按以下顺序执行，不可跳步或调换：**

**核心变更**：拿到环境后先验证初始服务可用，检测 plugin，再进行三版性能测试。

**三版测试**：V1 (Native) → V2 (Full FlagGems) → V3 (Optimized FlagGems)

```
① container-preparation       → 容器准备（含本地权重检查 + 多入口自动识别）
② pre-service-inspection      → 环境检测（plugin 探测）
③ service-startup (default)   → 以当前环境原样启动服务，验证初始环境可用
④ eval-comprehensive (V1)     → V1 精度评测（询问用户，quick 模式可跳过）
⑤ performance-testing (V1)    → V1 性能基线（关闭 FlagGems）
⑥ service-startup (flagos)    → 启用全量 FlagGems
⑦ eval-comprehensive (V2)     → V2 精度评测（**必须执行，不可跳过**）+ V1 vs V2 精度对比 + 算子报错自动处理
⑧ performance-testing (V2)    → V2 Full FlagGems 性能
⑨ [自动] 性能对比             → V2/V1 ≥ 80%?
   ├── 是 → V3 = V2，跳到 ⑫
   └── 否 → ⑩ operator-replacement（分组二分搜索）
             → 找到 ≥80% 的算子组合
⑪ performance-testing (V3)    → V3 Optimized FlagGems 性能（搜索过程中已产出）
⑫ 三版性能对比 + 生成最终报告
```

### Quick 模式与正式评测（二阶段）

流程支持两种执行模式，用户在流程开始前选择：

**Quick 模式**（筛查阶段）：
- 全 ①-⑫ 步骤完整执行，流程和算子替换逻辑**与标准模式完全一致**
- 区别仅在于：性能测试用 `--strategy quick`（只跑 4k_input_1k_output + max），精度评测用 GPQA Diamond 快速评测（fast_gpqa.py，自动适配 thinking/non-thinking）
- 目标：验证流程可走通 + 快速筛查算子问题（启动崩溃、eval 报错、精度不达标、性能不达标）
- 算子搜索内部始终用 quick benchmark，与外层模式无关
- **精度评测规则**：步骤④（V1 精度）可跳过；步骤⑦（V2 精度）**绝对不能跳过**，因为开启 FlagGems 后必须验证算子兼容性和精度

**正式评测**（复测阶段）：
- Quick 筛查完毕、算子问题已修复后，从步骤④或⑤开始复测
- 性能测试切换为 `fast`（饱和即停）或 `comprehensive`（全跑）
- 精度评测切换为完整模式（GPQA Diamond 全量 或远端 FlagRelease）
- 跳过 ①②③，直接复用已修复的环境和算子配置
- 产出正式的三版结果文件用于最终报告

**三版结果文件**（均位于 `results/` 目录下）：
- `results/native_performance.json` — V1 (Native，无 FlagGems)
- `results/flagos_full.json` — V2 (Full FlagGems，全量算子)
- `results/flagos_optimized.json` — V3 (Optimized FlagGems，≥80% 组合)

---

## 自动决策规则（零交互默认值）

以下决策**直接执行，不询问用户**：

| 决策项 | 默认值 | 说明 |
|--------|--------|------|
| FlagGems 仓库地址 | `https://github.com/FlagOpen/FlagGems.git` | 无需用户提供 |
| 性能目标 | 每个用例的每个并发级别均 ≥ 80% of V1 | 不询问"目标是多少" |
| pip install 模式 | `pip install .`（非 editable） | 避免 `-e .` 在容器中的问题 |
| 服务端口 | 从 README/容器配置中提取 | 不询问端口号 |
| GPU 设备 | 使用全部可见 GPU | 不询问使用哪些卡 |

---

## 仅在以下情况询问用户（全流程预期 ≤4 次交互）

1. **docker run 命令最终确认** — 不可逆操作，需用户确认参数
2. **任何网络操作失败** — pip install、数据集下载、git clone、docker pull 失败一次即问代理，不反复重试（详见"网络问题处理策略"）
3. **搜索 3 轮仍未达标** — 需要用户决定是否继续
4. **精度评测是否执行** — 仅步骤④（V1 精度）询问用户，quick 模式下可跳过；步骤⑦（V2 精度）**强制执行不询问**

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
- `generate_moban_report.py` — moban 格式报告生成（三版原始 benchmark JSON + 算子信息）
- `operator_optimizer.py` — 算子优化
- `operator_search.py` — 算子搜索编排
- `diagnose_ops.py` — 算子快速诊断（崩溃日志解析、精度分组测试、性能热点预扫描）
- `eval_monitor.py` — 评测监控

---

## 宿主机工作目录结构

宿主机 `/data/flagos-workspace/<model>/` 挂载到容器 `/flagos-workspace`，统一使用四个子目录：

```
/data/flagos-workspace/<model>/          ← 挂载到容器 /flagos-workspace
├── results/                              # 最终交付物
│   ├── native_performance.json              # V1 性能
│   ├── flagos_full.json                     # V2 性能
│   ├── flagos_optimized.json                # V3 性能（仅不达标时产出）
│   ├── ops_list.json
│   ├── performance_compare.csv              # 首次对比
│   ├── performance_compare_final.csv        # 最终三版对比
│   ├── gpqa_native.json                     # V1 精度 (GPQA Diamond)
│   ├── gpqa_flagos.json                     # V2 精度 (GPQA Diamond)
│   └── eval_result.json                     # 远端评测结果
│
├── traces/                               # 每步留痕（JSON）
│   ├── 01_container_preparation.json
│   ├── 02_environment_inspection.json
│   ├── 03_service_startup_default.json
│   ├── 04_eval_v1.json                  # V1 精度（可选）
│   ├── 05_perf_v1.json
│   ├── 06_service_startup_flagos.json
│   ├── 07_eval_v2.json
│   ├── 08_perf_v2.json
│   ├── 09_performance_compare.json
│   ├── 10_operator_replacement.json      # 仅不达标时
│   ├── 11_perf_v3.json                   # 仅不达标时
│   └── 12_final_report.json
│
├── logs/                                 # 运行日志
│   ├── startup_default.log
│   ├── startup_native.log
│   ├── startup_flagos.log
│   └── eval_gpqa_progress.log
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

**计时强制规则**：
- 每个 Skill 开始时记录 `timestamp_start`（ISO 8601），结束时记录 `timestamp_end` 和 `duration_seconds`
- 完成 trace 写入后，同步更新 `context.yaml` 的 `timing.steps.<step_name>` 字段
- 步骤①开始时额外写入 `timing.workflow_start`
- 步骤⑫完成时写入 `timing.workflow_end` 和 `timing.total_duration_seconds`（= workflow_end - workflow_start）

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
| ②环境检测 | `02_environment_inspection.json` | inspect_env.py 命令、关键输出（包版本、FlagGems 控制方式） |
| ③初始启动 | `03_service_startup_default.json` | 启动命令、env vars、健康检查结果、端口 |
| ④精度V1 | `04_eval_v1.json` | 评测方式(GPQA Diamond)、命令、精度结果 |
| ⑤性能V1 | `05_perf_v1.json` | benchmark_runner.py 命令（含 --strategy）、用例列表、峰值吞吐 |
| ⑥启动flagos | `06_service_startup_flagos.json` | toggle 命令、启动命令、ops_list 记录命令、健康检查 |
| ⑦精度V2 | `07_eval_v2.json` | 同④ + V1 vs V2 精度对比结果 |
| ⑧性能V2 | `08_perf_v2.json` | 同⑤ |
| ⑨性能对比 | `09_performance_compare.json` | compare 命令、对比结果摘要（达标/不达标）、返回码 |
| ⑩算子替换 | `10_operator_replacement.json` | 搜索策略、每轮测试命令、禁用算子列表、启用算子列表、最终性能比 |
| ⑪性能V3 | `11_perf_v3.json` | 同⑤ |
| ⑫最终报告 | `12_final_report.json` | 三版对比命令、最终对比表格、结论 |

### Trace 写入方式

由 Claude 编排层通过 shell heredoc 写 JSON 到容器内 `/flagos-workspace/traces/` 目录，例如：

```bash
docker exec $CONTAINER bash -c "cat > /flagos-workspace/traces/01_container_preparation.json << 'TRACE_EOF'
{...trace JSON...}
TRACE_EOF"
```

---

## 网络问题处理策略

所有网络操作（pip install、数据集下载、git clone、docker pull）遵循同一规则：

1. **尝试一次**，如果失败且错误信息包含网络关键词（timeout、connection refused、DNS、SSL、Could not resolve host、Network unreachable），**立即判定为网络问题**
2. **立即询问用户**：告知哪个操作因网络失败，索要代理地址（http_proxy）或镜像源
3. 用户提供代理后，设置环境变量重试：
   - 容器内：`docker exec -e http_proxy=xxx -e https_proxy=xxx`
   - pip：额外支持 `-i 镜像源` 如用户提供
4. 将代理配置写入 context.yaml `network` 字段，后续网络下载操作自动复用，不再重复询问
5. **下载完成后立即关闭代理**（`unset http_proxy https_proxy no_proxy`），避免代理影响后续本地服务访问（如 localhost API 调用）

**禁止行为**：
- 不要在网络失败后反复重试同一操作
- 不要尝试换源、换命令等 workaround
- 不要在宿主机上尝试替代方案后才问用户
- 识别到网络问题就停，问用户，拿到代理再继续

---

## 标准性能对比输出格式

使用 `python performance_compare.py --format markdown` 生成标准 markdown 表格：

```
| Test Case | Concurrency | V1 TPS | V3 TPS | V3/V1      | V2 TPS     | V2/V1      |
| --------- | ----------- | ------ | ------ | ---------- | ---------- | ---------- |
| 1k→1k     | 256         | 17328  | 16800  | **97.0%**  | 17511      | **101.1%** |
```

格式规则：
- TPS 列使用 Total token throughput（input + output）
- Test Case 使用简写 `1k→1k` 而非 `1k_input_1k_output`
- Ratio 列加粗显示
- 三版列：V1 (Native) / V3 (Optimized FlagGems) / V2 (Full FlagGems)
- 当 V3 = V2（全量已达标）时，V3 列显示 "= V2"

---

## 最终报告格式

流程结束时（步骤⑬）必须输出完整的迁移发布报告：

**交付物清单**：
- `results/` — 性能/精度结果文件
- `results/benchmark_report_moban.md` — moban 格式原始数据报告（三版 benchmark JSON + 算子信息）
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
  全量算子 (V2): XX 个
  最终启用 (V3): XX 个
  剔除算子: <op1>, <op2>, ...
  剔除原因:
    精度问题: <op1> (CUDA error), <op2> (精度偏差 >5%)
    性能问题: <op3> (禁用后 +XX%)

精度评测:
  GPQA Diamond: XX.X% (V1) / XX.X% (V2)
  V1 vs V2 偏差: X.XX% (阈值 5%)
  状态: 通过 / 有问题

性能对比:
| Test Case | Conc | V1 TPS | V3 TPS | V3/V1     | V2 TPS | V2/V1     |
| --------- | ---- | ------ | ------ | --------- | ------ | --------- |
| 1k→1k     | 256  | XXXXX  | XXXXX  | **XX.X%** | XXXXX  | **XX.X%** |

流程耗时:
  全流程: XXh XXm XXs
  ①容器准备:     XXm XXs
  ②环境检测:     XXm XXs
  ③初始启动:     XXm XXs
  ④精度V1:       XXm XXs
  ⑤性能V1:       XXm XXs
  ⑥启动FlagGems: XXm XXs
  ⑦精度V2:       XXm XXs
  ⑧性能V2:       XXm XXs
  ⑨性能对比:     XXm XXs
  ⑩算子替换:     XXm XXs
  ⑪性能V3:       XXm XXs
  ⑫最终报告:     XXm XXs

结论: V3 (Optimized) 达标(≥80%) / 不达标
========================================
```

**同步生成 moban 格式报告**：在输出上述标准报告的同时，必须调用 `generate_moban_report.py` 生成 `results/benchmark_report_moban.md`。该报告按 V3 → V2 → V1 顺序输出三版原始 benchmark JSON 数据和算子替换信息，没有数据的版本自动跳过不写入。详见 `flagos-performance-testing/SKILL.md` 步骤 9.1。

---

## 关键约束

1. **性能测试只能通过 `benchmark_runner.py` 执行**，禁止直接运行 `vllm bench serve`
2. **FlagGems 开关只能通过 `toggle_flaggems.py` 切换**，禁止手动 sed
3. **所有操作在 `/flagos-workspace` 目录下执行**，产出文件按类型分目录：`results/`（交付物）、`traces/`（留痕）、`logs/`（日志）、`config/`（配置快照）
4. **context.yaml 是 Skill 间共享状态**，每个 Skill 完成后必须更新
5. **每个 Skill 完成后必须写入对应的 trace JSON**，记录实际执行的命令、参数和关键输出
6. **禁止添加 SKILL.md 未记录的 vLLM/sglang 启动参数**（如 `--enforce-eager`、`--disable-log-stats` 等），遇到启动问题应分析日志找根因，而非猜测参数绕过
7. **精度评测和性能测试严禁同时进行**。必须等一个完全结束后再启动另一个。并发执行会互相抢占 GPU 资源，导致两边结果都不可信。启动前必须检查是否有正在运行的评测/测试进程
8. **性能达标判定粒度：每个用例的每个并发级别**。不是只看平均值或最佳并发，而是 `performance_compare.py` 中所有 ratio 的最小值 ≥ 80% 才算达标。包括 quick 模式也遵循此规则
8. **算子列表以 `flaggems_enable_oplist.txt` 为唯一权威来源**。每次服务启动后必须检查该文件（默认 `/tmp/flaggems_enable_oplist.txt`）：
   - **文件存在且有内容** → FlagGems 实际在运行，以此文件内容作为当前生效的算子列表
   - **文件不存在或为空** → FlagGems 未启用，不依赖任何缓存的算子列表
   - 每次 FlagGems 重新启动都会**重新生成**此文件，内容反映 blacklist 等配置生效后的实际结果
   - 如果启动模式为 native 但文件残留 → 是上次 flagos 的旧数据，不可作为当前算子列表
   - 所有后续操作（算子替换、搜索、性能对比、报告生成）中的"当前算子列表"均以此文件为准
9. **容器内 Python 必须用 conda 环境**。所有 `docker exec` 中的 python3/pip 命令必须加 `PATH=/opt/conda/bin:$PATH` 前缀，禁止依赖容器默认 `/usr/bin/python3`（系统 Python 缺少 torch/requests/yaml 等包）

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
