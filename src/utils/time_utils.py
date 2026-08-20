"""时间与交易日工具"""
import json
import os
import sys
from datetime import date, datetime, timedelta

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def project_root() -> str:
    """项目根目录：exe 场景用环境变量覆盖（数据写到 exe 旁），否则用代码位置推导"""
    env = os.environ.get('DAILY_REVIEW_ROOT')
    return env if env else _PROJECT_ROOT

# 简单交易日历：2026年法定节假日调休补班（逐年维护，可扩展）
_EXTRA_TRADE_DAYS = {
    "2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18",  # 春节调休补班示例
}
_EXTRA_HOLIDAYS = {
    "2026-01-01", "2026-01-02",
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-04-06", "2026-05-01", "2026-06-19",
    "2026-09-25", "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",
}


def is_trade_day(d: date, custom_trade_dates: list = None) -> bool:
    """判断是否交易日：节假日表优先，其次周末。custom_trade_dates 来自 settings.json"""
    ds = d.strftime("%Y-%m-%d")
    if custom_trade_dates:
        if ds in custom_trade_dates:
            return True
    if ds in _EXTRA_HOLIDAYS:
        return False
    if d.weekday() >= 5:
        return ds in _EXTRA_TRADE_DAYS
    return True


def previous_trade_day(d: date) -> date:
    """向前找最近交易日（最多回退10天）"""
    for i in range(1, 11):
        cand = d - timedelta(days=i)
        if is_trade_day(cand):
            return cand
    return d - timedelta(days=1)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")




def _config_path(name: str) -> str:
    """配置文件路径：exe 内置(_MEIPASS)优先，其次 exe 旁/项目目录"""
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle:
        p = os.path.join(bundle, 'config', name)
        if os.path.exists(p):
            return p
    return os.path.join(project_root(), 'config', name)

def load_settings() -> dict:
    with open(_config_path("settings.json"), encoding="utf-8") as f:
        return json.load(f)


def load_market_codes() -> dict:
    with open(_config_path("market_codes.json"), encoding="utf-8") as f:
        return json.load(f)


def load_watchlist() -> list:
    with open(_config_path("watchlist.json"), encoding="utf-8") as f:
        return json.load(f).get("watchlist", [])
