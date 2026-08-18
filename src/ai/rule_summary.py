"""规则兜底 AI 总结：基于数据生成市场总结5问 + 基金经理视角（无 LLM 时使用）"""
import logging
from datetime import date

logger = logging.getLogger("daily_review.ai.rule")


def generate_market_summary(market: dict, indices: list, sectors: list, stocks: list,
                            futures: list, crypto: list) -> str:
    """市场总结 5 问（Markdown）"""
    score = market.get("market_score")
    state = market.get("market_state")
    risk = market.get("risk_level")
    s = market.get("sentiment", {})
    up, down = s.get("up_count"), s.get("down_count")
    lu, ld = s.get("limit_up"), s.get("limit_down")
    avg = market.get("avg_index_pct")

    lines = []
    lines.append(f"## 今日市场总结（{date.today().strftime('%Y-%m-%d')}）\n")
    lines.append("### 1. 今天市场发生了什么？")
    top_up = [i for i in indices if i.get("pct_change") is not None]
    top_up.sort(key=lambda x: x["pct_change"], reverse=True)
    if top_up:
        best = top_up[0]
        lines.append(f"- 主要指数平均涨跌 {avg}%，其中 **{best['name']}** 领涨（{best['pct_change']}%）。"
                     f"市场总体处于「{state}」，情绪为「{market.get('sentiment_label','中性')}」。")
    lines.append(f"- 全市场上涨 {up} 家 / 下跌 {down} 家，涨停 {lu} 家 / 跌停 {ld} 家。")

    lines.append("\n### 2. 哪些资金正在流入？")
    with_inflow = [i for i in indices if i.get("main_net_inflow") is not None and i["main_net_inflow"] > 0]
    if with_inflow:
        lines.append("- 资金流入指数：`" + "、".join(i["name"] for i in with_inflow[:5]) + "`。")
    sec_flow = [x for x in sectors if x.get("main_net_inflow") is not None]
    if sec_flow:
        top_in = sorted(sec_flow, key=lambda x: x["main_net_inflow"], reverse=True)[:3]
        lines.append("- 行业资金流入前列：`" + "、".join(f"{x['name']}({_fmt_flow(x['main_net_inflow'])})" for x in top_in) + "`。")
    else:
        lines.append("- 主力资金实时数据源暂不可用（以指数与行业涨幅推断资金偏好）。")

    lines.append("\n### 3. 哪些行业正在走强？")
    valid_sec = sorted([x for x in sectors if x.get("pct_change") is not None],
                       key=lambda x: x["pct_change"], reverse=True)[:5]
    if valid_sec:
        lines.append("- " + "、".join(f"**{x['name']}**（{x['pct_change']}%）" for x in valid_sec) + "。")

    lines.append("\n### 4. 当前市场风险在哪里？")
    if risk == "高":
        lines.append("- 风险等级：**高**。市场处于弱势区间，注意控制仓位。")
    elif risk == "中":
        lines.append("- 风险等级：**中**。分化行情，结构性风险为主。")
    else:
        lines.append("- 风险等级：**低**。整体环境偏暖，但需防高位板块回撤。")
    weak_sec = [x for x in sectors if x.get("pct_change") is not None and x["pct_change"] < -1.5]
    if weak_sec:
        names = "、".join(x["name"] for x in sorted(weak_sec, key=lambda x: x["pct_change"])[:3])
        lines.append(f"- 弱势行业：{names}，回避或等待企稳。")

    lines.append("\n### 5. 明天重点关注什么？")
    lines.append("- 观察指数能否站稳关键均线（MA20/MA60）与量能是否延续；")
    lines.append("- 关注强势行业持续性及资金是否扩散；")
    if lu is not None and lu >= 80:
        lines.append("- 涨停家数偏高，注意情绪高潮后的分歧风险。")
    if futures:
        hot = sorted([f for f in futures if f.get("pct_change") is not None],
                     key=lambda x: x["pct_change"], reverse=True)[:2]
        if hot:
            lines.append("- 商品端关注：" + "、".join(f"{x['name']}({x['pct_change']}%)" for x in hot) + " 的波动传导。")
    return "\n".join(lines)


def generate_manager_view(market: dict, sectors: list, stocks: list) -> str:
    """基金经理视角：环境判断 / 风险等级 / 机会方向 / 仓位建议"""
    score = market.get("market_score")
    state = market.get("market_state")
    risk = market.get("risk_level")
    grade_a = [s for s in stocks if s.get("grade") == "A"]
    strong_sec = [x for x in sectors if x.get("strength") in ("强势", "偏强")]

    lines = []
    lines.append("## 投资者视角（模拟基金经理）\n")
    lines.append(f"- **市场环境判断**：评分 {score}/100，状态「{state}」。"
                 f"指数端与情绪端综合评估，当前处于{'进攻' if score >= 65 else ('防御' if score < 50 else '均衡')}格局。")
    lines.append(f"- **风险等级**：{risk}风险。"
                 f"{'建议控制仓位、保留现金缓冲。' if risk == '高' else ('保持灵活仓位，警惕结构性回撤。' if risk == '中' else '系统性风险有限，可适当提升仓位弹性。')}")
    if strong_sec:
        lines.append("- **机会方向（观察）**：" + "、".join(x["name"] for x in strong_sec[:5]) +
                     "。以上方向当前强度领先，值得纳入观察池，但需等待回踩确认。")
    else:
        lines.append("- **机会方向（观察）**：当前无明确强势主线，建议以防御性配置为主。")
    if grade_a:
        lines.append("- **自选池亮点（观察）**：" + "、".join(s["name"] for s in grade_a[:5]) +
                     " 技术面与基本面综合评级为 A，可作为重点跟踪标的。")
    lines.append("- **仓位建议**："
                 + ("趋势仓位可维持 6-7 成，跌破关键支撑则降至 5 成以下。" if score >= 65
                    else ("维持 4-6 成区间，逢低分批，不满仓、不追高。" if score >= 50
                          else "轻仓防守（3 成以内），等待风险释放后的右侧信号。")))
    lines.append("\n> 以上为规则化自动生成的市场观察，仅作趋势参考，不构成任何买卖建议。")
    return "\n".join(lines)


def _fmt_flow(v):
    if v is None:
        return "—"
    v = float(v)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.1f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.0f}万"
    return f"{v:.0f}"
