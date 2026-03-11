# Skills 概览

本文档整理了 FlagOS GPU 性能测试自动化框架中所有 Skill 的功能说明和执行顺序。

**工作重点场景**：已有可用容器/镜像，聚焦服务启动、评测和算子优化。

---

## 统一工作目录

**核心设计**：所有操作在统一挂载的 `/flagos-workspace` 目录下进行，宿主机可实时访问日志和结果。

```
宿主机: /data/flagos-workspace/<model_name>/
                      ↓ 挂载
容器内: /flagos-workspace/
             │
             ├── output/          # 服务启动后自动生成的日志
             │   └── <服务名>/
             │       └── serve/
             │           └── *.log
             │
             ├── eval/            # 评测结果和日志
             │   ├── aime_result.json
             │   ├── erqa_result.json
             │   └── eval_*.log
             │
             ├── perf/            # 性能测试结果
             │   └── benchmark_*.json
             │
             └── shared/
                 └── context.yaml # 共享上下文
```

**优势**：
- **实时日志监控**：宿主机直接 `tail -f /data/flagos-workspace/<model>/output/**/*.log`
- **无需 docker exec**：所有日志、配置、结果在宿主机可直接访问和编辑
- **结果持久化**：容器删除后数据仍保留在宿主机

---

## Skills 架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     主流程 (顺序执行)                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ① container-preparation    容器启动前准备                            │
│         ↓                                                           │
│  ② pre-service-inspection   启动服务前准备                            │
│         ↓                                                           │
│  ③ service-startup          启动服务及检查                            │
│         ↓                                                           │
│  ④ eval-correctness         精度评测                                 │
│         ↓                                                           │
│  ⑤ performance-testing      性能测试                                 │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│                     独立工具 (按需调用)                               │
├─────────────────────────────────────────────────────────────────────┤
│  ⑥ operator-replacement     算子替换                                 │
│  ⑦ flag-upgrade             flag 组件升级                            │
│  ⑧ log-analyzer             日志分析                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Skills 详细说明

### ① flagos-container-preparation (容器启动前准备)

| 属性 | 说明 |
|------|------|
| **功能** | 接收用户输入（模型名、模型 URL、镜像地址），检测 GPU，创建容器 |
| **依赖** | 无 (流程起点) |
| **触发词** | `container preparation`, `prepare container`, `容器准备`, `环境准备` |

**前提**：用户已有可用的 Docker 镜像（无需从 README 解析或下载模型）。

**主要工作:**
1. 接收用户输入（模型名、模型 URL、镜像地址）
2. 检测 GPU 厂商和状态 (支持 10 种: NVIDIA、华为、海光等)
3. 验证主机基础环境 (Docker、磁盘、内存)
4. 创建宿主机工作目录
5. 生成并执行 docker run 命令（含工作目录挂载）
6. 验证容器状态和 GPU 可见性

**输出字段:**
```yaml
model.name, model.url, model.local_path
container.name, container.status
image.name, image.tag
gpu.vendor, gpu.count, gpu.visible_devices_env
workspace.host_path, workspace.container_path
```

---

### ② flagos-pre-service-inspection (启动服务前准备)

| 属性 | 说明 |
|------|------|
| **功能** | 容器内环境全面检查：核心组件、flag 组件、FlagGems 代码逻辑、环境变量 |
| **依赖** | `flagos-container-preparation` |
| **触发词** | `pre-service inspection`, `inspect environment`, `服务前检查`, `环境检查` |

**主要工作:**
1. 核心组件检查 (torch, vllm, sglang)
2. flag/plugin 组件版本信息 (flaggems, flagscale, flagcx, vllm_plugin)
3. **FlagGems 代码逻辑检查**（核心步骤）
   - 定位 vllm 安装路径
   - grep 搜索 flaggems 相关代码
   - 分析控制方式 (env_var / code_comment)
   - 分析算子替换逻辑 (unused / only_enable)
4. 环境变量梳理 (USE_FLAGGEMS, USE_FLAGOS 等)

**输出字段:**
```yaml
inspection.core_packages, inspection.flag_packages
inspection.flaggems_control, inspection.flaggems_logic
inspection.flaggems_code_path, inspection.flaggems_code_lines
inspection.env_vars
```

---

### ③ flagos-service-startup (启动服务及检查)

| 属性 | 说明 |
|------|------|
| **功能** | 生成启动命令、执行启动、验证健康状态、检查 gems.txt |
| **依赖** | `flagos-pre-service-inspection` |
| **触发词** | `service startup`, `start service`, `启动服务`, `health check`, `健康检查` |

**主要工作:**

**阶段一 - 启动服务:**
1. 生成启动命令（基于 inspection 结果和 GPU 厂商）
2. 执行启动命令

**阶段二 - 服务验证:**
3. 检查进程状态
4. 查询 `/v1/models` API
5. 运行推理测试
6. 验证 FlagGems 是否生效

**阶段三 - 检查 gems.txt（新增）:**
7. 查找并读取 gems.txt，记录初始算子列表

**输出字段:**
```yaml
service.host, service.port, service.process_id, service.healthy, service.model_id
service.log_path, service.gems_txt_path, service.initial_operator_list
runtime.gpu_count, runtime.flaggems_enabled
```

---

### ④ flagos-eval-correctness (精度评测)

| 属性 | 说明 |
|------|------|
| **功能** | 自动化大模型正确性评测，优先远端 FlagEval 平台 API，支持错误自动处理和本地降级 |
| **依赖** | `flagos-service-startup` |
| **触发词** | `精度评测`, `正确性评测`, `accuracy test`, `eval correctness`, `AIME`, `ERQA` |

**评测方式（按优先级）:**
1. **远端 FlagEval 平台 API**（`http://110.43.160.159:5050`）
2. **本地评测脚本**（`eval_aime.py` / `eval_erqa.py`，作为降级方案）

**主要工作:**

**步骤 A - 远端评测（主流程）:**
1. 确定评测参数（eval_model、eval_url、domain、mode 等）
2. 调用 `/evaluation` 提交评测任务，获取 `request_id`
3. 调用 `/evaluation_progress` 轮询进度
4. 调用 `/evaldiffs` 获取最终结果

**步骤 B - 查询已有任务（用户提供 request_id）:**
- 查询进度 / 获取结果 / 停止 / 恢复 / 对比多任务

**步骤 C - 本地评测降级:**
- 远端平台不可达时，自动切换到容器内本地评测脚本

**步骤 D - 错误处理闭环:**

```
评测结果
  ├── 正常完成(S) → 输出精度报告
  ├── 算子失败(F/OOR) → 关闭问题算子 → 重启服务 → 重新评测
  └── 网络问题 → 降级到本地评测（步骤 C）
```

**输出字段:**
```yaml
eval.request_id, eval.domain, eval.mode
eval.eval_method, eval.status, eval.results
```
**支持的数据集:**
| 数据集 | 类型 | 远端支持 | 本地支持 |
|--------|------|----------|----------|
| AIME | 数学竞赛 (NLP) | 是 | 是 |
| ERQA | 具身推理 (MM) | 是 | 是 |

---

### ⑤ flagos-performance-testing (性能测试)

| 属性 | 说明 |
|------|------|
| **功能** | 执行 vLLM 模型性能基准测试 |
| **依赖** | `flagos-eval-correctness` |
| **触发词** | `性能测试`, `benchmark`, `vllm bench`, `吞吐量测试` |

**主要工作:**
1. 从 `shared/context.yaml` 读取服务连接信息
2. 从 `config/perf_config.yaml` 读取测试参数
3. 执行基准测试矩阵
4. 收集并保存结果

**默认测试矩阵:**

| 测试用例 | 输入长度 | 输出长度 |
|----------|----------|----------|
| 1k_input_1k_output | 1024 | 1024 |
| 4k_input_1k_output | 4096 | 1024 |
| 16k_input_1k_output | 16384 | 1024 |
| 32k_input_1k_output | 32768 | 1024 |

**采集指标:**
- 请求吞吐量 (req/s)
- Token 吞吐量 (tok/s)
- TTFT (首 Token 延迟): Mean/Median/P99
- TPOT (Token 间延迟): Mean/Median/P99
- ITL (Token 间隔延迟): Mean/Median/P99

---

### ⑥ flagos-operator-replacement (算子替换) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 根据 FlagGems 代码逻辑和 gems.txt 按需替换或排除指定算子 |
| **依赖** | 无 (可随时调用) |
| **触发词** | `operator replacement`, `replace operator`, `算子替换` |

**主要工作:**
1. 读取 gems.txt 和评测报错信息，确定需要替换的算子
2. 根据 `flaggems_control` 和 `flaggems_logic` 选择替换模式 (unused/enable/config)
3. 执行算子替换
4. 报告替换详情
5. 提醒重启服务

**输出字段:**
```yaml
operator_replacement.replaced_operators
operator_replacement.replacement_mode
operator_replacement.final_gems_txt
```

---

### ⑦ flagos-flag-upgrade (flag 组件升级) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 升级 flag 生态组件（flaggems、flagscale、flagcx、vllm_plugin） |
| **依赖** | 无 (可随时调用) |
| **触发词** | `flag upgrade`, `upgrade flaggems`, `组件升级`, `flag 升级` |

**注意**：在最新版本中，`vllm_plugin` 已替换了 `flagscale`。

**主要工作:**
1. 查看当前版本
2. 询问用户升级目标
3. git clone + pip install 升级
4. 验证升级
5. 提醒重新执行 pre-service-inspection

---

### ⑧ flagos-log-analyzer (日志分析) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 分析推理服务日志，诊断问题 |
| **依赖** | 无 (可随时调用) |
| **触发词** | `log analysis`, `analyze logs`, `日志分析` |

**主要工作:**
1. 定位日志文件（宿主机直接访问）
2. 检查最近日志输出
3. 检测启动错误 (error, cuda, oom, traceback)
4. 检测 FlagGems 执行状态
5. 检测 GPU/内存错误
6. 生成诊断报告和解决建议

**输出字段:**
```yaml
diagnosis.status, diagnosis.errors, diagnosis.suggestions
```

---

## 执行顺序总结

| 顺序 | Skill | 触发条件 |
|------|-------|----------|
| 1 | container-preparation | 用户提供模型名、模型 URL、镜像地址 |
| 2 | pre-service-inspection | container-preparation 完成 |
| 3 | service-startup | pre-service-inspection 完成 |
| 4 | eval-correctness | service-startup 完成且服务健康 |
| 5 | performance-testing | eval-correctness 完成 |
| - | operator-replacement | 评测报错或用户按需调用 |
| - | flag-upgrade | 用户按需调用 |
| - | log-analyzer | 任何阶段出现问题时调用 |

---

## 数据流

```
┌────────────────────────────┐
│ container-preparation (①) │──写入──┐
└────────────────────────────┘        │
                                      ↓
                             ┌─────────────────┐
                             │ context.yaml    │
                             │ (共享上下文)     │
                             └─────────────────┘
                                      ↑
┌──────────────────────────────┐      │
│ pre-service-inspection (②)  │──追加 (inspection.*)
└──────────────────────────────┘      │
                                      ↑
┌────────────────────┐                │
│ service-startup (③)│────────追加 (service.*, gems_txt)
└────────────────────┘
         │
         ↓ 读取
┌─────────────────────────┐
│ eval-correctness (④)    │
│ → 结果写入 /flagos-workspace/eval/
│ → 报错时触发 ⑥ operator-replacement
└─────────────────────────┘
         │
         ↓ 读取
┌───────────────────────────┐
│ performance-testing (⑤)  │
│ → 结果写入 /flagos-workspace/perf/
└───────────────────────────┘

独立工具:
┌───────────────────────────┐   ┌──────────────────┐   ┌──────────────┐
│ operator-replacement (⑥) │   │ flag-upgrade (⑦) │   │ log-analyzer (⑧)│
│ → 写入 operator_replacement.*│ → 写入 flag_upgrade.*│   │ → 宿主机直接访问日志│
└───────────────────────────┘   └──────────────────┘   └──────────────┘
```

**所有结果文件宿主机直接可访问**：`/data/flagos-workspace/<model_name>/`

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
| `skills/*/SKILL.md` | 项目目录内 | Skill 定义文件 |

---

## 宿主机常用命令

```bash
# 实时查看服务日志
tail -f /data/flagos-workspace/<model>/output/**/*.log

# 查看评测进度
tail -f /data/flagos-workspace/<model>/eval/eval_*.log

# 查看评测结果
cat /data/flagos-workspace/<model>/eval/aime_result.json
cat /data/flagos-workspace/<model>/eval/erqa_result.json

# 查看性能测试结果
cat /data/flagos-workspace/<model>/perf/output/benchmark_*.json

# 搜索错误日志
grep -ri "error" /data/flagos-workspace/<model>/output/
```
