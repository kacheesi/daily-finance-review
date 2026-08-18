"""自选股分析：趋势 / 技术状态 / 技术位置 / 基本面评级 / 综合评级 A/B/C/D"""
import logging

from src.analyzer.indicators import compute, last_indicators, ma_alignment

logger = logging.getLogger("daily_review.analyzer.stock")


def analyze_stock(code: str, name: str, spot: dict, kline: list, fundamental: dict, settings: dict = None) -> dict:
    """单只股票完整分析。返回 dict 含技术指标/趋势/评级。"""
    settings = settings or {}
    import pandas as pd
    df = pd.DataFrame(kline) if kline else pd.DataFrame()
    ind = compute(df, settings.get("technical", {}))
    li = last_indicators(ind)
    alignment = ma_alignment(ind)

    base = {
        "code": code, "name": name,
        "close": spot.get("close") if spot else None,
        "pct_change": spot.get("pct_change") if spot else None,
        "volume": spot.get("volume") if spot else None,
        "turnover_rate": spot.get("turnover_rate") if spot else None,
        "market_cap": spot.get("market_cap") if spot else None,
        "pe": spot.get("pe") if spot else None,
        "pb": spot.get("pb") if spot else None,
        "main_net_inflow": spot.get("main_net_inflow") if spot else None,
        **li,
        "trend": alignment,
        "tech_state": "数据不足",
        "tech_position": "未知",
        "risk_level": "中",
        "fundamental_grade": "N/A",
        "roe": fundamental.get("roe") if fundamental else None,
        "revenue_yoy": fundamental.get("revenue_yoy") if fundamental else None,
        "profit_yoy": fundamental.get("profit_yoy") if fundamental else None,
        "gross_margin": fundamental.get("gross_margin") if fundamental else None,
        "grade": "B",
    }

    close, ma20, ma60, rsi = li.get("close"), li.get("ma20"), li.get("ma60"), li.get("rsi14")
    macd_hist, macd_dif, macd_dea = li.get("macd_hist"), li.get("macd_dif"), li.get("macd_dea")
    boll_u, boll_l, kdj_j = li.get("boll_upper"), li.get("boll_lower"), li.get("kdj_j")
    if close is None:
        return base

    # ---- 技术状态 ----
    if macd_dif is not None and macd_dea is not None:
        if macd_dif > macd_dea and macd_hist is not None and macd_hist > 0:
            tech = "MACD多头"
        elif macd_dif < macd_dea and macd_hist is not None and macd_hist < 0:
            tech = "MACD空头"
        else:
            tech = "MACD钝化"
    else:
        tech = ""
    if rsi is not None:
        tech += "·" + ("RSI超买" if rsi > 70 else ("RSI超卖" if rsi < 30 else "RSI中性")) if tech else \
            ("RSI超买" if rsi > 70 else ("RSI超卖" if rsi < 30 else "RSI中性"))
    base["tech_state"] = tech or "中性"

    # ---- 技术位置 ----
    if boll_u is not None and boll_l is not None:
        if close >= boll_u:
            pos = "触及布林上轨"
        elif close <= boll_l:
            pos = "触及布林下轨"
        else:
            pos = "布林中轨区间"
    else:
        pos = "未知"
    if kdj_j is not None:
        pos += "·" + ("KDJ超买" if kdj_j > 100 else ("KDJ超卖" if kdj_j < 0 else "KDJ中性"))
    base["tech_position"] = pos

    # ---- 风险等级（技术） ----
    risk = "中"
    if alignment in ("多头排列", "偏多") and (rsi is None or rsi < 70):
        risk = "低"
    elif alignment in ("空头排列", "偏空") or (rsi is not None and rsi > 80):
        risk = "高"
    elif close < ma60 if ma60 else False:
        risk = "高"
    base["risk_level"] = risk

    # ---- 基本面评级 ----
    base["fundamental_grade"] = _fundamental_grade(fundamental)

    # ---- 综合评级 A/B/C/D ----
    base["grade"] = _composite_grade(alignment, risk, base["fundamental_grade"],
                                     close, ma60, macd_dif, macd_dea, rsi)
    return base


def _fundamental_grade(f: dict) -> str:
    if not f:
        return "N/A"
    roe = f.get("roe")
    rev = f.get("revenue_yoy")
    profit = f.get("profit_yoy")
    gm = f.get("gross_margin")
    scores = []
    if roe is not None:
        scores.append(1 if roe >= 15 else (0 if roe >= 5 else -1))
    if profit is not None:
        scores.append(1 if profit > 0 else -1)
    if rev is not None:
        scores.append(1 if rev > 0 else -1)
    if gm is not None:
        scores.append(1 if gm >= 30 else (0 if gm >= 15 else -1))
    if not scores:
        return "数据不足"
    s = sum(scores)
    if s >= 2:
        return "优秀"
    if s >= 0:
        return "良好"
    if s >= -2:
        return "一般"
    return "偏弱"


def _composite_grade(alignment: str, risk: str, fund_grade: str,
                     close, ma60, macd_dif, macd_dea, rsi) -> str:
    broken = (ma60 is not None and close is not None and close < ma60) or \
             (macd_dif is not None and macd_dea is not None and macd_dif < macd_dea and rsi is not None and rsi < 40)
    if broken:
        return "D"
    if alignment in ("多头排列", "偏多") and fund_grade in ("优秀", "良好"):
        return "A"
    if alignment in ("多头排列", "偏多") and fund_grade in ("一般", "数据不足", "N/A"):
        return "B"
    if fund_grade == "偏弱":
        return "C"
    if alignment in ("空头排列", "偏空") or risk == "高":
        return "C"
    return "B"


def analyze_watchlist(stocks: list, histories: dict, fundamentals: dict, settings: dict = None) -> list:
    """批量分析自选股池"""
    out = []
    for s in stocks:
        code = s["code"]
        kline = histories.get(code, [])
        fund = fundamentals.get(code, {})
        out.append(analyze_stock(code, s.get("name", code), s, kline, fund, settings))
    # 按评级排序：A > B > C > D，同级按涨幅降序
    grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "N/A": 4}
    out.sort(key=lambda x: (grade_order.get(x["grade"], 4), -(x.get("pct_change") or 0)))
    return out
