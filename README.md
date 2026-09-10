# 每日市场晨报 · 云端独立版

一套**不依赖 WorkBuddy 桌面客户端**的自动化研报系统：定时在云端拉取行情、生成 A4 研报、转 PDF、推送到微信。

## 为什么需要它

WorkBuddy 的定时自动化由**桌面客户端**调度。如果到点时客户端没运行（电脑关机/休眠/未启动），任务会被直接跳过且不补跑。

本项目把整条链路搬到云端（GitHub Actions），只要 GitHub 在线就会准时执行，与你的电脑是否开机无关。

## 架构

```
GitHub Actions 定时触发（工作日 09:00 北京时间）
        ↓
    腾讯行情拉数据（美股/港股/A股/指数/VIX/黄金/原油，实时 + 日K线）
        ↓
    规则引擎生成买卖建议（可选：接 LLM 生成深度分析）
        ↓
    生成 A4 HTML 研报（内置 CENTEN logo）
        ↓
    Playwright 转 PDF ──→ 发布到 GitHub Pages
        ↓
    PushPlus 推送到微信（附 PDF / 网页链接）
```

## 数据源

| 数据 | 来源 | 可靠性 |
|------|------|--------|
| 美股/港股/A股实时行情、PE、市值 | 腾讯行情 `qt.gtimg.cn` | 高，国内境外均可访问 |
| 5日 / 20日 / 今年以来涨跌幅 | 腾讯日K线 `web.ifzq.gtimg.cn` | 高 |
| 指数（道指/纳指/标普/恒指/恒生科技/上证/深证/创业板） | 腾讯行情 | 高 |
| VIX、COMEX黄金、WTI原油 | 腾讯行情 | 高 |
| 美债收益率曲线、港股股息率 | yfinance（Yahoo Finance） | 中，境外稳定；国内可能限流，降级显示 `—` |

**核心表格不依赖 yfinance**：即使后者被限流，个股与指数的现价、涨跌幅、PE、市值、区间涨跌等主要列依然完整。

## 成本

| 模式 | AI token 消耗 | 月成本 |
|------|--------------|--------|
| 纯规则模板（不配 LLM） | 0 | ¥0 |
| 接 LLM（DeepSeek 等） | 约 3 万输入 + 3 千输出/天 | 约 ¥2–5 |

GitHub Actions 公开仓库完全免费，私有仓库每月 2000 分钟也远超需求。

## 部署步骤（约 10 分钟）

### 1. 创建仓库

在 GitHub 新建仓库（建议设为 **Public** 以享受无限 Actions 额度），把本目录全部内容推送上去。

### 2. 配置 Secrets

进入仓库 **Settings → Secrets and variables → Actions**：

- **Secrets** 标签页 → `New repository secret`
  - `PUSHPLUS_TOKEN`：PushPlus 的 token（[pushplus.plus](https://www.pushplus.plus) 微信扫码登录即可获取）
  - `LLM_API_KEY`：（可选）LLM 接口 Key，不填则使用零成本规则模板

- **Variables** 标签页 → `New repository variable`
  - `REPORT_BASE_URL`：`https://你的用户名.github.io/仓库名`
  - `LLM_BASE_URL`：（可选）默认 `https://api.deepseek.com/v1`
  - `LLM_MODEL`：（可选）默认 `deepseek-chat`

### 3. 开启 GitHub Pages

**Settings → Pages → Source** 选择 `gh-pages` 分支，根目录 `/`，保存。

首次运行后 Actions 会自动创建该分支。

### 4. 手动测试

**Actions** 标签页 → 左侧选 `每日市场晨报` → 右上角 **Run workflow** → 运行。

约 3–5 分钟后检查：
- Actions 日志无报错
- 微信收到推送
- `https://你的用户名.github.io/仓库名/` 可访问研报

### 5. 完成

之后每个工作日 09:00（北京时间）自动执行。

## 本地运行

```bash
pip install -r requirements.txt
playwright install chromium

cp .env.example .env   # 填入 token
python main.py --dry-run    # 只生成 HTML，验证效果
python main.py --no-push    # 生成 HTML+PDF，不推送
python main.py              # 完整流程
```

产物输出在 `output/` 目录。

## 目录结构

```
market-report-cloud/
├── main.py                     # 主入口
├── requirements.txt
├── src/
│   ├── config.py               # 自选股/债券/指数清单 ← 改这里调整跟踪标的
│   ├── fetcher.py              # yfinance 数据获取
│   ├── analyzer.py             # 建议规则引擎 + 可选 LLM
│   ├── builder.py              # HTML 研报生成（八大板块）
│   ├── pdf.py                  # Playwright 转 PDF
│   └── notifier.py             # PushPlus 微信推送
├── assets/
│   ├── report.css              # 研报样式（深藏蓝+金色）
│   └── logo.txt                # CENTEN logo（base64）
├── .github/workflows/
│   └── daily-report.yml        # 定时工作流
└── output/                     # 生成的研报（自动创建）
```

## 自定义

- **调整跟踪标的**：编辑 `src/config.py` 中的 `US_AI` / `US_RESOURCE` / `US_ETF` / `HK_STOCKS` / `BONDS`
- **调整建议规则阈值**：`src/config.py` 底部的 `ADVICE_RULES` 与 `src/analyzer.py` 的 `rule_advice()`
- **调整视觉风格**：`assets/report.css`
- **调整运行时间**：`.github/workflows/daily-report.yml` 的 `cron`（注意是 UTC 时间，北京时间减 8 小时）

## 注意事项

- GitHub 对**连续 60 天无活动**的仓库会禁用定时任务。若长期无 commit，可偶尔手动触发一次，或加一个定期空提交的 workflow。
- Actions 定时任务在高峰期可能延迟几分钟，属正常现象。
- 主数据源为腾讯行情（免费无 key、无限流）。仅美债收益率与港股股息率走 Yahoo Finance，偶发限流时显示 `—`，不影响报告主体。
- 腾讯代码格式：美股 `usNVDA`（实时）/ `usNVDA.OQ`（K线，后缀 .OQ 纳斯达克 / .N 纽交所 / .AM 美交所）；港股 `hk00700`；A股 `sh000001` / `sz399001`。改标的时注意带对后缀。
- 债券参考买入价为按当日美债收益率 + 评级利差推算的**估算值**，实际以券商实时报价为准。

---

以上内容仅供参考，不构成投资建议。
