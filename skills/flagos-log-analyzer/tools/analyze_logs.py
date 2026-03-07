#!/usr/bin/env python3
"""
FlagOS Log Analyzer
Analyzes inference service logs to diagnose issues.
"""

import argparse
import json
import re
import os
from datetime import datetime
from pathlib import Path


# Error patterns to search for
ERROR_PATTERNS = {
    "cuda_oom": {
        "patterns": [r"CUDA out of memory", r"OOM", r"OutOfMemoryError"],
        "severity": "critical",
        "suggestion": "Reduce batch size, tensor_parallel_size, or use a smaller model"
    },
    "cuda_driver": {
        "patterns": [r"driver mismatch", r"CUDA driver version", r"CUDA initialization"],
        "severity": "critical",
        "suggestion": "Check CUDA driver compatibility with PyTorch version"
    },
    "model_not_found": {
        "patterns": [r"model.*not found", r"No such file", r"FileNotFoundError.*model"],
        "severity": "critical",
        "suggestion": "Verify model path exists and is accessible"
    },
    "tokenizer_error": {
        "patterns": [r"tokenizer.*error", r"TokenizerError", r"vocab.*not found"],
        "severity": "high",
        "suggestion": "Check tokenizer configuration and files"
    },
    "port_in_use": {
        "patterns": [r"Address already in use", r"port.*in use", r"bind.*failed"],
        "severity": "medium",
        "suggestion": "Kill existing process or use a different port"
    },
    "import_error": {
        "patterns": [r"ImportError", r"ModuleNotFoundError", r"No module named"],
        "severity": "high",
        "suggestion": "Install missing dependencies"
    },
    "general_error": {
        "patterns": [r"Error:", r"Exception:", r"Traceback"],
        "severity": "medium",
        "suggestion": "Review the full error traceback for details"
    }
}

# FlagGems patterns
FLAGGEMS_PATTERNS = [
    r"flag_gems",
    r"flaggems",
    r"GEMS MUL",
    r"GEMS RECIPROCAL",
    r"gems.*operator",
    r"Using FlagGems"
]

# Success patterns
SUCCESS_PATTERNS = [
    r"Uvicorn running on",
    r"Application startup complete",
    r"Started server process",
    r"INFO.*Serving",
    r"Model loaded successfully"
]


def read_log_file(log_path: str, max_lines: int = 10000) -> list:
    """Read log file and return lines."""
    path = Path(log_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()[-max_lines:]
    return lines


def analyze_errors(lines: list) -> list:
    """Analyze log lines for errors."""
    findings = []

    for category, config in ERROR_PATTERNS.items():
        for pattern in config["patterns"]:
            for i, line in enumerate(lines):
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append({
                        "category": category,
                        "severity": config["severity"],
                        "line_number": i + 1,
                        "content": line.strip()[:500],
                        "suggestion": config["suggestion"]
                    })
                    break  # One match per category is enough

    return findings


def detect_flaggems(lines: list) -> dict:
    """Detect FlagGems usage in logs."""
    matches = []

    for pattern in FLAGGEMS_PATTERNS:
        for i, line in enumerate(lines):
            if re.search(pattern, line, re.IGNORECASE):
                matches.append({
                    "line_number": i + 1,
                    "content": line.strip()[:200]
                })

    return {
        "detected": len(matches) > 0,
        "match_count": len(matches),
        "matches": matches[:10]  # Limit to 10 matches
    }


def detect_startup_status(lines: list) -> dict:
    """Detect service startup status."""
    for pattern in SUCCESS_PATTERNS:
        for line in lines[-100:]:  # Check last 100 lines
            if re.search(pattern, line, re.IGNORECASE):
                return {
                    "status": "success",
                    "message": line.strip()[:200]
                }

    return {
        "status": "unknown",
        "message": "Could not determine startup status"
    }


def generate_diagnosis(errors: list, flaggems: dict, startup: dict) -> dict:
    """Generate overall diagnosis."""
    critical_errors = [e for e in errors if e["severity"] == "critical"]
    high_errors = [e for e in errors if e["severity"] == "high"]

    if critical_errors:
        status = "failed"
        summary = f"Critical errors detected: {critical_errors[0]['category']}"
    elif high_errors:
        status = "warning"
        summary = f"High severity issues detected: {high_errors[0]['category']}"
    elif startup["status"] == "success":
        status = "healthy"
        summary = "Service appears to be running normally"
    else:
        status = "unknown"
        summary = "Unable to determine service status"

    return {
        "status": status,
        "summary": summary,
        "flaggems_enabled": flaggems["detected"],
        "error_count": len(errors),
        "critical_count": len(critical_errors),
        "recommendations": [e["suggestion"] for e in critical_errors + high_errors][:5]
    }


def main():
    parser = argparse.ArgumentParser(description="FlagOS Log Analyzer")
    parser.add_argument("--log", required=True, help="Path to log file")
    parser.add_argument("--output", default="diagnosis.json", help="Output file")
    parser.add_argument("--max-lines", type=int, default=10000, help="Max lines to analyze")
    args = parser.parse_args()

    print(f"Analyzing log file: {args.log}")

    try:
        lines = read_log_file(args.log, args.max_lines)
        print(f"Read {len(lines)} lines")

        errors = analyze_errors(lines)
        flaggems = detect_flaggems(lines)
        startup = detect_startup_status(lines)
        diagnosis = generate_diagnosis(errors, flaggems, startup)

        result = {
            "timestamp": datetime.now().isoformat(),
            "log_file": args.log,
            "lines_analyzed": len(lines),
            "diagnosis": diagnosis,
            "startup_status": startup,
            "flaggems": flaggems,
            "errors": errors
        }

        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\nDiagnosis: {diagnosis['status'].upper()}")
        print(f"Summary: {diagnosis['summary']}")
        print(f"FlagGems: {'Enabled' if flaggems['detected'] else 'Not detected'}")
        print(f"Errors found: {len(errors)}")
        print(f"\nFull report saved to: {args.output}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
