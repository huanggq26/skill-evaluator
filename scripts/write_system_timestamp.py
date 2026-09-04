#!/usr/bin/env python3
"""将当前系统 UTC 时间戳写入 JSON 文件。

用法：
    python3 scripts/write_system_timestamp.py
    python3 scripts/write_system_timestamp.py --output /path/to/end_timestamp.json

输出的 JSON 结构见 references/specs/timestamp.spec.md。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from _common import _utc_now_iso

SCRIPT_NAME = Path(__file__).name
SCRIPT_PATH = str(Path(__file__).resolve())


def generate_timestamp_payload() -> dict[str, str]:
    """生成规范的时间戳载荷。"""
    return {
        "schema_version": "system_timestamp_v1",
        "timestamp": _utc_now_iso(),
        "generated_by": SCRIPT_NAME,
        "generator_path": SCRIPT_PATH,
        "timestamp_source": "system_utc_now",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="将当前系统 UTC 时间戳写入 JSON 文件")
    parser.add_argument("--output", help="输出 JSON 文件路径，不指定则输出到标准输出")
    args = parser.parse_args()

    payload = generate_timestamp_payload()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        print(f"时间戳已写入：{output_path}")
    else:
        print(rendered, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
