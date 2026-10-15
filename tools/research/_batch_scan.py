# -*- coding: utf-8 -*-
"""全量 514 份快速扫描：为审查提供定量证据"""
import fitz, re, sys, io, os, json, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

files = sorted(glob.glob("funds/*.pdf"))
print("total files:", len(files))

stats = {
    "already_modified_marker": 0,   # 含“通过直销机构申购本基金”
    "old_clause_shen_gou_fei": 0,   # 含“申购费用由投资人承担”
    "has_tiao_di_shu_hui": 0,       # 调低赎回费率
    "has_bei_an": 0,                # 并报中国证监会备案
    "has_hu_xiang_zhuan_huan": 0,   # 不得互相转换
    "has_floating": 0,              # 浮动管理费
    "has_sales_service": 0,         # 销售服务费
    "has_chao_e_guan_li": 0,        # 超额管理费
    "has_huo_you_guan_li": 0,       # 或有管理费
    "money_fund": 0, "etf": 0, "reit": 0, "qdii": 0, "fof": 0, "lian_jie": 0, "feng_bi": 0,
    "open_fail": 0,
}
class_pat = re.compile(r'称为([A-Z])类基金份额')
class_sets = {}
both_marker = []       # 同时含旧条款与新规标志（部分修改？）
open_fails = []

for i, f in enumerate(files):
    try:
        doc = fitz.open(f)
        flat = ""
        for p in doc:
            flat += p.get_text()
        doc.close()
    except Exception as e:
        stats["open_fail"] += 1; open_fails.append((f, str(e))); continue
    flat = re.sub(r'\s+', '', flat)
    name = os.path.basename(f)
    new_m = "通过直销机构申购本基金" in flat
    old_m = "申购费用由投资人承担" in flat
    if new_m: stats["already_modified_marker"] += 1
    if old_m: stats["old_clause_shen_gou_fei"] += 1
    if new_m and old_m: both_marker.append(name)
    if "调低赎回费率" in flat: stats["has_tiao_di_shu_hui"] += 1
    if "并报中国证监会备案" in flat: stats["has_bei_an"] += 1
    if "不得互相转换" in flat: stats["has_hu_xiang_zhuan_huan"] += 1
    if "浮动管理费" in flat: stats["has_floating"] += 1
    if "销售服务费" in flat: stats["has_sales_service"] += 1
    if "超额管理费" in flat: stats["has_chao_e_guan_li"] += 1
    if "或有管理费" in flat: stats["has_huo_you_guan_li"] += 1
    if "货币市场基金" in name: stats["money_fund"] += 1
    if "交易型开放式" in name and "联接" not in name: stats["etf"] += 1
    if "不动产" in name: stats["reit"] += 1
    if "QDII" in name: stats["qdii"] += 1
    if "FOF" in name: stats["fof"] += 1
    if "联接" in name: stats["lian_jie"] += 1
    if "封闭式" in name or "定期开放" in name or "持有期" in name: stats["feng_bi"] += 1
    letters = tuple(sorted(set(class_pat.findall(flat))))
    class_sets[letters] = class_sets.get(letters, 0) + 1
    if (i+1) % 100 == 0:
        print(f"...{i+1}/{len(files)}", flush=True)

print("\n===== STATS =====")
print(json.dumps(stats, ensure_ascii=False, indent=1))
print("\n===== 份额类别组合分布 (top20) =====")
for k, v in sorted(class_sets.items(), key=lambda x: -x[1])[:20]:
    print(f"  {k}: {v}")
print("\n===== 新旧标志同时命中的合同 (%d) =====" % len(both_marker))
for n in both_marker[:15]: print("  ", n)
print("\n===== 打开失败 (%d) =====" % len(open_fails))
for n, e in open_fails[:10]: print("  ", n, e[:80])
