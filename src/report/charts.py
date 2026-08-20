"""ECharts 图表配置生成器：输出内嵌 JS（含降级处理）"""
import json

RED = "#e64545"
GREEN = "#1a9e5a"


def _color(v):
    """A股配色：涨红跌绿"""
    return RED if (v or 0) >= 0 else GREEN


def build_charts_js(data: dict) -> str:
    """生成全部图表初始化 JS。data 为渲染 context。"""
    charts = []
    charts.append(_gauge(data.get("market_score")))
    charts.append(_index_bar(data.get("indices", [])))
    charts.append(_sentiment_radar(data))
    charts.append(_sector_inflow_bar(data.get("sectors", [])))
    charts.append(_sector_bar(data.get("sectors", [])))
    charts.append(_stock_bar(data.get("stocks", [])))
    charts.append(_stock_kline(data.get("stocks", [])))
    charts.append(_futures_bar(data.get("futures", [])))
    charts.append(_etf_chart(data.get("etfs", [])))
    charts.append(_asia_chart(data.get("asia_indices", [])))
    charts.extend(_crypto_line(data.get("crypto", [])))

    init = "\n".join(
        f"initChart('{cid}', {json.dumps(opt, ensure_ascii=False)});" for cid, opt in charts
    )
    return f"""
<script>
function initChart(elId, option) {{
  var el = document.getElementById(elId);
  if (!el || typeof echarts === 'undefined') return;
  var chart = echarts.init(el);
  chart.setOption(option);
  window.addEventListener('resize', function () {{ chart.resize(); }});
}}
function _color(v) {{ return v >= 0 ? '#e64545' : '#1a9e5a'; }}
{init}
</script>"""


def _tooltip(trigger="axis"):
    return {"trigger": trigger, "backgroundColor": "rgba(30,30,40,0.92)", "borderColor": "#444",
            "textStyle": {"color": "#ddd", "fontSize": 12}}


def _gauge(score):
    score = score or 0
    return "gauge_score", {
        "series": [{
            "type": "gauge", "min": 0, "max": 100, "radius": "95%",
            "progress": {"show": True, "width": 14, "itemStyle": {"color": {"type": "linear",
                          "x": 0, "y": 0, "x2": 1, "y2": 0, "colorStops": [
                              {"offset": 0, "color": GREEN}, {"offset": 0.5, "color": "#d9a514"},
                              {"offset": 1, "color": RED}]}}},
            "axisLine": {"lineStyle": {"width": 14, "color": [[1, "rgba(255,255,255,0.08)"]]}},
            "axisTick": {"show": False}, "splitLine": {"show": False},
            "axisLabel": {"color": "#888", "distance": 18, "fontSize": 10},
            "pointer": {"show": False},
            "title": {"show": True, "offsetCenter": [0, "72%"], "color": "#aaa", "fontSize": 12},
            "detail": {"valueAnimation": True, "formatter": "{value}", "color": "#fff",
                       "fontSize": 42, "offsetCenter": [0, "28%"]},
            "data": [{"value": score, "name": "市场评分"}],
        }],
    }


def _index_bar(indices):
    rows = [(i["name"], i.get("pct_change")) for i in indices if i.get("pct_change") is not None]
    names = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    return "chart_indices", {
        "tooltip": _tooltip(),
        "grid": {"left": 80, "right": 20, "top": 20, "bottom": 30},
        "xAxis": {"type": "value", "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
        "yAxis": {"type": "category", "data": names[::-1], "axisLabel": {"color": "#ccc", "fontSize": 11}},
        "series": [{"type": "bar", "data": [{"value": v, "itemStyle": {"color": _color(v)}} for v in vals[::-1]], "barWidth": 14,
                    "itemStyle": {"borderRadius": 3}}],
    }


def _sentiment_radar(data):
    s = data.get("market_sentiment", {})
    up, down = s.get("up_count") or 0, s.get("down_count") or 0
    total = up + down or 1
    lu, ld = s.get("limit_up") or 0, s.get("limit_down") or 0
    amount = s.get("total_amount")
    prev = s.get("prev_total_amount")
    amount_score = 50
    if amount and prev and prev > 0:
        amount_score = min(100, max(0, int((amount / prev - 1) * 500 + 100)))
    inflow = s.get("main_net_inflow")
    inflow_score = 50 if inflow is None else min(100, max(0, int(inflow / 1e10 + 50)))
    return "chart_sentiment", {
        "tooltip": _tooltip(),
        "radar": {"indicator": [{"name": "上涨占比", "max": 100}, {"name": "涨停强度", "max": 100},
                                {"name": "量能水平", "max": 100}, {"name": "主力资金", "max": 100}],
                  "radius": "70%", "axisName": {"color": "#bbb"},
                  "splitArea": {"areaStyle": {"color": ["rgba(255,255,255,0.02)", "rgba(255,255,255,0.04)"]}},
                  "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.1)"}}},
        "series": [{"type": "radar", "data": [{"value": [up / total * 100, min(100, lu * 1.2),
                                                         amount_score, inflow_score],
                                               "name": "市场情绪",
                                               "areaStyle": {"color": "rgba(90,140,255,0.25)"},
                                               "lineStyle": {"color": "#5a8cff"},
                                               "itemStyle": {"color": "#5a8cff"}}]}],
    }


def _sector_heatmap(sectors):
    """行业涨跌热力色块图（14行业×涨跌幅，红涨绿跌）"""
    rows = [(s["name"], s.get("pct_change")) for s in sectors if s.get("pct_change") is not None]
    if not rows:
        return "chart_sector_heat", {"title": {"text": "无数据", "textStyle": {"color": "#888"}}}
    rows.sort(key=lambda x: x[1])
    y = [r[0] for r in rows]
    vals = [[i, 0, r[1]] for i, r in enumerate(rows)]
    return "chart_sector_heat", {
        "tooltip": {"formatter": "{b}：{c}%"},
        "grid": {"left": 90, "right": 24, "top": 10, "bottom": 10},
        "xAxis": {"type": "category", "data": ["涨跌幅"], "axisLabel": {"show": False}},
        "yAxis": {"type": "category", "data": y, "axisLabel": {"color": "#ccc", "fontSize": 11}},
        "visualMap": {"min": -3, "max": 3, "show": False,
                      "inRange": {"color": [GREEN, "#3d5a3d", "#7a6a3a", RED]}},
        "series": [{"type": "heatmap", "data": vals,
                    "label": {"show": True, "formatter": "{c}%", "color": "#fff",
                              "fontSize": 11, "position": "right"},
                    "itemStyle": {"borderColor": "#101319", "borderWidth": 2, "borderRadius": 4}}],
    }


def _sector_inflow_bar(sectors):
    """行业主力资金流向 bar（流入红/流出绿，按资金额排序）"""
    rows = [(s["name"], s.get("main_net_inflow")) for s in sectors if s.get("main_net_inflow") is not None]
    if not rows:
        return "chart_sector_inflow", {"title": {"text": "无数据", "textStyle": {"color": "#888"}}}
    rows.sort(key=lambda x: x[1])
    return "chart_sector_inflow", {
        "tooltip": _tooltip(),
        "grid": {"left": 90, "right": 24, "top": 10, "bottom": 30},
        "xAxis": {"type": "value", "axisLabel": {"color": "#888"},
                  "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
        "yAxis": {"type": "category", "data": [r[0] for r in rows],
                  "axisLabel": {"color": "#ccc", "fontSize": 11}},
        "series": [{"type": "bar",
                    "data": [{"value": round(r[1] / 1e8, 2),
                              "itemStyle": {"color": RED if r[1] >= 0 else GREEN}}
                             for r in rows],
                    "barWidth": 12,
                    "label": {"show": True, "position": "right",
                              "color": "#aaa", "fontSize": 10,
                              "formatter": "{c}亿"}}],
    }


def _sector_bar(sectors):
    rows = [(s["name"], s.get("pct_change")) for s in sectors if s.get("pct_change") is not None]
    rows.sort(key=lambda x: x[1])
    return "chart_sector_bar", {
        "tooltip": _tooltip(),
        "grid": {"left": 90, "right": 20, "top": 10, "bottom": 30},
        "xAxis": {"type": "value", "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
        "yAxis": {"type": "category", "data": [r[0] for r in rows], "axisLabel": {"color": "#ccc", "fontSize": 11}},
        "series": [{"type": "bar", "data": [{"value": r[1], "itemStyle": {"color": _color(r[1])}} for r in rows], "barWidth": 12}],
    }


def _stock_bar(stocks):
    rows = [(s["name"], s.get("pct_change")) for s in stocks if s.get("pct_change") is not None]
    rows.sort(key=lambda x: x[1])
    return "chart_stocks", {
        "tooltip": _tooltip(),
        "grid": {"left": 90, "right": 20, "top": 10, "bottom": 30},
        "xAxis": {"type": "value", "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
        "yAxis": {"type": "category", "data": [r[0] for r in rows], "axisLabel": {"color": "#ccc", "fontSize": 11}},
        "series": [{"type": "bar", "data": [{"value": r[1], "itemStyle": {"color": _color(r[1])}} for r in rows], "barWidth": 10}],
    }


def _stock_kline(stocks):
    """自选股 K 线（取前3只评级为A/B且有历史数据的股票）"""
    picks = [s for s in stocks if s.get("kline") and len(s["kline"]) >= 30][:1]
    if not picks:
        return "chart_kline", {"title": {"text": "无足够K线数据", "textStyle": {"color": "#888"}}, "xAxis": {}, "yAxis": {}}
    s = picks[0]
    k = s["kline"]
    dates = [x["date"] for x in k]
    ohlc = [[x["open"], x["close"], x["low"], x["high"]] for x in k]
    ma5 = [x.get("ma5") for x in s.get("kline_indicators", [])]
    return "chart_kline", {
        "tooltip": _tooltip("axis"),
        "legend": {"data": ["K线", "MA5", "MA10", "MA20"], "textStyle": {"color": "#aaa"}, "top": 0},
        "grid": {"left": 60, "right": 20, "top": 30, "bottom": 30},
        "xAxis": {"type": "category", "data": dates, "axisLabel": {"color": "#888", "fontSize": 10}},
        "yAxis": {"scale": True, "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
        "dataZoom": [{"type": "inside", "start": 60, "end": 100}],
        "series": [
            {"name": "K线", "type": "candlestick", "data": ohlc,
             "itemStyle": {"color": RED, "color0": GREEN, "borderColor": RED, "borderColor0": GREEN}},
            {"name": "MA5", "type": "line", "data": ma5, "showSymbol": False, "lineStyle": {"width": 1, "color": "#f0c75e"}},
        ],
    }


def _futures_bar(futures):
    rows = [(f["name"], f.get("pct_change")) for f in futures if f.get("pct_change") is not None]
    rows.sort(key=lambda x: x[1])
    return "chart_futures", {
        "tooltip": _tooltip(),
        "grid": {"left": 80, "right": 20, "top": 10, "bottom": 30},
        "xAxis": {"type": "value", "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
        "yAxis": {"type": "category", "data": [r[0] for r in rows], "axisLabel": {"color": "#ccc"}},
        "series": [{"type": "bar", "data": [{"value": r[1], "itemStyle": {"color": _color(r[1])}} for r in rows], "barWidth": 14}],
    }



def _asia_chart(asia_indices):
    """日韩股市近10日走势（日经/KOSPI 双线，双 y 轴）"""
    with_kline = [a for a in asia_indices if a.get('kline')]
    if not with_kline:
        return "chart_asia", {"title": {"text": "无数据", "textStyle": {"color": "#888"}}}
    dates = [x['date'] for x in with_kline[0]['kline']]
    colors = ['#5a8cff', '#f0c75e']
    series = []
    for i, a in enumerate(with_kline):
        series.append({
            "name": a.get('name', ''), "type": "line", "showSymbol": False, "smooth": True,
            "data": [x.get('close') for x in a.get('kline', [])],
            "yAxisIndex": i % 2, "lineStyle": {"width": 2, "color": colors[i % 2]},
        })
    return "chart_asia", {
        "tooltip": _tooltip(),
        "legend": {"textStyle": {"color": "#aaa"}, "top": 0},
        "grid": {"left": 70, "right": 70, "top": 30, "bottom": 30},
        "xAxis": {"type": "category", "data": dates, "axisLabel": {"color": "#888", "fontSize": 10}},
        "yAxis": [
            {"type": "value", "scale": True, "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
            {"type": "value", "scale": True, "axisLabel": {"color": "#888"}, "splitLine": {"show": False}},
        ],
        "series": series,
    }



def _etf_chart(etfs):
    """宽基ETF尾盘监测：有异动→尾盘涨跌条形图；平时→尾盘成交占比条形图(18%参考线)"""
    valid = [e for e in etfs if e.get('tail_pct') is not None or e.get('tail_ratio') is not None]
    if not valid:
        return "chart_etf", {"title": {"text": "无数据", "textStyle": {"color": "#888"}}}
    abn = [e for e in etfs if e.get('level') in ("高", "中", "低") and e.get('tail_pct') is not None]
    if abn:
        names = [e['name'] for e in abn]
        vals = [e['tail_pct'] for e in abn]
        return "chart_etf", {
            "tooltip": _tooltip(),
            "title": {"text": "异动ETF尾盘涨跌(%)", "textStyle": {"color": "#aaa", "fontSize": 12}, "top": 0},
            "grid": {"left": 60, "right": 20, "top": 28, "bottom": 30},
            "xAxis": {"type": "category", "data": names, "axisLabel": {"color": "#ccc", "fontSize": 10, "interval": 0, "rotate": 20}},
            "yAxis": {"type": "value", "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
            "series": [{"type": "bar", "data": [{"value": round(v, 2), "itemStyle": {"color": RED if v >= 0 else GREEN}} for v in vals], "barWidth": 18}],
        }
    names = [e['name'] for e in valid]
    vals = [e['tail_ratio'] for e in valid]
    return "chart_etf", {
        "tooltip": _tooltip(),
        "title": {"text": "尾盘30分钟成交占比(%)", "textStyle": {"color": "#aaa", "fontSize": 12}, "top": 0},
        "grid": {"left": 60, "right": 20, "top": 28, "bottom": 30},
        "xAxis": {"type": "category", "data": names, "axisLabel": {"color": "#ccc", "fontSize": 10, "interval": 0, "rotate": 20}},
        "yAxis": {"type": "value", "axisLabel": {"color": "#888"}, "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
        "series": [{"type": "bar", "data": [{"value": v, "itemStyle": {"color": '#5a8cff' if (v or 0) < 18 else RED}} for v in vals], "barWidth": 18,
                     "markLine": {"silent": True, "symbol": "none", "label": {"formatter": "18%阈值", "color": "#f0c75e", "fontSize": 10},
                                   "lineStyle": {"color": "#f0c75e", "type": "dashed"}, "data": [{"yAxis": 18}]}}],
    }


def _crypto_line(crypto):
    """每只币独立成图（BTC/ETH 价差大，共轴会压扁波动）"""
    charts = []
    colors = ["#f0a020", "#5a8cff", "#9b8cff"]
    for i, c in enumerate(crypto):
        hist = c.get("history") or []
        if not hist:
            continue
        cid = f"chart_crypto_{c.get('symbol', 'coin').lower()}"
        charts.append((cid, {
            "tooltip": _tooltip(),
            "title": {"text": f"{c['name']} 近7日走势", "textStyle": {"color": "#aaa", "fontSize": 12}, "top": 0},
            "grid": {"left": 70, "right": 20, "top": 28, "bottom": 30},
            "xAxis": {"type": "category", "data": [h["date"] for h in hist],
                      "axisLabel": {"color": "#888", "fontSize": 10}},
            "yAxis": {"type": "value", "scale": True, "axisLabel": {"color": "#888"},
                      "splitLine": {"lineStyle": {"color": "rgba(255,255,255,0.06)"}}},
            "series": [{"name": c["name"], "type": "line", "showSymbol": False, "smooth": True,
                        "data": [h["close"] for h in hist], "lineStyle": {"width": 2, "color": colors[i % 3]}}],
        }))
    if not charts:
        return [("chart_crypto", {"title": {"text": "无数据", "textStyle": {"color": "#888"}}})]
    return charts

