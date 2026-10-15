# -*- coding: utf-8 -*-
"""变体库：枚举促销条款/7日赎回费句/赎回费归属句的真实写法"""
import fitz, re, sys, io, os, glob, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def norm(s):
    s = re.sub(r'\s+', '', s)
    return s

files = sorted(glob.glob("funds/*.pdf"))
promo = collections.Counter()
seven = collections.Counter()
shuhui = collections.Counter()

for f in files:
    doc = fitz.open(f)
    flat = norm("".join(p.get_text() for p in doc))
    doc.close()
    # 促销句：取"适当调低"后至句号
    for m in re.finditer(r'适当调低([^。]{0,60}。)', flat):
        promo["适当调低" + m.group(1)] += 1
    # 7日句：取"持续持有期少于7"前后窗口
    for m in re.finditer(r'(.{0,25}持续持有期少于7[^。]{0,80}。)', flat):
        seven[m.group(1)] += 1
    # 赎回费归属句
    for m in re.finditer(r'(赎回费用归入基金财产[^。]{0,60}。)', flat):
        shuhui[m.group(1)] += 1

def dump(title, c, n=25):
    print(f"\n### {title} —— {len(c)} 种变体")
    for s, cnt in c.most_common(n):
        print(f"  x{cnt:3d}  {s[:110]}")

dump("促销条款（适当调低…）", promo)
dump("7日赎回费句", seven)
dump("赎回费归属句", shuhui)
