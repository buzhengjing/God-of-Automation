# Step 1: 收集环境版本信息

## 目标

收集容器内所有关键软件版本信息，用于构建标准化镜像名称。

## 执行方式

```bash
bash tools/collect_env.sh <container_name>
```

## 收集项目

| 字段 | 命令 | 示例值 |
|------|------|--------|
| vendor | 用户输入 | iluvatar, nvidia |
| model_name | 从启动参数提取 | qwen2.5-7b |
| tree_version | `pip show triton` | 3.0.0 |
| gems_version | `pip show flag-gems` | 2.1.0 |
| scale_version | `pip show flagscale` | 0.5.0 |
| cx_version | 用户输入 | 1.0.0 |
| python_version | `python --version` | 3.10 |
| torch_version | `python -c "import torch;print(torch.__version__)"` | 2.1.0 |
| cuda_version | `nvcc --version` | 12.1 |
| gpu_type | `nvidia-smi --query-gpu=name --format=csv,noheader` | A100 |
| architecture | `uname -m` | x86_64 |
| driver_version | `nvidia-smi --query-gpu=driver_version --format=csv,noheader` | 535.104 |

## 输出

生成 `env_info.json`：

```json
{
  "vendor": "iluvatar",
  "model_name": "qwen2.5-7b",
  "tree_version": "3.0.0",
  "gems_version": "2.1.0",
  "scale_version": "0.5.0",
  "cx_version": "1.0.0",
  "python_version": "3.10",
  "torch_version": "2.1.0",
  "cuda_version": "12.1",
  "gpu_type": "A100",
  "architecture": "x86_64",
  "driver_version": "535.104"
}
```

## 验证

确认所有必填字段已收集。
