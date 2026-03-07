# Step 2: 构建 Docker 镜像

## 目标

从运行中的容器创建 Docker 镜像。

## 前置条件

- Step 1 已完成，`env_info.json` 已生成
- 目标容器正在运行

## 执行步骤

### 2.1 生成镜像名称

根据 `env_info.json` 生成完整镜像名称：

```bash
bash tools/generate_image_name.sh
```

输出示例：

```
flagrelease-iluvatar-release-model_qwen2.5-7b-tree_3.0.0-gems_2.1.0-scale_0.5.0-cx_1.0.0-python_3.10-torch_2.1.0-pcp_12.1-gpu_a100-arc_x86_64-driver_535.104
```

### 2.2 创建镜像

```bash
docker commit <container_name> <image_name>:<tag>
```

**示例**：

```bash
docker commit my_inference_container flagrelease-iluvatar-release-model_qwen2.5-7b-tree_3.0.0-gems_2.1.0-scale_0.5.0-cx_1.0.0-python_3.10-torch_2.1.0-pcp_12.1-gpu_a100-arc_x86_64-driver_535.104:2603071200
```

### 2.3 验证镜像

```bash
docker images | grep flagrelease
```

## 输出

- 本地 Docker 镜像已创建
- 镜像信息记录到 `build_info.json`

## 注意事项

- Tag 格式为 YYMMDDHHMM（年月日时分）
- 确保容器在 commit 前处于稳定状态
