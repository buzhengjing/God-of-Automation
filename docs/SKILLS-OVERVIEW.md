# God-of-Automation Skills 概览

本文档整理了 FlagOS GPU 性能测试自动化框架中所有 Skill 的功能说明和执行顺序。

---

## Skills 架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           主流程 (顺序执行)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ①                    ②                       ③                    ④      │
│   model-introspection → environment-preparation → service-startup → Performance_Testing
│   (模型检查)            (环境准备)               (服务启动)          (性能测试)  │
│                                                       │                     │
│                                                       ↓                     │
│                                                 ⑤ flagos-release            │
│                                                   (镜像/模型发布)            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           独立工具 (按需调用)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ⑥ flagos-log-analyzer (日志分析诊断)                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Skills 详细说明

### ① flagos-model-discovery (模型检查)

| 属性 | 说明 |
|------|------|
| **功能** | 从模型仓库的 README 提取部署说明 |
| **依赖** | 无 (流程起点) |
| **触发词** | `model introspection`, `inspect model`, `模型检查`, `检查部署说明` |

**主要工作:**
1. 获取模型来源 (ModelScope/HuggingFace/Git/本地)
2. 读取 README 内容
3. 提取 Docker 镜像、docker run 命令、服务启动命令
4. 确定运行时框架 (FlagScale/vLLM/SGLang)
5. 写入 `shared/context.yaml`

**服务启动命令识别模式:**
| 命令模式 | 框架 |
|----------|------|
| `flagscale serve ...` | FlagScale |
| `vllm serve ...` | vLLM |
| `python -m vllm.entrypoints...` | vLLM |
| `python -m sglang.launch_server ...` | SGLang |

**注意:** FlagScale 是 FlagOS 推荐的统一推理框架，优先检测。

**输出字段:**
```yaml
model.name, model.source, model.readme_found
deployment.image, deployment.docker_run, deployment.startup_command, deployment.model_download
runtime.framework  # vllm | sglang | flagscale
```

---

### ② flagos-environment-preparation (环境准备)

| 属性 | 说明 |
|------|------|
| **功能** | 准备运行时环境：镜像拉取、容器创建、GPU 检测 |
| **依赖** | `flagos-model-discovery` |
| **触发词** | `environment preparation`, `prepare environment`, `环境准备` |

**主要工作:**
1. 检测 GPU 厂商 (支持 10 种: NVIDIA、华为、海光等)
2. 验证主机基础环境 (Docker、磁盘、内存)
3. 检查模型是否已存在 / 执行下载
4. 拉取 Docker 镜像
5. 创建并启动容器
6. 验证容器状态和 GPU 可见性

**输出字段:**
```yaml
container.name, container.status
image.name, image.tag
model.local_path, model.container_path
gpu.vendor, gpu.count, gpu.visible_devices_env
```

---

### ③ flagos-service-startup (服务启动)

| 属性 | 说明 |
|------|------|
| **功能** | 在容器内启动推理服务并验证健康状态 |
| **依赖** | `flagos-environment-preparation` |
| **触发词** | `service startup`, `start service`, `启动服务`, `health check`, `健康检查` |

**主要工作:**

**阶段一 - 环境检查:**
1. 进入容器
2. 检查 GPU 可见性
3. 检查运行时环境 (torch, vllm, sglang, flag-gems)
4. 检测 FlagGems 集成状态
5. 询问用户是否启用 FlagGems

**阶段二 - 启动服务:**
6. 生成启动命令 (含 `USE_FLAGGEMS` 环境变量)
7. 执行启动命令

**阶段三 - 服务验证:**
8. 检查进程状态
9. 查询 `/v1/models` API
10. 运行推理测试
11. 验证 FlagGems 是否生效

**输出字段:**
```yaml
service.host, service.port, service.process_id, service.healthy, service.model_id
runtime.gpu_count, runtime.flaggems_enabled
```

---

### ④ Performance_Testing (性能测试)

| 属性 | 说明 |
|------|------|
| **功能** | 执行 vLLM 模型性能基准测试 |
| **依赖** | `flagos-service-startup` |
| **触发词** | `性能测试`, `benchmark`, `vllm bench`, `吞吐量测试`, `TTFT 测试`, `TPOT 测试`, `延迟测试` |

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

**输出字段:**
```yaml
benchmark.results, benchmark.timestamp
```

---

### ⑤ flagos-release (发布)

| 属性 | 说明 |
|------|------|
| **功能** | 打包并发布 Docker 镜像和模型 |
| **依赖** | `flagos-service-startup` |
| **触发词** | `release`, `image upload`, `package image`, `model release`, `upload model`, `发布`, `镜像上传`, `模型发布` |

**发布选项:**
1. **仅镜像** — 推送到 Harbor
2. **仅模型** — 上传到 HuggingFace + ModelScope
3. **完整发布** — 两者都发布

**主要工作:**

**镜像发布:**
1. 收集环境信息 (FlagOS 组件版本、CUDA、驱动等)
2. `docker commit` 容器为镜像
3. 按命名规范标记镜像
4. 推送到 Harbor

**模型发布:**
1. 准备 README (含基准测试结果、启动命令)
2. 上传到 HuggingFace
3. 上传到 ModelScope

**输出字段:**
```yaml
image.registry_url, image.upload_timestamp
release.huggingface_url, release.modelscope_url
```

---

### ⑥ flagos-log-analyzer (日志分析) — 独立工具

| 属性 | 说明 |
|------|------|
| **功能** | 分析推理服务日志，诊断问题 |
| **依赖** | 无 (可随时调用) |
| **触发词** | `log analysis`, `analyze logs`, `日志分析` |

**主要工作:**
1. 定位日志文件 (`service.log`, `vllm.log`, `nohup.out` 等)
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
| 1 | model-introspection | 用户提供模型来源 |
| 2 | environment-preparation | model-introspection 完成 |
| 3 | service-startup | environment-preparation 完成 |
| 4 | Performance_Testing | service-startup 完成且服务健康 |
| 5 | flagos-release | service-startup 完成 (可选) |
| - | flagos-log-analyzer | 任何阶段出现问题时调用 |

---

## 数据流

```
┌──────────────────┐
│ model-introspection │──写入──┐
└──────────────────┘         │
                             ↓
                    ┌─────────────────┐
                    │ context.yaml    │
                    │ (共享上下文)     │
                    └─────────────────┘
                             ↑
┌────────────────────────┐   │
│ environment-preparation │──追加
└────────────────────────┘   │
                             ↑
┌──────────────────┐         │
│ service-startup  │─────追加┘
└──────────────────┘
         │
         ↓ 读取
┌──────────────────┐    ┌──────────────┐
│ Performance_Testing │    │ flagos-release │
└──────────────────┘    └──────────────┘
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

| 文件 | 用途 |
|------|------|
| `shared/context.yaml` | Skill 间共享上下文 |
| `config/perf_config.yaml` | 性能测试配置 |
| `skills/*/SKILL.md` | Skill 定义文件 |
