# -*- coding: utf-8 -*-
"""OOXML 特征普查：funds_word/ 514 份 docx 的 XML 现实
校验设计方案 v2 §3.7 守卫清单是否完备"""
import zipfile, re, sys, io, os, glob, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

FEATS = {
 "w_ins":        ("word/document.xml", r'<w:ins[ >]'),
 "w_del":        ("word/document.xml", r'<w:del[ >]'),
 "comment_part": ("word/comments.xml", None),           # 仅查部件存在
 "comment_ref":  ("word/document.xml", r'commentRangeStart'),
 "fldChar":      ("word/document.xml", r'<w:fldChar'),
 "instrText":    ("word/document.xml", r'<w:instrText'),
 "TOC_field":    ("word/document.xml", r'TOC\s+\\'),
 "fldSimple":    ("word/document.xml", r'<w:fldSimple'),
 "sdt":          ("word/document.xml", r'<w:sdt[ >]'),
 "txbxContent":  ("word/document.xml", r'<w:txbxContent'),
 "altChunk":     ("word/document.xml", r'<w:altChunk'),
 "tbl":          ("word/document.xml", r'<w:tbl[ >]'),
 "hyperlink":    ("word/document.xml", r'<w:hyperlink'),
 "protection":   ("word/settings.xml", r'documentProtection'),
 "trackChanges": ("word/settings.xml", r'<w:trackChanges'),
 "evenAndOddHdr":("word/settings.xml", r'evenAndOddHeaders'),
}

files = sorted(glob.glob("funds_word/*.docx"))
print("docx files:", len(files))
stats = {k: {"files": 0, "occ": 0} for k in FEATS}
open_fail = []
hdr_parts = {"files_with_header": 0, "files_with_footer": 0}
no_fldchar = 0

for i, f in enumerate(files):
    name = os.path.basename(f)
    try:
        z = zipfile.ZipFile(f)
        namelist = z.namelist()
    except Exception as e:
        open_fail.append((name, str(e)[:60])); continue
    cache = {}
    def get(part):
        if part not in cache:
            try: cache[part] = z.read(part).decode("utf-8", "ignore")
            except KeyError: cache[part] = None
        return cache[part]
    for k, (part, pat) in FEATS.items():
        if pat is None:
            if part in namelist:
                stats[k]["files"] += 1; stats[k]["occ"] += 1
            continue
        xml = get(part)
        if xml is None: continue
        n = len(re.findall(pat, xml))
        if n > 0:
            stats[k]["files"] += 1; stats[k]["occ"] += n
    if any(x.startswith("word/header") for x in namelist): hdr_parts["files_with_header"] += 1
    if any(x.startswith("word/footer") for x in namelist): hdr_parts["files_with_footer"] += 1
    doc = get("word/document.xml")
    if doc is not None and "<w:fldChar" not in doc: no_fldchar += 1
    if (i+1) % 100 == 0: print(f"...{i+1}/{len(files)}", flush=True)

out = ["# OOXML 特征普查（funds_word/ docx）\n",
       "|特征|命中文件数|出现次数|", "|---|---|---|"]
for k, v in sorted(stats.items(), key=lambda x: -x[1]["files"]):
    out.append(f"|{k}|{v['files']}|{v['occ']}|")
out.append(f"\n含页眉部件: {hdr_parts['files_with_header']} 份；含页脚部件: {hdr_parts['files_with_footer']} 份")
out.append(f"document.xml 无任何 fldChar（目录域等）: {no_fldchar} 份")
out.append(f"打开失败: {len(open_fail)}")
for n, e in open_fail[:10]: out.append(f"  - {n}: {e}")
with open("_ooxml_census.md", "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))
print("DONE")
print(json.dumps({k: v for k, v in stats.items()}, ensure_ascii=False, indent=1))
print(hdr_parts, "no_fldchar:", no_fldchar)
