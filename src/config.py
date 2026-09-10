# -*- coding: utf-8 -*-
"""
配置模块 —— 每日市场晨报的标的清单与全局常量

数据来源为腾讯行情接口（qt.gtimg.cn），代码格式：
  美股   实时 usNVDA      K线 usNVDA.OQ（后缀 .OQ 纳斯达克 / .N 纽交所 / .AM 美交所）
  港股   hk00700（5位）
  A股    sh000001（沪）/ sz399001（深）
  指数   usDJI 道指 / usIXIC 纳指 / usINX 标普 / hkHSI 恒指 / hkHSTECH 恒生科技
  VIX    usVIX
  商品   hf_GC 黄金 / hf_CL 原油（逗号分隔格式，非 ~ 分隔）

修改本文件即可调整每日跟踪的标的。
"""

# ==================== 市场概览指数 ====================
INDICES = [
    {
        "market": "A股",
        "label": "收盘",
        "items": [
            ("sh000001", "上证指数"),
            ("sz399001", "深证成指"),
            ("sz399006", "创业板指"),
        ],
    },
    {
        "market": "港股",
        "label": "盘中",
        "items": [
            ("hkHSI", "恒生指数"),
            ("hkHSTECH", "恒生科技指数"),
        ],
    },
    {
        "market": "美股",
        "label": "隔夜收盘",
        "items": [
            ("usDJI", "道琼斯工业"),
            ("usIXIC", "纳斯达克综合"),
            ("usINX", "标普500"),
        ],
    },
]

# 波动率指数
VIX_CODE = "usVIX"

# 美债收益率曲线（Yahoo 代码，由 yfinance 补充，失败则显示 —）
TREASURY = [
    ("^IRX", "3M"),
    ("^FVX", "5Y"),
    ("^TNX", "10Y"),
    ("^TYX", "30Y"),
]

# 商品（腾讯 hf_ 代码；美元指数腾讯未提供，用 Yahoo 代码补充）
COMMODITIES = [
    ("hf_GC", "COMEX黄金"),
    ("hf_CL", "WTI原油"),
]
USD_INDEX_CODE = "DX-Y.NYB"   # 美元指数（yfinance，可选）

# ==================== 板块与主题 ETF（板块轮动 / 风险偏好分析）====================
# 11 大行业（SPDR 精选行业）—— 用于判断当日资金在行业间的流向
SECTOR_ETFS = [
    ("usXLK", "科技"),
    ("usXLC", "通信服务"),
    ("usXLY", "可选消费"),
    ("usXLP", "必选消费"),
    ("usXLE", "能源"),
    ("usXLF", "金融"),
    ("usXLV", "医疗保健"),
    ("usXLI", "工业"),
    ("usXLB", "原材料"),
    ("usXLU", "公用事业"),
    ("usXLRE", "房地产"),
]

# 主题 / 赛道 —— 用于观察 AI 产业链内部结构与风格切换
THEME_ETFS = [
    ("usSOXX", "费城半导体"),
    ("usSMH", "半导体"),
    ("usIGV", "软件"),
    ("usIBB", "生物科技"),
    ("usGDX", "金矿"),
    ("usARKK", "创新科技"),
]

# 规模 / 债券 / 汇率 —— 用于判断风险偏好、信用环境与资金面
MACRO_ETFS = [
    ("usSPY", "标普500ETF"),
    ("usQQQ", "纳指100ETF"),
    ("usIWM", "罗素2000"),
    ("usEEM", "新兴市场"),
    ("usFXI", "中国大盘"),
    ("usTLT", "20年+美债"),
    ("usHYG", "高收益债"),
    ("usUUP", "美元指数"),
]

# ==================== 美股自选股 16 只 ====================
# 排列顺序：AI科技12 → 黄金/能源2 → ETF 2（垫底放表格最下方）
# ⚠️ 2026-09-10 按用户要求移除雪佛龙 usCVX，勿加回；usQQQ 显示名改为「QQQ」

US_AI = [
    ("usNVDA.OQ", "英伟达", "AI芯片"),
    ("usTSM.N", "台积电", "半导体代工"),
    ("usAMD.OQ", "超威半导体", "AI芯片"),
    ("usAVGO.OQ", "博通", "AI ASIC"),
    ("usMU.OQ", "美光", "HBM存储"),
    ("usSNDK.OQ", "闪迪", "NAND存储"),
    ("usMRVL.OQ", "迈威尔", "定制AI芯片"),
    ("usMSFT.OQ", "微软", "AI云/应用"),
    ("usGOOGL.OQ", "谷歌-A", "AI全栈"),
    ("usAMZN.OQ", "亚马逊", "AI云"),
    ("usMETA.OQ", "Meta", "AI应用"),
    ("usTSLA.OQ", "特斯拉", "人形机器人"),
]

US_RESOURCE = [
    ("usNEM.N", "纽蒙特", "金矿"),
    ("usXOM.N", "埃克森美孚", "油气"),
]

US_ETF = [
    ("usQQQ.OQ", "QQQ", "宽基ETF"),
    ("usGLD.AM", "黄金ETF-SPDR", "黄金ETF"),
]

US_STOCKS = US_AI + US_RESOURCE + US_ETF
US_ETF_START = len(US_AI) + len(US_RESOURCE)

# ==================== 港股自选股 10 只 ====================
HK_STOCKS = [
    ("hk00700", "腾讯控股", "互联网/AI·混元"),
    ("hk09988", "阿里巴巴-W", "电商/云/AI·通义千问"),
    ("hk03690", "美团-W", "本地生活/AI·自研"),
    ("hk02513", "智谱", "AI大模型·智谱清言"),
    ("hk00100", "MINIMAX-W", "AI大模型·MiniMax"),
    ("hk00005", "汇丰控股", "银行"),
    ("hk00941", "中国移动", "电信/AI·九天"),
    ("hk00883", "中国海洋石油", "能源"),
    ("hk02318", "中国平安", "保险"),
    ("hk02899", "紫金矿业", "黄金/铜"),
]

# ==================== 投资级美元债 5 只 ====================
BONDS = [
    {
        "issuer": "腾讯控股",
        "coupon": 2.39,
        "issue": "2020-06-03",
        "maturity": "2030-06-03",
        "rating": "A / A+",
        "note": "中资科技龙头，现金流稳健",
    },
    {
        "issuer": "阿里巴巴",
        "coupon": 4.875,
        "issue": "2024-11-26",
        "maturity": "2030-05-26",
        "rating": "A / A+",
        "note": "票息最高，云与AI业务支撑",
    },
    {
        "issuer": "埃克森美孚",
        "coupon": 3.482,
        "issue": "2020-03-17",
        "maturity": "2030-03-19",
        "rating": "Aa2 / AA+",
        "note": "美国油企，无地缘制裁风险",
    },
    {
        "issuer": "汇丰控股",
        "coupon": 4.583,
        "issue": "2018-06-19",
        "maturity": "2029-06-19",
        "rating": "A3 / A- / A+",
        "note": "2028-06-19 可赎回，期限最短",
    },
    {
        "issuer": "Alphabet（谷歌）",
        "coupon": 4.100,
        "issue": "2026-02-13",
        "maturity": "2031-02-15",
        "rating": "Aa2 / AA+",
        "note": "新发债，评级最高档",
    },
]

# ==================== 报告元信息 ====================
REPORT_TITLE = "每日市场晨报"
COMPANY = "CENTEN"
DISCLAIMER = "以上内容仅供参考，不构成投资建议。投资有风险，决策需谨慎。"
