"""CoinGecko 数字货币数据源（免费、无需 key、本机可直连）
注意：免费 API 有速率限制，遇 429 自动退避重试。"""
import logging
import time

import requests

logger = logging.getLogger("daily_review.collector.coingecko")

PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin}/market_chart"

# 币名 -> CoinGecko id
_ID_MAP = {"BTCUSDT": "bitcoin", "ETHUSDT": "ethereum"}
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _get(url, params, timeout):
    """带 429 退避的 GET"""
    for attempt in range(3):
        r = requests.get(url, params=params, headers=_HEADERS, timeout=timeout)
        if r.status_code == 429:
            wait = 8 * (attempt + 1)
            logger.warning("CoinGecko 429 限流，%.0fs 后重试", wait)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError("CoinGecko 持续限流")


def fetch_crypto(symbols: list, timeout: int = 20) -> (bool, list):
    """BTC/ETH 现价 + 24h 涨跌幅"""
    ids = ",".join(_ID_MAP.get(s["symbol"], s["symbol"].lower()) for s in symbols)
    out = []
    ok = False
    try:
        r = _get(PRICE_URL, {"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"}, timeout)
        data = r.json()
        for s in symbols:
            cid = _ID_MAP.get(s["symbol"], s["symbol"].lower())
            d = data.get(cid, {})
            out.append({
                "symbol": s["symbol"], "name": s["name"],
                "price": _num(d.get("usd")),
                "pct_change": _num(d.get("usd_24h_change")),
                "high_24h": None, "low_24h": None, "volume_24h": None,
            })
        ok = True
    except Exception as e:
        logger.warning("CoinGecko 行情失败: %s", e)
        for s in symbols:
            out.append({"symbol": s["symbol"], "name": s["name"], "price": None,
                        "pct_change": None, "high_24h": None, "low_24h": None, "volume_24h": None})
    return (ok, out)


def fetch_crypto_klines(symbol: str, days: int = 7, timeout: int = 20) -> (bool, list):
    """最近 N 日日K。返回 [{'date','close'}]"""
    cid = _ID_MAP.get(symbol, symbol.lower())
    try:
        r = _get(CHART_URL.format(coin=cid),
                 {"vs_currency": "usd", "days": days, "interval": "daily"}, timeout)
        data = r.json().get("prices", [])
        out = []
        for p in data:
            out.append({"date": time.strftime("%Y-%m-%d", time.localtime(p[0] / 1000)),
                        "close": _num(p[1])})
        return (True, out)
    except Exception as e:
        logger.warning("CoinGecko K线失败 %s: %s", symbol, e)
        return (False, [])
