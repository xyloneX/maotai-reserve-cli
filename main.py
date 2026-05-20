#!/usr/bin/env python3
"""
i茅台自动预约 — 个人自用。

用法:
  python main.py              # 正式预约
  python main.py --dry-run    # 试跑
  python cli.py               # 交互式 CLI（推荐）
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.exceptions import ConfigError
from src.runner import execute_reserve

LOG_DIR = Path(__file__).resolve().parent / "data"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "run.log", encoding="utf-8"),
    ],
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="i茅台自动预约")
    p.add_argument("--dry-run", action="store_true", help="试跑，不提交")
    p.add_argument("--skip-wait", action="store_true", help="跳过定时等待")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    try:
        success, lines = execute_reserve(
            dry_run=args.dry_run,
            skip_wait=args.skip_wait,
        )
    except (FileNotFoundError, ConfigError) as e:
        logging.error("%s", e)
        sys.exit(1)

    body = "\n".join(lines)
    print("\n" + "=" * 40)
    print(body)
    print("=" * 40)
    if args.dry_run:
        print("试跑未提交。确认后: python main.py  或  python cli.py")
    else:
        print("预约≠中签，中签后请在 App 内 24 小时内支付。")
    sys.exit(0 if success or args.dry_run else 1)


if __name__ == "__main__":
    main()
