---
name: flagos-image-package-upload
description: Package and upload a FlagOS docker image for a validated model environment.
---

This skill packages a verified FlagOS runtime container into a standardized Docker image
and uploads it to the Harbor registry.

Workflow steps:

1. Collect environment version information
2. Build docker image from container
3. Tag and push image to Harbor registry

The user may stop the workflow after any step.

Image naming format:

harbor.baai.ac.cn/flagrelease-public/flagrelease-<vendor>-release-model_<model_name>-tree_<ver>-gems_<ver>-scale_<ver>-cx_<ver>-python_<ver>-torch_<ver>-pcp_<cuda>-gpu_<gpu>-arc_<arch>-driver_<driver>:<tag>

Rules:

- model name must be lowercase
- if version contains "+", replace with "-"
- tag = upload timestamp (YYMMDDHHMM)

Example tag:

2603031041