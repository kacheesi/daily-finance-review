"""市场状态判定规则引擎：0-100 评分 + 状态标签 + 风险等级。
缺失维度不扣分：按实际可用权重归一化（工业级容错）。"""
import logging

logger = logging.getLogger("daily_review.analyzer.market_state")

MAIN_INDICES = ["上证指数", "深证成指", "创业板指", "沪深300"]


def evaluate(collection: dict, settings: dict = None) -> dict:
    """输入 collection（含 indices/market_sentiment/index_history），输出评分与状态。"""
    settings = settings or {}
    weights = settings.get("weights", {"index_pct": 30, "advance_ratio": 25, "limit_up_down": 15,
                                       "amount_change": 15, "main_inflow": 15})
    thresholds = settings.get("score_thresholds", {"strong_up": 80, "osc_strong": 65,
                                                   "osc_neutral": 50, "weak_down": 35})

    sentiment = collection.get("market_sentiment", {})
    indices = collection.get("indices", [])
    available = {}
    warnings = []

    # ---- 1. 指数涨跌幅 (30) ----
    main_pcts = [i.get("pct_change") for i in indices if i.get("name") in MAIN_INDICES and i.get("pct_change") is not None]
    if main_pcts:
        avg_pct = sum(main_pcts) / len(main_pcts)
        # -1.5% ~ +1.5% 线性映射 0~30
        available["index_pct"] = max(0.0, min(30.0, (avg_pct + 1.5) / 3.0 * 30.0))
    else:
        warnings.append("指数数据缺失，评分归一化")

    # ---- 2. 涨跌家数比 (25) ----
    up = sentiment.get("up_count")
    down = sentiment.get("down_count")
    if up is not None and down is not None and (up + down) > 0:
        ratio = up / (up + down)
        available["advance_ratio"] = ratio * 25.0
    else:
        warnings.append("涨跌家数缺失")

    # ---- 3. 涨停/跌停 (15) ----
    limit_up = sentiment.get("limit_up")
    limit_down = sentiment.get("limit_down")
    if limit_up is not None:
        lu = min(limit_up / 80.0, 1.0) * 7.5
        ld = min(limit_down / 20.0, 1.0) * 7.5 if limit_down is not None else 0.0
        available["limit_up_down"] = 7.5 + lu - ld  # 基础7.5 ± 7.5
    else:
        warnings.append("涨停跌停缺失")

    # ---- 4. 成交额环比 (15) ----
    amount = sentiment.get("total_amount")
    prev = sentiment.get("prev_total_amount")
    if amount and prev and prev > 0:
        chg = amount / prev - 1.0
        # 放量+20% 满分，缩量-20% 0分
        available["amount_change"] = max(0.0, min(15.0, (chg + 0.2) / 0.4 * 15.0))
    else:
        warnings.append("成交额环比数据缺失")

    # ---- 5. 主力资金 (15) ----
    inflow = sentiment.get("main_net_inflow")
    if inflow is not None and amount:
        ratio = inflow / amount
        # 净流入占比 +1% → 满分，-1% → 0
        available["main_inflow"] = max(0.0, min(15.0, (ratio + 0.01) / 0.02 * 15.0))
    else:
        warnings.append("主力资金缺失，权重归一化")

    # ---- 汇总：权重归一化 ----
    total_w = sum(weights[k] for k in weights if k in available)
    score = sum(available[k] * weights[k] / weights[k] for k in available) if available else 0.0
    # available 里已是满分制值（如 index_pct 最大30），直接按权重占比归一
    score = sum(available.values()) / total_w * 100.0 if total_w > 0 else 0.0
    score = int(round(score))

    # ---- 状态判定 ----
    state = _state_label(score, thresholds)
    # 恐慌/风险释放细分
    if score < thresholds["weak_down"]:
        state = _panic_vs_release(collection, sentiment, state)

    risk_level = "低" if score >= settings.get("risk_levels", {}).get("low", 60) else \
                 ("中" if score >= settings.get("risk_levels", {}).get("medium", 40) else "高")

    sentiment_label = _sentiment_label(sentiment, main_pcts)

    return {
        "market_score": score,
        "market_state": state,
        "risk_level": risk_level,
        "sentiment_label": sentiment_label,
        "avg_index_pct": round(avg_pct, 2) if main_pcts else None,
        "warnings": warnings,
    }


def _state_label(score: int, t: dict) -> str:
    if score >= t["strong_up"]:
        return "强势上涨"
    if score >= t["osc_strong"]:
        return "震荡偏强"
    if score >= t["osc_neutral"]:
        return "震荡整理"
    if score >= t["weak_down"]:
        return "弱势调整"
    return "恐慌或风险释放"


def _panic_vs_release(collection: dict, sentiment: dict, state: str) -> str:
    """低分区分：恐慌（放量下跌） vs 风险释放（缩量连跌后）"""
    idx_hist = collection.get("index_history", {})
    sh = None
    for code, hist in idx_hist.items():
        if "000001" in str(code) and hist:
            sh = hist
            break
    if not sh or len(sh) < 3:
        return state
    closes = [x.get("close") for x in sh[-4:] if x.get("close")]
    if len(closes) < 4:
        return state
    down_days = sum(1 for i in range(1, 4) if closes[i] < closes[i - 1])
    amount = sentiment.get("total_amount")
    if down_days >= 3:
        return "恐慌阶段" if amount and amount > 2.2e12 else "风险释放阶段"
    return "恐慌阶段"


def _sentiment_label(sentiment: dict, main_pcts: list) -> str:
    up = sentiment.get("up_count")
    down = sentiment.get("down_count")
    limit_up = sentiment.get("limit_up") or 0
    parts = []
    if up is not None and down and (up + down) > 0:
        ratio = up / (up + down)
        parts.append("涨多跌少" if ratio > 0.55 else ("跌多涨少" if ratio < 0.45 else "多空均衡"))
    if limit_up >= 80:
        parts.append("涨停潮")
    elif limit_up is not None and limit_up <= 20:
        parts.append("赚钱效应弱")
    if main_pcts:
        avg = sum(main_pcts) / len(main_pcts)
        parts.append("指数走强" if avg > 0.5 else ("指数走弱" if avg < -0.5 else "指数平稳"))
    return "，".join(parts) if parts else "情绪中性"
