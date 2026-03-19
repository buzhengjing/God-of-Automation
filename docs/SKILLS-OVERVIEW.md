# Skills 概览

本文档整理了 FlagOS GPU 性能测试自动化框架中所有 Skill 的功能说明和执行顺序。

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
    │   ├── operator_optimizer.py
    │   ├── operator_search.py
    │   ├── eval_monitor.py
    │   └── ...
    ├── logs/                 # 操作日志
    ├── results/              # 性能数据
    │   ├── native_performance.json
    │   ├── flagos_initial.json
    │   ├── flagos_optimized.json
    │   ├── operator_config.json
    │   └── performance_compare.csv
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

## 工作流程图

### 新模型迁移发布

```
① container-preparation     自动识别入口（已有容器/已有镜像/README）
        ↓
② pre-service-inspection    环境检测 + FlagGems 深度探测
        ↓                   → env_report.md + flag_gems_detection.md
   ┌── 判断 FlagGems 是否已启用 ──┐
   │                               │
   ▼ [已启用 → 路径 A]             ▼ [未启用 → 路径 B]
③A 记录算子列表（强制）          ③B service-startup (native)
④A eval-correctness (flagos)    ④B eval-correctness (native)
⑤A performance-testing (flagos) ⑤B performance-testing (native)
⑥A service-startup (native)     ⑥B service-startup (flagos)
⑦A eval-correctness (native)    ⑦B 记录算子列表（强制）
⑧A performance-testing (native) ⑧B eval-correctness (flagos)
   │                             ⑨B performance-testing (flagos)
   └──────── 汇合 ───────────────┘
⑨ 自动性能对比              → flagos/native ≥ 80%?
   ├── 是 → 跳到 ⑪
   └── 否 → ⑩ operator-replacement（分组二分搜索）
⑪ 生成最终报告
```

**自动化**：步骤③~⑪无需人工干预。仅在以下情况询问用户：
- docker run 命令最终确认
- 是否执行精度评测
- 搜索 3 轮仍未达标时

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
│  ④ eval-correctness         精度评测（询问用户）                      │
│         ↓                                                           │
│  ⑤ performance-testing      性能测试（并发搜索+早停+自动对比）         │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                     独立工具 (按需调用)                               │
├─────────────────────────────────────────────────────────────────────┤
│  ⑥ operator-replacement     算子替换 + 分组二分搜索优化               │
│  ⑦ log-analyzer             日志分析 + 失败恢复指引                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Skills 详细说明

### ① flagos-container-preparation (多入口容器准备)

| 属性 | 说明 |
|------|------|
| **功能** | 自动识别入口类型（容器名/镜像/URL），检测 GPU，创建或接入容器 |
| **依赖** | 无 (流程起点) |
| **触发词** | `container preparation`, `prepare container`, `容器准备`, `环境准备` |

**三种入口**：

| 入口 | 用户提供什么 | 系统做什么 |
|------|-------------|-----------|
| 已有容器 | 容器名/ID | docker inspect → 验证 → 接入 |
| 已有镜像 | 镜像地址 + 模型信息 | docker run 创建 |
| README | URL 链接 | WebFetch → 解析 → docker pull + run |

---

### ② flagos-pre-service-inspection (环境检测 + 深度探测)

| 属性 | 说明 |
|------|------|
| **功能** | 执行模式检测 + 核心组件检查 + FlagGems 多维度深度探测 + 报告生成 |
| **依赖** | `flagos-container-preparation` |
| **触发词** | `pre-service inspection`, `inspect environment`, `服务前检查`, `环境检查` |

---

### ③ flagos-service-startup (服务启动 — 支持模式切换)

| 属性 | 说明 |
|------|------|
| **功能** | 生成启动命令、支持 native/flagos 模式切换、验证健康状态、失败自动恢复 |
| **依赖** | `flagos-pre-service-inspection` |
| **触发词** | `service startup`, `start service`, `启动服务`, `health check` |

**启动模式**：native（关闭 FlagGems）/ flagos（启用 FlagGems）/ default（原始配置）

---

### ④ flagos-eval-correctness (精度评测)

| 属性 | 说明 |
|------|------|
| **功能** | 自动化正确性评测，优先远端 FlagEval API，支持本地降级 |
| **依赖** | `flagos-service-startup` |
| **触发词** | `精度评测`, `正确性评测`, `accuracy test`, `eval correctness` |

服务启动后、性能测试前询问用户是否执行。错误处理闭环：算子失败→关闭→重启→重评。

---

### ⑤ flagos-performance-testing (性能测试 — 自动对比+优化触发)

| 属性 | 说明 |
|------|------|
| **功能** | 性能基准测试，支持并发自动搜索+早停、native/flagos 对比、自动优化触发 |
| **依赖** | `flagos-service-startup` |
| **触发词** | `性能测试`, `benchmark`, `vllm bench`, `吞吐量测试` |

**脚本**：
- `benchmark_runner.py`：测试入口，支持 `--concurrency-search`、`--quick`
- `performance_compare.py`：多结果对比 + CSV 生成

---

### ⑥ flagos-operator-replacement (算子替换 + 优化) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 被动排除（评测报错）+ 主动分组二分搜索优化（性能驱动） |
| **依赖** | 无 (可随时调用) |
| **触发词** | `operator replacement`, `replace operator`, `算子替换`, `算子优化` |

**脚本**：
- `operator_optimizer.py`：分组二分搜索引擎、算子列表自动发现
- `operator_search.py`：全自动搜索编排（next→toggle→restart→benchmark→update）

---

### ⑦ flagos-log-analyzer (日志分析) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 分析日志，诊断问题，提供失败恢复指引 |
| **依赖** | 无 (可随时调用) |
| **触发词** | `log analysis`, `analyze logs`, `日志分析` |

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
| 算子优化搜索 | 全自动分组二分搜索 |
| 报告生成 | 自动生成 |

### 需要人工确认的环节

1. docker run 命令最终确认
2. 是否执行精度评测
3. 搜索 3 轮仍未达标时

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
│ pre-service-inspection (②)  │──追加──┤
│ + env_report.md              │        │
│ + flag_gems_detection.md     │        │
└──────────────────────────────┘        │
                                        ↑
┌──────────────────────────────┐        │
│ service-startup (③)          │──追加──┤
│ (native/flagos 模式切换)      │        │
└──────────────────────────────┘        │
         │                              ↑
         ↓                              │
┌──────────────────────────────┐        │
│ performance-testing (⑤)      │──追加──┘
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
│ + operator_search.py         │
│ → operator_config.json       │
└──────────────────────────────┘

独立工具:
┌──────────────────┐  ┌──────────────────┐
│ eval-correctness │  │ log-analyzer (⑦) │
│ (④) 询问用户     │  │ + 失败恢复指引    │
└──────────────────┘  └──────────────────┘
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
