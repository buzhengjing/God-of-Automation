---
name: flagos-flag-upgrade
description: 升级 flag 生态组件（flaggems、flagscale、flagcx、vllm_plugin），支持 git 源码 + pip install。Scenario B 核心步骤。
version: 2.0.0
license: internal
triggers:
  - flag upgrade
  - upgrade flaggems
  - upgrade flagscale
  - 组件升级
  - flag 升级
depends_on: []
provides:
  - flag_upgrade.upgraded_packages
  - flag_upgrade.previous_versions
  - flag_upgrade.current_versions
---

# flag 组件升级 Skill

独立工具，用于升级 flag 生态系统组件。

**目标组件**：flaggems、flagscale、flagcx、vllm_plugin

**注意**：在最新版本中，`vllm_plugin` 已替换了 `flagscale`。

**升级方法**：git 源码 clone + pip install

**在双场景流程中的位置**：
- **Scenario A**：按需调用
- **Scenario B**：步骤④，核心步骤（FlagGems 自动升级）

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
execution:
  mode: <来自 pre-service-inspection>
  cmd_prefix: <来自 pre-service-inspection>
inspection:
  flag_packages: <来自 pre-service-inspection>
```

## 写入 shared/context.yaml

```yaml
flag_upgrade:
  upgraded_packages:
    - name: "<package>"
      previous_version: "<old_version>"
      current_version: "<new_version>"
      branch: "<git_branch>"
  timestamp: "<ISO timestamp>"
```

---

# 工作流程

## 步骤 1 — 查看当前版本

```bash
${CMD_PREFIX} pip show flag-gems flagscale flagcx vllm-plugin 2>/dev/null
```

结果反馈：

| 组件 | 当前版本 | 安装状态 |
|------|----------|----------|
| flag-gems | x.x.x | 已安装/未安装 |
| flagscale | x.x.x | 已安装/未安装 |
| flagcx | x.x.x | 已安装/未安装 |
| vllm-plugin | x.x.x | 已安装/未安装 |

---

## 步骤 2 — 确定升级目标

### Scenario A（按需调用）

询问用户：
- 升级哪些组件
- 目标版本/分支
- 仓库地址

### Scenario B（自动升级流程）

自动确定升级目标：
- 从用户提供的仓库链接解析组件和版本
- 或使用默认的最新 main 分支

---

## 步骤 3 — 环境一致性检查（Scenario B 新增）

升级前检查版本兼容性：

```bash
${CMD_PREFIX} python3 -c "
import torch, json
info = {
    'torch': torch.__version__,
    'cuda': torch.version.cuda if hasattr(torch.version, 'cuda') else 'N/A',
}
try:
    import vllm
    info['vllm'] = vllm.__version__
except: pass
try:
    import flag_gems
    info['flaggems'] = flag_gems.__version__
except: pass
print(json.dumps(info, indent=2))
"
```

如果发现版本冲突（如新版 FlagGems 要求不同的 torch 版本），生成 `env_diff_report.md` 并报告用户。

---

## 步骤 4 — 执行升级

```bash
${CMD_PREFIX} bash -c "
  cd /tmp && \
  git clone <repo_url> && \
  cd <repo_dir> && \
  git checkout <branch> && \
  pip install -e .
"
```

**各组件参考仓库**（实际地址以用户提供为准）：

| 组件 | 仓库地址 | 备注 |
|------|----------|------|
| flaggems | 用户提供 | 算子替换库 |
| flagscale | 用户提供 | 推理框架 |
| flagcx | 用户提供 | 通信库 |
| vllm_plugin | 用户提供 | vLLM 插件 |

**注意事项**：
- 部分组件可能有额外依赖，需要 `pip install -e .[all]` 或指定依赖
- 如果安装失败，检查编译依赖（如 CUDA toolkit、gcc 等）
- 向用户展示将要执行的命令，确认后再执行

---

## 步骤 5 — 验证升级

```bash
${CMD_PREFIX} pip show <package>
```

对比升级前后的版本：

```
升级结果：
  flaggems: 1.0.0 → 1.2.0
  flagcx: 0.2.0 → 0.3.0
```

---

## 步骤 6 — 升级后自动验证（Scenario B 新增）

### 6.1 快速启动验证

```bash
# 以 flagos 模式启动服务（参考 service-startup）
# 验证服务是否能成功启动
```

### 6.2 成功 / 失败处理

| 结果 | 操作 |
|------|------|
| 启动成功 | 继续性能测试 → flagos_after_upgrade benchmark |
| 启动失败 | 自动恢复旧环境 → 进入算子优化 |

### 6.3 自动恢复旧环境

如果升级后启动失败：

```bash
# 回退 FlagGems
${CMD_PREFIX} pip install flag-gems==<old_version>

# 或重新安装旧版
${CMD_PREFIX} bash -c "
  cd /tmp/<old_repo_dir> && \
  git checkout <old_branch> && \
  pip install -e .
"
```

---

## 步骤 7 — 提醒后续操作

升级完成后：

1. **重新执行环境检查**：重新执行 `flagos-pre-service-inspection`，更新 context.yaml
2. **重启服务**：如果服务正在运行，需要重启
3. **性能测试**：运行升级后 benchmark 对比

---

# 完成条件

组件升级成功的标志：

- 目标组件已确定
- （Scenario B）环境一致性已检查
- 升级操作已执行
- 版本变化已记录
- （Scenario B）升级后启动验证已完成
- 已提醒用户后续操作

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| git clone 失败 | 检查网络连接和仓库地址，可能需要配置代理 |
| pip install 编译失败 | 检查编译工具链（gcc、g++）和 CUDA 版本 |
| 版本冲突 | 检查依赖关系，可能需要先卸载旧版本 `pip uninstall <package>` |
| 升级后服务启动失败 | 版本不兼容 → 自动恢复旧环境 → 算子优化 |
| 升级后算子不兼容 | 部分新版算子可能需要排除 → 触发 operator-replacement |
