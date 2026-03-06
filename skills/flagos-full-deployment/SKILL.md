---
name: flagos-full-deployment
description: Execute full model deployment including model inspection, environment preparation, service startup, and service validation.
license: internal
---

# FLAGOS FULL DEPLOYMENT ORCHESTRATOR

This skill orchestrates the full deployment pipeline.

---

# WORKFLOW

Execute skills in order.

STEP 1  
flagos-model-introspection

STEP 2  
flagos-environment-preparation

STEP 3  
flagos-service-startup-environment-check

STEP 4  
flagos-service-health-check

---

# COMPLETION CRITERIA

Deployment is successful when:

- model inspected
- container running
- service started
- API responding