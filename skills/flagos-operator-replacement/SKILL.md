---
name: flagos-operator-replacement
description: 算子替换工具，根据 FlagGems 代码逻辑和 gems.txt 按需替换或排除指定算子
version: 1.0.0
license: internal
triggers:
  - operator replacement
  - replace operator
  - 算子替换
  - gems replace
depends_on: []
provides:
  - operator_replacement.replaced_operators
  - operator_replacement.replacement_mode
  - operator_replacement.final_gems_txt
---

# 算子替换 Skill

独立工具，可在任何阶段按需调用。根据评测报错信息或用户需求，执行 FlagGems 算子的替换操作。

---

# 上下文集成

## 从 shared/context.yaml 读取

```yaml
container:
  name: <来自 container-preparation>
inspection:
  flaggems_control: <来自 pre-service-inspection>
  flaggems_logic: <来自 pre-service-inspection>
  flaggems_code_path: <来自 pre-service-inspection>
  flaggems_code_lines: <来自 pre-service-inspection>
service:
  gems_txt_path: <来自 service-startup>
  initial_operator_list: <来自 service-startup>
```

## 写入 shared/context.yaml

```yaml
operator_replacement:
  replaced_operators: []          # 已替换/排除的算子列表
  replacement_mode: ""            # unused | enable | config
  final_gems_txt: ""              # 最终 gems.txt 内容/路径
```

---

# 工作流程

## 步骤 1 — 判断需要替换的算子

读取上下文信息，确定替换目标：

```bash
# 读取 gems.txt 内容（初始算子列表）
docker exec <container> cat <gems_txt_path>
```

**确定替换算子的来源**：

| 来源 | 说明 |
|------|------|
| 评测报错 | 服务端 CUDA error、算子不支持等报错 → 排除问题算子 |
| 用户指定 | 用户明确指定需要替换/排除的算子 |
| gems.txt 分析 | 根据初始算子列表和已知兼容性问题判断 |

结果反馈：

- 当前算子列表
- 需要替换/排除的算子及原因

---

## 步骤 2 — 根据替换逻辑执行操作

读取 context.yaml 中的 `flaggems_control` 和 `flaggems_logic`，选择对应的操作方式。

### 模式一：unused（排除模式）

将指定算子标记为不使用（加入排除列表）。

```bash
# 查看当前排除列表
docker exec <container> cat <flaggems_code_path> | sed -n '<start>,<end>p'

# 修改排除列表，添加需要排除的算子
docker exec <container> sed -i 's/unused_ops = \[/unused_ops = ["<operator_name>", /' <flaggems_code_path>
```

### 模式二：enable（启用模式）

仅启用指定算子（修改启用列表）。

```bash
# 查看当前启用列表
docker exec <container> cat <flaggems_code_path> | sed -n '<start>,<end>p'

# 修改启用列表
docker exec <container> sed -i 's/enabled_ops = \[/enabled_ops = ["<operator_name>", /' <flaggems_code_path>
```

### 模式三：config（配置文件模式）

通过配置文件控制算子替换。

```bash
# 编辑配置文件（具体路径和格式待用户后续补充）
docker exec <container> vi <config_path>
```

**注意**：具体的操作命令需要根据实际的代码结构和 FlagGems 版本调整。向用户展示将要执行的修改，确认后再执行。

---

## 步骤 3 — 告知替换详情

逐步报告每次替换操作：

```
替换报告：
  - 操作模式: unused
  - 替换算子: ["softmax", "layer_norm"]
  - 替换原因: CUDA error in softmax op, layer_norm precision mismatch
  - 代码修改: /path/to/file.py L42
```

查看替换后的 gems.txt 或代码状态：

```bash
docker exec <container> cat <gems_txt_path>
```

结果反馈：

- 替换了哪些算子
- 替换方式
- 最终状态

---

## 步骤 4 — 提醒服务重启

算子替换后需要重启服务才能生效。

提示用户：

1. **停止当前服务**：
   ```bash
   docker exec <container> pkill -f "vllm\|sglang"
   ```
2. **重新启动服务**：执行 `flagos-service-startup`
3. **验证替换效果**：检查新的 gems.txt 和服务日志

---

## 步骤 5 — 写入 context.yaml

```yaml
operator_replacement:
  replaced_operators:
    - name: "softmax"
      reason: "CUDA error"
      action: "excluded"
    - name: "layer_norm"
      reason: "precision mismatch"
      action: "excluded"
  replacement_mode: "unused"
  final_gems_txt: "/path/to/gems.txt"
```

---

# 完成条件

算子替换成功的标志：

- 需要替换的算子已确定
- 替换操作已执行
- 替换详情已报告给用户
- context.yaml 已更新 `operator_replacement` 字段
- 已提醒用户重启服务

---

# 故障排查

| 问题 | 解决方案 |
|------|----------|
| gems.txt 不存在 | 服务可能未启动过，先执行 `flagos-service-startup` |
| 代码路径不存在 | 重新执行 `flagos-pre-service-inspection` 更新路径 |
| 替换后服务仍报错 | 检查报错的算子是否全部被排除，可能需要多轮替换 |
| 不确定替换哪些算子 | 使用 `flagos-log-analyzer` 分析报错日志 |
