---
name: flagos-flag-upgrade
description: 升级 flag 生态组件，通过 upgrade_component.py 支持自动网络降级和构建依赖检查
version: 3.0.0
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

通过 `upgrade_component.py` 自动化升级 flag 生态组件，支持网络检测和宿主机降级。

**工具脚本**: `skills/flagos-flag-upgrade/tools/upgrade_component.py`（已由 setup_workspace.sh 部署到容器）

**默认仓库**（硬编码，无需用户提供）：
- FlagGems: `https://github.com/FlagOpen/FlagGems.git`
- FlagScale: `https://github.com/FlagOpen/FlagScale.git`
- FlagCX: `https://github.com/FlagOpen/FlagCX.git`

**默认分支**: `main`（不询问用户）

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
execution:
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
docker exec $CONTAINER pip show flag-gems flagscale flagcx 2>/dev/null
```

## 步骤 2 — 停止服务（如在运行）

```bash
docker exec $CONTAINER bash -c "pkill -f 'vllm\|sglang\|flagscale' 2>/dev/null; sleep 3"
```

## 步骤 3 — 执行升级（容器内优先）

```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/upgrade_component.py \
  --component flaggems --branch main --json
```

脚本自动完成：
1. 检测容器网络连通性
2. 网络可用 → 容器内直接 git clone + pip install
3. 网络不可用 → 输出宿主机操作指令（JSON），Claude Code 在宿主机执行：
   ```bash
   cd /tmp && git clone --depth 1 --branch main https://github.com/FlagOpen/FlagGems.git
   docker cp /tmp/FlagGems $CONTAINER:/tmp/FlagGems
   docker exec $CONTAINER bash -c "cd /tmp/FlagGems && pip install ."
   ```
4. 预检并安装构建依赖（setuptools, scikit-build-core）
5. 使用非 editable 模式：`pip install .`

**如有代理**（从用户获取后传入）：
```bash
docker exec $CONTAINER python3 /flagos-workspace/scripts/upgrade_component.py \
  --component flaggems --branch main --proxy http://10.8.36.21:17890 --json
```

## 步骤 4 — 验证升级

```bash
docker exec $CONTAINER pip show flag-gems
```

输出版本对比：
```
升级结果: flaggems 2.2 → 4.2.1rc0
```

## 步骤 5 — API 兼容性检查

```bash
docker exec $CONTAINER python3 -c "
import flag_gems, inspect, json
result = {
    'version': flag_gems.__version__,
    'has_enable': hasattr(flag_gems, 'enable'),
    'has_only_enable': hasattr(flag_gems, 'only_enable'),
}
if hasattr(flag_gems, 'enable'):
    sig = inspect.signature(flag_gems.enable)
    result['enable_params'] = list(sig.parameters.keys())
print(json.dumps(result, indent=2))
"
```

## 步骤 6 — 写入 context.yaml

---

# 完成条件

- 目标组件已确定
- 网络策略已执行（容器内直连或宿主机降级）
- 升级操作已完成
- 版本变化已记录
- API 兼容性已检查
- context.yaml 已更新

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| 容器无网络 | upgrade_component.py 自动输出宿主机操作指令 |
| pip install 编译失败 | 脚本自动安装 setuptools/scikit-build-core |
| 版本冲突 | 检查依赖关系，可能需先 `pip uninstall` |
| 升级后服务启动失败 | 版本不兼容 → `pip install flag-gems==<old_version>` 回退 |
