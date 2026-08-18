"""Binance 数字货币数据源（无需 API key）"""
import logging
import time

import requests

logger = logging.getLogger("daily_review.collector.binance")

BASE = "https://api.binance.com"
TICKER_URL = f"{BASE}/api/v3/ticker/24hr"
KLINE_URL = f"{BASE}/api/v3/klines"


def fetch_crypto(symbols: list, timeout: int = 15) -> (bool, list):
    """BTC/ETH 24hr 行情。symbols: [{'symbol':'BTCUSDT','name':'Bitcoin'}]"""
    out = []
    ok = False
    try:
        syms = [s["symbol"] for s in symbols]
        r = requests.get(TICKER_URL, params={"symbols": '["' + '","'.join(syms) + '"]'}, timeout=timeout)
        r.raise_for_status()
        data = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        by_sym = {d["symbol"]: d for d in data}
        for s in symbols:
            d = by_sym.get(s["symbol"])
            if d is None:
                out.append({"symbol": s["symbol"], "name": s["name"], "price": None,
                            "pct_change": None, "high_24h": None, "low_24h": None, "volume_24h": None})
                continue
            out.append({
                "symbol": s["symbol"], "name": s["name"],
                "price": _f(d.get("lastPrice")), "pct_change": _f(d.get("priceChangePercent")),
                "high_24h": _f(d.get("highPrice")), "low_24h": _f(d.get("lowPrice")),
                "volume_24h": _f(d.get("quoteVolume")),
            })
        ok = True
    except Exception as e:
        logger.warning("Binance 24hr 行情失败: %s", e)
        for s in symbols:
            out.append({"symbol": s["symbol"], "name": s["name"], "price": None,
                        "pct_change": None, "high_24h": None, "low_24h": None, "volume_24h": None})
    return (ok, out)


def fetch_crypto_klines(symbol: str, limit: int = 7, timeout: int = 15) -> (bool, list):
    """最近 N 日日K。返回 [{'date','close'}]"""
    try:
        r = requests.get(KLINE_URL, params={"symbol": symbol, "interval": "1d", "limit": limit}, timeout=timeout)
        r.raise_for_status()
        out = []
        for k in r.json():
            out.append({"date": time.strftime("%Y-%m-%d", time.localtime(k[0] / 1000)), "close": _f(k[4])})
        return (True, out)
    except Exception as e:
        logger.warning("Binance K线失败 %s: %s", symbol, e)
        return (False, [])


def _f(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
