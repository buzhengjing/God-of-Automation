# Step 2: 上传到 HuggingFace

## 目标

将模型上传到 HuggingFace Hub。

## 前置条件

- Step 1 已完成，README.md 已准备
- 已安装 `huggingface-cli`
- 已登录 HuggingFace 账号

## 执行步骤

### 2.1 安装 CLI（如未安装）

```bash
pip install huggingface_hub
```

### 2.2 登录 HuggingFace

```bash
huggingface-cli login
```

输入 Access Token。

### 2.3 创建仓库

```bash
huggingface-cli repo create <model_name> --type model
```

### 2.4 上传模型

```bash
huggingface-cli upload <username>/<model_name> ./model_directory
```

或使用 Python API：

```python
from huggingface_hub import HfApi
api = HfApi()
api.upload_folder(
    folder_path="./model_directory",
    repo_id="username/model_name",
    repo_type="model"
)
```

### 2.5 上传 README

```bash
huggingface-cli upload <username>/<model_name> README.md
```

### 2.6 验证上传

访问仓库页面确认：

```
https://huggingface.co/<username>/<model_name>
```

## 输出

- 模型已上传到 HuggingFace
- 仓库 URL 已记录

## 注意事项

- 大模型上传可能需要较长时间
- 确保网络连接稳定
- 可使用 `--private` 创建私有仓库
