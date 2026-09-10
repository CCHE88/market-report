# -*- coding: utf-8 -*-
"""
HTML 研报生成模块 —— 按八大板块规范生成 A4 打印友好的研报

板块顺序（先宏观再微观）：
  宏观：一 全球概览 → 二 政策要闻 → 三 美股深度分析
  行业：四 热点板块（含黄金/能源专题）
  标的：五 美股自选股 → 六 港股自选股
  配置：七 投资级美元债
  决策：八 综合建议与风险提示
"""

from __future__ import annotations

from datetime import date
from typing import Any

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 美股深度分析 6 个子板块
US_ANALYSIS_SECTIONS = [
    ("指数与估值水平", "valuation"),
    ("板块轮动与风格", "rotation"),
    ("资金与情绪面", "sentiment"),
    ("美联储与经济数据", "fed"),
    ("AI产业链景气跟踪", "ai_chain"),
    ("科技巨头动态", "giants"),
]


# ==================== 格式化工具 ====================

def _cls(v: Any) -> str:
    if v is None:
        return "neutral"
    return "up" if v > 0 else ("down" if v < 0 else "neutral")


def _pct(v: Any, digits: int = 2) -> str:
    if v is None:
        return '<span class="neutral">—</span>'
    return f'<span class="{_cls(v)}">{v:+.{digits}f}%</span>'


def _num(v: Any, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{digits}f}"


def _mcap(v: Any, cur: str = "$") -> str:
    if v is None:
        return "—"
    if v >= 1e12:
        return f"{cur}{v / 1e12:.2f}万亿"
    if v >= 1e8:
        return f"{cur}{v / 1e8:.0f}亿"
    return f"{cur}{v / 1e8:.2f}亿"


def _h2(tag_cls: str, tag_text: str, title: str, en: str, cnt: str | None = None) -> str:
    c = f'<span class="cnt">{cnt}</span>' if cnt else ""
    return (f'<h2><span class="tag {tag_cls}">{tag_text}</span> {title} '
            f'<span class="en">{en}</span>{c}</h2>')


def _card(head: str, items: list[str], extra_cls: str = "") -> str:
    lis = "".join(f"<li>{x}</li>" for x in items if x)
    return (f'<div class="card {extra_cls}">'
            f'<div class="card-head">{head}</div>'
            f'<div class="card-body"><ul>{lis}</ul></div></div>')


# ==================== 债券计算 ====================

def _years_to(maturity: str) -> float:
    y, m, d = (int(x) for x in maturity.split("-"))
    return max((date(y, m, d) - date.today()).days / 365.25, 0.0)


def _spread(rating: str) -> float:
    r = rating.upper()
    if "AA" in r or "AA+" in r:
        return 0.5
    if "A3" in r or "A-" in r:
        return 1.2
    return 1.0


def _bond_price(coupon: float, n: float, ytm: float) -> float:
    """按年付息估算债券净价（面值100）。"""
    if n <= 0:
        return 100.0
    y = max(ytm, 0.01) / 100
    pv_c = coupon * (1 - (1 + y) ** -n) / y
    pv_f = 100 / (1 + y) ** n
    return pv_c + pv_f


# ==================== 各板块 ====================

def _sec_overview(data: dict) -> str:
    rows = []
    for grp in data.get("indices", []):
        n = len(grp["items"])
        for i, it in enumerate(grp["items"]):
            grp_cls = "grp" if i == 0 else ""
            mkt_td = ""
            if i == 0:
                mkt_td = (f'<td class="mkt" rowspan="{n}">{grp["market"]}<br>'
                          f'<span style="font-size:9px;font-weight:400;letter-spacing:0">'
                          f'{grp["label"]}</span></td>')
            rows.append(
                f'<tr class="{grp_cls}">{mkt_td}'
                f'<td class="col-left">{it["name"]}</td>'
                f'<td>{_num(it.get("price"))}</td>'
                f'<td>{_pct(it.get("chg"))}</td>'
                f'<td></td></tr>'
            )
    body = "".join(rows)

    # 底部一行关键指标
    vix = data.get("vix") or {}
    t10 = next((t for t in data.get("treasury", []) if t["name"] == "10Y"), None)
    parts = [f'VIX {_num(vix.get("price"))}（{_pct(vix.get("chg"))}）']
    if t10 and t10.get("yield") is not None:
        parts.append(f'10Y美债 {t10["yield"]:.2f}%')
    for c in data.get("commodities", []):
        if c.get("price") is not None:
            parts.append(f'{c["name"]} {_num(c["price"])}（{_pct(c.get("chg"))}）')
    footer = " | ".join(parts)

    return f'''
{_h2("tag-macro", "宏观", "一、全球市场概览", "GLOBAL MARKET OVERVIEW")}
<table class="overview">
<colgroup>
<col style="width:14%"><col style="width:16%"><col style="width:14%"><col style="width:12%"><col style="width:44%">
</colgroup>
<thead><tr><th>市场</th><th>指数</th><th>收盘/点位</th><th>涨跌幅</th><th>关键信息</th></tr></thead>
<tbody>{body}</tbody>
</table>
<div style="margin:6px 0 0 0;font-size:10px;color:var(--text-gray);text-align:right;">{footer}</div>
'''


def _sec_news(nar: dict, data: dict) -> str:
    items = []
    for i, n in enumerate(nar.get("news", [])):
        cls = ["", "gold", "red", "green"][i % 4]
        items.append(f'<div class="news-item"><span class="news-tag {cls}">'
                     f'{n.get("tag", "要闻")}</span>{n.get("title", "")}</div>')

    return (f'{_h2("tag-macro", "宏观", "二、宏观与政策要闻", "MACRO & POLICY")}'
            f'<div class="card"><div class="card-body">{"".join(items)}</div></div>')


def _sec_us_analysis(nar: dict) -> str:
    ua = nar.get("us_analysis", {})
    cards = []
    for i, (title, key) in enumerate(US_ANALYSIS_SECTIONS):
        items = ua.get(key) or ["暂无数据"]
        if isinstance(items, str):
            items = [items]
        cards.append(_card(f'{["①","②","③","④","⑤","⑥"][i]} {title}', list(items)))

    # 两两成对放入 grid-2
    grid = ""
    for i in range(0, len(cards), 2):
        pair = cards[i:i + 2]
        grid += f'<div class="grid-2">{"".join(pair)}</div>'

    return (f'{_h2("tag-macro", "宏观", "三、美股深度分析", "US MARKET DEEP DIVE")}'
            f'{grid}')


def _etf_table(rows: list, title: str) -> str:
    """行业 / 主题 ETF 涨跌表（按涨跌幅降序），52周分位反映技术位置"""
    trs = []
    for r in rows:
        pos = f'{r["pos52"]:.0f}%' if r.get("pos52") is not None else "—"
        trs.append(f'<tr><td class="col-left">{r["name"]}</td>'
                   f'<td>{_num(r.get("price"))}</td>'
                   f'<td>{_pct(r.get("chg"))}</td>'
                   f'<td>{pos}</td></tr>')
    return (f'<div class="card"><div class="card-head">{title}</div>'
            f'<div class="card-body" style="padding:0;">'
            f'<table class="stock-table"><thead><tr>'
            f'<th>名称</th><th>现价</th><th>涨跌幅</th><th>52周分位</th>'
            f'</tr></thead><tbody>{"".join(trs)}</tbody></table></div></div>')


def _sec_sectors(nar: dict, data: dict) -> str:
    """四、热点板块与个股机会 —— 单一「当日热点板块速览」卡片。

    ⚠️ 2026-09-10 定稿：黄金 / 能源**不得单独成卡**（用户明确要求，
    单独分卡内容分散、篇幅过长），改为各占一条并入速览，共约 6 条。
    """
    rot = nar.get("us_analysis", {}).get("rotation") or ["暂无数据"]
    if isinstance(rot, str):
        rot = [rot]
    gold = nar.get("gold") or []
    energy = nar.get("energy") or []
    if isinstance(gold, str):
        gold = [gold]
    if isinstance(energy, str):
        energy = [energy]

    items = list(rot)

    def one_line(seq, label, keep=3):
        """把专题的多条压成一条：取价格和最具代表性的一条标的。"""
        body = "；".join(seq[:keep])
        return f"<b>{label}</b>：{body}" if body else None

    for seq, label in ((gold, "黄金"), (energy, "能源")):
        line = one_line(seq, label)
        if line:
            items.append(line)

    overview = _card("当日热点板块速览", items)

    return (f'{_h2("tag-industry", "行业", "四、热点板块与个股机会", "SECTORS & OPPORTUNITIES")}'
            f'{overview}')


def _sec_us_table(data: dict, us_date: str) -> str:
    rows = []
    for r in data.get("us", []):
        row_cls = "etf-row" if r.get("is_etf") else ""
        pe = f'{r["pe"]:.1f}' if r.get("pe") else "—"
        advice = r.get("advice", "持有")
        style = r.get("advice_style", "advice-hold")
        rows.append(
            f'<tr class="{row_cls}">'
            f'<td class="name-col"><strong>{r["name"]}</strong><br>'
            f'<span style="font-size:9px;color:var(--text-gray)">{r["code"]} · {r["tag"]}</span></td>'
            f'<td>${_num(r.get("price"))}</td>'
            f'<td>{_pct(r.get("chg"))}</td>'
            f'<td>{pe}</td>'
            f'<td>{_mcap(r.get("mcap"), "$")}</td>'
            f'<td>{_pct(r.get("chg5"), 1)}</td>'
            f'<td>{_pct(r.get("chg20"), 1)}</td>'
            f'<td>{_pct(r.get("chg_ytd"), 1)}</td>'
            f'<td><span class="advice {style}">{advice}</span></td>'
            f'<td style="text-align:left;font-size:10px;line-height:1.4">{r.get("logic","")}</td>'
            f'</tr>'
        )

    # 数量随 config 动态计算（2026-09-10 移除 CVX 后为 16 只 = 个股14 + ETF 2）
    rows_us = data.get("us", [])
    n_total = len(rows_us)
    n_etf = sum(1 for r in rows_us if r.get("is_etf"))
    n_stock = n_total - n_etf
    cnt = f'{n_total}只（个股{n_stock}+ETF {n_etf}）· {us_date}隔夜收盘 · $'
    return f'''
{_h2("tag-target", "标的", "五、美股自选股与买卖建议", "US WATCHLIST", cnt)}
<table class="stock-table">
<colgroup>
<col style="width:11%"><col style="width:7%"><col style="width:7%"><col style="width:6%"><col style="width:9%">
<col style="width:6%"><col style="width:6%"><col style="width:8%"><col style="width:8%"><col style="width:*">
</colgroup>
<thead><tr><th>公司</th><th>现价</th><th>涨跌幅</th><th>PE</th><th>总市值</th>
<th>5日</th><th>20日</th><th>今年以来</th><th>建议</th><th>逻辑</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
'''


def _sec_hk_table(data: dict, hk_date: str) -> str:
    rows = []
    for r in data.get("hk", []):
        pe = f'{r["pe"]:.1f}' if r.get("pe") else "—"
        div = f'{r["div"]:.2f}%' if r.get("div") else "—"
        advice = r.get("advice", "持有")
        style = r.get("advice_style", "advice-hold")
        rows.append(
            f'<tr>'
            f'<td class="name-col"><strong>{r["name"]}</strong><br>'
            f'<span style="font-size:9px;color:var(--text-gray)">{r["tag"]}</span></td>'
            f'<td>HK${_num(r.get("price"))}</td>'
            f'<td>{_pct(r.get("chg"))}</td>'
            f'<td>{pe}</td>'
            f'<td>{_mcap(r.get("mcap"), "HK$")}</td>'
            f'<td class="{_cls(r.get("div"))}">{div}</td>'
            f'<td>{_pct(r.get("chg20"), 1)}</td>'
            f'<td>{_pct(r.get("chg_ytd"), 1)}</td>'
            f'<td><span class="advice {style}">{advice}</span></td>'
            f'<td style="text-align:left;font-size:10px;line-height:1.4">{r.get("logic","")}</td>'
            f'</tr>'
        )

    cnt = f'10只 · {hk_date}盘中 · HK$'
    return f'''
{_h2("tag-target", "标的", "六、港股自选股与买卖建议", "HK WATCHLIST", cnt)}
<table class="stock-table">
<colgroup>
<col style="width:12%"><col style="width:8%"><col style="width:7%"><col style="width:6%"><col style="width:9%">
<col style="width:7%"><col style="width:7%"><col style="width:8%"><col style="width:8%"><col style="width:*">
</colgroup>
<thead><tr><th>公司</th><th>现价</th><th>涨跌幅</th><th>PE</th><th>市值</th>
<th>股息率</th><th>20日</th><th>今年以来</th><th>建议</th><th>逻辑</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
'''


def _sec_bonds(data: dict, cfg) -> str:
    t10 = next((t for t in data.get("treasury", []) if t["name"] == "10Y"), None)
    base_y = t10.get("yield") if t10 and t10.get("yield") else 4.2
    curve = " | ".join(
        f'{t["name"]} <strong>{t["yield"]:.3f}%</strong>'
        for t in data.get("treasury", []) if t.get("yield") is not None
    )

    rows = []
    for b in cfg.BONDS:
        n = _years_to(b["maturity"])
        ytm = base_y + _spread(b["rating"])
        price = _bond_price(b["coupon"], n, ytm)
        rows.append(
            f'<tr>'
            f'<td><strong>{b["issuer"]}</strong></td>'
            f'<td>{b["coupon"]:.3f}%</td>'
            f'<td>{b["issue"]}</td>'
            f'<td>{b["maturity"]}</td>'
            f'<td>{n:.1f}年</td>'
            f'<td><strong>{ytm:.2f}%</strong></td>'
            f'<td>≈{price:.1f}</td>'
            f'<td>{b["rating"]}</td>'
            f'<td style="text-align:left;font-size:10px">{b["note"]}</td>'
            f'</tr>'
        )

    base_card = f'''
<div class="card" style="border-left-color:var(--navy);margin-bottom:14px;">
<div class="card-head">🇺🇸 美债基准：10年期国债收益率 {base_y:.2f}%</div>
<div class="card-body"><ul>
<li><strong>收益率曲线</strong>：{curve or "暂无数据"}</li>
<li><strong>定价基准</strong>：下表公司债参考 YTM = 10Y 美债 {base_y:.2f}% + 评级信用利差（AA+约0.5%、A+约1.0%、A-约1.2%）</li>
<li><strong>配置逻辑</strong>：美债收益率越高，存量低票息债券价格承压；新买入可锁定更高到期收益率</li>
</ul></div></div>
'''

    cnt = "5只 · 均为5年内到期 · $"
    return f'''
{_h2("tag-config", "配置", "七、投资级美元债", "INVESTMENT-GRADE USD BONDS", cnt)}
{base_card}
<table class="bond-table">
<colgroup>
<col style="width:13%"><col style="width:8%"><col style="width:10%"><col style="width:10%"><col style="width:8%">
<col style="width:8%"><col style="width:9%"><col style="width:11%"><col style="width:*">
</colgroup>
<thead><tr><th>发行人</th><th>票息</th><th>发行日</th><th>到期日</th><th>剩余期限</th>
<th>参考YTM</th><th>参考买入价</th><th>评级</th><th>备注</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
<div style="margin:6px 0 0 0;font-size:10px;color:var(--text-gray);">
参考买入价以面值100计，按票息/剩余期限/当日YTM推算，为估算值，以券商实时报价为准。
</div>
'''


def _sec_strategy(nar: dict) -> str:
    advice = nar.get("advice") or []
    risks = nar.get("risks") or []
    return f'''
{_h2("tag-decision", "决策", "八、综合建议与风险提示", "STRATEGY & RISK")}
<div class="sec-h4-blue">综合建议（框架性参考）</div>
<div class="card"><div class="card-body"><ul>{"".join(f"<li>{a}</li>" for a in advice)}</ul></div></div>
<div class="sec-h4-red">风险提示</div>
<div class="card card-red"><div class="card-body"><ul>{"".join(f"<li>{r}</li>" for r in risks)}</ul></div></div>
'''


# ==================== 主入口 ====================

def build_html(data: dict, nar: dict, meta: dict) -> str:
    """
    meta 需包含: date_label, us_date, hk_date, css, logo_b64, title, company, disclaimer
    """
    header = f'''
<div class="header">
    <div class="header-left">
        <span class="date-badge">{meta["date_label"]}</span>
        <h1>{meta["title"]}</h1>
    </div>
    <div class="logo-side">
        <img src="data:image/png;base64,{meta["logo_b64"]}" alt="{meta["company"]}">
    </div>
</div>
'''

    footer = f'''
<div class="footer">
    {meta["disclaimer"]}<br>
    {meta["company"]} {meta["title"]} · {meta["date_label"]} · 美股 {meta["us_date"]} 收盘 / 港股 {meta["hk_date"]}
</div>
'''

    body = "".join([
        _sec_overview(data),
        _sec_news(nar, data),
        _sec_us_analysis(nar),
        _sec_sectors(nar, data),
        _sec_us_table(data, meta["us_date"]),
        _sec_hk_table(data, meta["hk_date"]),
        _sec_bonds(data, meta["cfg"]),
        _sec_strategy(nar),
    ])

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{meta["title"]} - {meta["date_label"]}</title>
<style>
{meta["css"]}
</style>
</head>
<body>
<div class="page">
{header}
<div class="content">
{body}
</div>
{footer}
</div>
</body>
</html>
'''
