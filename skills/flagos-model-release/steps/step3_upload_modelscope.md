# Step 3: 上传到 ModelScope

## 目标

将模型上传到 ModelScope。

## 前置条件

- Step 1 已完成，README.md 已准备
- 已安装 `modelscope`
- 已登录 ModelScope 账号

## 执行步骤

### 3.1 安装 CLI（如未安装）

```bash
pip install modelscope
```

### 3.2 登录 ModelScope

```bash
modelscope login
```

或设置环境变量：

```bash
export MODELSCOPE_API_TOKEN="your_token"
```

### 3.3 创建仓库

在 ModelScope 网站创建模型仓库：

```
https://modelscope.cn/models/create
```

### 3.4 上传模型

```bash
modelscope upload --model <namespace>/<model_name> ./model_directory
```

或使用 Python API：

```python
from modelscope.hub.api import HubApi
api = HubApi()
api.push_model(
    model_id="namespace/model_name",
    model_dir="./model_directory"
)
```

### 3.5 上传 README

README.md 通常随模型目录一起上传。

### 3.6 验证上传

访问仓库页面确认：

```
https://modelscope.cn/models/<namespace>/<model_name>
```

## 输出

- 模型已上传到 ModelScope
- 仓库 URL 已记录

## 注意事项

- 大模型上传可能需要较长时间
- 确保网络连接稳定
- ModelScope 支持断点续传
