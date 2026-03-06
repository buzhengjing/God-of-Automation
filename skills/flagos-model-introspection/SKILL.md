---
name: flagos-model-introspection
description: Inspect a provided model repository or directory to determine model structure, framework compatibility, and available deployment instructions.
license: internal
---

# FLAGOS MODEL INTROSPECTION SKILL

This skill analyzes a model source before deployment.

Supported sources include:

- ModelScope repositories
- HuggingFace repositories
- Git repositories
- Local model directories
- User provided URLs

The goal is to understand the model structure and deployment requirements before environment preparation.

---

# WORKFLOW

## STEP 1 — Identify Model Source

The user should provide one of the following:

- model repository URL
- local model directory
- model download command

Determine:

- source platform
- repository location
- model name

Result feedback:

- model name
- repository source
- repository URL

---

## STEP 2 — Locate README or Deployment Guide

Search for:

README.md  
deployment documentation  
usage instructions

If a README exists, extract:

- model download command
- docker image source
- docker run command
- inference startup command

Result feedback:

- README detected or not
- available deployment instructions

---

## STEP 3 — Inspect Model Directory

Check for key files such as:

config.json  
tokenizer.json  
model.safetensors  
pytorch_model.bin

Determine model format.

Result feedback:

- model file structure
- weight format

---

## STEP 4 — Detect Supported Runtime

Determine compatible frameworks.

Typical frameworks:

- vLLM
- SGLang
- Transformers
- TGI

Heuristics:

- presence of vllm instructions
- presence of sglang instructions
- tokenizer configuration

Result feedback:

- recommended runtime framework
- alternative runtime options

---

# COMPLETION CRITERIA

Model introspection is complete when:

- model source identified
- README status known
- runtime framework determined

The next step should be **flagos-environment-preparation**.