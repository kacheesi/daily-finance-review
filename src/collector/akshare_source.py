"""AkShare 数据源（通道B）。若 akshare 未安装/导入失败，自动切换东财 HTTP 直连（同一签名）。"""
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("daily_review.collector.akshare")

try:
    import akshare as ak
    AK_OK = True
except Exception as e:  # pragma: no cover
    AK_OK = False
    logger.warning("akshare 导入失败(%s)，将使用东财 HTTP 直连", e)

from src.utils.retry import retry


class AkShareSource:
    """统一取数入口。所有方法返回 (ok, data)，不抛异常。"""

    def __init__(self, codes: dict, watchlist: list):
        self.codes = codes                # market_codes.json 内容
        self.watchlist = watchlist

    # ============ 指数 ============
    @retry()
    def fetch_index_spot(self) -> (bool, list):
        """9大指数当日行情：close/pct_change/amount"""
        if AK_OK:
            df = ak.stock_zh_index_spot_em()
            df = df.set_index("代码")
            out = []
            for idx in self.codes["indices"]:
                em_code = idx["code"]  # 如 sh000001
                raw = str(idx["code"]).replace("sh", "").replace("sz", "").replace("csi", "")
                row = None
                for cand in (raw, idx["code"]):
                    if cand in df.index:
                        row = df.loc[cand]
                        break
                if row is None:
                    continue
                out.append({
                    "code": idx["code"], "name": idx["name"],
                    "close": _num(row.get("最新价")),
                    "pct_change": _num(row.get("涨跌幅")),
                    "amount": _num(row.get("成交额")),
                })
            return (True, out)
        return self._http_index_spot()

    def _http_index_spot(self) -> (bool, list):
        """东财 HTTP 直连：push2 批量行情"""
        import requests
        codes = ",".join(f"1.{c}" if c.startswith("sh") else (f"0.{c[2:]}" if c.startswith("sz") else f"1.{c[2:]}")
                         for c in [i["code"] for i in self.codes["indices"]])
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
        params = {"fltt": "2", "invt": "2", "fields": "f12,f14,f2,f3,f6",
                  "secids": codes}
        r = requests.get(url, params=params, timeout=20)
        data = r.json()["data"]["diff"]
        out = []
        for it in data:
            out.append({"code": it["f12"], "name": it["f14"], "close": _num(it.get("f2")),
                        "pct_change": _num(it.get("f3")), "amount": _num(it.get("f6"))})
        return (True, out)

    @retry()
    def fetch_index_kline(self, code: str, name: str, days: int = 80) -> (bool, list):
        """指数日K线（用于技术指标）"""
        if AK_OK:
            raw = str(code).replace("sh", "").replace("sz", "").replace("csi", "")
            df = ak.stock_zh_index_daily_em(symbol=raw)
            df = df.tail(days)
            return (True, kline_to_list(df))
        return (False, [])

    # ============ 市场情绪 ============
    @retry()
    def fetch_market_sentiment(self) -> (bool, dict):
        """涨跌家数/涨停跌停/总成交额/主力资金"""
        out = {"up_count": None, "down_count": None, "limit_up": None, "limit_down": None,
               "total_amount": None, "main_net_inflow": None, "prev_total_amount": None}
        if AK_OK:
            spot = ak.stock_zh_a_spot_em()
            pct = spot["涨跌幅"].dropna()
            out["up_count"] = int((pct > 0).sum())
            out["down_count"] = int((pct < 0).sum())
            out["total_amount"] = float(spot["成交额"].sum())
            out["prev_total_amount"] = out["total_amount"]  # 占位，环比用大盘资金流接口校准
            # 涨停/跌停
            try:
                today = datetime.now().strftime("%Y%m%d")
                zt = ak.stock_zt_pool_em(date=today)
                out["limit_up"] = len(zt)
            except Exception:
                out["limit_up"] = int((pct >= 9.8).sum())
            try:
                dt = ak.stock_zt_pool_dtgc_em(date=today)
                out["limit_down"] = len(dt)
            except Exception:
                out["limit_down"] = int((pct <= -9.8).sum())
            # 主力资金
            try:
                fund = ak.stock_market_fund_flow()
                last = fund.iloc[-1]
                out["main_net_inflow"] = _num(last.get("主力净流入-净额"))
                if len(fund) >= 2:
                    out["prev_total_amount"] = _num(fund.iloc[-2].get("上证-成交额", None)) * 2
            except Exception as e:
                logger.warning("主力资金获取失败: %s", e)
            return (True, out)
        return (False, out)

    # ============ 行业板块 ============
    @retry()
    def fetch_sectors(self) -> (bool, list):
        """一级行业板块涨跌幅与资金流（东财行业板块）"""
        if AK_OK:
            df = ak.stock_board_industry_name_em()
            out = []
            for _, row in df.iterrows():
                out.append({
                    "code": str(row.get("板块代码", "")),
                    "name": str(row.get("板块名称", "")),
                    "pct_change": _num(row.get("涨跌幅")),
                    "main_net_inflow": None,  # 资金流单独接口
                })
            # 资金流
            try:
                flow = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
                flow_map = {str(r["名称"]): _num(r.get("主力净流入-净额")) for _, r in flow.iterrows()}
                for it in out:
                    it["main_net_inflow"] = flow_map.get(it["name"])
            except Exception as e:
                logger.warning("行业资金流获取失败: %s", e)
            return (True, out)
        return (False, [])

    # ============ 自选股 ============
    @retry()
    def fetch_stocks_spot(self) -> (bool, list):
        """自选股当日行情快照"""
        if AK_OK:
            df = ak.stock_zh_a_spot_em()
            df = df.set_index("代码")
            out = []
            for s in self.watchlist:
                code, name = s["code"], s["name"]
                if code not in df.index:
                    out.append({"code": code, "name": name})
                    continue
                row = df.loc[code]
                out.append({
                    "code": code, "name": str(row.get("名称", name)),
                    "close": _num(row.get("最新价")), "pct_change": _num(row.get("涨跌幅")),
                    "volume": _num(row.get("成交量")), "turnover_rate": _num(row.get("换手率")),
                    "market_cap": _num(row.get("总市值")), "pe": _num(row.get("市盈率-动态")),
                    "pb": _num(row.get("市净率")), "main_net_inflow": None,
                })
            return (True, out)
        return (False, [])

    @retry()
    def fetch_stock_kline(self, code: str, days: int = 120) -> (bool, list):
        """个股日K线（前复权）"""
        if AK_OK:
            df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
            df = df.tail(days)
            return (True, kline_to_list(df))
        return (False, [])

    @retry()
    def fetch_fundamental(self, code: str) -> (bool, dict):
        """基本面/估值（乐咕：pe/pb/总市值；东财接口补充财务比率）"""
        out = {"pe": None, "pb": None, "roe": None, "revenue_yoy": None,
               "profit_yoy": None, "gross_margin": None, "total_mv": None}
        if AK_OK:
            try:
                df = ak.stock_a_indicator_lg(symbol=code)
                last = df.iloc[-1]
                out["pe"] = _num(last.get("pe"))
                out["pb"] = _num(last.get("pb"))
                out["total_mv"] = _num(last.get("total_mv"))
            except Exception as e:
                logger.warning("个股估值获取失败 %s: %s", code, e)
            try:
                df2 = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
                if len(df2) >= 2:
                    last = df2.iloc[0]
                    cols = {str(c): c for c in df2.columns}
                    def pick(*keys):
                        for k in keys:
                            if k in cols:
                                return _num(last.get(cols[k]))
                        return None
                    out["revenue_yoy"] = pick("营业总收入同比增长率", "营业收入同比增长率")
                    out["profit_yoy"] = pick("归母净利润同比增长率", "净利润同比增长率")
                    out["gross_margin"] = pick("销售毛利率", "毛利率")
                    out["roe"] = pick("净资产收益率")
            except Exception as e:
                logger.warning("财务指标获取失败 %s: %s", code, e)
            return (True, out)
        return (False, out)

    # ============ 期货 ============
    @retry()
    def fetch_futures(self) -> (bool, list):
        """期货主力合约：最新两日收盘算涨跌幅"""
        if AK_OK:
            out = []
            for ft in self.codes["futures"]:
                try:
                    df = ak.futures_zh_daily_sina(symbol=ft["sin"])
                    if len(df) >= 2:
                        last, prev = df.iloc[-1], df.iloc[-2]
                        close, prev_close = _num(last.get("close")), _num(prev.get("close"))
                        pct = (close - prev_close) / prev_close * 100 if prev_close else None
                        out.append({"symbol": ft["symbol"], "name": ft["name"],
                                    "close": close, "pct_change": round(pct, 2) if pct is not None else None})
                    else:
                        close = _num(df.iloc[-1].get("close")) if len(df) else None
                        out.append({"symbol": ft["symbol"], "name": ft["name"], "close": close, "pct_change": None})
                except Exception as e:
                    logger.warning("期货获取失败 %s: %s", ft["symbol"], e)
                    out.append({"symbol": ft["symbol"], "name": ft["name"], "close": None, "pct_change": None})
            return (True, out)
        return (False, [])


def kline_to_list(df) -> list:
    """DataFrame(含 date/open/high/low/close/volume/amount) -> list[dict]"""
    import pandas as pd
    out = []
    for _, r in df.iterrows():
        out.append({
            "date": str(r.get("date", "")),
            "open": _num(r.get("open")), "high": _num(r.get("high")),
            "low": _num(r.get("low")), "close": _num(r.get("close")),
            "volume": _num(r.get("volume")), "amount": _num(r.get("amount")),
        })
    return out


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # NaN -> None
    except (TypeError, ValueError):
        return None
