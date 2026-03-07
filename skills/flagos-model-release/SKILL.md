---
name: flagos-model-release
description: 将 FlagOS 适配的模型上传到 HuggingFace 和 ModelScope
version: 1.0.0
triggers:
  - 发布模型
  - 上传模型
  - model release
  - publish model
  - huggingface upload
  - modelscope upload
dependencies:
  - flagos-image-package-upload
next_skill: null
---

# FlagOS 模型发布 Skill

将验证过的 FlagOS 模型发布到 HuggingFace 和 ModelScope。

---

## 工作流程

用户可在任意步骤后停止工作流。

### 步骤 1：准备 README 文档

为模型仓库准备标准化的 README.md。

详见 `steps/step1_prepare_readme.md`。

---

### 步骤 2：上传到 HuggingFace

使用 `huggingface-cli` 上传模型。

详见 `steps/step2_upload_huggingface.md`。

---

### 步骤 3：上传到 ModelScope

使用 `modelscope` CLI 上传模型。

详见 `steps/step3_upload_modelscope.md`。

---

## 完成标准

模型发布完成的条件：

- README 文档已准备
- 模型已上传到 HuggingFace（可选）
- 模型已上传到 ModelScope（可选）
- 模型仓库 URL 已记录
