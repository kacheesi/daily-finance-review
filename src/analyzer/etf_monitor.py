"""宽基 ETF 异动监测：尾盘资金异动 / 异常放量 / 尾盘价格异动 / 振幅异常
数据来源：东财 trends2 分时（每分钟额/均价）+ 东财 spot（收盘/换手/主力净流入）+ 腾讯日K（量/振幅基准）
"""
from datetime import datetime

# 标准判定阈值（用户选定口径）
TAIL_START = "14:30"          # 尾盘窗口起点
TAIL_RATIO = 0.18             # 尾盘成交占比 > 18%
TAIL_SURGE = 1.5              # 尾盘放量 > 1.5 倍（相对全天匀速）
VOL_RATIO = 2.0               # 全天量比 > 2
TURNOVER = 5.0                # 换手率 > 5%
TAIL_MOVE = 0.5               # 尾盘价格异动 > 0.5%
AMP_RATIO = 2.0               # 振幅 > 近20日均振幅 × 2
EXTREME_TAIL = 0.30           # 尾盘占比 > 30% → 直接高
EXTREME_VOL = 5.0             # 量比 > 5 → 直接高


def analyze_etfs(etf_monitor: dict) -> list:
    """返回每只 ETF 的异动分析结果列表"""
    spot_map = {s.get("code"): s for s in etf_monitor.get("spot", [])}
    trends_map = etf_monitor.get("trends", {})
    history_map = etf_monitor.get("history", {})

    out = []
    for code, spot in spot_map.items():
        name = spot.get("name") or code
        try:
            item = _analyze_one(code, name, spot, trends_map.get(code), history_map.get(code))
        except Exception:
            item = _base_item(code, name, spot, "数据异常")
        out.append(item)
    return out


def _base_item(code, name, spot, summary="") -> dict:
    return {
        "code": code, "name": name,
        "close": spot.get("close"), "pct_change": spot.get("pct_change"),
        "amount": spot.get("amount"), "turnover": spot.get("turnover_rate"),
        "vol_ratio": None, "tail_ratio": None, "tail_pct": None,
        "main_net_inflow": spot.get("main_net_inflow"),
        "level": None, "alerts": [], "summary": summary,
    }


def _analyze_one(code, name, spot, trends_data, history) -> dict:
    item = _base_item(code, name, spot)
    if not trends_data or not trends_data.get("trends"):
        item["summary"] = "数据缺失" if not history else "分时缺失"
        return item

    trends = trends_data["trends"]
    pre_close = trends_data.get("preClose")
    alerts = []

    # --- 分时解析（时间,开,收,高,低,量,额,均价） ---
    total_amount = 0.0
    total_vol = 0.0
    tail_amount = 0.0
    tail_start_price = None
    tail_end_price = None
    for t in trends:
        parts = t.split(",")
        if len(parts) < 8:
            continue
        tm, o, c, hi, lo, v, amt = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], parts[6]
        try:
            amt_f = float(amt)
            v_f = float(v)
        except (TypeError, ValueError):
            continue
        total_amount += amt_f
        total_vol += v_f
        hhmm = tm.split(" ")[1] if " " in tm else tm
        if hhmm >= TAIL_START:
            tail_amount += amt_f
            if tail_start_price is None and c:
                try:
                    tail_start_price = float(c)
                except (TypeError, ValueError):
                    tail_start_price = None
            if c:
                try:
                    tail_end_price = float(c)
                except (TypeError, ValueError):
                    pass

    # 全天额优先用 spot（东财 f6），避免分时缺段
    if spot.get("amount"):
        total_amount = float(spot["amount"])

    # --- 规则 1/2：尾盘占比 / 尾盘放量 ---
    if total_amount > 0 and tail_amount > 0:
        ratio = tail_amount / total_amount
        item["tail_ratio"] = round(ratio * 100, 1)
        if ratio > TAIL_RATIO:
            alerts.append(f"尾盘成交占比 {item['tail_ratio']}%（>18%）")
        surge = tail_amount / (total_amount / 240 * 30)
        if surge > TAIL_SURGE:
            alerts.append(f"尾盘放量 {surge:.1f} 倍")

    # --- 规则 3：全天量比（当日量 / 近20日均量） ---
    if history:
        closes_vol = [x.get("volume") for x in history if x.get("volume") is not None]
        if closes_vol:
            today_vol = closes_vol[-1]
            base_vol = sum(closes_vol[-21:-1]) / max(len(closes_vol[-21:-1]), 1)
            if base_vol > 0 and today_vol is not None:
                vr = today_vol / base_vol
                item["vol_ratio"] = round(vr, 2)
                if vr > VOL_RATIO:
                    alerts.append(f"全天量比 {vr:.1f}（放量）")

    # --- 规则 4：换手率 ---
    if spot.get("turnover_rate") is not None:
        item["turnover"] = spot["turnover_rate"]
        if spot["turnover_rate"] > TURNOVER:
            alerts.append(f"换手率 {spot['turnover_rate']:.1f}%")

    # --- 规则 5：尾盘价格异动（与全天背离或显著） ---
    pct = spot.get("pct_change")
    if tail_start_price and tail_end_price and tail_start_price > 0:
        tail_pct = (tail_end_price - tail_start_price) / tail_start_price * 100
        item["tail_pct"] = round(tail_pct, 2)
        if abs(tail_pct) > TAIL_MOVE:
            if pct is not None and (tail_pct * pct < 0 or abs(tail_pct) > 1.0):
                direction = "拉升" if tail_pct > 0 else "跳水"
                alerts.append(f"尾盘{direction} {tail_pct:+.2f}%（与全天背离）")

    # --- 规则 6：振幅异常 ---
    if history and pre_close:
        highs = [x.get("high") for x in history if x.get("high") is not None]
        lows = [x.get("low") for x in history if x.get("low") is not None]
        if highs and lows:
            cur_amp = (highs[-1] - lows[-1]) / pre_close * 100 if pre_close > 0 else 0
            base_amps = []
            for i in range(max(0, len(highs) - 21), max(0, len(highs) - 1)):
                if highs[i] and lows[i] and pre_close > 0:
                    base_amps.append((highs[i] - lows[i]) / pre_close * 100)
            if base_amps:
                avg_amp = sum(base_amps) / len(base_amps)
                if avg_amp > 0 and cur_amp > avg_amp * AMP_RATIO:
                    alerts.append(f"振幅 {cur_amp:.1f}%（高于均值 {avg_amp:.1f}% 的2倍）")

    # --- 分级 ---
    n = len(alerts)
    extreme = (item["tail_ratio"] or 0) > EXTREME_TAIL * 100 or (item["vol_ratio"] or 0) > EXTREME_VOL
    if extreme or n >= 4:
        item["level"] = "高"
    elif n >= 2:
        item["level"] = "中"
    elif n == 1:
        item["level"] = "低"
    else:
        item["level"] = "无"
    item["alerts"] = alerts
    item["summary"] = "；".join(alerts) if alerts else "无异常"
    return item


def etf_overview(etfs: list) -> str:
    """报告摘要文字：发现 N 个异常 + 关键条目"""
    abn = [e for e in etfs if e.get("level") in ("高", "中", "低")]
    if not etfs:
        return "宽基ETF数据缺失"
    if not abn:
        return "8只宽基ETF无异常（尾盘成交占比均正常）"
    top = sorted(abn, key=lambda e: {"高": 3, "中": 2, "低": 1}.get(e.get("level"), 0), reverse=True)[:3]
    parts = [f"{e['name']}：{e['summary']}" for e in top]
    return f"发现{len(abn)}只异动（高{sum(1 for e in abn if e['level']=='高')}/中{sum(1 for e in abn if e['level']=='中')}/低{sum(1 for e in abn if e['level']=='低')}）：{'；'.join(parts)}"
