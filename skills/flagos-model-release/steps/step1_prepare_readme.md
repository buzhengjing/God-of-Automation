# Step 1: 准备 README 文档

## 目标

为模型仓库准备标准化的 README.md 文档。

## README 模板

```markdown
# {MODEL_NAME} - FlagOS Optimized

This model has been optimized for FlagOS inference platform.

## Model Information

- **Base Model**: {BASE_MODEL}
- **Optimization**: FlagGems accelerated operators
- **Framework**: vLLM / SGLang

## Quick Start

### Pull Docker Image

\`\`\`bash
docker pull {DOCKER_IMAGE_URL}
\`\`\`

### Download Model

\`\`\`bash
modelscope download --model {MODEL_REPO} --local_dir ./model
\`\`\`

### Start Inference Service

\`\`\`bash
docker run -it --gpus all \\
  --name inference \\
  --shm-size 32g \\
  -v $(pwd)/model:/model \\
  {DOCKER_IMAGE_URL} \\
  /bin/bash

# Inside container
vllm serve /model --served-model-name {MODEL_NAME}
\`\`\`

## Performance

| Metric | Value |
|--------|-------|
| Throughput | {THROUGHPUT} tok/s |
| TTFT (P99) | {TTFT_P99} ms |
| TPOT (P99) | {TPOT_P99} ms |

## License

{LICENSE}
```

## 执行步骤

1. 使用模板生成 README.md
2. 填入实际的模型信息
3. 添加性能测试结果
4. 审核文档内容

## 输出

- `README.md` 文件已生成
- 文档内容已审核确认
