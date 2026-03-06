# Performance Benchmark Report

**Date:** {{timestamp}}
**Model:** {{model_name}}
**Server:** {{host}}:{{port}}

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Input Length | {{input_len}} |
| Output Length | {{output_len}} |
| Concurrency Levels | {{concurrency_levels}} |

## Results Summary

| Test Case | Throughput (tok/s) | Mean TTFT (ms) | Mean TPOT (ms) |
|-----------|--------------------| ---------------|----------------|
{{#each results}}
| {{name}} | {{throughput}} | {{ttft}} | {{tpot}} |
{{/each}}

## Detailed Metrics

### Throughput

{{throughput_chart}}

### Latency Distribution

{{latency_chart}}

## Conclusion

{{conclusion}}
