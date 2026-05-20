#!/usr/bin/env python3
"""茅台抢单软件 — 启动 CLI（推荐唯一入口）"""

import sys

from src.cli_app import run_interactive


def main() -> None:
    try:
        run_interactive()
    except KeyboardInterrupt:
        print("\n已退出")
        sys.exit(0)


if __name__ == "__main__":
    main()
