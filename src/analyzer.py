# -*- coding: utf-8 -*-
"""
分析模块 —— 规则化建议引擎 + 可选 LLM 深度分析

两种运行模式：
1. 无 LLM_API_KEY：纯规则引擎，基于当日真实行情生成结构化分析（零 token 成本）
   —— 内容来自板块 ETF 涨跌、AI 链内部分化、风险偏好指标、美债曲线等硬数据
2. 有 LLM_API_KEY：调用 OpenAI 兼容接口，在同样数据基础上生成更细的研判
"""

from __future__ import annotations

import json
import os
from typing import Any

# 建议文案 → CSS 样式类
ADVICE_STYLE = {
    "持有": "advice-hold",
    "逢低关注": "advice-buy",
    "观望": "advice-watch",
    "不追高": "advice-watch",
    "高估警惕": "advice-warn",
}

# AI 产业链分组（用于观察 AI 交易重心在算力还是应用）
AI_COMPUTE = {"英伟达", "台积电", "超威半导体", "博通", "美光", "闪迪", "迈威尔"}
AI_APP = {"微软", "谷歌-A", "亚马逊", "Meta"}
AI_GIANTS = {"微软", "谷歌-A", "亚马逊", "Meta", "英伟达", "特斯拉"}


def pct(v: Any, digits: int = 2, sign: bool = True) -> str:
    """格式化百分比。"""
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%" if sign else f"{v:.{digits}f}%"


def rule_advice(row: dict, market: str = "us") -> tuple[str, str]:
    """
    基于估值与涨跌幅生成方向性建议。
    返回 (建议标签, 一句话逻辑)
    """
    pe = row.get("pe")
    chg20 = row.get("chg20")
    ytd = row.get("chg_ytd")
    chg5 = row.get("chg5")
    tag = row.get("tag", "")
    yr = f"{ytd:+.0f}%" if ytd is not None else "—"

    # 1) 年内涨幅过大 → 估值无锚，严格风控
    if ytd is not None and ytd > 100:
        return "高估警惕", f"{tag}年内涨{yr}，涨幅过大估值无历史锚，严格仓位管理"

    # 2) 短期过热或估值极高 → 不追高
    if (chg20 is not None and chg20 > 20) or (pe is not None and pe > 60):
        hot = f"20日涨{pct(chg20, 1)}" if chg20 is not None and chg20 > 20 else ""
        hv = f"PE {pe:.0f}倍" if pe is not None and pe > 60 else ""
        reason = "、".join([x for x in (hot, hv) if x])
        return "不追高", f"{reason}已计入较多乐观预期，等回调更从容"

    # 3) 近期明显回调 → 逢低关注
    if chg20 is not None and chg20 < -10:
        return "逢低关注", f"20日回调{pct(chg20, 1)}，等待企稳信号再分批介入"

    # 4) 估值处于低位 → 逢低关注
    if pe is not None and 0 < pe < 20:
        extra = f"、股息率{row['div']:.1f}%" if market == "hk" and row.get("div") else ""
        return "逢低关注", f"PE仅{pe:.1f}倍{extra}，估值具备安全边际"

    # 5) 亏损或数据缺失 → 观望
    if pe is None or pe < 0:
        return "观望", f"{tag}当前盈利口径为负，等待盈利改善或估值回归"

    return "持有", f"{tag}景气度延续，年内{yr}，核心持仓继续跟踪"


# ==================== LLM（可选） ====================

def llm_available() -> bool:
    return bool(os.getenv("LLM_API_KEY"))


def _llm_call(prompt: str, max_tokens: int = 4000) -> str | None:
    """调用 OpenAI 兼容的 chat completions 接口。"""
    import urllib.request

    key = os.getenv("LLM_API_KEY")
    # 注意用 `or` 而非 os.getenv 默认值：GitHub Actions 未设置变量时会传空字符串，
    # 空字符串不会被当成"未设置"，会导致请求 URL 变成 "/chat/completions" 而失败
    base = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/")
    model = os.getenv("LLM_MODEL") or "deepseek-chat"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content":
                "你是资深美股/港股策略分析师，服务于专业投资者。"
                "输出严谨、客观、基于数据的中文研报文案，观点明确但不承诺收益。只输出JSON。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[analyzer] LLM 调用失败，降级为模板: {e}")
        return None


def _parse_json(text: str) -> dict | None:
    """从 LLM 返回文本中尽力解析 JSON。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    try:
        return json.loads(t)
    except Exception:
        s, e = t.find("{"), t.rfind("}")
        if s != -1 and e > s:
            try:
                return json.loads(t[s:e + 1])
            except Exception:
                return None
    return None


# ==================== 数据摘要（供 LLM 使用） ====================

def _data_digest(data: dict) -> str:
    lines = []
    for grp in data.get("indices", []):
        for it in grp["items"]:
            lines.append(f"{grp['market']} {it['name']}: {it['price']} ({pct(it.get('chg'))})")
    v = data.get("vix") or {}
    lines.append(f"VIX: {v.get('price')} ({pct(v.get('chg'))})")
    for t in data.get("treasury", []):
        if t.get("yield") is not None:
            lines.append(f"美债{t['name']}: {t['yield']:.3f}%")
    for c in data.get("commodities", []):
        if c.get("price") is not None:
            lines.append(f"{c['name']}: {c['price']} ({pct(c.get('chg'))})")

    for g, label in (("sector", "行业ETF"), ("theme", "主题ETF"), ("macro", "宏观ETF")):
        rows = [r for r in data.get("etfs", {}).get(g, []) if r.get("chg") is not None]
        rows.sort(key=lambda r: r["chg"], reverse=True)
        if rows:
            lines.append(f"{label}（按涨跌排序）: " +
                         "，".join(f"{r['name']} {pct(r['chg'])}" for r in rows))

    lines.append("美股自选股:")
    for r in data.get("us", []):
        lines.append(f"  {r['name']}({r['code']}) {r['price']} {pct(r['chg'])} "
                     f"PE={r['pe']} 5日{pct(r.get('chg5'))} 20日{pct(r.get('chg20'))} "
                     f"年内{pct(r.get('chg_ytd'))} 建议={r.get('advice')}")
    lines.append("港股自选股:")
    for r in data.get("hk", []):
        lines.append(f"  {r['name']}({r['code']}) {r['price']} {pct(r['chg'])} "
                     f"PE={r['pe']} 20日{pct(r.get('chg20'))} 年内{pct(r.get('chg_ytd'))} "
                     f"建议={r.get('advice')}")
    return "\n".join(lines)


# ==================== 模板引擎（数据驱动，零 token） ====================

def _template_narrative(data: dict) -> dict:
    """基于当日真实行情生成结构化分析，覆盖全部研报文案板块。"""
    etfs = data.get("etfs", {})
    vix = (data.get("vix") or {}).get("price")
    tr = {t["name"]: t.get("yield") for t in data.get("treasury", [])}
    t10, t5, t30, t3m = tr.get("10Y"), tr.get("5Y"), tr.get("30Y"), tr.get("3M")

    def E(name):
        for g in ("macro", "theme", "sector"):
            for r in etfs.get(g, []):
                if r["name"] == name:
                    return r
        return None

    def srt(g):
        rows = [r for r in etfs.get(g, []) if r.get("chg") is not None]
        return sorted(rows, key=lambda r: r["chg"], reverse=True)

    def fe(r):
        """ETF：名称 + 带色涨跌幅"""
        if not r or r.get("chg") is None:
            return "—"
        c = "up" if r["chg"] > 0 else "down"
        return f'{r["name"]}<span class="{c}">{r["chg"]:+.2f}%</span>'

    def fp(v, d=2):
        if v is None:
            return "—"
        return f'<span class="{"up" if v > 0 else "down"}">{v:+.{d}f}%</span>'

    sec = srt("sector")
    up_n = len([r for r in sec if r["chg"] > 0])
    dn_n = len(sec) - up_n
    top3 = sec[:3]
    bot3 = sec[-3:][::-1] if len(sec) >= 3 else []

    gold = next((c for c in data.get("commodities", []) if "黄金" in c["name"]), None)
    oil = next((c for c in data.get("commodities", []) if "原油" in c["name"]), None)

    us = data.get("us", [])
    hk = data.get("hk", [])

    def pick(names):
        return [r for r in us if r["name"] in names and r.get("chg") is not None]

    def avg(rs):
        return sum(r["chg"] for r in rs) / len(rs) if rs else None

    compute, app = pick(AI_COMPUTE), pick(AI_APP)
    c_avg, a_avg = avg(compute), avg(app)

    us_up = len([r for r in us if (r.get("chg") or 0) > 0])
    us_dn = len([r for r in us if (r.get("chg") or 0) < 0])
    hk_up = len([r for r in hk if (r.get("chg") or 0) > 0])
    hk_dn = len([r for r in hk if (r.get("chg") or 0) < 0])

    pes = sorted([r["pe"] for r in us if r.get("pe") and r["pe"] > 0])
    pe_med = pes[len(pes) // 2] if pes else None

    # ---------- 宏观要闻 ----------
    news = []
    if t10 is not None:
        curve = "、".join(f"{k} {v:.2f}%" for k, v in (("3M", t3m), ("5Y", t5), ("30Y", t30)) if v)
        news.append({"tag": "利率", "title":
            f"10年期美债收益率报 <strong>{t10:.2f}%</strong>{'（' + curve + '）' if curve else ''}；"
            f"{'收益率处于高位，对高估值成长股形成持续压制，分母端压力是当前主要矛盾' if t10 >= 4.3 else '利率维持区间震荡，对权益资产估值压力相对可控'}"})
    else:
        news.append({"tag": "利率", "title":
            "美债收益率数据本次未取到（数据源限流）。利率水平仍是成长股估值的核心变量，"
            "建议以券商终端实时数据为准，重点关注 10Y 是否突破 4.5% 关口。"})

    if vix is not None:
        if vix > 20:
            mood = "站上20，避险情绪升温，对冲需求增加，宜控制仓位波动敞口"
        elif vix < 15:
            mood = "低于15，市场情绪偏乐观，需警惕过度乐观下的回撤风险"
        else:
            mood = "位于15–20正常区间，情绪中性，可按既定节奏配置"
        news.append({"tag": "情绪", "title": f"VIX 恐慌指数报 <strong>{vix:.2f}</strong>，{mood}"})

    if gold and gold.get("price") is not None:
        g_chg = gold.get("chg")
        news.append({"tag": "商品", "title":
            f"COMEX黄金 <strong>{gold['price']:,.2f}</strong>（{fp(g_chg)}），"
            f"{'避险与降息预期共振下延续强势' if (g_chg or 0) >= 0 else '短线承压回调，关注实际利率变化'}"
            f"；" + (f"WTI原油 <strong>{oil['price']:,.2f}</strong>（{fp(oil.get('chg'))}）"
                     f"{'地缘溢价抬升' if (oil.get('chg') or 0) >= 0 else '回落'}。" if oil and oil.get("price") else "")})

    if top3:
        news.append({"tag": "板块", "title":
            f"美股11大行业ETF <strong>{up_n}涨{dn_n}跌</strong>，{fe(top3[0])}领涨"
            + (f"，{fe(bot3[0])}领跌" if bot3 else "")
            + f"；{'资金明显向少数板块集中，市场宽度偏弱' if up_n <= 3 else '上涨面较广，市场参与度尚可'}。"})

    eem, fxi = E("新兴市场"), E("中国大盘")
    if eem:
        news.append({"tag": "资金流", "title":
            f"新兴市场ETF {fe(eem)}" + (f"，中国大盘ETF {fe(fxi)}" if fxi else "")
            + f"；外资对新兴市场风险偏好{'回升，利好港股与中概估值修复' if (eem['chg'] or 0) > 0 else '回落，需关注外资流出压力'}。"})

    uup = E("美元指数")
    if uup and uup.get("chg") is not None:
        news.append({"tag": "汇率", "title":
            f"美元指数 {fe(uup)}，{'美元走强压制大宗商品计价与新兴市场资金流' if uup['chg'] > 0 else '美元走弱利好大宗商品与新兴市场资产估值'}。"})

    # ---------- 美股深度分析 6 子板块 ----------
    spy, qqq, iwm = E("标普500ETF"), E("纳指100ETF"), E("罗素2000")
    tlt, hyg, gdx = E("20年+美债"), E("高收益债"), E("金矿")
    soxx, smh, igv = E("费城半导体"), E("半导体"), E("软件")

    valuation = []
    for g in data.get("indices", []):
        if g["market"] != "美股":
            continue
        for it in g["items"]:
            if it.get("price") is not None:
                valuation.append(f'{it["name"]} <strong>{it["price"]:,.2f}</strong>（{fp(it.get("chg"))}）')
    if valuation:
        valuation = ["美股三大指数：" + "，".join(valuation)]
    if iwm and spy:
        valuation.append(
            f"大小盘风格：罗素2000 {fp(iwm.get('chg'))} vs 标普500ETF {fp(spy.get('chg'))}，"
            f"{'小盘跑赢，市场风险偏好扩张' if (iwm.get('chg') or 0) > (spy.get('chg') or 0) else '大盘跑赢，资金向龙头集中、防御倾向上升'}")
    if qqq and qqq.get("off_high") is not None:
        valuation.append(f"技术位置：纳指100ETF 距52周高点 <strong>{qqq['off_high']:.1f}%</strong>"
                         + (f"，52周区间分位 {qqq['pos52']:.0f}%" if qqq.get("pos52") is not None else "")
                         + ("，仍处高位区，回撤空间需留意" if qqq["off_high"] > -5 else "，已有一定回调，位置相对安全"))
    if vix is not None:
        valuation.append(f"波动率：VIX {vix:.2f}，{'抬升' if vix > 20 else '低位'}环境下"
                         f"{'期权对冲成本上升，高估值资产波动放大' if vix > 20 else '市场定价平稳，但需防范低波动后的跳升风险'}")
    if pe_med:
        valuation.append(f"自选股估值：美股17只标的 PE 中位数 <strong>{pe_med:.1f}倍</strong>，"
                         f"整体处于{'偏高' if pe_med > 30 else ('合理' if pe_med > 18 else '偏低')}水平")

    rotation = []
    if sec:
        rotation.append(f"行业全景（11大行业ETF）：<strong>{up_n}涨{dn_n}跌</strong>，" +
                        "领涨 " + "、".join(fe(r) for r in top3) +
                        ("；领跌 " + "、".join(fe(r) for r in bot3) if bot3 else ""))
    if soxx and igv:
        gap = (soxx.get("chg") or 0) - (igv.get("chg") or 0)
        rotation.append(
            f"科技内部结构：费城半导体 {fp(soxx.get('chg'))} vs 软件 {fp(igv.get('chg'))}，"
            f"剪刀差 <strong>{gap:+.1f}个百分点</strong>——"
            + ("资金明显从软件/应用流向算力/硬件，AI交易重心在'卖铲子'环节" if gap > 1
               else ("软件跑赢硬件，市场开始为AI变现与应用落地定价" if gap < -1
                     else "软硬件同步，AI产业链景气未出现结构性分化")))
    if gdx and gold:
        gv, cv = gdx.get("chg") or 0, gold.get("chg") or 0
        if gv * cv > 0:
            desc = "同向走强，避险交易升温" if gv > 0 else "同向走弱，避险需求阶段性降温"
        else:
            desc = "走势背离，需关注金价向矿股的传导时滞"
        rotation.append(f"避险资产：金矿ETF {fp(gdx.get('chg'))}，与COMEX黄金 {fp(gold.get('chg'))} {desc}")
    if up_n <= 3:
        rotation.append("市场宽度：上涨板块不足三成，指数虽窄幅波动但内部结构分化剧烈，"
                        "少数权重板块主导指数表现，需警惕'指数失真'风险")
    elif up_n >= 7:
        rotation.append("市场宽度：上涨板块超六成，普涨格局下赚钱效应较好，趋势延续性相对可靠")

    sentiment = []
    if vix is not None:
        sentiment.append(f"恐慌指数 VIX <strong>{vix:.2f}</strong>："
                         + ("突破20，避险情绪主导，建议降低高β仓位、提高现金比例" if vix > 20
                            else ("低于15，情绪过热信号，历史上低VIX往往对应脆弱的平静" if vix < 15
                                  else "处于中性区间，情绪面未给方向性指引")))
    if tlt and hyg:
        sentiment.append(f"债市风险偏好：长债ETF {fp(tlt.get('chg'))}、高收益债ETF {fp(hyg.get('chg'))}，"
                         + ("两者同涨，流动性宽松预期主导" if (tlt.get("chg") or 0) > 0 and (hyg.get("chg") or 0) > 0
                            else ("长债涨而高收益债跌，避险情绪升温、信用环境收紧" if (tlt.get("chg") or 0) > 0
                                  else "长债承压，利率上行压制风险资产估值")))
    if iwm and spy:
        sentiment.append(f"大小盘：罗素2000 {fp(iwm.get('chg'))} vs 标普500 {fp(spy.get('chg'))}，"
                         + ("小盘占优，风险偏好扩张，资金愿意下沉" if (iwm.get("chg") or 0) > (spy.get("chg") or 0) else "大盘占优，资金抱团龙头，防御性抬升"))
    sentiment.append(f"自选股涨跌：美股 <strong>{us_up}涨{us_dn}跌</strong>，港股 <strong>{hk_up}涨{hk_dn}跌</strong>"
                     + ("，两地同步走弱，风险偏好整体偏弱" if us_up < us_dn and hk_up < hk_dn
                        else ("，两地同步回暖，情绪修复" if us_up > us_dn and hk_up > hk_dn else "，两地表现分化，需区别对待")))
    if gdx:
        sentiment.append(f"避险需求：金矿ETF {fp(gdx.get('chg'))}，"
                         + ("资金流入避险资产" if (gdx.get("chg") or 0) > 0 else "避险需求阶段性降温"))

    fed = []
    if t10 is not None:
        fed.append(f"收益率曲线：{'、'.join(f'{k} {v:.2f}%' for k, v in (('3M', t3m), ('5Y', t5), ('10Y', t10), ('30Y', t30)) if v is not None)}")
        if t5 is not None:
            sp = t10 - t5
            fed.append(f"5s10s 利差 <strong>{sp:+.0f}bp</strong>，"
                       + ("曲线陡峭化，长端定价通胀与增长预期" if sp > 30 else ("曲线平坦，增长预期偏弱或政策偏紧" if sp < 10 else "曲线形态正常")))
        fed.append(f"政策含义：10Y 位于 {t10:.2f}%，"
                   + ("高利率环境对成长股估值构成持续压制，短期难见分母端改善" if t10 >= 4.3
                      else "利率压力缓和，为估值修复提供空间")
                   + "；后续重点关注 CPI、非农就业与 FOMC 点阵图对路径的修正")
    else:
        fed.append("美债曲线数据本次未取到（数据源限流）。当前政策路径的关键观察点为："
                   "核心PCE能否回落至2%目标、就业市场是否走弱、FOMC对年内政策路径的指引")
        fed.append("利率敏感度提示：10Y美债每上行约50bp，高PE成长股通常面临5%–10%的估值下修；"
                   "若突破4.5%关口，建议主动降低组合久期，向现金流稳定的价值股与短久期债券倾斜")
    fed.append("交易提示：在利率方向明确前，建议以盈利确定性高、现金流稳健的标的为底仓，"
               "对高久期资产（高PE成长股、长债）保持谨慎")

    ai = []
    if c_avg is not None and a_avg is not None:
        ai.append(f"AI 交易重心：算力链（英伟达/台积电/AMD/博通/美光/闪迪/迈威尔）均涨 <strong>{c_avg:+.2f}%</strong>，"
                  f"应用与云（微软/谷歌/亚马逊/Meta）均涨 <strong>{a_avg:+.2f}%</strong>——"
                  + ("资金聚焦算力硬件，'卖铲子'逻辑占优" if c_avg > a_avg + 0.5
                     else ("应用端跑赢，市场开始为AI变现定价" if a_avg > c_avg + 0.5 else "算力与应用同步，产业链景气整体平稳")))
    if soxx and smh:
        ai.append(f"半导体景气：费城半导体 {fp(soxx.get('chg'))}、半导体ETF {fp(smh.get('chg'))}，"
                  + ("板块整体走强，代工与设备订单预期上修" if (soxx.get("chg") or 0) > 0 else "板块回调，需跟踪订单与库存数据验证"))
    for nm in ("英伟达", "博通", "美光", "闪迪"):
        r = next((x for x in us if x["name"] == nm), None)
        if r and r.get("chg") is not None:
            ai.append(f"{nm}：<strong>{r['price']}</strong>（{fp(r['chg'])}），"
                      f"年内{pct(r.get('chg_ytd'), 1)}，PE {r['pe']:.1f}倍" if r.get("pe") else
                      f"{nm}：<strong>{r['price']}</strong>（{fp(r['chg'])}），年内{pct(r.get('chg_ytd'), 1)}")
            break
    ai.append("跟踪清单：HBM 价格与产能、CoWoS 先进封装扩产进度、云厂商资本开支指引、"
              "定制ASIC（博通/迈威尔）订单能见度，四项共同决定AI算力链的持续性")

    giants = []
    for nm in ("英伟达", "微软", "谷歌-A", "亚马逊", "Meta", "特斯拉"):
        r = next((x for x in us if x["name"] == nm), None)
        if r and r.get("chg") is not None:
            pe = f"，PE {r['pe']:.1f}倍" if r.get("pe") else ""
            giants.append(f"{nm}：<strong>{r['price']}</strong>（{fp(r['chg'])}{pe}），年内{pct(r.get('chg_ytd'), 1)}")
    if giants:
        giants.append("关注要点：云厂商资本开支指引（决定算力需求天花板）、AI变现进度（决定估值能否兑现）、"
                      "财报窗口期的业绩指引对板块情绪的牵引")

    # ---------- 黄金 / 能源专题 ----------
    gold_items = []
    if gold and gold.get("price") is not None:
        gold_items.append(f"COMEX黄金 <strong>{gold['price']:,.2f}</strong>（{fp(gold.get('chg'))}）"
                          + ("，延续创新高走势" if (gold.get("chg") or 0) > 0 else "，高位回调"))
    gld = next((r for r in us if r["name"] == "黄金ETF-SPDR"), None)
    nem = next((r for r in us if r["name"] == "纽蒙特"), None)
    zijin = next((r for r in hk if r["name"] == "紫金矿业"), None)
    for r, desc in ((gld, "黄金ETF（GLD）"), (nem, "纽蒙特 NEM（金矿龙头）"), (zijin, "紫金矿业（港股·黄金+铜）")):
        if r and r.get("price") is not None:
            gold_items.append(f"{desc}：<strong>{r['price']}</strong>（{fp(r.get('chg'))}），"
                              f"{r.get('advice', '持有')}——{r.get('logic', '')}")
    if gdx:
        gold_items.append(f"金矿板块：GDX ETF {fp(gdx.get('chg'))}，"
                          + ("矿企弹性大于金价，金价上行时放大收益" if (gdx.get("chg") or 0) > 0 else "矿股回调，关注成本端与产量指引"))
    gold_items.append("驱动逻辑：实际利率下行、央行购金、地缘避险三条主线；"
                      "若10Y美债实际利率抬升，金价短期承压但不改中长期配置价值")

    energy_items = []
    if oil and oil.get("price") is not None:
        energy_items.append(f"WTI原油 <strong>{oil['price']:,.2f}</strong>（{fp(oil.get('chg'))}）"
                            + ("，地缘溢价抬升" if (oil.get("chg") or 0) > 0 else "，回落整理"))
    for nm, desc in (("埃克森美孚", "埃克森美孚 XOM"),):   # CVX 已于 2026-09-10 移除
        r = next((x for x in us if x["name"] == nm), None)
        if r and r.get("price") is not None:
            energy_items.append(f"{desc}：<strong>{r['price']}</strong>（{fp(r.get('chg'))}），"
                                f"{r.get('advice', '持有')}——{r.get('logic', '')}")
    cnooc = next((r for r in hk if r["name"] == "中国海洋石油"), None)
    if cnooc and cnooc.get("price") is not None:
        energy_items.append(f"中海油（港股）：<strong>{cnooc['price']}</strong>（{fp(cnooc.get('chg'))}），"
                            f"{cnooc.get('advice', '持有')}——{cnooc.get('logic', '')}")
    xle = E("能源")
    if xle:
        energy_items.append(f"能源板块：XLE 行业ETF {fp(xle.get('chg'))}，"
                            + ("板块整体走强" if (xle.get("chg") or 0) > 0 else "板块承压"))
    energy_items.append("驱动逻辑：OPEC+产量政策、地缘冲突对供给端的扰动、全球库存水平；"
                        "油价高位时一体化油企现金流充沛，分红与回购具备吸引力")

    # ---------- 综合建议 ----------
    hold_names = [r["name"] for r in us if r.get("advice") == "持有"]
    buy_names = [r["name"] for r in us if r.get("advice") == "逢低关注"]
    warn_names = [r["name"] for r in us if r.get("advice") in ("不追高", "高估警惕")]
    wait_names = [r["name"] for r in us if r.get("advice") == "观望"] + \
                 [r["name"] for r in hk if r.get("advice") == "观望"]

    advice = []
    if hold_names:
        advice.append(f"<strong>持有为主</strong>：{'、'.join(hold_names[:8])}"
                      + (f" 等{len(hold_names)}只" if len(hold_names) > 8 else "")
                      + f"——AI算力链景气未见拐点"
                      + (f"，算力链均涨{c_avg:+.2f}%" if c_avg is not None else "")
                      + "，核心仓位不动摇")
    if buy_names:
        advice.append(f"<strong>逢低关注</strong>：{'、'.join(buy_names[:6])}——估值处于低位或近期明显回调，"
                      "分批介入比一次性买入更从容，建议预留后续加仓空间")
    if warn_names:
        advice.append(f"<strong>不追高</strong>：{'、'.join(warn_names[:6])}——短期涨幅或估值已计入较多乐观预期，"
                      "等待回调至合理区间再考虑，避免情绪化加仓")
    if wait_names:
        advice.append(f"<strong>观望</strong>：{'、'.join(wait_names[:6])}——盈利口径为负或缺乏明确催化，"
                      "等待基本面改善信号")
    base = f"10Y美债 {t10:.2f}%" if t10 is not None else "当前利率环境"
    advice.append(f"<strong>稳健配置（美元债）</strong>：5只投资级美元债提供票息保护，在{base}水平下"
                  "锁定到期收益率仍有吸引力，建议作为组合的防御底仓，优先AA+评级与期限较短品种")
    advice.append(f"<strong>组合思路</strong>：AI科技 50%（算力链为核心）+ 资源/能源 15%（对冲通胀与地缘）+ "
                  "港股核心 20%（估值洼地）+ 投资级美元债 15%（票息防御），"
                  + ("当前风险偏好偏弱，可适当提高债券与黄金比例" if (vix or 0) > 20 else "维持股债均衡，避免单一赛道过度集中"))

    # ---------- 风险提示 ----------
    risks = []
    if t10 is not None:
        risks.append(f"<strong>利率风险</strong>：10Y美债 {t10:.2f}%"
                     + ("处于高位" if t10 >= 4.3 else "")
                     + "，高利率对高估值成长股持续压制；若通胀反复导致加息预期升温，"
                       "高久期资产面临估值与盈利双杀")
    else:
        risks.append("<strong>利率风险</strong>：当前利率水平是成长股估值的核心变量，"
                     "若10Y美债进一步上行突破4.5%，高PE标的将面临显著杀估值压力")
    if vix is not None:
        risks.append(f"<strong>情绪面风险</strong>：VIX {vix:.2f}"
                     + ("已站上20，市场脆弱性上升" if vix > 20 else "处于低位，需防范低波动后跳升")
                     + "；低波动环境常伴随杠杆累积，一旦波动率跳升易触发被动减仓")
    risks.append("<strong>高位回撤风险</strong>：部分标的年内涨幅巨大（如AI算力链、2026年新股），"
                 "估值缺乏历史锚，回调幅度可能超出预期，务必设定止损位")
    risks.append("<strong>市场宽度风险</strong>：" 
                 + (f"当日仅{up_n}个行业上涨，指数由少数权重板块支撑" if up_n <= 4 else "需持续跟踪上涨板块数量变化")
                 + "，若领涨板块熄火而广度未改善，指数回撤压力将放大")
    risks.append("<strong>地缘风险</strong>：中东、东欧等地局势可能推升油价与输入型通胀，"
                 "进而压缩企业毛利率并扰动央行政策节奏")
    risks.append("<strong>结构性风险</strong>：AI算力建设瓶颈正从GPU转向数据中心物理建设"
                 "（电力、散热、钢结构与电工短缺），HBM成本高企可能压缩整机毛利率")
    risks.append("<strong>港股特有风险</strong>：受内地经济基本面、美元流动性、地缘因素三重影响，"
                 "波动幅度通常大于美股；2026年新上市AI标的估值无锚、流动性较差，需严格仓位管理")

    return {
        "news": news,
        "us_analysis": {
            "valuation": valuation or ["暂无数据"],
            "rotation": rotation or ["暂无数据"],
            "sentiment": sentiment or ["暂无数据"],
            "fed": fed or ["暂无数据"],
            "ai_chain": ai or ["暂无数据"],
            "giants": giants or ["暂无数据"],
        },
        "gold": gold_items,
        "energy": energy_items,
        "advice": advice,
        "risks": risks,
    }


# ==================== LLM Prompt ====================

def _llm_prompt(data: dict) -> str:
    # 注入当日新闻：这是分析质量的关键，没有新闻 LLM 只能输出空泛套话
    news_block = ""
    if data.get("news"):
        try:
            from .news import to_prompt_text
            txt = to_prompt_text(data["news"])
            if txt:
                news_block = f"\n【当日新闻】\n{txt}\n"
        except Exception as e:
            print(f"[analyzer] 新闻注入失败: {e}")

    return f"""以下是今日全球市场与自选股的真实行情数据：

{_data_digest(data)}
{news_block}
请基于以上真实数据（务必结合当日新闻中的具体事件与数字），为专业投资者生成中文研报分析文案。要求：
- 只使用上面给出的数据做判断，不要编造具体数字
- 观点明确、有洞察力，每条 80 字以内，不承诺收益
- 充分展开：板块轮动要讲清资金从哪流向哪、AI链要区分算力与应用、风险偏好要结合VIX/债市/大小盘
- 严格按以下 JSON 格式输出，不要输出任何其他内容：

{{
  "news": [{{"tag":"利率","title":"..."}}, {{"tag":"板块","title":"..."}}],
  "us_analysis": {{
    "valuation": ["...", "...", "..."],
    "rotation": ["...", "...", "..."],
    "sentiment": ["...", "..."],
    "fed": ["...", "..."],
    "ai_chain": ["...", "...", "..."],
    "giants": ["...", "..."]
  }},
  "gold": ["...", "...", "..."],
  "energy": ["...", "...", "..."],
  "advice": ["<strong>持有为主</strong>：...", "<strong>逢低关注</strong>：...", "<strong>不追高</strong>：...", "<strong>稳健配置（美元债）</strong>：...", "<strong>组合思路</strong>：..."],
  "risks": ["<strong>利率风险</strong>：...", "<strong>情绪面风险</strong>：...", "<strong>高位回撤风险</strong>：...", "<strong>地缘风险</strong>：...", "<strong>结构性风险</strong>：..."]
}}

数量要求：news 5-7 条；us_analysis 每个子项 2-4 条；gold/energy 各 3-4 条；advice 5-6 条；risks 5-7 条。
文案中需要强调数字时可用 <strong> 标签，涨跌可用 <span class="up"> / <span class="down">。"""


def build_narrative(data: dict) -> dict:
    """
    生成全部分析文案。优先 LLM，失败或无 Key 时降级为数据驱动模板。
    """
    if llm_available():
        raw = _llm_call(_llm_prompt(data))
        parsed = _parse_json(raw)
        if parsed and isinstance(parsed, dict):
            base = _template_narrative(data)
            for k, v in parsed.items():
                if v:
                    base[k] = v
            base["source"] = "llm"
            return base
        print("[analyzer] LLM 输出解析失败，使用模板文案")

    n = _template_narrative(data)
    n["source"] = "template"
    return n
