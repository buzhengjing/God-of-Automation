#!/usr/bin/env python3
"""
MAPE (Mean Absolute Percentage Error) 评测脚本
用于端到端机器人模型（如 RoboBrain-X0-Preview, pi0）的动作张量评测。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import ProgressLogger, load_config, build_detail, save_json

try:
    import numpy as np
except ImportError:
    np = None


def compute_mape(reference: 'np.ndarray', predicted: 'np.ndarray', epsilon: float = 1e-8) -> float:
    """
    计算 MAPE (Mean Absolute Percentage Error)。

    MAPE = mean(|reference - predicted| / (|reference| + epsilon)) * 100

    Args:
        reference: 参考动作张量
        predicted: 预测动作张量
        epsilon: 避免除零

    Returns:
        MAPE 百分比值
    """
    if np is None:
        raise ImportError("numpy is required for MAPE computation")

    reference = np.array(reference, dtype=np.float64)
    predicted = np.array(predicted, dtype=np.float64)

    if reference.shape != predicted.shape:
        raise ValueError(f"Shape mismatch: reference {reference.shape} vs predicted {predicted.shape}")

    abs_error = np.abs(reference - predicted)
    abs_ref = np.abs(reference) + epsilon

    mape = np.mean(abs_error / abs_ref) * 100
    return float(mape)


def evaluate_mape(config: dict, logger: ProgressLogger = None) -> dict:
    """
    评测 MAPE。

    从配置中读取参考动作张量和预测动作张量路径。
    """
    if np is None:
        return build_detail("MAPE", 0.0, {"error": "numpy not installed"}, "F")

    model_name = config['model']['name']
    mape_cfg = config.get('mape', {})
    ref_path = mape_cfg.get('reference_actions_path', '')
    pred_path = mape_cfg.get('predicted_actions_path', '')

    if not ref_path or not pred_path:
        msg = "MAPE requires both reference_actions_path and predicted_actions_path in config"
        if logger:
            logger.log(f"[ERROR] {msg}")
        return build_detail("MAPE", 0.0, {"error": msg}, "F")

    if logger:
        logger.section(f"MAPE Evaluation - {model_name}")
        logger.log(f"Reference: {ref_path}")
        logger.log(f"Predicted: {pred_path}")

    try:
        reference = np.load(ref_path)
        predicted = np.load(pred_path)

        if logger:
            logger.log(f"Reference shape: {reference.shape}")
            logger.log(f"Predicted shape: {predicted.shape}")

        mape_value = compute_mape(reference, predicted)

        if logger:
            logger.log(f"MAPE = {mape_value:.4f}%")

        return build_detail("MAPE", mape_value, {
            "mape_percent": round(mape_value, 4),
            "reference_shape": list(reference.shape),
            "predicted_shape": list(predicted.shape),
        })

    except Exception as e:
        error_msg = f"MAPE computation error: {str(e)}"
        if logger:
            logger.log(f"[ERROR] {error_msg}")
        return build_detail("MAPE", 0.0, {"error": error_msg}, "F")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='MAPE Evaluation')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--reference', default=None, help='Override reference actions path')
    parser.add_argument('--predicted', default=None, help='Override predicted actions path')
    parser.add_argument('--output', default='outputs/custom/mape_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_mape.log')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    if args.reference:
        config.setdefault('mape', {})['reference_actions_path'] = args.reference
    if args.predicted:
        config.setdefault('mape', {})['predicted_actions_path'] = args.predicted

    logger = ProgressLogger(args.log)
    result = evaluate_mape(config, logger)
    save_json(result, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
