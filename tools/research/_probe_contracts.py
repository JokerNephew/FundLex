# -*- coding: utf-8 -*-
"""抽查基金合同 PDF：章节结构 + 关键条款命中情况"""
import fitz, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FILES = [
    "funds/广发优势增长股票型证券投资基金基金合同_20250722.pdf",
    "funds/广发中证红利低波动交易型开放式指数证券投资基金基金合同_20260929.pdf",
    "funds/广发现金增利货币市场基金基金合同_20251213.pdf",
    "funds/广发新城吾悦封闭式商业不动产证券投资基金基金合同_20260918.pdf",
    "funds/广发丰和债券型证券投资基金基金合同_20260924.pdf",
    "funds/广发悦恒多元稳健3个月持有期混合型基金中基金（FOF）基金合同_20261009.pdf",
]

KEYS = [
    "申购费用由投资人承担",
    "调低赎回费率",
    "并报中国证监会备案",
    "不得互相转换",
    "销售服务费",
    "浮动管理费",
    "持续持有期少于",
    "适当调低基金申购费率",
    "超额管理费",
    "或有管理费",
    "基金销售服务费",
    "直销机构",
]
HEAD_PAT = re.compile(r'^\s*(第[一二三四五六七八九十百]+部分|[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）)')

for f in FILES:
    print("="*100)
    print("FILE:", f)
    try:
        doc = fitz.open(f)
    except Exception as e:
        print("OPEN FAIL", e); continue
    print("pages:", len(doc))
    text = "\n".join(p.get_text() for p in doc)
    # 1) headings (Part-level)
    heads = [l.strip() for l in text.splitlines() if re.match(r'^\s*第[一二三四五六七八九十]+部分', l)]
    print("--- 部分标题(%d):" % len(heads))
    for h in heads[:30]: print("   ", h)
    # 2) key clause hits
    flat = re.sub(r'\s+', '', text)
    print("--- 关键条款命中(全文去空白后子串):")
    for k in KEYS:
        kf = re.sub(r'\s+','',k)
        print(f"    {k}: {flat.count(kf)}")
    # 3) 份额类别定义片段
    m = re.search(r'基金份额分为[^。]{0,200}', flat)
    if m: print("--- 份额类别定义片段:", m.group(0)[:220])
    # 4) 申购费相关上下文
    idx = flat.find("申购费用由")
    if idx >= 0: print("--- '申购费用由'上下文:", flat[max(0,idx-60):idx+120])
    doc.close()
