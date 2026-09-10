# -*- coding: utf-8 -*-
"""
微信推送模块 —— 基于 PushPlus

环境变量:
  PUSHPLUS_TOKEN  必填，PushPlus 的 token
  REPORT_BASE_URL 可选，静态站点根地址（如 https://user.github.io/repo）
                  配置后推送消息会附带 PDF / 网页版链接
"""

from __future__ import annotations

import json
import os
import urllib.request

from .analyzer import pct


def _fmt(v, digits=2):
    return f"{v:,.{digits}f}" if isinstance(v, (int, float)) else "—"


def build_content(data: dict, nar: dict, date_label: str,
                  pdf_url: str | None = None, html_url: str | None = None) -> str:
    """构造推送正文（HTML 模板）。"""
    # 三大指数
    us_grp = next((g for g in data.get("indices", []) if g["market"] == "美股"), None)
    hk_grp = next((g for g in data.get("indices", []) if g["market"] == "港股"), None)
    vix = data.get("vix") or {}
    t10 = next((t for t in data.get("treasury", []) if t["name"] == "10Y"), None)
    gold = next((c for c in data.get("commodities", []) if "黄金" in c["name"]), None)
    oil = next((c for c in data.get("commodities", []) if "原油" in c["name"]), None)

    def idx_line(grp):
        if not grp:
            return "—"
        return " ｜ ".join(
            f'{it["name"]} <b>{_fmt(it.get("price"))}</b>（{pct(it.get("chg"))}）'
            for it in grp["items"]
        )

    parts = [
        f'<h3 style="color:#1d3f78;font-size:14px;margin:12px 0 6px;">美股隔夜收盘</h3>',
        f'<p style="font-size:13px;">{idx_line(us_grp)}</p>',
        f'<p style="font-size:13px;">VIX <b>{_fmt(vix.get("price"))}</b>（{pct(vix.get("chg"))}）'
        f' ｜ 10Y美债 <b>{t10["yield"]:.2f}%</b>' if t10 and t10.get("yield") else '',
        f'<h3 style="color:#1d3f78;font-size:14px;margin:12px 0 6px;">港股</h3>',
        f'<p style="font-size:13px;">{idx_line(hk_grp)}</p>',
        f'<h3 style="color:#1d3f78;font-size:14px;margin:12px 0 6px;">黄金 / 能源</h3>',
        f'<p style="font-size:13px;">COMEX黄金 <b>{_fmt(gold.get("price"))}</b>（{pct(gold.get("chg"))}）'
        f' ｜ WTI原油 <b>{_fmt(oil.get("price"))}</b>（{pct(oil.get("chg"))}）</p>',
    ]

    # 自选股亮点：涨跌前 2
    allrows = data.get("us", []) + data.get("hk", [])
    valid = [r for r in allrows if r.get("chg") is not None]
    if valid:
        valid.sort(key=lambda r: r["chg"], reverse=True)
        top = valid[:2]
        bot = valid[-2:] if len(valid) > 3 else []
        hl = "".join(
            f'<p style="font-size:13px;">• <b>{r["name"]}</b> {pct(r["chg"])}'
            f' ｜ {r.get("advice","")} — {r.get("logic","")[:40]}</p>'
            for r in top + bot
        )
        parts.append('<h3 style="color:#1d3f78;font-size:14px;margin:12px 0 6px;">自选股亮点</h3>')
        parts.append(hl)

    # 链接
    if pdf_url or html_url:
        links = []
        if pdf_url:
            links.append(
                f'<a href="{pdf_url}" style="display:inline-block;background:#1d3f78;color:#fff;'
                f'padding:8px 20px;border-radius:6px;text-decoration:none;font-weight:600;">'
                f'打开/下载 PDF 版研报</a>')
        if html_url:
            links.append(
                f'<a href="{html_url}" style="display:inline-block;background:#c9a227;color:#14213d;'
                f'padding:8px 20px;border-radius:6px;text-decoration:none;font-weight:600;">网页版</a>')
        parts.append(
            '<hr style="border:none;border-top:1px solid #c9a227;margin:14px 0;">'
            f'<p>{" &nbsp;|&nbsp; ".join(links)}</p>')

    parts.append('<p style="color:#999;font-size:11px;margin-top:10px;">'
                 '以上内容仅供参考，不构成投资建议</p>')

    return "".join(parts)


def send(title: str, content: str) -> bool:
    """发送消息。成功返回 True。"""
    token = os.getenv("PUSHPLUS_TOKEN")
    if not token:
        print("[push] 未配置 PUSHPLUS_TOKEN，跳过推送")
        return False

    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
        "channel": os.getenv("PUSHPLUS_CHANNEL", "wechat"),
    }
    req = urllib.request.Request(
        "http://www.pushplus.plus/send",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        code = res.get("code")
        print(f"[push] PushPlus 返回 code={code}, msg={res.get('msg')}")
        return code == 200
    except Exception as e:
        print(f"[push] 推送失败: {e}")
        return False
