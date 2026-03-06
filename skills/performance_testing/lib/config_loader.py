#!/usr/bin/env python3
"""
Configuration Loader - Load and validate YAML configuration
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

import yaml


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


def validate_config(config: Dict[str, Any], schema_path: Optional[str] = None) -> bool:
    """
    Validate configuration against schema.

    Args:
        config: Configuration dictionary
        schema_path: Optional path to JSON schema file

    Returns:
        True if valid, False otherwise
    """
    # Basic required fields check
    required_sections = ["server", "model", "benchmark", "test_matrix", "concurrency", "output"]

    for section in required_sections:
        if section not in config:
            print(f"ERROR: Missing required section: {section}")
            return False

    # Validate server
    server = config.get("server", {})
    if not server.get("host"):
        print("ERROR: server.host is required")
        return False
    if not isinstance(server.get("port"), int):
        print("ERROR: server.port must be an integer")
        return False

    # Validate model
    model = config.get("model", {})
    if not model.get("name"):
        print("ERROR: model.name is required")
        return False
    if not model.get("tokenizer_path"):
        print("ERROR: model.tokenizer_path is required")
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
