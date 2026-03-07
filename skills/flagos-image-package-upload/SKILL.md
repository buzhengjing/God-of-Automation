---
name: flagos-image-package-upload
description: 将验证过的 FlagOS 运行时容器打包为标准化 Docker 镜像并上传到 Harbor 仓库
version: 1.0.0
triggers:
  - 打包镜像
  - 上传镜像
  - package image
  - push image
  - harbor upload
dependencies:
  - flagos-performance-testing
next_skill: flagos-model-release
---

# FlagOS 镜像打包上传 Skill

将验证过的 FlagOS 运行时容器打包为标准化 Docker 镜像并上传到 Harbor 仓库。

---

## 工作流程

用户可在任意步骤后停止工作流。

### 步骤 1：收集环境版本信息

执行 `tools/collect_env.sh` 收集以下信息：

- vendor (厂商)
- model_name (模型名称)
- tree_version (triton 版本)
- gems_version (FlagGems 版本)
- scale_version (FlagScale 版本)
- cx_version
- python_version
- torch_version
- cuda_version (pcp)
- gpu_type
- architecture
- driver_version

详见 `steps/step1_collect_env.md`。

---

### 步骤 2：构建 Docker 镜像

从运行中的容器创建镜像：

```bash
docker commit <container_name> <image_name>:<tag>
```

详见 `steps/step2_build_image.md`。

---

### 步骤 3：推送镜像到 Harbor

```bash
docker tag <image_name>:<tag> harbor.baai.ac.cn/flagrelease-public/<full_image_name>:<tag>
docker push harbor.baai.ac.cn/flagrelease-public/<full_image_name>:<tag>
```

详见 `steps/step3_push_image.md`。

---

## 镜像命名格式

```
harbor.baai.ac.cn/flagrelease-public/flagrelease-<vendor>-release-model_<model_name>-tree_<ver>-gems_<ver>-scale_<ver>-cx_<ver>-python_<ver>-torch_<ver>-pcp_<cuda>-gpu_<gpu>-arc_<arch>-driver_<driver>:<tag>
```

**规则**：

- 模型名称必须小写
- 版本号中的 `+` 替换为 `-`
- tag = 上传时间戳 (YYMMDDHHMM)

**示例 tag**：

```
2603031041
```

---

## 完成标准

镜像打包上传完成的条件：

- 环境信息已收集
- Docker 镜像已创建
- 镜像已推送到 Harbor
- 镜像 URL 已记录
