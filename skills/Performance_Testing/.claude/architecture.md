# Performance Testing Skill - 项目架构

## 项目概述

GPU 算子性能测试框架，支持多厂商（MetaX、MThreads 等）GPU 的性能基准测试和对比分析。

## 目录结构

```
Performance_Testing/
├── .claude/              # Claude Code 项目配置
├── config/               # 配置文件
│   ├── perf_config.yaml  # 主配置文件
│   ├── schema.json       # 配置 schema 验证
│   └── examples/         # 厂商配置示例
├── src/                  # 核心源码
│   ├── perf.py           # 主入口，性能测试协调器
│   ├── runner.py         # 测试执行器
│   ├── parser.py         # 结果解析器
│   └── reporter.py       # 报告生成器
├── lib/                  # 工具库
│   ├── config_loader.py  # 配置加载
│   ├── env_detector.py   # 环境检测
│   └── validators.py     # 数据验证
├── scripts/              # 脚本工具
├── templates/            # 模板文件
├── tests/                # 单元测试
└── output/               # 输出目录
```

## 模块职责

| 模块 | 职责 | 关键文件 |
|------|------|----------|
| **src/** | 核心业务逻辑 | perf.py (入口), runner.py (执行), parser.py (解析), reporter.py (报告) |
| **lib/** | 通用工具函数 | config_loader.py, env_detector.py, validators.py |
| **config/** | 配置管理 | perf_config.yaml 为主配置，examples/ 存放厂商特定配置 |
| **scripts/** | Shell/Python 脚本 | 一次性或辅助脚本 |
| **templates/** | 模板 | 配置模板、报告模板 |
| **tests/** | 测试 | pytest 单元测试 |

## Agent 工作流程

```
1. 环境检测 (env_detector.py)
   ↓
2. 加载配置 (config_loader.py + perf_config.yaml)
   ↓
3. 执行测试 (runner.py)
   ↓
4. 解析结果 (parser.py)
   ↓
5. 生成报告 (reporter.py → output/)
```

## 文件权限规则

### 只读文件 (不可修改)
- `config/schema.json` - 配置验证规范
- `templates/*` - 模板文件

### 可修改文件
- `config/perf_config.yaml` - 根据测试需求调整
- `src/*.py` - 功能开发
- `lib/*.py` - 工具库扩展
- `output/*` - 输出结果

### 新增规则
- 新配置示例 → `config/examples/`
- 新脚本 → `scripts/`
- 新测试 → `tests/test_*.py`

## 设计原则

1. **配置驱动**: 通过 YAML 配置控制测试行为，避免硬编码
2. **模块解耦**: src/ 各模块职责单一，通过接口交互
3. **可扩展性**: 新厂商支持只需添加 config/examples/ 配置
4. **输出规范**: 所有产出物写入 output/，不污染源码目录
5. **测试优先**: 核心逻辑需有对应 tests/test_*.py

## 技术栈

- Python 3.10+
- PyYAML - 配置解析
- pytest - 单元测试
- Bash - 辅助脚本

## 快速命令

```bash
# 运行测试
python -m pytest tests/

# 执行性能测试
python src/perf.py --config config/perf_config.yaml

# 环境检测
bash scripts/detect_env.sh
```
