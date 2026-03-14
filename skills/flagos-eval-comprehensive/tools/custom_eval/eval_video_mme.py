#!/usr/bin/env python3
"""
Video-MME 评测脚本
视频理解评测（Video Multi-Modal Evaluation）。
通过抽帧方式将视频转为多张图片，调用多模态 API 评测。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import (
    ProgressLogger, load_config, call_multimodal_api,
    extract_choice_answer, build_detail, save_json, load_jsonl,
    MULTIMODAL_CHOICE_PROMPT_TEMPLATE,
)


def extract_video_frames(video_path: str, num_frames: int = 8):
    """
    从视频中均匀抽取帧并编码为 base64。
    需要安装 opencv-python: pip install opencv-python

    Returns:
        list of base64 encoded frames (bytes)
    """
    try:
        import cv2
        import base64
    except ImportError:
        return None

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if total_frames <= 0:
        cap.release()
        return None

    indices = [int(i * total_frames / num_frames) for i in range(num_frames)]
    frames = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            _, buffer = cv2.imencode('.jpg', frame)
            frames.append(buffer.tobytes())

    cap.release()
    return frames if frames else None


def evaluate_video_mme(config: dict, dataset_path: str = "datasets/Video-MME",
                       limit: int = None, num_frames: int = 8,
                       logger: ProgressLogger = None) -> dict:
    """
    评测 Video-MME。

    数据集格式（JSONL）：
    {"id": str, "video": str(path), "question": str, "options": list, "answer": str, "duration": str}
    """
    model_name = config['model']['name']
    data_file = os.path.join(dataset_path, "test.jsonl")
    data = load_jsonl(data_file)

    if not data:
        if logger:
            logger.log(f"[ERROR] Video-MME dataset not found at {data_file}")
        return build_detail("Video-MME", 0.0, {"error": f"Dataset not found: {data_file}"}, "F")

    if limit:
        data = data[:limit]

    if logger:
        logger.section(f"Video-MME Evaluation - {model_name}")
        logger.log(f"Total samples: {len(data)}, Frames per video: {num_frames}")

    from collections import defaultdict
    dur_correct = defaultdict(int)
    dur_total = defaultdict(int)
    correct = 0
    total = len(data)

    for i, item in enumerate(data):
        qid = item.get('id', i)
        video_path = item.get('video', '')
        question = item.get('question', '')
        options = item.get('options', [])
        expected = item.get('answer', '').strip().upper()
        duration = item.get('duration', 'medium')

        dur_total[duration] += 1

        # 构建带选项的问题
        if options:
            options_str = "\n".join([f"{chr(65+j)}. {opt}" for j, opt in enumerate(options)])
            full_question = f"{question}\n\n{options_str}"
        else:
            full_question = question

        prompt = MULTIMODAL_CHOICE_PROMPT_TEMPLATE.format(
            question=full_question, choices="A, B, C, D"
        )

        # 抽帧
        full_video_path = os.path.join(dataset_path, video_path) if not os.path.isabs(video_path) else video_path
        frames = extract_video_frames(full_video_path, num_frames)

        if frames is None:
            if logger:
                logger.log(f"[{i+1}/{total}] ID={qid}: FRAME_EXTRACT_ERROR")
            continue

        response, _ = call_multimodal_api(prompt, frames, config)
        if response is None:
            if logger:
                logger.log(f"[{i+1}/{total}] ID={qid}: API_ERROR")
            continue

        predicted = extract_choice_answer(response)
        is_correct = predicted == expected

        if is_correct:
            correct += 1
            dur_correct[duration] += 1

        status = "CORRECT" if is_correct else "WRONG"
        if logger:
            logger.log(f"[{i+1}/{total}] ID={qid} [{duration}]: {status} | Pred={predicted} | Exp={expected}")

    accuracy = (correct / total * 100) if total > 0 else 0.0

    raw_details = {"accuracy": round(accuracy, 2)}
    for dur in ['short', 'medium', 'long']:
        if dur_total[dur] > 0:
            raw_details[dur] = round(dur_correct[dur] / dur_total[dur] * 100, 2)

    if logger:
        logger.section(f"Video-MME Complete: {correct}/{total} = {accuracy:.2f}%")

    return build_detail("Video-MME", accuracy, raw_details)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Video-MME Evaluation')
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--dataset-path', default='datasets/Video-MME')
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument('--num-frames', type=int, default=8)
    parser.add_argument('--output', default='outputs/custom/video_mme_result.json')
    parser.add_argument('--log', default='outputs/custom/eval_video_mme.log')
    args = parser.parse_args()

    config = load_config(args.config)
    if not config:
        sys.exit(1)

    logger = ProgressLogger(args.log)
    result = evaluate_video_mme(config, args.dataset_path, args.limit, args.num_frames, logger)
    save_json(result, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
