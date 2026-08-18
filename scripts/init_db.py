"""初始化数据库（建表）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage.database import Database

if __name__ == "__main__":
    db = Database()
    print("数据库初始化完成:", db.db_path)
    print("表清单:")
    with db._conn() as conn:
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
            print("  -", r["name"])
