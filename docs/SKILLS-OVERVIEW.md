# Skills 概览

本文档整理了 FlagOS GPU 性能测试自动化框架中所有 Skill 的功能说明和执行顺序。

**支持双场景**：
- **Scenario A**：新模型迁移发布（性能驱动的全流程）
- **Scenario B**：旧模型升级 FlagGems（升级前后对比）

**支持双执行模式**：
- **Host 模式**：Claude Code 在宿主机，通过 `docker exec` 操作容器
- **Container 模式**：Claude Code 在容器内，直接执行命令

**支持多入口**：
- 已有容器 → 直接接入
- 已有镜像 → 创建容器
- README 链接 → 解析后创建容器

---

## 统一工作目录

**核心设计**：所有操作在统一挂载的 `/flagos-workspace` 目录下进行，宿主机可实时访问日志和结果。

```
宿主机: /data/flagos-workspace/<model_name>/
                      ↓ 挂载
容器内: /flagos-workspace/
    ├── scripts/              # 自动化脚本
    │   ├── benchmark_runner.py
    │   ├── performance_compare.py
    │   └── operator_optimizer.py
    ├── logs/                 # 操作日志
    ├── results/              # 性能数据
    │   ├── native_performance.json
    │   ├── flagos_initial.json
    │   ├── flagos_optimized.json
    │   ├── operator_config.json
    │   ├── performance_compare.csv
    │   ├── flagos_before_upgrade.json   # Scenario B
    │   └── flagos_after_upgrade.json    # Scenario B
    ├── reports/              # 报告
    │   ├── env_report.md
    │   ├── flag_gems_detection.md
    │   └── final_report.md
    ├── output/               # 服务日志
    ├── eval/                 # 评测结果
    ├── perf/                 # 兼容旧性能测试
    └── shared/
        └── context.yaml
```

---

## 双场景流程图

### Scenario A：新模型迁移发布

```
① container-preparation     自动识别入口（已有容器/已有镜像/README）
        ↓
② pre-service-inspection    环境检测 + FlagGems 深度探测
        ↓                   → env_report.md + flag_gems_detection.md
③ 自动判断任务              根据环境自动决定流程
        ↓
④ service-startup (native)  关闭 FlagGems → 启动服务
        ↓
⑤ performance-testing       原生性能基线 → native_performance.json
        ↓
⑥ service-startup (flagos)  启用 FlagGems → 启动服务
        ↓
⑦ performance-testing       FlagOS 初始性能 → flagos_initial.json
        ↓
⑧ 自动性能对比判断          flagos / native >= 80%？
    ├── 是 → 跳到 ⑩
    └── 否 → ⑨
        ↓
⑨ operator-replacement      自动贪心搜索最优算子集
        ↓                   → flagos_optimized.json
⑩ [可选] eval-correctness   精度评测（默认跳过）
        ↓
⑪ 自动生成最终报告          final_report.md + performance_compare.csv
```

**自动化**：步骤③~⑪无需人工干预。仅在以下情况询问用户：
- docker run 命令最终确认
- 是否执行精度评测
- 贪心搜索 3 轮仍未达标时

### Scenario B：旧模型升级 FlagGems

```
① container-preparation     解析 README / 接入已有容器
        ↓
② pre-service-inspection    环境检测 + 版本冲突检查
        ↓
③ 旧版性能基线测试
   ③a service-startup (native) → native_performance.json
   ③b service-startup (flagos) → flagos_before_upgrade.json
        ↓
④ flag-upgrade              FlagGems 自动升级
        ↓
⑤ 升级后验证
    ├── 成功 → benchmark → flagos_after_upgrade.json
    └── 失败 → 自动恢复旧环境 → 算子优化
        ↓
⑥ [条件] operator-replacement  升级后性能 < 80% 时自动触发
        ↓
⑦ [可选] eval-correctness   精度评测
        ↓
⑧ 自动生成最终报告          含升级前后对比
```

---

## Skills 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     主流程 (顺序执行)                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ① container-preparation    多入口容器准备（已有容器/镜像/README）     │
│         ↓                                                           │
│  ② pre-service-inspection   环境检测 + FlagGems 深度探测 + 报告       │
│         ↓                                                           │
│  ③ service-startup          启动服务（支持 native/flagos 模式切换）    │
│         ↓                                                           │
│  ④ performance-testing      性能测试（并发搜索+早停+自动对比）         │
│         ↓                                                           │
│  ⑤ eval-correctness         精度评测（可选）                          │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                     独立工具 (按需调用)                               │
├─────────────────────────────────────────────────────────────────────┤
│  ⑥ operator-replacement     算子替换 + 贪心搜索优化                   │
│  ⑦ flag-upgrade             flag 组件升级（Scenario B 核心）          │
│  ⑧ log-analyzer             日志分析 + 失败恢复指引                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Skills 详细说明

### ① flagos-container-preparation (多入口容器准备)

| 属性 | 说明 |
|------|------|
| **功能** | 自动识别入口类型（容器名/镜像/URL），检测 GPU，创建或接入容器 |
| **版本** | 3.0.0 |
| **依赖** | 无 (流程起点) |
| **触发词** | `container preparation`, `prepare container`, `容器准备`, `环境准备` |

**三种入口**：

| 入口 | 用户提供什么 | 系统做什么 |
|------|-------------|-----------|
| 已有容器 | 容器名/ID | docker inspect → 验证 → 接入 |
| 已有镜像 | 镜像地址 + 模型信息 | docker run 创建 |
| README | URL 链接 | WebFetch → 解析 → docker pull + run |

**输出字段:**
```yaml
entry.type, entry.source
model.name, model.url, model.local_path
container.name, container.status
image.name, image.tag
gpu.vendor, gpu.count, gpu.visible_devices_env
workspace.host_path, workspace.container_path
```

---

### ② flagos-pre-service-inspection (环境检测 + 深度探测)

| 属性 | 说明 |
|------|------|
| **功能** | 执行模式检测 + 核心组件检查 + FlagGems 多维度深度探测 + 报告生成 |
| **版本** | 3.0.0 |
| **依赖** | `flagos-container-preparation` |
| **触发词** | `pre-service inspection`, `inspect environment`, `服务前检查`, `环境检查` |

**新增能力**：
- 步骤 0：执行模式检测（host / container）
- 步骤 3.5：多维度 FlagGems 集成方式探测（环境变量/插件入口/代码扫描/脚本扫描/配置文件）
- 步骤 3.6：推导 FlagGems 启用/关闭方法
- 步骤 6：生成 `env_report.md` + `flag_gems_detection.md`

**输出字段:**
```yaml
execution.mode, execution.cmd_prefix
inspection.core_packages, inspection.flag_packages
inspection.flaggems_capabilities
flaggems_control.enable_method, flaggems_control.disable_method, flaggems_control.integration_type
```

---

### ③ flagos-service-startup (服务启动 — 支持模式切换)

| 属性 | 说明 |
|------|------|
| **功能** | 生成启动命令、支持 native/flagos 模式切换、验证健康状态、失败自动恢复 |
| **版本** | 3.0.0 |
| **依赖** | `flagos-pre-service-inspection` |
| **触发词** | `service startup`, `start service`, `启动服务`, `health check` |

**启动模式**：

| 模式 | 说明 | 使用场景 |
|------|------|----------|
| native | 关闭 FlagGems | 原生性能基线 |
| flagos | 启用 FlagGems | FlagOS 性能测试 |
| default | 原始配置 | 不指定模式时 |

**FlagGems 开关切换**：不再硬编码 `USE_FLAGGEMS=0/1`，根据 `flaggems_control.enable_method` 和 `disable_method` 动态决定。

**失败恢复**：FlagOS 模式失败 → 自动切回 Native 验证 → Native 也失败则报告环境问题。

**输出字段:**
```yaml
service.host, service.port, service.process_id, service.healthy, service.model_id
service.log_path, service.gems_txt_path, service.initial_operator_list
runtime.framework, runtime.gpu_count, runtime.flaggems_enabled
```

---

### ④ flagos-performance-testing (性能测试 — 自动对比+优化触发)

| 属性 | 说明 |
|------|------|
| **功能** | 性能基准测试，支持并发自动搜索+早停、native/flagos 对比、自动优化触发 |
| **版本** | 3.0.0 |
| **依赖** | `flagos-service-startup` |
| **触发词** | `性能测试`, `benchmark`, `vllm bench`, `吞吐量测试` |

**新增脚本**：
- `benchmark_runner.py`：重构版测试入口，支持 `--concurrency-search`（吞吐增长 < 3% 时早停）
- `performance_compare.py`：多结果对比 + CSV 生成

**自动化流程**：
1. Native benchmark → `native_performance.json`
2. FlagOS benchmark → `flagos_initial.json`
3. 自动对比 → 是否 ≥ 80%
4. 不达标 → 触发算子优化 → `flagos_optimized.json`
5. 生成 `performance_compare.csv`

**输出字段:**
```yaml
native_perf.result_path, native_perf.output_throughput, native_perf.total_throughput
flagos_perf.initial_path, flagos_perf.optimized_path
```

---

### ⑤ flagos-eval-correctness (精度评测 — 可选)

| 属性 | 说明 |
|------|------|
| **功能** | 自动化正确性评测，优先远端 FlagEval API，支持本地降级 |
| **版本** | 3.1.0 |
| **依赖** | `flagos-service-startup` |
| **触发词** | `精度评测`, `正确性评测`, `accuracy test`, `eval correctness` |

**在双场景中**：默认跳过，用户指定时执行。

**评测方式**: 远端 FlagEval API → 本地评测降级。

**错误处理闭环**: 算子失败 → 关闭问题算子 → 重启 → 重评。

---

### ⑥ flagos-operator-replacement (算子替换 + 优化) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 被动排除（评测报错）+ 主动贪心搜索优化（性能驱动） |
| **版本** | 3.0.0 |
| **依赖** | 无 (可随时调用) |
| **触发词** | `operator replacement`, `replace operator`, `算子替换`, `算子优化` |

**两种模式**：
1. 被动排除：Layer 1-4 分层降级（YAML → API → 源码修改）
2. 主动优化：`operator_optimizer.py` 贪心搜索最优算子集

**输出字段:**
```yaml
operator_replacement.replaced_operators, operator_replacement.replacement_mode
optimization.enabled_ops, optimization.disabled_ops, optimization.operator_config_path
```

---

### ⑦ flagos-flag-upgrade (组件升级) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 升级 flag 组件，Scenario B 核心步骤 |
| **版本** | 2.0.0 |
| **依赖** | 无 (可随时调用) |
| **触发词** | `flag upgrade`, `upgrade flaggems`, `组件升级` |

**Scenario B 增强**：环境一致性检查 + 升级后自动验证 + 失败自动恢复。

---

### ⑧ flagos-log-analyzer (日志分析) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 分析日志，诊断问题，提供失败恢复指引 |
| **版本** | 2.0.0 |
| **依赖** | 无 (可随时调用) |
| **触发词** | `log analysis`, `analyze logs`, `日志分析` |

**新增**：失败恢复指引（服务启动失败、Benchmark 失败、算子优化中断）。

---

## 自动化程度

### 无需人工介入的环节

| 环节 | 说明 |
|------|------|
| GPU 检测 | 自动检测 10 种 GPU 厂商 |
| 入口类型判断 | 自动识别容器名/镜像/URL |
| FlagGems 集成方式 | 运行时多维探测 |
| FlagGems 启停方法 | 从探测结果推导 |
| 性能对比判断 | 自动计算比例 |
| 是否需要算子优化 | 自动判断 < 80% 触发 |
| 算子优化搜索 | 全自动贪心搜索 |
| 报告生成 | 自动生成 |

### 需要人工确认的环节

1. docker run 命令最终确认
2. 是否执行精度评测（默认跳过）
3. 贪心搜索 3 轮仍未达标时

---

## 报告体系

| 报告 | 生成者 | 触发时机 |
|------|--------|---------|
| `env_report.md` | pre-service-inspection | 环境检测完成后 |
| `flag_gems_detection.md` | pre-service-inspection | FlagGems 探测完成后 |
| `env_diff_report.md` | flag-upgrade | Scenario B 版本冲突时 |
| `performance_compare.csv` | performance_compare.py | 每次对比测试后 |
| `final_report.md` | 流程末尾自动生成 | 全流程结束时 |

---

## 数据流

```
┌──────────────────────────────┐
│ container-preparation (①)    │──写入──┐
│ (多入口: 容器/镜像/README)    │        │
└──────────────────────────────┘        ↓
                                ┌─────────────────┐
                                │ context.yaml    │
                                │ (共享上下文)     │
                                └─────────────────┘
                                        ↑
┌──────────────────────────────┐        │
│ pre-service-inspection (②)  │──追加──┤ (execution.*, inspection.*, flaggems_control.*)
│ + env_report.md              │        │
│ + flag_gems_detection.md     │        │
└──────────────────────────────┘        │
                                        ↑
┌──────────────────────────────┐        │
│ service-startup (③)          │──追加──┤ (service.*, runtime.*)
│ (native/flagos 模式切换)      │        │
└──────────────────────────────┘        │
         │                              ↑
         ↓                              │
┌──────────────────────────────┐        │
│ performance-testing (④)      │──追加──┘ (native_perf.*, flagos_perf.*)
│ + benchmark_runner.py        │
│ + performance_compare.py     │
│ → results/*.json             │
│ → performance_compare.csv    │
└──────────────────────────────┘
         │
         ↓ (< 80% 自动触发)
┌──────────────────────────────┐
│ operator-replacement (⑥)    │
│ + operator_optimizer.py      │
│ → operator_config.json       │
└──────────────────────────────┘

独立工具:
┌──────────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ flag-upgrade (⑦)     │  │ eval-correctness │  │ log-analyzer (⑧) │
│ Scenario B 核心       │  │ (⑤) 可选         │  │ + 失败恢复指引    │
└──────────────────────┘  └──────────────────┘  └──────────────────┘
```

---

## GPU 厂商支持

| 厂商 | 检测命令 | 可见设备环境变量 |
|------|----------|------------------|
| NVIDIA | `nvidia-smi` | `CUDA_VISIBLE_DEVICES` |
| 华为 (Ascend) | `npu-smi info` | `ASCEND_RT_VISIBLE_DEVICES` |
| 海光 (Hygon) | `hy-smi` | `HIP_VISIBLE_DEVICES` |
| 摩尔线程 | `mthreads-gmi` | `MUSA_VISIBLE_DEVICES` |
| 昆仑芯 | `xpu-smi` | `XPU_VISIBLE_DEVICES` |
| 天数 | `ixsmi` | `CUDA_VISIBLE_DEVICES` |
| 沐曦 | `mx-smi` | `CUDA_VISIBLE_DEVICES` |
| 清微智能 | `tsm_smi` | `TXDA_VISIBLE_DEVICES` |
| 寒武纪 | `cnmon` | `MLU_VISIBLE_DEVICES` |
| 平头哥 | - | `CUDA_VISIBLE_DEVICES` |

---

## 关键配置文件

| 文件 | 宿主机路径 | 用途 |
|------|-----------|------|
| `context.yaml` | `/data/flagos-workspace/<model>/shared/context.yaml` | Skill 间共享上下文 |
| `perf_config.yaml` | `/data/flagos-workspace/<model>/perf/config/perf_config.yaml` | 性能测试配置 |
| `config.yaml` | `/data/flagos-workspace/<model>/eval/config.yaml` | 评测配置 |
| `operator_config.json` | `/data/flagos-workspace/<model>/results/operator_config.json` | 算子优化状态 |
| `skills/*/SKILL.md` | 项目目录内 | Skill 定义文件 |

---

## 宿主机常用命令

```bash
# 实时查看服务日志
tail -f /data/flagos-workspace/<model>/output/**/*.log

# 查看性能测试结果
cat /data/flagos-workspace/<model>/results/native_performance.json
cat /data/flagos-workspace/<model>/results/flagos_initial.json
cat /data/flagos-workspace/<model>/results/performance_compare.csv

# 查看报告
cat /data/flagos-workspace/<model>/reports/env_report.md
cat /data/flagos-workspace/<model>/reports/flag_gems_detection.md
cat /data/flagos-workspace/<model>/reports/final_report.md

# 查看评测进度
tail -f /data/flagos-workspace/<model>/eval/eval_*.log

# 查看算子优化状态
cat /data/flagos-workspace/<model>/results/operator_config.json

# 搜索错误日志
grep -ri "error" /data/flagos-workspace/<model>/output/
```
