# 评测报告: qwen3-8b-flagos

> 模型类型: LLM
> 生成时间: 2026-03-16 03:35:00
> Benchmark 总数: 5
> 成功: 4 | 失败: 1
> 总耗时: 263m 12.3s

---

## 评测结果总览

| Benchmark | 状态 | 得分 | 耗时 |
|-----------|------|------|------|
| MMLU_5shot | Pass | 81.71 | 11327.99s |
| AIME24_0shot | Pass | 76.67 | 757.34s |
| AIME25_0shot | Pass | 76.67 | 1091.03s |
| GPQA_Diamond_0shot | Fail | 0.00 | 1578.14s |
| MUSR_0shot | Pass | 62.96 | 1037.82s |

---

## 详细结果

### MMLU_5shot

- **得分**: 81.71

### AIME24_0shot

- **得分**: 76.67

### AIME25_0shot

- **得分**: 76.67

### MUSR_0shot

- **得分**: 62.96

## 失败的 Benchmark

- **GPQA_Diamond_0shot**: EvalScope error on gpqa_diamond: Error code: 400 - {'object': 'error', 'message': "This model's maximum context length is 32768 tokens. However, you requested 32825 tokens (2825 in the messages, 30000 in the completion). Please reduce the length of the messages or completion. None", 'type': 'BadRequestError', 'param': None, 'code': 400}

---

*报告由 flagos-eval-comprehensive 自动生成于 2026-03-16 03:35:00*