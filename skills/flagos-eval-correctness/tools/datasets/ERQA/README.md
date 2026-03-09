---
dataset_info:
  features:
  - name: question_id
    dtype: string
  - name: question
    dtype: string
  - name: question_type
    dtype: string
  - name: answer
    dtype: string
  - name: visual_indices
    sequence: int32
  - name: images
    sequence: image
  splits:
  - name: test
    num_bytes: 91359624.0
    num_examples: 400
  download_size: 77790243
  dataset_size: 91359624.0
configs:
- config_name: default
  data_files:
  - split: test
    path: data/test-*
---

# Introduction

**Disclaimer:** This dataset is organized and adapted from [embodiedreasoning/ERQA](https://github.com/embodiedreasoning/ERQA). The original data was provided in TFRecord format and has been converted here into a more accessible and easy-to-use format.

This evaluation benchmark covers a variety of topics related to spatial reasoning and world knowledge focused on real-world scenarios, particularly in the context of robotics. Please find more details and visualizations in the tech report.

# Data Fields

| Field Name       | Type              | Description             |
|------------------|-------------------|-------------------------|
| question_id      | string            | Unique question ID      |
| question         | string            | Question text           |
| question_type    | string            | Type of question        |
| answer           | string            | Answer                  |
| visual_indices   | list[int]         | List of visual indices  |
| images           | list[Image]       | Image data              |
| images_base64    | list[string]      | Image data in base64    |