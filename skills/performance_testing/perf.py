import subprocess
import re
import json

# 基础命令模板（不含 --max-concurrency 和 --num-prompts）
base_cmd = [
    "vllm", "bench", "serve",
    "--host", "10.1.15.35",
    "--port", "9011",
    "--model", "Qwen3-4B-metax-flagos",
    "--tokenizer", "/nfs/Qwen3-4B",
    "--dataset-name", "random",
    "--random-input-len", "1",
    "--random-output-len", "512",
    "--endpoint", "/v1/completions",
    "--ignore-eos",
    "--trust-remote-code"
]

def parse_benchmark_output(output: str):
    """从 benchmark 输出中提取关键指标"""
    metrics = {}

    # 使用正则匹配关键行（value 用 raw string，key 用自然名称）
    patterns = {
        'Successful requests': r'Successful requests:\s+(\d+)',
        'Failed requests': r'Failed requests:\s+(\d+)',
        'Benchmark duration (s)': r'Benchmark duration \(s\):\s+([\d.]+)',
        'Total input tokens': r'Total input tokens:\s+(\d+)',
        'Total generated tokens': r'Total generated tokens:\s+(\d+)',
        'Request throughput (req/s)': r'Request throughput \(req/s\):\s+([\d.]+)',
        'Output token throughput (tok/s)': r'Output token throughput \(tok/s\):\s+([\d.]+)',
        'Peak output token throughput (tok/s)': r'Peak output token throughput \(tok/s\):\s+([\d.]+)',
        'Peak concurrent requests': r'Peak concurrent requests:\s+([\d.]+)',
        'Total Token throughput (tok/s)': r'Total Token throughput \(tok/s\):\s+([\d.]+)',
        'Mean TTFT (ms)': r'Mean TTFT \(ms\):\s+([\d.]+)',
        'Median TTFT (ms)': r'Median TTFT \(ms\):\s+([\d.]+)',
        'P99 TTFT (ms)': r'P99 TTFT \(ms\):\s+([\d.]+)',
        'Mean TPOT (ms)': r'Mean TPOT \(ms\):\s+([\d.]+)',
        'Median TPOT (ms)': r'Median TPOT \(ms\):\s+([\d.]+)',
        'P99 TPOT (ms)': r'P99 TPOT \(ms\):\s+([\d.]+)',
        'Mean ITL (ms)': r'Mean ITL \(ms\):\s+([\d.]+)',
        'Median ITL (ms)': r'Median ITL \(ms\):\s+([\d.]+)',
        'P99 ITL (ms)': r'P99 ITL \(ms\):\s+([\d.]+)',
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            value_str = match.group(1)
            # 自动判断是整数还是浮点数
            if '.' in value_str:
                metrics[key] = float(value_str)
            else:
                metrics[key] = int(value_str)
        else:
            metrics[key] = None  # 未匹配到设为 None

    return metrics

# 总结果字典
all_results = {}

# Step 1: concurrency = 1, 2, 4, ..., 256
concurrency = 1
while concurrency <= 256:
    num_prompts = concurrency
    cmd = base_cmd + ["--num-prompts", str(num_prompts), "--max-concurrency", str(concurrency)]

    print(f"Running with concurrency={concurrency}, num_prompts={num_prompts}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"⚠️ Command failed for concurrency={concurrency}")
        print("STDERR:", result.stderr)
        all_results[concurrency] = {"error": result.stderr}
    else:
        metrics = parse_benchmark_output(result.stdout)
        all_results[concurrency] = metrics
        print(f"✅ Completed concurrency={concurrency}:\n {metrics}\n\n")

    concurrency *= 2

# Step 2: 最后跑一次无 --max-concurrency，num_prompts=1000
print("Running final test without --max-concurrency, num_prompts=1000")
cmd_final = base_cmd + ["--num-prompts", "1000"]
result = subprocess.run(cmd_final, capture_output=True, text=True)

if result.returncode != 0:
    print("⚠️ Final command failed")
    print("STDERR:", result.stderr)
    all_results['max'] = {"error": result.stderr}
else:
    metrics = parse_benchmark_output(result.stdout)
    all_results['max'] = metrics
    print("✅ Final test completed")

# 打印汇总结果
print("\n=== ALL BENCHMARK RESULTS ===")
print(json.dumps(all_results, indent=2, ensure_ascii=False))

# 可选：保存到文件
with open("benchmark_results.json", "w") as f:
    json.dump(all_results, f, indent=2, ensure_ascii=False)
print("\nResults saved to benchmark_results.json")