#!/usr/bin/env python3
"""计算两个规范时间戳 JSON 文件之间的耗时。

用法：
    python3 scripts/calculate_timestamp_diff.py \\
        --start /path/to/start_timestamp.json \\
        --end /path/to/end_timestamp.json

    python3 scripts/calculate_timestamp_diff.py \\
        --start /path/to/start_timestamp.json \\
        --end /path/to/end_timestamp.json \\
        --output /path/to/duration.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_NAME = Path(__file__).name
SCRIPT_PATH = str(Path(__file__).resolve())
# 用于验证时间戳文件是否由规范的 write_system_timestamp.py 生成
_TIMESTAMP_GENERATOR_NAME = "write_system_timestamp.py"
_TIMESTAMP_GENERATOR_PATH = str(
    (Path(__file__).resolve().parent / "write_system_timestamp.py").resolve()
)


def _parse_timestamp(value: str) -> datetime:
    """解析 ISO 8601 时间戳字符串为 UTC datetime。"""
    raw = str(value or "").strip().replace("Z", "+00:00")
    if not raw:
        raise ValueError("时间戳为空")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_timestamp_payload(path: Path) -> dict[str, Any]:
    """读取并验证时间戳 JSON 载荷。

    验证规则：
    - 必须包含 timestamp、generated_by、generator_path 字段
    - generated_by 必须为 write_system_timestamp.py
    - generator_path 必须与当前工程中的 write_system_timestamp.py 路径一致
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} 的内容不是 JSON 对象")

    timestamp = str(payload.get("timestamp") or "").strip()
    generator = str(payload.get("generated_by") or "").strip()
    generator_path = str(payload.get("generator_path") or "").strip()
    if not timestamp:
        raise ValueError(f"{path} 缺少 timestamp 字段")
    if generator != _TIMESTAMP_GENERATOR_NAME or generator_path != _TIMESTAMP_GENERATOR_PATH:
        raise ValueError(
            f"{path} 不是由规范的 write_system_timestamp.py 生成，"
            f"expected generated_by={_TIMESTAMP_GENERATOR_NAME}, "
            f"generator_path={_TIMESTAMP_GENERATOR_PATH}"
        )
    return payload


def calculate_duration(start_path: Path, end_path: Path) -> dict[str, Any]:
    """计算两个时间戳之间的耗时。

    Args:
        start_path: start_timestamp.json 路径
        end_path: end_timestamp.json 路径

    Returns:
        包含 start_timestamp、end_timestamp、duration_seconds 等字段的字典

    Raises:
        ValueError: 时间戳文件无效或 end 早于 start
    """
    start_payload = _read_timestamp_payload(start_path)
    end_payload = _read_timestamp_payload(end_path)

    start_timestamp = str(start_payload["timestamp"]).strip()
    end_timestamp = str(end_payload["timestamp"]).strip()
    start_dt = _parse_timestamp(start_timestamp)
    end_dt = _parse_timestamp(end_timestamp)
    duration_seconds = round((end_dt - start_dt).total_seconds(), 6)
    if duration_seconds < 0:
        raise ValueError("结束时间戳早于开始时间戳")

    return {
        "schema_version": "timestamp_duration_v1",
        "start_timestamp": start_timestamp,
        "end_timestamp": end_timestamp,
        "duration_seconds": duration_seconds,
        "duration_milliseconds": int(round(duration_seconds * 1000)),
        "method": SCRIPT_NAME,
        "formula": "end_timestamp - start_timestamp",
        "start_evidence_path": str(start_path.resolve()),
        "end_evidence_path": str(end_path.resolve()),
        "calculated_by": SCRIPT_NAME,
        "calculator_path": SCRIPT_PATH,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="计算两个规范时间戳 JSON 文件之间的耗时")
    parser.add_argument("--start", required=True, help="start_timestamp.json 文件路径")
    parser.add_argument("--end", required=True, help="end_timestamp.json 文件路径")
    parser.add_argument("--output", help="可选的输出 JSON 文件路径")
    args = parser.parse_args()

    payload = calculate_duration(Path(args.start), Path(args.end))
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"耗时计算结果已写入：{output_path}")
    else:
        print(rendered, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
