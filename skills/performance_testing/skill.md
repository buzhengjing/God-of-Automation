---
name: performance-testing
description: vLLM model performance benchmark testing tool
version: 1.0.0
triggers:
  - performance test
  - benchmark
  - vllm bench
  - throughput test
  - TTFT test
  - TPOT test
  - latency test
---

# Performance Testing Skill

## Overview
Automated vLLM model performance benchmark testing with support for multiple input/output length combinations.

## Trigger Conditions
- User requests model performance testing
- User mentions benchmark, throughput, or latency testing
- User needs to test different input/output length combinations

## Agent Workflow

### Step 1: Configuration
Only modify `config/perf_config.yaml`. Validate against `config/schema.json`.

Key configuration items:
- `server.host` / `server.port`: Service endpoint
- `model.name` / `model.tokenizer_path`: Model settings
- `test_matrix`: Enable/disable specific test cases

### Step 2: Execute Tests
```bash
python -m src.perf --config config/perf_config.yaml
```

Or use the convenience script:
```bash
bash scripts/run_benchmark.sh
```

### Step 3: Collect Results
Results are automatically saved to `output/` directory with timestamps.

## File Permissions

### Modifiable (Agent CAN edit)
- `config/perf_config.yaml` - Main configuration file

### Read-Only (Agent CANNOT edit)
- `src/*` - Source code
- `lib/*` - Library modules
- `scripts/*` - Executable scripts
- `templates/*` - Template files

## Test Matrix (Default)

| Test Case | Input Length | Output Length |
|-----------|--------------|---------------|
| 1k_input_1k_output | 1024 | 1024 |
| 4k_input_1k_output | 4096 | 1024 |
| 16k_input_1k_output | 16384 | 1024 |
| 32k_input_1k_output | 32768 | 1024 |

## Output Format

```json
{
  "metadata": {
    "timestamp": "2026-03-05T10:30:00",
    "config_snapshot": { ... }
  },
  "results": {
    "1k_input_1k_output": {
      "concurrency_1": { ... },
      "concurrency_2": { ... },
      "max": { ... }
    }
  }
}
```

## Key Metrics Collected
- Request throughput (req/s)
- Output token throughput (tok/s)
- Total token throughput (tok/s)
- Mean/Median/P99 TTFT (ms)
- Mean/Median/P99 TPOT (ms)
- Mean/Median/P99 ITL (ms)

## Example Usage

1. Update config:
   - Edit `config/perf_config.yaml` with correct host/port/model

2. Run benchmark:
   ```bash
   python -m src.perf --config config/perf_config.yaml
   ```

3. View results:
   ```bash
   ls output/
   cat output/benchmark_YYYYMMDD_HHMMSS.json
   ```
