# -*- coding: utf-8 -*-
import fitz, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def flat_of(f):
    doc = fitz.open(f)
    t = "".join(p.get_text() for p in doc)
    doc.close()
    return t

def show(tag, flat, key, w=100, n=3):
    idxs = [m.start() for m in re.finditer(re.escape(key), re.sub(r'\s+','',flat))]
    print(f"--- [{tag}] '{key}' x{len(idxs)}")
    f2 = re.sub(r'\s+','',flat)
    for i in idxs[:n]:
        print("   …", f2[max(0,i-50):i+len(key)+w])

# 1) 丰和债券：是否已按新规修改（变体措辞）
f1 = flat_of("funds/广发丰和债券型证券投资基金基金合同_20260924.pdf")
print("########## 广发丰和债券 20260924 ##########")
for k in ["通过直销机构申购", "不再继续收取销售服务费", "调低销售服务费率", "调低赎回费率",
          "扣除或加上", "随赎回款", "并报中国证监会备案", "不得互相转换", "持续持有期少于7",
          "适当调低基金申购费率"]:
    show("丰和", f1, k)

# 2) 新动力混合 20251103：推测未修改的旧版
f2 = flat_of("funds/广发新动力混合型证券投资基金基金合同_20251103.pdf")
print("\n########## 广发新动力混合 20251103 ##########")
for k in ["申购费用由投资人承担", "本基金的申购费率由基金管理人决定", "通过直销机构申购",
          "调低赎回费率", "并报中国证监会备案", "不得互相转换", "持续持有期少于7",
          "适当调低基金申购费率", "赎回费用归入基金财产"]:
    show("新动力", f2, k)

# 3) ETF 申购赎回部分的二级标题
print("\n########## 红利低波ETF 第八部分二级标题 ##########")
f3 = flat_of("funds/广发中证红利低波动交易型开放式指数证券投资基金基金合同_20260929.pdf")
i = f3.find("第八部分")
i2 = f3.find("第八部分", i+10)  # 正文中的（第一次可能是目录）
seg = f3[i2:i2+4000] if i2>0 else f3[i:i+4000]
for l in seg.splitlines():
    ls = l.strip()
    if re.match(r'^[一二三四五六七八九十]+、', ls):
        print("   ", ls)

# 4) 释义部分里“直销机构”定义是否已存在（丰和）
show("丰和-释义", f1, "直销机构：指", 150)
show("新动力-释义", f2, "直销机构", 150)
