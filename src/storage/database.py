"""SQLite 存储层：建表 / upsert / 查询"""
import json
import os
import sqlite3
from datetime import datetime
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS run_log (
  run_date TEXT PRIMARY KEY, status TEXT,
  started_at TEXT, finished_at TEXT, report_path TEXT, source TEXT, error_msg TEXT);
CREATE TABLE IF NOT EXISTS trade_dates ( date TEXT PRIMARY KEY, is_trade_day INTEGER DEFAULT 1 );
CREATE TABLE IF NOT EXISTS daily_market (
  date TEXT PRIMARY KEY, market_score INTEGER, state TEXT, risk_level TEXT,
  up_count INTEGER, down_count INTEGER, limit_up INTEGER, limit_down INTEGER,
  total_amount REAL, main_net_inflow REAL, sentiment TEXT );
CREATE TABLE IF NOT EXISTS daily_indices (
  date TEXT, code TEXT, name TEXT, close REAL, pct_change REAL, amount REAL,
  main_net_inflow REAL, ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL,
  PRIMARY KEY(date,code) );
CREATE TABLE IF NOT EXISTS daily_stocks (
  date TEXT, code TEXT, name TEXT, close REAL, pct_change REAL, volume REAL,
  turnover_rate REAL, market_cap REAL, pe REAL, pb REAL, main_net_inflow REAL,
  ma5 REAL, ma10 REAL, ma20 REAL, ma60 REAL, macd_dif REAL, macd_dea REAL,
  macd_hist REAL, rsi14 REAL, kdj_k REAL, kdj_d REAL, kdj_j REAL,
  boll_upper REAL, boll_mid REAL, boll_lower REAL, trend TEXT, tech_state TEXT,
  risk_level TEXT, fundamental_grade TEXT, grade TEXT,
  roe REAL, revenue_yoy REAL, profit_yoy REAL, gross_margin REAL,
  PRIMARY KEY(date,code) );
CREATE TABLE IF NOT EXISTS daily_sectors (
  date TEXT, code TEXT, name TEXT, pct_change REAL, main_net_inflow REAL,
  rank INTEGER, strength TEXT, consecutive_up_days INTEGER, heat REAL,
  PRIMARY KEY(date,code) );
CREATE TABLE IF NOT EXISTS daily_futures (
  date TEXT, symbol TEXT, name TEXT, close REAL, pct_change REAL,
  trend TEXT, risk_hint TEXT, PRIMARY KEY(date,symbol) );
CREATE TABLE IF NOT EXISTS daily_crypto (
  date TEXT, symbol TEXT, price REAL, pct_change REAL,
  sentiment TEXT, risk_level TEXT, PRIMARY KEY(date,symbol) );
CREATE TABLE IF NOT EXISTS daily_reports (
  date TEXT PRIMARY KEY, market_summary TEXT, manager_view TEXT,
  html_path TEXT, data_sources TEXT, created_at TEXT );
"""


class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(_PROJECT_ROOT, "data", "market.db")
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_db(self):
        with self._conn() as conn:
            conn.executescript(_SCHEMA)
        self._migrate()

    def _migrate(self):
        """轻量迁移：为旧库补充新增列"""
        try:
            with self._conn() as conn:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(daily_stocks)").fetchall()]
                for col, ddl in (("grade", "TEXT"), ("roe", "REAL"), ("revenue_yoy", "REAL"),
                                 ("profit_yoy", "REAL"), ("gross_margin", "REAL")):
                    if cols and col not in cols:
                        conn.execute(f"ALTER TABLE daily_stocks ADD COLUMN {col} {ddl}")
        except Exception:
            pass

    # ---------- run_log ----------
    def start_run(self, run_date: str, source: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO run_log(run_date,status,started_at,source) VALUES(?,?,?,?) "
                "ON CONFLICT(run_date) DO UPDATE SET status='running',started_at=excluded.started_at,source=excluded.source,error_msg=NULL",
                (run_date, "running", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), source))

    def finish_run(self, run_date: str, status: str, report_path: str = "", error_msg: str = "") -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE run_log SET status=?,finished_at=?,report_path=?,error_msg=? WHERE run_date=?",
                (status, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), report_path, error_msg, run_date))

    def get_latest_run(self) -> Optional[str]:
        with self._conn() as conn:
            row = conn.execute("SELECT MAX(run_date) AS d FROM run_log WHERE status IN ('success','partial')").fetchone()
            return row["d"] if row and row["d"] else None

    def has_run(self, run_date: str) -> bool:
        with self._conn() as conn:
            row = conn.execute("SELECT 1 FROM run_log WHERE run_date=?", (run_date,)).fetchone()
            return row is not None

    # ---------- upsert ----------
    def clear_date(self, table: str, date: str) -> None:
        """清空某日数据（保证入库与当日数据源一致，不残留已删除标的）"""
        with self._conn() as conn:
            conn.execute(f"DELETE FROM {table} WHERE date=?", (date,))

    def upsert_market(self, d: dict) -> None:
        keys = ["date", "market_score", "state", "risk_level", "up_count", "down_count",
                "limit_up", "limit_down", "total_amount", "main_net_inflow", "sentiment"]
        cols = ", ".join(keys)
        placeholders = ", ".join("?" * len(keys))
        update = ", ".join(f"{k}=excluded.{k}" for k in keys if k != "date")
        with self._conn() as conn:
            conn.execute(f"INSERT INTO daily_market({cols}) VALUES({placeholders}) "
                         f"ON CONFLICT(date) DO UPDATE SET {update}", [d.get(k) for k in keys])

    def upsert_indices(self, date: str, rows: list) -> None:
        self._bulk("daily_indices", date, rows,
                   ["code", "name", "close", "pct_change", "amount", "main_net_inflow",
                    "ma5", "ma10", "ma20", "ma60"])

    def upsert_stocks(self, date: str, rows: list) -> None:
        self._bulk("daily_stocks", date, rows,
                   ["code", "name", "close", "pct_change", "volume", "turnover_rate",
                    "market_cap", "pe", "pb", "main_net_inflow",
                    "ma5", "ma10", "ma20", "ma60", "macd_dif", "macd_dea", "macd_hist",
                    "rsi14", "kdj_k", "kdj_d", "kdj_j",
                    "boll_upper", "boll_mid", "boll_lower",
                    "trend", "tech_state", "risk_level", "fundamental_grade", "grade",
                    "roe", "revenue_yoy", "profit_yoy", "gross_margin"])

    def upsert_sectors(self, date: str, rows: list) -> None:
        self._bulk("daily_sectors", date, rows,
                   ["code", "name", "pct_change", "main_net_inflow", "rank", "strength",
                    "consecutive_up_days", "heat"])

    def upsert_futures(self, date: str, rows: list) -> None:
        self._bulk("daily_futures", date, rows,
                   ["symbol", "name", "close", "pct_change", "trend", "risk_hint"])

    def upsert_crypto(self, date: str, rows: list) -> None:
        self._bulk("daily_crypto", date, rows,
                   ["symbol", "price", "pct_change", "sentiment", "risk_level"])

    def _bulk(self, table: str, date: str, rows: list, cols: list) -> None:
        if not rows:
            return
        placeholders = ", ".join("?" * (len(cols) + 1))
        update = ", ".join(f"{c}=excluded.{c}" for c in cols)
        with self._conn() as conn:
            for r in rows:
                values = [date] + [r.get(c) for c in cols]
                conn.execute(f"INSERT INTO {table}(date,{','.join(cols)}) VALUES({placeholders}) "
                             f"ON CONFLICT(date,{cols[0]}) DO UPDATE SET {update}", values)

    def save_report(self, date: str, market_summary: str, manager_view: str,
                    html_path: str, data_sources: dict) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO daily_reports(date,market_summary,manager_view,html_path,data_sources,created_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET "
                "market_summary=excluded.market_summary, manager_view=excluded.manager_view, "
                "html_path=excluded.html_path, data_sources=excluded.data_sources",
                (date, market_summary, manager_view, html_path, json.dumps(data_sources, ensure_ascii=False),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # ---------- 查询 ----------
    def get_report(self, date: str) -> Optional[dict]:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM daily_reports WHERE date=?", (date,)).fetchone()
            return dict(row) if row else None

    def get_stocks(self, date: str) -> list:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM daily_stocks WHERE date=? ORDER BY pct_change DESC", (date,)).fetchall()
            return [dict(r) for r in rows]

    def get_indices(self, date: str) -> list:
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM daily_indices WHERE date=? ORDER BY weight DESC", (date,)).fetchall() \
                if self._has_col("daily_indices", "weight") else \
                conn.execute("SELECT * FROM daily_indices WHERE date=?", (date,)).fetchall()
            return [dict(r) for r in rows]

    def _has_col(self, table: str, col: str) -> bool:
        with self._conn() as conn:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            return col in cols


if __name__ == "__main__":
    db = Database()
    print("DB init OK:", db.db_path)
