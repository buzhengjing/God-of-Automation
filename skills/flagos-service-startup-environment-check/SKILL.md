---
name: flagos-service-startup-environment-check
description: Start the model inference service and inspect the runtime environment including GPU status, framework version, and FlagGems integration.
license: internal
---

# FLAGOS SERVICE STARTUP AND ENVIRONMENT CHECK

This skill starts the inference service inside the running container and verifies the runtime environment.

---

# WORKFLOW

## STEP 1 — Enter Container

docker exec -it <container_name> /bin/bash

Result feedback:

- container entered successfully

---

## STEP 2 — Check GPU

nvidia-smi

Result feedback:

- GPU visibility
- GPU count

---

## STEP 3 — Inspect Runtime Environment

Check packages:

pip list

Important packages:

- torch
- vllm
- sglang
- flaggems

Result feedback:

- package versions

---

## STEP 4 — Detect FlagGems Integration

Locate framework path.

Example:

pip show vllm

Find installation directory.

Search for gems:

grep gems -rn ./

Determine whether FlagGems support exists.

Do not modify code.

Result feedback:

- framework detected
- FlagGems integration status

---

## STEP 5 — Determine Startup Command

If README provides startup command:

Show command to the user.

Ask the user:

"Do you want to use the README startup command?"

Possible outcomes:

1 Use README command  
2 User provides custom command  
3 No command available

---

## STEP 6 — Generate Startup Command (If Needed)

If no startup command exists, generate based on framework.

Example for vLLM:

vllm serve <model_path> \
--served-model-name <model_name>

Example for SGLang:

python -m sglang.launch_server \
--model-path <model_path>

Show generated command to the user.

Allow the user to:

- approve
- modify
- replace

Execute command only after user confirmation.

Result feedback:

- final startup command
- process status