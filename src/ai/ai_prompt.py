"""通道A AI 分析提示词模板：供 WorkBuddy 自动化任务中的 agent 使用（替代 LLM API）"""


def build_ai_prompt(context: dict) -> str:
    """组装 agent 生成市场总结与投资者视角所需的完整提示词。
    context 含: date / market(评分状态) / indices / sectors / stocks / futures / crypto / data_sources
    返回的 prompt 指示 agent 以 Markdown 输出两段内容。"""
    return f"""你是资深 A 股量化研究员与公募基金经理。请基于以下【今日真实数据】，输出专业的市场复盘分析。要求：
1. 语言客观、专业，只基于数据描述，不得编造数据；
2. 不给出绝对买卖指令，使用"机会观察""风险提示""趋势判断"等措辞；
3. 输出两部分 Markdown：`## 市场总结`（回答5问）与 `## 投资者视角`（环境判断/风险等级/机会方向/仓位建议）。

【分析日期】{context.get('date', '')}

【市场总览】
评分: {context.get('market_score')}/100 | 状态: {context.get('market_state')} | 风险: {context.get('risk_level')}
情绪: {context.get('sentiment_label')}
涨跌家数: {context.get('up_count')}涨 / {context.get('down_count')}跌 | 涨停: {context.get('limit_up')} | 跌停: {context.get('limit_down')}

【主要指数】
{_fmt_rows(context.get('indices', []), ['name', 'close', 'pct_change'])}

【行业板块（按涨幅排序）】
{_fmt_rows(context.get('sectors', []), ['name', 'pct_change', 'strength', 'main_net_inflow'])}

【自选股评级】
{_fmt_rows(context.get('stocks', []), ['name', 'close', 'pct_change', 'trend', 'grade', 'risk_level'])}

【商品期货】
{_fmt_rows(context.get('futures', []), ['name', 'close', 'pct_change', 'trend'])}

【数字货币（辅助）】
{_fmt_rows(context.get('crypto', []), ['name', 'price', 'pct_change', 'sentiment'])}

【数据源说明】
{context.get('data_sources', '')}

请直接输出 Markdown 正文（不要输出代码块包裹）。"""


def _fmt_rows(rows: list, keys: list) -> str:
    if not rows:
        return "（无数据）"
    lines = []
    for r in rows:
        cells = []
        for k in keys:
            v = r.get(k)
            if isinstance(v, float):
                v = f"{v:.2f}"
            cells.append(str(v if v is not None else "—"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
