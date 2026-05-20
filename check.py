#!/usr/bin/env python3
"""一键自检（命令行版）。"""

import sys

from src.health import run_health_check

ICONS = {"ok": "✓", "warn": "!", "fail": "✗"}


def main() -> int:
    print("i茅台工具 · 健康检查\n")
    report = run_health_check()
    for item in report.items:
        icon = ICONS.get(item.level, "?")
        print(f"  [{icon}] [{item.category}] {item.message}")
    print()
    if report.passed:
        print("检查通过。交互界面: python cli.py")
        return 0
    print(f"检查未通过 ({report.error_count} 项)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
