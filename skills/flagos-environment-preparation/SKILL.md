---
name: flagos-environment-preparation
description: Prepare the FlagOS inference environment including model download, Docker image preparation, and container creation.
license: internal
---

# FLAGOS ENVIRONMENT PREPARATION SKILL

This skill prepares the runtime environment required for model deployment.

It does not start inference services.

---

# DEPLOYMENT PRIORITY

Always follow this order:

1 README instructions  
2 Official repository instructions  
3 User provided instructions  
4 Manual deployment

---

# WORKFLOW

## STEP 1 — Confirm Deployment Instructions

Check whether the previous step discovered a README.

If README exists:

Use the commands provided.

If README does not exist:

Request from the user:

- model download method
- docker image source
- container configuration

Result feedback:

- deployment method
- docker image source
- model path

---

## STEP 2 — Verify Host Environment

Check GPU:

nvidia-smi

Check Docker:

docker --version

Check ModelScope:

modelscope --version

Install if missing:

pip install modelscope

Result feedback:

- GPU status
- Docker version
- ModelScope status

---

## STEP 3 — Download Model

Preferred method:

Use README download command.

Otherwise use ModelScope or user provided URL.

Example:

modelscope download \
--model <model_repo> \
--local_dir <model_directory>

Verify files exist.

Result feedback:

- model path
- download status

---

## STEP 4 — Pull Docker Image

If README specifies an image:

docker pull <image>

Otherwise use the user provided image.

Verify image:

docker images

Result feedback:

- image name
- image tag

---

## STEP 5 — Create Container

If README provides docker run command:

Use that command.

Otherwise construct a container launch:

docker run -it --gpus all \
--name <container_name> \
--shm-size 32g \
-v <host_model_path>:<container_model_path> \
<image> \
/bin/bash

Verify container:

docker ps

Result feedback:

- container name
- container status

---

# COMPLETION CRITERIA

Environment preparation is successful when:

- model downloaded
- docker image pulled
- container running