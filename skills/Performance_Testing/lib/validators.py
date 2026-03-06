#!/usr/bin/env python3
"""
Validators - Parameter validation utilities
"""

import re
from typing import Any, Optional, Tuple


def validate_host(host: str) -> Tuple[bool, Optional[str]]:
    """
    Validate hostname or IP address.

    Returns:
        (is_valid, error_message)
    """
    if not host:
        return False, "Host cannot be empty"

    # Check for valid IP address
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    if re.match(ip_pattern, host):
        parts = host.split('.')
        for part in parts:
            if int(part) > 255:
                return False, f"Invalid IP address: {host}"
        return True, None

    # Check for valid hostname
    hostname_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    if re.match(hostname_pattern, host):
        return True, None

    return False, f"Invalid hostname: {host}"


def validate_port(port: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate port number.

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(port, int):
        return False, f"Port must be an integer, got {type(port).__name__}"

    if port < 1 or port > 65535:
        return False, f"Port must be between 1 and 65535, got {port}"

    return True, None


def validate_positive_int(value: Any, name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate positive integer.

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(value, int):
        return False, f"{name} must be an integer, got {type(value).__name__}"

    if value < 1:
        return False, f"{name} must be positive, got {value}"

    return True, None


def validate_test_case_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate test case name format.

    Returns:
        (is_valid, error_message)
    """
    if not name:
        return False, "Test case name cannot be empty"

    pattern = r'^[a-zA-Z0-9_]+$'
    if not re.match(pattern, name):
        return False, f"Test case name must contain only alphanumeric characters and underscores: {name}"

    return True, None


def validate_path(path: str, must_exist: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Validate file/directory path.

    Returns:
        (is_valid, error_message)
    """
    if not path:
        return False, "Path cannot be empty"

    if must_exist:
        import os
        if not os.path.exists(path):
            return False, f"Path does not exist: {path}"

    return True, None
