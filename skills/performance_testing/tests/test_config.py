#!/usr/bin/env python3
"""
Tests for configuration loader
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.config_loader import validate_config


def test_valid_config():
    """Test validation of valid configuration."""
    config = {
        "server": {"host": "10.1.15.35", "port": 9011},
        "model": {"name": "test-model", "tokenizer_path": "/path/to/tokenizer"},
        "benchmark": {"dataset_name": "random", "endpoint": "/v1/completions"},
        "test_matrix": [
            {"name": "test1", "input_len": 1024, "output_len": 1024, "enabled": True}
        ],
        "concurrency": {"levels": [1, 2, 4], "final_num_prompts": 100},
        "output": {"dir": "./output", "format": "json"}
    }

    assert validate_config(config) == True
    print("Valid config test passed!")


def test_missing_server():
    """Test validation with missing server section."""
    config = {
        "model": {"name": "test-model", "tokenizer_path": "/path"},
        "benchmark": {"dataset_name": "random", "endpoint": "/v1/completions"},
        "test_matrix": [{"name": "test1", "input_len": 1024, "output_len": 1024}],
        "concurrency": {"levels": [1], "final_num_prompts": 100},
        "output": {"dir": "./output", "format": "json"}
    }

    assert validate_config(config) == False
    print("Missing server test passed!")


def test_invalid_port():
    """Test validation with invalid port."""
    config = {
        "server": {"host": "10.1.15.35", "port": "invalid"},
        "model": {"name": "test-model", "tokenizer_path": "/path"},
        "benchmark": {"dataset_name": "random", "endpoint": "/v1/completions"},
        "test_matrix": [{"name": "test1", "input_len": 1024, "output_len": 1024}],
        "concurrency": {"levels": [1], "final_num_prompts": 100},
        "output": {"dir": "./output", "format": "json"}
    }

    assert validate_config(config) == False
    print("Invalid port test passed!")


def test_empty_test_matrix():
    """Test validation with empty test matrix."""
    config = {
        "server": {"host": "10.1.15.35", "port": 9011},
        "model": {"name": "test-model", "tokenizer_path": "/path"},
        "benchmark": {"dataset_name": "random", "endpoint": "/v1/completions"},
        "test_matrix": [],
        "concurrency": {"levels": [1], "final_num_prompts": 100},
        "output": {"dir": "./output", "format": "json"}
    }

    assert validate_config(config) == False
    print("Empty test matrix test passed!")


if __name__ == "__main__":
    test_valid_config()
    test_missing_server()
    test_invalid_port()
    test_empty_test_matrix()
    print("\nAll config tests passed!")
