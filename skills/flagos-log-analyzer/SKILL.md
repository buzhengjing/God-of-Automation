---
name: flagos-log-analyzer
description: 分析推理服务日志以诊断启动失败、运行时错误、GPU 问题或 FlagGems 集成问题
version: 1.0.0
license: internal
triggers:
  - log analysis
  - analyze logs
  - 日志分析
depends_on: []
provides:
  - diagnosis.status
  - diagnosis.errors
  - diagnosis.suggestions
---

# 日志分析 Skill

此 Skill 分析推理服务生成的日志，以识别部署或运行时问题。

典型日志包括：

- vLLM 启动日志
- SGLang 服务器日志
- CUDA 运行时日志
- FlagGems 相关日志

目标是自动识别常见的部署问题并提供诊断反馈。

---

# 工作流程

按顺序执行步骤。

---

## 步骤 1 — 定位日志文件

识别可能的日志位置。

常见示例：

service.log
vllm.log
sglang.log
nohup.out

如果用户使用 nohup 启动服务：

nohup <command> > service.log 2>&1 &

则日志通常在：

service.log

如果日志文件位置未知，请用户提供。

结果反馈必须包括：

- 检测到的日志文件路径
- 日志大小
- 最后修改时间

---

## 步骤 2 — 检查最近的日志输出

显示最新的日志行：

tail -n 100 <log_file>

关注：

- 启动序列
- 模型加载
- GPU 初始化
- 服务器端口绑定

结果反馈：

- 服务启动状态
- 最后的日志消息

---

## 步骤 3 — 检测常见启动错误

搜索常见的失败关键词。

示例：

grep -i "error" <log_file>
grep -i "cuda" <log_file>
grep -i "oom" <log_file>
grep -i "traceback" <log_file>

典型失败类型：

GPU 内存问题
CUDA 驱动不匹配
缺少模型文件
Tokenizer 错误
依赖冲突

结果反馈：

- 检测到的错误类别
- 相关日志行

---

## 步骤 4 — 检测 FlagGems 执行

搜索 FlagGems 执行消息。

示例：

grep -i "gems" <log_file>

典型模式：

flag_gems.ops
GEMS MUL
GEMS RECIPROCAL

这些日志表明 FlagGems 加速算子正在执行。

结果反馈：

- 是否检测到 FlagGems
- 相关日志条目

---

## 步骤 5 — 检测 GPU 或内存错误

搜索 GPU 相关问题。

示例关键词：

CUDA out of memory
device not found
driver mismatch

结果反馈：

- GPU 错误状态
- 可能的原因

---

## 步骤 6 — 提供诊断

总结发现。

可能的结果：

服务启动成功
服务运行但 API 无法访问
模型加载失败
GPU 内存不足
FlagGems 未启用

根据检测到的问题提供建议。

示例：

减少张量并行大小
检查模型路径
验证 CUDA 兼容性
使用正确的参数重启服务

---

# 完成条件

日志分析完成的标志：

- 日志文件已检查
- 错误已分类
- 诊断已生成
- 可能的解决方案已建议
