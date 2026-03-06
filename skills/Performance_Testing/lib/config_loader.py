#!/usr/bin/env python3
"""
Configuration Loader - Load and validate YAML configuration

配置加载逻辑:
1. 读取 shared/context.yaml 获取连接信息 (host, port, model)
2. 读取 config/perf_config.yaml 获取测试参数
3. 合并配置执行测试
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional

import yaml

# 默认 context.yaml 路径 (项目根目录/shared/context.yaml)
DEFAULT_CONTEXT_PATH = Path(__file__).parent.parent.parent.parent / "shared" / "context.yaml"


def load_context(context_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load shared context from context.yaml.

    Args:
        context_path: Path to context.yaml, defaults to shared/context.yaml

    Returns:
        Context dictionary with service and model info

    Raises:
        FileNotFoundError: If context file doesn't exist
    """
    path = Path(context_path) if context_path else DEFAULT_CONTEXT_PATH

    if not path.exists():
        raise FileNotFoundError(
            f"Context file not found: {path}\n"
            "请确保上游 skill 已写入 shared/context.yaml，或手动创建该文件。"
        )

    with open(path, "r", encoding="utf-8") as f:
        context = yaml.safe_load(f)

    return context or {}


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        yaml.YAMLError: If config file is invalid YAML
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    return config


def load_full_config(
    config_path: str,
    context_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Load and merge context + perf_config into a complete configuration.

    Args:
        config_path: Path to perf_config.yaml
        context_path: Optional path to context.yaml

    Returns:
        Complete merged configuration
    """
    context = load_context(context_path)
    perf_config = load_config(config_path)

    # 构建完整配置: context 提供连接信息，perf_config 提供测试参数
    full_config = {
        "server": {
            "host": context.get("service", {}).get("host", ""),
            "port": context.get("service", {}).get("port", 8000),
            "endpoint": context.get("service", {}).get("endpoint", "/v1/completions"),
        },
        "model": {
            "name": context.get("model", {}).get("name", ""),
            "path": context.get("model", {}).get("path", ""),
            "tokenizer_path": context.get("model", {}).get("tokenizer_path", ""),
        },
        "environment": context.get("environment", {}),
        **perf_config,
    }

    # 如果 perf_config 中有 benchmark.endpoint，使用它覆盖 context 的 endpoint
    if perf_config.get("benchmark", {}).get("endpoint"):
        full_config["server"]["endpoint"] = perf_config["benchmark"]["endpoint"]

    return full_config


def validate_context(context: Dict[str, Any]) -> bool:
    """
    Validate context has required connection info.

    Args:
        context: Context dictionary

    Returns:
        True if valid
    """
    service = context.get("service", {})
    model = context.get("model", {})

    if not service.get("host"):
        print("ERROR: context service.host is required")
        return False
    if not model.get("tokenizer_path"):
        print("ERROR: context model.tokenizer_path is required")
        return False

    return True


def validate_config(config: Dict[str, Any], schema_path: Optional[str] = None) -> bool:
    """
    Validate merged configuration.

    Args:
        config: Full merged configuration dictionary
        schema_path: Optional path to JSON schema file

    Returns:
        True if valid, False otherwise
    """
    # Validate server (from context)
    server = config.get("server", {})
    if not server.get("host"):
        print("ERROR: server.host is required (check shared/context.yaml)")
        return False
    if not isinstance(server.get("port"), int):
        print("ERROR: server.port must be an integer")
        return False

    # Validate model (from context)
    model = config.get("model", {})
    if not model.get("tokenizer_path"):
        print("ERROR: model.tokenizer_path is required (check shared/context.yaml)")
        return False

    # Validate test_matrix
    test_matrix = config.get("test_matrix", [])
    if not test_matrix:
        print("ERROR: test_matrix cannot be empty")
        return False

    for i, tc in enumerate(test_matrix):
        if not tc.get("name"):
            print(f"ERROR: test_matrix[{i}].name is required")
            return False
        if not isinstance(tc.get("input_len"), int) or tc["input_len"] < 1:
            print(f"ERROR: test_matrix[{i}].input_len must be a positive integer")
            return False
        if not isinstance(tc.get("output_len"), int) or tc["output_len"] < 1:
            print(f"ERROR: test_matrix[{i}].output_len must be a positive integer")
            return False

    # Validate concurrency
    concurrency = config.get("concurrency", {})
    if not concurrency.get("levels"):
        print("ERROR: concurrency.levels is required")
        return False
    if not isinstance(concurrency.get("final_num_prompts"), int):
        print("ERROR: concurrency.final_num_prompts must be an integer")
        return False

    # Validate output
    output = config.get("output", {})
    if not output.get("dir"):
        print("ERROR: output.dir is required")
        return False

    return True


def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two configurations, with override taking precedence.

    Args:
        base: Base configuration
        override: Override configuration

    Returns:
        Merged configuration
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value

    return result
