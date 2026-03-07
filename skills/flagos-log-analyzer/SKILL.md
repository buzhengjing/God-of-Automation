---
name: flagos-log-analyzer
description: 分析推理服务日志以诊断启动失败、运行时错误、GPU 问题或 FlagGems 集成问题
version: 1.0.0
triggers:
  - 日志分析
  - 错误诊断
  - log analyzer
  - diagnose error
dependencies: []
next_skill: null
---

# FlagOS 日志分析 Skill

分析推理服务生成的日志以识别部署或运行时问题。

## 典型日志类型

- vLLM 启动日志
- SGLang 服务日志
- CUDA 运行时日志
- FlagGems 相关日志

---

## 工作流程

### 步骤 1：定位日志文件

识别可能的日志位置：

- service.log
- vllm.log
- sglang.log
- nohup.out

如果用户使用 nohup 启动服务：

```bash
nohup <command> > service.log 2>&1 &
```

日志通常在 `service.log`。

如果日志文件位置未知，请求用户提供。

**结果反馈**：

- 检测到的日志文件路径
- 日志大小
- 最后修改时间

---

### 步骤 2：检查最近日志输出

显示最新日志行：

```bash
tail -n 100 <log_file>
```

**关注点**：

- 启动序列
- 模型加载
- GPU 初始化
- 服务端口绑定

**结果反馈**：

- 服务启动状态
- 最新日志消息

---

### 步骤 3：检测常见启动错误

搜索常见故障关键字：

```bash
grep -i "error" <log_file>
grep -i "cuda" <log_file>
grep -i "oom" <log_file>
grep -i "traceback" <log_file>
```

**典型故障类型**：

- GPU 内存问题
- CUDA 驱动不匹配
- 模型文件缺失
- tokenizer 错误
- 依赖冲突

**结果反馈**：

- 检测到的错误类别
- 相关日志行

---

### 步骤 4：检测 FlagGems 执行

搜索 FlagGems 执行消息：

```bash
grep -i "gems" <log_file>
```

**典型模式**：

- flag_gems.ops
- GEMS MUL
- GEMS RECIPROCAL

这些日志表明 FlagGems 加速算子正在执行。

**结果反馈**：

- FlagGems 是否检测到
- 相关日志条目

---

### 步骤 5：检测 GPU 或内存错误

搜索 GPU 相关问题：

**关键字示例**：

- CUDA out of memory
- device not found
- driver mismatch

**结果反馈**：

- GPU 错误状态
- 可能的原因

---

### 步骤 6：提供诊断

汇总发现。

**可能的结果**：

- 服务启动成功
- 服务运行但 API 不可达
- 模型加载失败
- GPU 内存不足
- FlagGems 未启用

根据检测到的问题提供建议：

- 减少 tensor parallel size
- 检查模型路径
- 验证 CUDA 兼容性
- 使用正确参数重启服务

---

## 完成标准

日志分析完成的条件：

- 日志文件已检查
- 错误已分类
- 诊断已生成
- 建议的解决方案已提供

---

## 工具脚本

可使用 `tools/analyze_logs.py` 进行自动化分析。

```bash
python tools/analyze_logs.py --log <log_file> --output diagnosis.json
```
