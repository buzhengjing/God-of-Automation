# FlagOS Skills Collection

优化后的 FlagOS 工作流 Skill 集合。

## 目录结构

```
new_skill/
├── README.md                                    # 本文件
├── flagos-model-introspection/                  # 模型检查
│   └── SKILL.md
├── flagos-environment-preparation/              # 环境准备
│   └── SKILL.md
├── flagos-service-startup-environment-check/    # 服务启动
│   └── SKILL.md
├── flagos-service-health-check/                 # 服务验证
│   ├── SKILL.md
│   └── tools/
│       ├── check_health.sh
│       └── config.yaml
├── flagos-eval-correctness/                     # 精度评测
│   ├── SKILL.md
│   └── tools/
│       └── config.yaml
├── flagos-performance-testing/                  # 性能评测
│   ├── SKILL.md
│   ├── config/
│   │   └── perf_config.yaml
│   └── scripts/
│       └── run_benchmark.sh
├── flagos-image-package-upload/                 # 镜像打包上传
│   ├── SKILL.md
│   ├── steps/
│   │   ├── step1_collect_env.md
│   │   ├── step2_build_image.md
│   │   └── step3_push_image.md
│   └── tools/
│       ├── collect_env.sh
│       └── config.yaml
├── flagos-model-release/                        # 模型发布
│   ├── SKILL.md
│   ├── steps/
│   │   ├── step1_prepare_readme.md
│   │   ├── step2_upload_huggingface.md
│   │   └── step3_upload_modelscope.md
│   └── tools/
│       └── config.yaml
├── flagos-log-analyzer/                         # 日志分析（辅助）
│   ├── SKILL.md
│   └── tools/
│       ├── analyze_logs.py
│       └── config.yaml
├── flagos-full-deployment/                      # 部署编排（步骤1-4）
│   └── SKILL.md
└── flagos-complete-pipeline/                    # 完整流水线（步骤1-8）
    └── SKILL.md
```

## 工作流程映射

| 工作流步骤 | Skill |
|-----------|-------|
| 1. 环境准备 | flagos-environment-preparation |
| 2. 下载模型 | flagos-environment-preparation |
| 3. 拉取镜像 | flagos-environment-preparation |
| 4. 启动容器 | flagos-environment-preparation |
| 5. 部署模型服务 | flagos-service-startup-environment-check |
| 6. 服务验证 | flagos-service-health-check |
| 7. 精度评测 | flagos-eval-correctness |
| 8. 性能评测 | flagos-performance-testing |
| 9. 打包镜像 | flagos-image-package-upload |
| 10. 上传镜像 | flagos-image-package-upload |
| 11. 发布模型 | flagos-model-release |

## 命名规范

所有 Skill 统一使用：
- 前缀：`flagos-`
- 分隔符：连字符 `-`
- 小写字母

## SKILL.md 标准格式

```yaml
---
name: flagos-xxx
description: 描述
version: 1.0.0
triggers:
  - 触发词1
  - 触发词2
dependencies:
  - 依赖的skill
next_skill: 下一个skill
---

# 标题

## 工作流程

### 步骤 1：xxx

## 完成标准
```

## 优化内容

1. **统一命名规范**：所有 skill 使用 `flagos-` 前缀
2. **统一文档格式**：标准化 SKILL.md 元数据和结构
3. **补充工具脚本**：为缺少工具的 skill 添加自动化脚本
4. **完整流水线编排**：新增 `flagos-complete-pipeline` 编排全流程
5. **依赖关系明确**：每个 skill 声明 dependencies 和 next_skill
