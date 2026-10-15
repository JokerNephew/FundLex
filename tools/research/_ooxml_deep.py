# -*- coding: utf-8 -*-
"""深挖：7 份含文本框 / 50 份含表格的 docx —— 条款是否落在主流之外"""
import zipfile, re, sys, io, os, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

KEYS = ["申购费", "赎回费", "销售服务费", "管理费", "费率"]

def texts_of(xml):
    return "".join(re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml, re.S))

tb_files, tbl_files = [], []
for f in sorted(glob.glob("funds_word/*.docx")):
    z = zipfile.ZipFile(f)
    try: xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except KeyError: continue
    name = os.path.basename(f)
    if "<w:txbxContent" in xml: tb_files.append((f, name, xml))
    if "<w:tbl" in xml: tbl_files.append((f, name, xml))

print("### 文本框文件 (%d)" % len(tb_files))
for f, name, xml in tb_files:
    boxes = re.findall(r'<w:txbxContent>(.*?)</w:txbxContent>', xml, re.S)
    joined = "".join(texts_of(b) for b in boxes)
    joined = re.sub(r'\s+', '', joined)
    hits = [k for k in KEYS if k in joined]
    print(f"- {name}")
    print(f"  文本框{len(boxes)}个 总字数{len(joined)} 关键词命中:{hits}")
    print(f"  内容样例: {joined[:120]}")

print("\n### 表格文件 (%d) —— 表格内是否含费率类条款" % len(tbl_files))
tbl_with_fee = []
for f, name, xml in tbl_files:
    tbls = re.findall(r'<w:tbl[ >].*?</w:tbl>', xml, re.S)
    joined = "".join(texts_of(t) for t in tbls)
    joined = re.sub(r'\s+', '', joined)
    hits = [k for k in KEYS if k in joined]
    if hits:
        tbl_with_fee.append((name, len(tbls), hits, joined[:100]))
print("表格内含费率/费用关键词的文件: %d" % len(tbl_with_fee))
for name, n, hits, sample in tbl_with_fee[:20]:
    print(f"- {name} 表{n}个 {hits}")
    print(f"  {sample}")

print("\n### 表格文件名单（全部 %d 份）" % len(tbl_files))
for f, name, xml in tbl_files:
    print("-", name)
