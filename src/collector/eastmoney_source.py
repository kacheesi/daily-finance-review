"""东方财富数据源：push2delay（延时行情，收盘后=准确收盘价）+ datacenter-web（数据中心财务）
- 解决：中证A50 行情缺失、主力资金缺失、基本面缺失、行业资金流缺失
- 字段约定：f2=最新价 f3=涨跌幅% f5=成交量 f6=成交额 f8=换手率 f9=PE f12=代码 f14=名称
           f20=总市值 f23=PB f62=主力净流入
- 说明：本机网络对 push2.eastmoney.com 被阻断，但 push2delay/datacenter-web/np-listapi 可达；
        延时行情在收盘后数据即最终收盘价，不影响复盘准确性。
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger("daily_review.collector.eastmoney")

# 云端模式（GitHub Actions 海外执行）：缩短超时并快速失败，及时切备用源
CLOUD = os.environ.get("DAILY_REVIEW_CLOUD") == "1"
_TIMEOUT = 8 if CLOUD else 15

BASE_QUOTE = "https://push2delay.eastmoney.com/api/qt"
BASE_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

# 全A股过滤（沪深京A股）
FS_ALL_A = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
# 东财行业板块（细分行业）
FS_SECTORS = "m:90+t:2"


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _get(url, params):
    r = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _index_secid(code: str) -> str:
    """配置 code(sh000001/sz399006/csi930050) -> 东财 secid"""
    code = str(code)
    if code.startswith("csi"):
        return f"2.{code[3:]}"
    if code.startswith("sz"):
        return f"0.{code[2:]}"
    return f"1.{code[2:]}"


def _stock_secid(code: str) -> str:
    """6位股票代码 -> secid（沪 1.xxx / 深 0.xxx）"""
    if code.startswith(("6", "9", "5")):
        return f"1.{code}"
    return f"0.{code}"


# ============ 指数（含中证A50 + 主力资金） ============
def fetch_index_spot(indices_cfg: list) -> (bool, list):
    secids = ",".join(_index_secid(i["code"]) for i in indices_cfg)
    try:
        d = _get(f"{BASE_QUOTE}/ulist.np/get",
                 {"fltt": "2", "invt": "2", "fields": "f2,f3,f6,f12,f14,f62", "secids": secids})
        diff = (d.get("data") or {}).get("diff") or []
        by_code = {str(x.get("f12")): x for x in diff}
        out = []
        for idx in indices_cfg:
            raw = str(idx["code"]).replace("sh", "").replace("sz", "").replace("csi", "")
            it = by_code.get(raw)
            if not it:
                out.append({"code": idx["code"], "name": idx["name"],
                            "close": None, "pct_change": None, "amount": None,
                            "main_net_inflow": None})
                continue
            out.append({
                "code": idx["code"], "name": idx["name"],
                "close": _num(it.get("f2")), "pct_change": _num(it.get("f3")),
                "amount": _num(it.get("f6")), "main_net_inflow": _num(it.get("f62")),
            })
        return (True, out)
    except Exception as e:
        logger.warning("东财指数行情失败: %s", e)
        return (False, [])


# ============ 市场情绪（全A统计：涨跌家数/涨停跌停/成交额/主力资金） ============
def fetch_market_sentiment() -> (bool, dict):
    out = {"up_count": None, "down_count": None, "limit_up": None, "limit_down": None,
           "total_amount": None, "main_net_inflow": None, "prev_total_amount": None,
           "flat_count": None}
    try:
        # 先取总数
        first = _get(f"{BASE_QUOTE}/clist/get",
                     {"pn": "1", "pz": "1", "po": "1", "np": "1", "fltt": "2", "invt": "2",
                      "fid": "f3", "fs": FS_ALL_A, "fields": "f3"})
        total = (first.get("data") or {}).get("total") or 0
        pages = (total + 99) // 100

        def fetch_page(p):
            d = _get(f"{BASE_QUOTE}/clist/get",
                     {"pn": str(p), "pz": "100", "po": "1", "np": "1", "fltt": "2", "invt": "2",
                      "fid": "f3", "fs": FS_ALL_A, "fields": "f2,f3,f6,f12,f62"})
            diff = (d.get("data") or {}).get("diff") or []
            return diff if isinstance(diff, list) else []

        up = down = flat = limit_up = limit_down = 0
        total_amount = inflow = 0.0
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(fetch_page, p) for p in range(1, pages + 1)]
            for fut in as_completed(futs):
                try:
                    rows = fut.result()
                except Exception as e:
                    logger.warning("东财分页失败: %s", e)
                    continue
                for x in rows:
                    pct = _num(x.get("f3"))
                    if pct is None:
                        continue
                    if pct > 0:
                        up += 1
                    elif pct < 0:
                        down += 1
                    else:
                        flat += 1
                    if pct >= 9.8:
                        limit_up += 1
                    if pct <= -9.8:
                        limit_down += 1
                    total_amount += _num(x.get("f6")) or 0
                    inflow += _num(x.get("f62")) or 0
        out.update(up_count=up, down_count=down, flat_count=flat,
                   limit_up=limit_up, limit_down=limit_down,
                   total_amount=round(total_amount, 2),
                   main_net_inflow=round(inflow, 2))
        return (True, out)
    except Exception as e:
        logger.warning("东财市场情绪统计失败: %s", e)
        return (False, out)


# ============ 行业板块（东财行业，含资金流） ============
def fetch_sectors() -> (bool, list):
    """东财行业板块全量（细分行业），返回 [{code,name,pct_change,main_net_inflow,amount}]"""
    try:
        first = _get(f"{BASE_QUOTE}/clist/get",
                     {"pn": "1", "pz": "1", "po": "1", "np": "1", "fltt": "2", "invt": "2",
                      "fid": "f3", "fs": FS_SECTORS, "fields": "f3"})
        total = (first.get("data") or {}).get("total") or 0
        pages = (total + 99) // 100

        def fetch_page(p):
            d = _get(f"{BASE_QUOTE}/clist/get",
                     {"pn": str(p), "pz": "100", "po": "1", "np": "1", "fltt": "2", "invt": "2",
                      "fid": "f3", "fs": FS_SECTORS, "fields": "f3,f6,f12,f14,f62"})
            diff = (d.get("data") or {}).get("diff") or []
            return diff if isinstance(diff, list) else []

        out = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(fetch_page, p) for p in range(1, pages + 1)]
            for fut in as_completed(futs):
                try:
                    rows = fut.result()
                except Exception as e:
                    logger.warning("东财行业分页失败: %s", e)
                    continue
                for x in rows:
                    out.append({
                        "code": str(x.get("f12", "")), "name": str(x.get("f14", "")),
                        "pct_change": _num(x.get("f3")),
                        "main_net_inflow": _num(x.get("f62")),
                        "amount": _num(x.get("f6")),
                    })
        return (True, out) if out else (False, [])
    except Exception as e:
        logger.warning("东财行业板块失败: %s", e)
        return (False, [])


# ============ 自选股行情（含主力资金） ============
def fetch_stocks_spot(watchlist: list) -> (bool, list):
    secids = ",".join(_stock_secid(s["code"]) for s in watchlist)
    try:
        d = _get(f"{BASE_QUOTE}/ulist.np/get",
                 {"fltt": "2", "invt": "2",
                  "fields": "f2,f3,f5,f8,f9,f12,f14,f20,f23,f62", "secids": secids})
        diff = (d.get("data") or {}).get("diff") or []
        by_code = {str(x.get("f12")): x for x in diff}
        out = []
        for s in watchlist:
            it = by_code.get(str(s["code"]))
            if not it:
                out.append({"code": s["code"], "name": s["name"], "close": None,
                            "pct_change": None, "volume": None, "turnover_rate": None,
                            "market_cap": None, "pe": None, "pb": None, "main_net_inflow": None})
                continue
            out.append({
                "code": s["code"], "name": str(it.get("f14", s["name"])),
                "close": _num(it.get("f2")), "pct_change": _num(it.get("f3")),
                "volume": _num(it.get("f5")), "turnover_rate": _num(it.get("f8")),
                "market_cap": (_num(it.get("f20")) or 0) / 1e8 if it.get("f20") else None,
                "pe": _num(it.get("f9")), "pb": _num(it.get("f23")),
                "main_net_inflow": _num(it.get("f62")),
            })
        return (True, out)
    except Exception as e:
        logger.warning("东财自选股行情失败: %s", e)
        return (False, [])


# ============ 基本面（datacenter 财务主要指标） ============
_FUND_FIELDS = {
    "roe": "ROEJQ",              # 净资产收益率(加权)
    "gross_margin": "XSMLL",     # 销售毛利率
    "revenue_yoy": "TOTALOPERATEREVETZ",   # 营业总收入同比增长
    "profit_yoy": "PARENTNETPROFITTZ",     # 归母净利润同比增长
}

def fetch_fundamental(code: str) -> (bool, dict):
    out = {"pe": None, "pb": None, "roe": None, "revenue_yoy": None,
           "profit_yoy": None, "gross_margin": None, "total_mv": None}
    try:
        suffix = "SH" if code.startswith(("6", "9", "5")) else "SZ"
        d = _get(BASE_DC, {"reportName": "RPT_F10_FINANCE_MAINFINADATA", "columns": "ALL",
                           "pageSize": "1", "pageNumber": "1",
                           "filter": f'(SECUCODE="{code}.{suffix}")',
                           "sortColumns": "REPORT_DATE", "sortTypes": "-1"})
        rows = ((d.get("result") or {}).get("data") or [])
        if not rows:
            return (True, out)
        row = rows[0]
        for key, col in _FUND_FIELDS.items():
            out[key] = _num(row.get(col))
        return (True, out)
    except Exception as e:
        logger.warning("东财基本面失败 %s: %s", code, e)
        return (False, out)


# ============ 指数K线（push2delay，可能部分指数为空） ============
def fetch_index_kline(code: str, days: int = 80) -> (bool, list):
    try:
        secid = _index_secid(code)
        d = _get(f"{BASE_QUOTE}/stock/kline/get",
                 {"secid": secid, "klt": "101", "fqt": "1", "lmt": str(days),
                  "end": "20500101", "fields1": "f1,f2,f3", "fields2": "f51,f52,f53,f54,f55,f56,f57"})
        klines = ((d.get("data") or {}).get("klines")) or []
        if not klines:
            return (False, [])
        out = []
        for k in klines:
            p = k.split(",")
            out.append({"date": p[0], "open": _num(p[1]), "close": _num(p[2]),
                        "high": _num(p[3]), "low": _num(p[4]), "volume": _num(p[5]),
                        "amount": _num(p[6]) if len(p) > 6 else None})
        return (True, out)
    except Exception as e:
        logger.warning("东财指数K线失败 %s: %s", code, e)
        return (False, [])


# ============ 亚太指数（日韩） ============
def fetch_asia_indices(asia_cfg: list) -> (bool, list):
    """日经225 / 韩国KOSPI 收盘行情（东财 push2delay 国际指数）"""
    out = []
    ok_any = False
    for a in asia_cfg:
        try:
            d = _get(f"{BASE_QUOTE}/ulist.np/get",
                     {"fltt": "2", "invt": "2", "fields": "f2,f3,f6,f12,f14", "secids": a["code"]})
            diff = (d.get("data") or {}).get("diff") or []
            x = diff[0] if isinstance(diff, list) and diff else {}
            out.append({
                "code": a["code"], "name": x.get("f14") or a["name"],
                "market": a.get("market", ""),
                "close": _num(x.get("f2")), "pct_change": _num(x.get("f3")),
                "amount": _num(x.get("f6")),
            })
            if x.get("f2") is not None:
                ok_any = True
        except Exception as e:
            logger.warning("东财亚太指数失败 %s: %s", a["code"], e)
            out.append({"code": a["code"], "name": a["name"], "market": a.get("market", ""),
                        "close": None, "pct_change": None, "amount": None})
    return (ok_any, out)


def fetch_asia_kline(code: str, days: int = 10) -> (bool, list):
    """亚太指数近 N 日收盘（push2delay kline，可能为空则跳过）"""
    try:
        d = _get(f"{BASE_QUOTE}/stock/kline/get",
                 {"secid": code, "klt": "101", "fqt": "1", "lmt": str(days),
                  "end": "20500101", "fields1": "f1,f2,f3", "fields2": "f51,f52,f53,f54,f55"})
        klines = ((d.get("data") or {}).get("klines")) or []
        out = []
        for k in klines:
            p = k.split(",")
            if len(p) >= 5:
                out.append({"date": p[0], "open": _num(p[1]), "close": _num(p[2]),
                            "high": _num(p[3]), "low": _num(p[4])})
        return (True, out) if out else (False, [])
    except Exception as e:
        logger.warning("东财亚太K线失败 %s: %s", code, e)
        return (False, [])
