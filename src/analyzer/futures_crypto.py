"""商品期货与数字货币分析"""
import logging

logger = logging.getLogger("daily_review.analyzer.futures_crypto")


def analyze_futures(futures: list) -> list:
    """期货：当日涨跌 + 趋势方向 + 风险提示"""
    out = []
    for f in futures:
        pct = f.get("pct_change")
        if pct is None:
            trend, hint = "数据缺失", "数据源不可用，未生成提示"
        elif pct >= 2:
            trend, hint = "强势上行", "涨幅显著，关注追高风险与持仓波动"
        elif pct > 0:
            trend, hint = "温和上行", "偏多运行，关注上方压力位"
        elif pct <= -2:
            trend, hint = "显著回落", "跌幅较大，注意止损与情绪修复"
        elif pct < 0:
            trend, hint = "温和回落", "偏弱运行，关注下方支撑位"
        else:
            trend, hint = "横盘整理", "方向不明，观望为主"
        out.append({
            "symbol": f.get("symbol"), "name": f.get("name"),
            "close": f.get("close"), "pct_change": pct,
            "trend": trend, "risk_hint": hint,
            "category": f.get("category", ""),
        })
    return out


def analyze_crypto(crypto: list, histories: dict = None) -> list:
    """币：价格变化 + 情绪 + 风险（仅辅助观察）"""
    out = []
    for c in crypto:
        pct = c.get("pct_change")
        if pct is None:
            sentiment, risk = "数据缺失", "高"
        elif pct >= 5:
            sentiment, risk = "市场贪婪", "高（涨幅大，波动加剧）"
        elif pct <= -5:
            sentiment, risk = "市场恐慌", "高（跌幅大，注意波动）"
        elif pct > 0:
            sentiment, risk = "偏乐观", "中"
        else:
            sentiment, risk = "偏谨慎", "中"
        hist = (histories or {}).get(c.get("symbol"), [])
        closes = [h.get("close") for h in hist if h.get("close") is not None]
        week_high = max(closes) if closes else None
        week_low = min(closes) if closes else None
        out.append({
            "symbol": c.get("symbol"), "name": c.get("name"),
            "price": c.get("price"), "pct_change": pct,
            "sentiment": sentiment, "risk_level": risk,
            "week_high": week_high, "week_low": week_low,
            "history": hist,
        })
    return out


def analyze_asia(indices: list) -> list:
    """日韩股市：当日涨跌 + 近5日趋势描述"""
    out = []
    for a in indices:
        pct = a.get("pct_change")
        kline = a.get("kline") or []
        closes = [x.get("close") for x in kline if x.get("close") is not None]
        if len(closes) >= 3:
            up_days = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i - 1])
            last5 = closes[-5:]
            if len(last5) >= 2 and closes[-1] == max(last5):
                trend = "近5日走强"
            elif len(last5) >= 2 and closes[-1] == min(last5):
                trend = "近5日走弱"
            elif up_days >= len(closes) - 1:
                trend = "连涨趋势"
            elif up_days <= 1:
                trend = "连跌趋势"
            else:
                trend = "区间震荡"
        else:
            trend = "数据不足"
        if pct is not None:
            trend += f"，当日{'上涨' if pct >= 0 else '下跌'}{abs(pct):.2f}%"
        out.append({**a, "trend": trend})
    return out
