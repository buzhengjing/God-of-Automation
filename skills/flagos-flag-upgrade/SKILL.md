---
name: flagos-flag-upgrade
description: 升级 flag 生态组件（flaggems、flagscale、flagcx、vllm_plugin），支持 git 源码 + pip install
version: 1.0.0
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

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
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
docker exec <container> pip show flag-gems flagscale flagcx vllm-plugin 2>/dev/null
```

结果反馈：

| 组件 | 当前版本 | 安装状态 |
|------|----------|----------|
| flag-gems | x.x.x | 已安装/未安装 |
| flagscale | x.x.x | 已安装/未安装 |
| flagcx | x.x.x | 已安装/未安装 |
| vllm-plugin | x.x.x | 已安装/未安装 |

---

## 步骤 2 — 询问用户升级目标

询问用户：

- **升级哪些组件**（可多选）
- **目标版本/分支**（如 `main`、`v1.2.0`、`dev` 等）
- **仓库地址**（如有自定义 fork）

示例对话：

```
请选择需要升级的组件：
1. flaggems
2. flagscale
3. flagcx
4. vllm_plugin

请提供目标分支或版本（默认 main）：
```

---

## 步骤 3 — 执行升级

对每个选中的组件执行升级操作：

```bash
# 通用升级流程
docker exec <container> bash -c "
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

## 步骤 4 — 验证升级

```bash
docker exec <container> pip show <package>
```

对比升级前后的版本：

```
升级结果：
  flaggems: 1.0.0 → 1.2.0
  flagcx: 0.2.0 → 0.3.0
```

---

## 步骤 5 — 提醒后续操作

升级完成后，提示用户：

1. **重新执行环境检查**：建议重新执行 `flagos-pre-service-inspection`，更新 context.yaml 中的组件版本信息
2. **重启服务**：如果服务正在运行，需要重启才能使用新版本
3. **验证兼容性**：新版本可能引入接口变化，建议运行推理测试验证

---

# 完成条件

组件升级成功的标志：

- 目标组件已确定
- 升级操作已执行
- 版本变化已记录
- 已提醒用户后续操作（重新检查环境、重启服务）

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| git clone 失败 | 检查网络连接和仓库地址，可能需要配置代理 |
| pip install 编译失败 | 检查编译工具链（gcc、g++）和 CUDA 版本 |
| 版本冲突 | 检查依赖关系，可能需要先卸载旧版本 `pip uninstall <package>` |
| 升级后服务启动失败 | 版本不兼容，考虑回退或检查 changelog |
