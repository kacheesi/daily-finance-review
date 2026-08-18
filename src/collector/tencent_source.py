"""腾讯行情数据源：指数/个股实时行情 + 日K线（免费、稳定、国内直连）
接口：qt.gtimg.cn（实时批量）/ web.ifzq.gtimg.cn（K线）"""
import logging
import re

import requests

logger = logging.getLogger("daily_review.collector.tencent")

QUOTE_URL = "https://qt.gtimg.cn/q={symbols}"
KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_TIMEOUT = 15

# 腾讯实时行情字段索引（v_xxx 按 ~ 分割，实测校准 2026-08）
# [38]=换手率 [39]=PE [41]=最高 [42]=最低 [43]=振幅 [44]=流通市值(亿)
# [45]=总市值(亿) [46]=PB [47]=涨停价 [48]=跌停价 [37]=成交额(万)
IDX = {
    "name": 1, "code": 2, "price": 3, "pre_close": 4, "open": 5,
    "volume": 6, "time": 30, "pct_change": 32, "high": 41, "low": 42,
    "amount": 37, "turnover": 38, "pe": 39, "mktcap": 45, "pb": 46,
}
AMOUNT_UNIT_WAN = 10000.0  # 腾讯成交额单位为万元


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def tx_symbol(code: str) -> str:
    """A股代码 -> 腾讯代码（指数/个股自动加前缀）"""
    if code.startswith(("sh", "sz", "bj")):
        return code
    if code.startswith(("6", "5", "9", "000001")):  # 沪市: 60x/68x/5xx/9xx + 上证指数
        return "sh" + code
    return "sz" + code


def fetch_quotes(symbols: list) -> (bool, dict):
    """批量实时行情。symbols 为已带前缀的腾讯代码。返回 {symbol: {字段dict}}"""
    out = {}
    if not symbols:
        return (True, out)
    try:
        r = requests.get(QUOTE_URL.format(symbols=",".join(symbols)),
                         headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        text = r.text
        for m in re.finditer(r'v_(\w+)="([^"]*)"', text):
            sym = m.group(1)
            fields = m.group(2).split("~")
            if len(fields) < 46:
                continue
            out[sym] = {
                "name": fields[IDX["name"]],
                "code": fields[IDX["code"]],
                "price": _num(fields[IDX["price"]]),
                "pre_close": _num(fields[IDX["pre_close"]]),
                "pct_change": _num(fields[IDX["pct_change"]]),
                "volume": _num(fields[IDX["volume"]]),
                "amount": (_num(fields[IDX["amount"]]) or 0) * AMOUNT_UNIT_WAN if _num(fields[IDX["amount"]]) else None,
                "turnover": _num(fields[IDX["turnover"]]),
                "pe": _num(fields[IDX["pe"]]),
                "mktcap": _num(fields[IDX["mktcap"]]),
                "pb": _num(fields[IDX["pb"]]),
                "high": _num(fields[IDX["high"]]),
                "low": _num(fields[IDX["low"]]),
            }
        return (True, out)
    except Exception as e:
        logger.warning("腾讯行情失败: %s", e)
        return (False, out)


def fetch_index_spot(indices_cfg: list) -> (bool, list):
    """9大指数行情（含涨跌幅/成交额）"""
    syms = [tx_symbol(i["code"]) for i in indices_cfg]
    ok, quotes = fetch_quotes(syms)
    out = []
    for i, sym in zip(indices_cfg, syms):
        q = quotes.get(sym)
        if not q:
            out.append({"code": i["code"], "name": i["name"], "close": None,
                        "pct_change": None, "amount": None, "main_net_inflow": None})
            continue
        out.append({"code": i["code"], "name": i["name"], "close": q["price"],
                    "pct_change": q["pct_change"], "amount": q["amount"],
                    "main_net_inflow": None})
    return (ok, out)


def fetch_stock_spot(watchlist: list) -> (bool, list):
    """自选股行情快照（含换手/市值/PE/PB）"""
    syms = [tx_symbol(s["code"]) for s in watchlist]
    ok, quotes = fetch_quotes(syms)
    out = []
    for s, sym in zip(watchlist, syms):
        q = quotes.get(sym)
        if not q:
            out.append({"code": s["code"], "name": s["name"], "close": None,
                        "pct_change": None, "volume": None, "turnover_rate": None,
                        "market_cap": None, "pe": None, "pb": None, "main_net_inflow": None})
            continue
        out.append({
            "code": s["code"], "name": q.get("name") or s["name"],
            "close": q["price"], "pct_change": q["pct_change"],
            "volume": q["volume"], "turnover_rate": q["turnover"],
            "market_cap": q["mktcap"], "pe": q["pe"], "pb": q["pb"],
            "main_net_inflow": None,
        })
    return (ok, out)


def fetch_kline(code: str, days: int = 120) -> (bool, list):
    """个股/指数日K线（前复权）。返回 [{date,open,close,high,low,volume}]"""
    sym = tx_symbol(code)
    try:
        r = requests.get(KLINE_URL, params={"param": f"{sym},day,,,{days},qfq"},
                         headers=_HEADERS, timeout=_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
        data = payload.get("data", {}).get(sym)
        if not isinstance(data, dict):  # 指数可能返回 list 或缺失
            logger.warning("腾讯K线结构异常 %s: %s", code, type(data).__name__)
            return (False, [])
        # 腾讯返回 key 可能是 day/qfqday/hfqday
        klist = data.get("qfqday") or data.get("day") or data.get("hfqday") or []
        out = []
        for k in klist:
            # [date, open, close, high, low, volume, ...]
            out.append({
                "date": k[0], "open": _num(k[1]), "close": _num(k[2]),
                "high": _num(k[3]), "low": _num(k[4]), "volume": _num(k[5]),
                "amount": None,
            })
        return (True, out)
    except Exception as e:
        logger.warning("腾讯K线失败 %s: %s", code, e)
        return (False, [])


def fetch_index_kline(code: str, days: int = 80) -> (bool, list):
    return fetch_kline(code, days)


# 别名：与东财数据源函数名对齐（供编排层统一调用）
fetch_stocks_spot = fetch_stock_spot
