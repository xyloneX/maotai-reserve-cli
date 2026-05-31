#!/usr/bin/env python3
"""将 SQLite admin.db 迁移到 MySQL（生产环境扩容用）。

用法:
  export MYSQL_URL='mysql+pymysql://user:pass@127.0.0.1:3306/maotai?charset=utf8mb4'
  python scripts/migrate_sqlite_to_mysql.py

迁移后设置 deploy/.env:
  MT_DATABASE_URL=mysql+pymysql://...
  sudo systemctl restart maotai-api
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SQLITE_URL = os.environ.get("SQLITE_URL", f"sqlite:///{ROOT / 'data' / 'admin.db'}")
MYSQL_URL = os.environ.get("MYSQL_URL", "")


def main() -> int:
    if not MYSQL_URL:
        print("请设置环境变量 MYSQL_URL", file=sys.stderr)
        print("示例: mysql+pymysql://maotai:密码@127.0.0.1:3306/maotai?charset=utf8mb4")
        return 1

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.app.models.entities import (
        Account,
        Job,
        LotteryResult,
        Product,
        ReserveRecord,
        SystemSetting,
    )
    from backend.app.core.database import Base

    src = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    dst = create_engine(MYSQL_URL, pool_pre_ping=True)

    print("==> 在 MySQL 创建表结构")
    Base.metadata.create_all(bind=dst)

    SrcSession = sessionmaker(bind=src)
    DstSession = sessionmaker(bind=dst)

    order = [Product, Account, Job, ReserveRecord, LotteryResult, SystemSetting]

    for model in order:
        name = model.__tablename__
        s = SrcSession()
        d = DstSession()
        try:
            rows = s.query(model).all()
            if not rows:
                print(f"  {name}: 0 行，跳过")
                continue
            d.query(model).delete()
            for row in rows:
                d.merge(row)
            d.commit()
            print(f"  {name}: {len(rows)} 行")
        except Exception as e:
            d.rollback()
            print(f"  {name}: 失败 {e}", file=sys.stderr)
            return 1
        finally:
            s.close()
            d.close()

    print("\n✅ 迁移完成。请更新 MT_DATABASE_URL 并重启 API。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
