---
name: flagos-service-health-check
description: Verify that the deployed inference service is accessible and responding correctly.
license: internal
---

# FLAGOS SERVICE HEALTH CHECK

This skill validates that the inference service is running correctly.

---

# WORKFLOW

## STEP 1 — Check Process

ps -ef | grep vllm

Result feedback:

- process id
- process status

---

## STEP 2 — Query Model API

curl http://localhost:8000/v1/models

Result feedback:

- API response
- model identifier

---

## STEP 3 — Run Inference Test

curl http://localhost:8000/v1/chat/completions \
-H "Content-Type: application/json" \
-d '{
"model":"<model_name>",
"messages":[{"role":"user","content":"hello"}]
}'

Result feedback:

- inference result
- latency

---

# COMPLETION CRITERIA

Service is considered healthy when:

- API reachable
- model listed
- inference result returned