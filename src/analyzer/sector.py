"""行业板块分析：强弱评级 / 热度排名 / 资金流向（数据源可用时）"""
import logging

logger = logging.getLogger("daily_review.analyzer.sector")


def analyze_sectors(sectors: list) -> list:
    """输入已映射的行业列表，输出带 强弱评级/排名/热度 的分析结果"""
    out = []
    valid = [s for s in sectors if s.get("pct_change") is not None]
    valid.sort(key=lambda s: s["pct_change"], reverse=True)
    rank = {s["name"]: i + 1 for i, s in enumerate(valid)}

    for s in sectors:
        name = s.get("name")
        pct = s.get("pct_change")
        inflow = s.get("main_net_inflow")
        if pct is None:
            strength, heat = "数据缺失", 0
        elif pct >= 2.5:
            strength = "强势"
        elif pct >= 0.5:
            strength = "偏强"
        elif pct >= -0.5:
            strength = "中性"
        elif pct >= -2.5:
            strength = "偏弱"
        else:
            strength = "弱势"
        heat = rank.get(name, 0)  # 热度=涨幅排名
        out.append({
            "code": s.get("code"), "name": name,
            "pct_change": pct,
            "main_net_inflow": inflow,
            "rank": heat,
            "strength": strength,
            "heat": max(0.0, 100 - heat * 4) if heat else 0,  # 热度分 0-100
            "leader": s.get("leader"), "leader_pct": s.get("leader_pct"),
        })
    out.sort(key=lambda x: x["rank"] or 999)
    return out
