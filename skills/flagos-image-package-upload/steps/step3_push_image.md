# Step 3: 推送镜像到 Harbor

## 目标

将构建的镜像推送到 Harbor 仓库。

## 前置条件

- Step 2 已完成，本地镜像已创建
- 已登录 Harbor 仓库

## 执行步骤

### 3.1 登录 Harbor

```bash
docker login harbor.baai.ac.cn
```

输入用户名和密码。

### 3.2 Tag 镜像

```bash
docker tag <local_image>:<tag> harbor.baai.ac.cn/flagrelease-public/<image_name>:<tag>
```

**示例**：

```bash
docker tag flagrelease-iluvatar-release-model_qwen2.5-7b-tree_3.0.0-gems_2.1.0-scale_0.5.0-cx_1.0.0-python_3.10-torch_2.1.0-pcp_12.1-gpu_a100-arc_x86_64-driver_535.104:2603071200 \
  harbor.baai.ac.cn/flagrelease-public/flagrelease-iluvatar-release-model_qwen2.5-7b-tree_3.0.0-gems_2.1.0-scale_0.5.0-cx_1.0.0-python_3.10-torch_2.1.0-pcp_12.1-gpu_a100-arc_x86_64-driver_535.104:2603071200
```

### 3.3 推送镜像

```bash
docker push harbor.baai.ac.cn/flagrelease-public/<image_name>:<tag>
```

### 3.4 验证推送

登录 Harbor Web UI 确认镜像已上传：

```
https://harbor.baai.ac.cn/harbor/projects/flagrelease-public/repositories
```

## 输出

- 镜像已推送到 Harbor
- 完整镜像 URL 记录到 `push_result.json`

## 注意事项

- 大镜像推送可能需要较长时间
- 确保网络连接稳定
- 推送失败时检查 Harbor 配额
