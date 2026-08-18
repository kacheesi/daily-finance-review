"""新浪数据源：全市场涨跌统计(情绪) / 行业板块 / 期货主力合约 / 财务摘要"""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

logger = logging.getLogger("daily_review.collector.sina")

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://finance.sina.com.cn/",
}
_TIMEOUT = 15

MARKET_DATA_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData"
SECTOR_URL = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
FUTURE_URL = "https://stock.finance.sina.com.cn/futures/api/jsonp.php/var%20_{sym}=/InnerFuturesNewService.getDailyKLine"
FINANCE_URL = "https://money.finance.sina.com.cn/corp/go.php/vFD_FinancialGuideLine/stockid/{code}/ctrl/{year}/displaytype/4.phtml"


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _http_get(url, params=None):
    r = requests.get(url, params=params, headers=_HEADERS, timeout=_TIMEOUT)
    r.raise_for_status()
    return r


# ============ 市场情绪（涨跌家数/涨停跌停/总成交额） ============
def fetch_market_sentiment() -> (bool, dict):
    """并发分页拉全A股，统计涨跌家数/涨停跌停/总成交额。
    主力资金新浪无公开接口 -> None（评分引擎会做缺失归一化）"""
    out = {"up_count": None, "down_count": None, "limit_up": None, "limit_down": None,
           "total_amount": None, "main_net_inflow": None, "prev_total_amount": None,
           "flat_count": None}
    try:
        # 获取总数
        r = _http_get("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCount",
                      {"node": "hs_a"})
        total = int(json.loads(r.text))
        pages = (total + 99) // 100

        def fetch_page(p):
            rr = _http_get(MARKET_DATA_URL, {"page": str(p), "num": "100", "sort": "changepercent",
                                             "asc": "0", "node": "hs_a"})
            return json.loads(rr.text)

        up = down = flat = limit_up = limit_down = 0
        total_amount = 0.0
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(fetch_page, p) for p in range(1, pages + 1)]
            for fut in as_completed(futs):
                try:
                    rows = fut.result()
                except Exception as e:
                    logger.warning("分页拉取失败: %s", e)
                    continue
                for row in rows:
                    pct = _num(row.get("changepercent"))
                    amount = _num(row.get("amount"))
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
                    if amount:
                        total_amount += amount
        out.update(up_count=up, down_count=down, flat_count=flat,
                   limit_up=limit_up, limit_down=limit_down, total_amount=round(total_amount, 2))
        return (True, out)
    except Exception as e:
        logger.warning("市场情绪统计失败: %s", e)
        return (False, out)


# ============ 行业板块 ============
def fetch_sectors() -> (bool, list):
    """新浪一级行业板块。
    原始字段: 代码,名称,总家数,指数值,涨跌幅%,涨跌额,成交量,成交额,领涨股代码,领涨股涨幅,领涨股价,领涨股涨跌额,领涨股名称"""
    try:
        r = _http_get(SECTOR_URL)
        m = re.search(r"\{.*\}", r.text)
        if not m:
            return (False, [])
        data = json.loads(m.group(0))
        out = []
        for key, val in data.items():
            f = val.split(",")
            if len(f) < 9:
                continue
            out.append({
                "code": f[0], "name": f[1],
                "pct_change": _num(f[4]),
                "amount": _num(f[7]) if len(f) > 7 else None,
                "total_count": _num(f[2]),
                "main_net_inflow": None,
                "leader": f[12] if len(f) > 12 else None,
                "leader_pct": _num(f[9]) if len(f) > 9 else None,
            })
        return (True, out)
    except Exception as e:
        logger.warning("行业板块获取失败: %s", e)
        return (False, [])


# ============ 期货主力 ============
def fetch_futures(symbols: list) -> (bool, list):
    """新浪期货主力合约日线，最近两日算涨跌幅。symbols: [{'symbol','sin','name'}]"""
    out = []
    ok_any = False
    for ft in symbols:
        try:
            r = _http_get(FUTURE_URL.format(sym=ft["sin"]), params={"symbol": ft["sin"]})
            m = re.search(r"\((\[.*\])\)", r.text, re.S)
            if not m:
                out.append({"symbol": ft["symbol"], "name": ft["name"], "close": None, "pct_change": None})
                continue
            rows = json.loads(m.group(1))
            if len(rows) >= 2:
                last, prev = rows[-1], rows[-2]
                # 新浪期货日线为 dict: {d:日期, o,h,l,c:收盘, v:成交量, s:结算}
                close, prev_close = _num(last.get("c")), _num(prev.get("c"))
                pct = (close - prev_close) / prev_close * 100 if prev_close else None
                out.append({"symbol": ft["symbol"], "name": ft["name"], "close": close,
                            "pct_change": round(pct, 2) if pct is not None else None})
                ok_any = True
            else:
                close = _num(rows[-1].get("c")) if rows else None
                out.append({"symbol": ft["symbol"], "name": ft["name"], "close": close,
                            "pct_change": None})
        except Exception as e:
            logger.warning("期货获取失败 %s: %s", ft["symbol"], e)
            out.append({"symbol": ft["symbol"], "name": ft["name"], "close": None, "pct_change": None})
    return (ok_any, out)


# ============ 财务摘要（简化解析） ============
def fetch_fundamental(code: str) -> (bool, dict):
    """新浪财务指标页解析：ROE/营收增速/净利润增速/毛利率（最近年报）。
    解析失败则返回空 dict（不致命）。"""
    out = {"pe": None, "pb": None, "roe": None, "revenue_yoy": None,
           "profit_yoy": None, "gross_margin": None, "total_mv": None}
    try:
        r = _http_get(FINANCE_URL.format(code=code, year=2025))
        text = r.text
        # 提取表格行：指标名 -> 数值
        rows = re.findall(r'<td[^>]*>\s*(净资产收益率|主营业务收入增长率|净利润增长率|销售毛利率)\s*</td>\s*<td[^>]*>\s*([\d.\-]+)\s*</td>', text)
        for name, val in rows:
            v = _num(val)
            if name == "净资产收益率":
                out["roe"] = v
            elif name == "主营业务收入增长率":
                out["revenue_yoy"] = v
            elif name == "净利润增长率":
                out["profit_yoy"] = v
            elif name == "销售毛利率":
                out["gross_margin"] = v
        return (True, out)
    except Exception as e:
        logger.warning("财务摘要获取失败 %s: %s", code, e)
        return (False, out)
