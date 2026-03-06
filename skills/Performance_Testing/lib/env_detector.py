#!/usr/bin/env python3
"""
Environment Detector - Detect container environment for auto-configuration
"""

import os
import subprocess
import json
from pathlib import Path
from typing import Dict, Any, Optional, List


def detect_environment() -> Dict[str, Any]:
    """
    Detect current environment settings.

    Returns:
        Dictionary with detected environment info
    """
    env_info = {
        "hostname": get_hostname(),
        "gpu_info": detect_gpu(),
        "vllm_version": get_vllm_version(),
        "model_paths": find_model_paths(),
        "env_vars": get_relevant_env_vars(),
    }

    return env_info


def get_hostname() -> str:
    """Get current hostname."""
    try:
        import socket
        return socket.gethostname()
    except Exception:
        return os.environ.get("HOSTNAME", "unknown")


def detect_gpu() -> Dict[str, Any]:
    """Detect GPU information using nvidia-smi."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            gpus = []
            for line in lines:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 3:
                    gpus.append({
                        "name": parts[0],
                        "memory": parts[1],
                        "driver": parts[2]
                    })
            return {"available": True, "gpus": gpus, "count": len(gpus)}

    except FileNotFoundError:
        pass
    except Exception as e:
        return {"available": False, "error": str(e)}

    return {"available": False}


def get_vllm_version() -> Optional[str]:
    """Get installed vLLM version."""
    try:
        result = subprocess.run(
            ["pip", "show", "vllm"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()

    except Exception:
        pass

    return None


def find_model_paths(search_dirs: Optional[List[str]] = None) -> List[str]:
    """
    Find potential model paths in common locations.

    Args:
        search_dirs: List of directories to search

    Returns:
        List of discovered model paths
    """
    if search_dirs is None:
        search_dirs = ["/nfs", "/models", "/data/models", "/home"]

    model_paths = []

    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if not search_path.exists():
            continue

        # Look for common model file patterns
        patterns = ["*.safetensors", "config.json", "tokenizer.json"]

        for pattern in patterns:
            try:
                for match in search_path.rglob(pattern):
                    model_dir = str(match.parent)
                    if model_dir not in model_paths:
                        model_paths.append(model_dir)
                        if len(model_paths) >= 10:  # Limit results
                            return model_paths
            except PermissionError:
                continue

    return model_paths


def get_relevant_env_vars() -> Dict[str, str]:
    """Get environment variables relevant to ML workloads."""
    relevant_keys = [
        "CUDA_VISIBLE_DEVICES",
        "NCCL_DEBUG",
        "VLLM_ATTENTION_BACKEND",
        "HF_HOME",
        "TRANSFORMERS_CACHE",
        "MODEL_PATH",
        "TOKENIZER_PATH",
        "HOST",
        "PORT",
    ]

    return {k: os.environ.get(k, "") for k in relevant_keys if os.environ.get(k)}


def suggest_config(env_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate configuration suggestions based on detected environment.

    Args:
        env_info: Environment info from detect_environment()

    Returns:
        Suggested configuration values
    """
    suggestions = {}

    # Suggest host/port from env vars
    env_vars = env_info.get("env_vars", {})
    if env_vars.get("HOST"):
        suggestions["server.host"] = env_vars["HOST"]
    if env_vars.get("PORT"):
        suggestions["server.port"] = int(env_vars["PORT"])

    # Suggest model path
    if env_vars.get("MODEL_PATH"):
        suggestions["model.tokenizer_path"] = env_vars["MODEL_PATH"]
    elif env_info.get("model_paths"):
        suggestions["model.tokenizer_path"] = env_info["model_paths"][0]

    return suggestions


if __name__ == "__main__":
    # Run detection and print results
    env_info = detect_environment()
    print(json.dumps(env_info, indent=2, ensure_ascii=False))
