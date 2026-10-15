# -*- coding: utf-8 -*-
"""M0 裁决证据包 + 条款变体普查（514 份 PDF，单次遍历）
产出：
  _m0_evidence.md   —— 附录A 各裁决项的合同级证据
  _variant_census.md —— 15 组规则候选在全语料的命中分布（L1精确/L2模糊/缺失）
"""
import fitz, re, sys, io, os, glob, json
from difflib import SequenceMatcher
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def norm(s):
    s = re.sub(r'\s+', '', s)
    for a, b in [('（','('),('）',')'),('，',','),('。','.'),('；',';'),('：',':'),('％','%'),('、',','),('“','"'),('”','"')]:
        s = s.replace(a, b)
    return s

# ---------- 规则候选（指引 v4，归一化前原文） ----------
RULES = {
 "R01释义类别定义": ["基金份额类别：本基金将基金份额分为A类和C类不同的类别。"],
 "R03调低赎回费率": ["调低赎回费率"],
 "R03删备案": ["并报中国证监会备案"],
 "R04不得转换": ["除非基金管理人在未来条件成熟后另行公告开通相关业务，本基金不同基金份额类别之间不得互相转换。"],
 "R05申购费率句": ["本基金的申购费率由基金管理人决定，并在招募说明书中列示。"],
 "R06赎回费率句": ["本基金的赎回费率由基金管理人决定，并在招募说明书中列示。"],
 "R07单类别申购费": ["申购费用由投资人承担，不列入基金财产。"],
 "R07多类别条款1": ["本基金A类基金份额的申购费用由投资人承担，不列入基金财产；C类基金份额不收取申购费用。"],
 "R08赎回费描述1": ["赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示。"],
 "R08赎回费描述2": ["赎回费用归入基金财产的比例依照相关法律法规设定，具体见招募说明书的规定"],
 "R09长条款": ["本基金的申购费率、申购份额具体的计算方法、赎回费率、赎回金额具体的计算方法和收费方式由基金管理人根据基金合同的规定确定"],
 "R09删7日句": ["本基金对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并将上述赎回费全额计入基金财产"],
 "R10促销表述1": ["基金管理人可以适当调低基金申购费率和赎回费率"],
 "R10促销表述2": ["基金管理人可以适当调低基金申购费率、赎回费率和转换费率"],
 "R10促销表述3": ["基金管理人可以适当调低基金申购费率、赎回费率、转换费率和销售服务费率"],
 "R11删支付句": ["销售服务费每日计提，按月支付"],
 "R12删用途句": ["销售服务费主要用于支付销售机构佣金"],
 "R13收益分配句": ["不收取销售服务费，而C类基金份额收取销售服务费"],
 "R14R15清算句": ["依据基金财产清算的分配方案"],
}
NRULES = {k: [norm(x) for x in v] for k, v in RULES.items()}

# 幂等 fingerprint（新规文本特征）
FINGERPRINTS = {
 "FP_直销申购": "投资者通过直销机构(含基金管理人及其销售子公司",
 "FP_直销申购简": "通过直销机构申购本基金",
 "FP_持有超一年": "持续持有期限超过一年的,不再继续收取销售服务费",
 "FP_随赎回款": "随赎回款(或清算款)一并返还",
 "FP_赎回费全额": "赎回费用全额计入基金财产",
 "FP_扣除或加上": "扣除或加上相应的费用",
 "FP_调低销售服务费率": "调低销售服务费率",
 "FP_费用收取不同": "费用收取不同",
 "FP_销售服务费如有": "销售服务费(如有)",
}
NFP = {k: norm(v) for k, v in FINGERPRINTS.items()}

def fund_type(name):
    if "不动产" in name: return "reit"
    if "货币市场" in name: return "money_market"
    if "联接" in name: return "etf_feeder"
    if "交易型开放式" in name: return "etf"
    if "QDII" in name: return "qdii"
    if "基金中基金" in name: return "fof"
    if "封闭式" in name: return "closed"
    return "open_general"

files = sorted(glob.glob("funds/*.pdf"))
N = len(files)

# 聚合器
rule_exact = {k: 0 for k in RULES}          # 至少1处精确命中
rule_exact_files = {k: [] for k in RULES}
fp_files = {k: [] for k in FINGERPRINTS}
type_stats = {}                              # fund_type -> dict(rule->exact命中数)
mixed_fp_old = []                            # 新旧并存
summary_dup = {"R14R15清算句":0,"R08赎回费描述1":0,"R12删用途句":0,"R11删支付句":0}
bei_an_ctx = {"份额类别语境":0, "估值偏差语境":0, "其他语境":0}
fuzzy_dist = {k: {"exact":0, "fuzzy_092":0, "fuzzy_080":0, "absent":0} for k in RULES}

FUZZY_RULES = ["R07单类别申购费","R08赎回费描述1","R09长条款","R10促销表述1","R12删用途句","R05申购费率句"]

for i, f in enumerate(files):
    name = os.path.basename(f)
    ft = fund_type(name)
    doc = fitz.open(f)
    paras = []
    for p in doc:
        paras.extend(p.get_text().splitlines())
    doc.close()
    raw = "".join(paras)
    flat = norm(raw)
    nparas = [norm(x) for x in paras if len(norm(x)) >= 6]

    # 1) 规则候选精确命中
    hits = {}
    for k, cands in NRULES.items():
        c = sum(flat.count(x) for x in cands)
        hits[k] = c
        if c > 0:
            rule_exact[k] += 1
            rule_exact_files[k].append(name)
    ts = type_stats.setdefault(ft, {k: 0 for k in RULES} | {"_n": 0})
    ts["_n"] += 1
    for k in RULES:
        if hits[k] > 0: ts[k] += 1

    # 2) fingerprint
    fph = [k for k, v in NFP.items() if v in flat]
    for k in fph: fp_files[k].append(name)
    if fph and hits["R07单类别申购费"] > 0:
        mixed_fp_old.append(name)

    # 3) 摘要双命中（出现>=2次即视为正文+摘要重复，供 A1）
    for k in summary_dup:
        if hits[k] >= 2: summary_dup[k] += 1

    # 4) 备案语境分类（A9）
    for m in re.finditer("并报中国证监会备案", flat):
        ctx = flat[max(0, m.start()-80):m.start()]
        if "偏差" in ctx: bei_an_ctx["估值偏差语境"] += 1
        elif ("公告" in ctx and "调整" in ctx) or "需及时公告" in ctx: bei_an_ctx["份额类别语境"] += 1
        else: bei_an_ctx["其他语境"] += 1

    # 5) 模糊分布（重点规则，抽样段落比对）
    for k in FUZZY_RULES:
        cand = NRULES[k][0]
        if norm(RULES[k][0]) in flat:
            fuzzy_dist[k]["exact"] += 1; continue
        best = 0.0
        Lc = len(cand)
        for para in nparas:
            if abs(len(para) - Lc) > Lc:  # 长度差超过候选长度才跳过
                continue
            sm = SequenceMatcher(None, cand, para)
            if sm.real_quick_ratio() > best and sm.quick_ratio() > best:
                r = sm.ratio()
                if r > best: best = r
        if best >= 0.92: fuzzy_dist[k]["fuzzy_092"] += 1
        elif best >= 0.80: fuzzy_dist[k]["fuzzy_080"] += 1
        else: fuzzy_dist[k]["absent"] += 1

    if (i+1) % 50 == 0:
        print(f"...{i+1}/{N}", flush=True)

# ---------- 输出 ----------
out = []
out.append("# M0 裁决证据包（514 份全量）\n")
out.append("## A2/A3 已改合同指纹命中分布")
for k, v in fp_files.items():
    out.append(f"- {k}: {len(v)} 份")
out.append(f"\n新旧并存（fingerprint命中 且 旧R07候选命中）: {len(mixed_fp_old)} 份")
for n in mixed_fp_old[:30]: out.append(f"  - {n}")

out.append("\n## A4 各基金类型 × 规则候选精确命中率")
hdr = ["fund_type","n"] + list(RULES.keys())
out.append("|" + "|".join(hdr) + "|")
out.append("|" + "|".join(["---"]*len(hdr)) + "|")
for ft, ts in sorted(type_stats.items(), key=lambda x:-x[1]["_n"]):
    row = [ft, str(ts["_n"])] + [f'{ts[k]}/{ts["_n"]}' for k in RULES]
    out.append("|" + "|".join(row) + "|")

out.append("\n## A1 正文+摘要双命中（候选出现≥2次）的合同数")
for k, v in summary_dup.items(): out.append(f"- {k}: {v} 份")

out.append("\n## A9 '并报中国证监会备案'语境分布（全部出现位置）")
for k, v in bei_an_ctx.items(): out.append(f"- {k}: {v} 处")

out.append("\n## 规则候选精确命中合同数（全语料）")
for k in RULES: out.append(f"- {k}: {rule_exact[k]} 份")

with open("_m0_evidence.md", "w", encoding="utf-8") as fo:
    fo.write("\n".join(out))

vc = ["# 条款变体普查：重点规则的命中层级分布（L1精确 / L2≥0.92 / L2 0.80–0.92 / 缺失）\n"]
vc.append("|规则|L1精确|L2高相似|L2中相似|缺失|")
vc.append("|---|---|---|---|---|")
for k in FUZZY_RULES:
    d = fuzzy_dist[k]
    vc.append(f"|{k}|{d['exact']}|{d['fuzzy_092']}|{d['fuzzy_080']}|{d['absent']}|")
with open("_variant_census.md", "w", encoding="utf-8") as fo:
    fo.write("\n".join(vc))

print("DONE")
print(json.dumps({"fuzzy": fuzzy_dist, "summary_dup": summary_dup, "bei_an": bei_an_ctx}, ensure_ascii=False, indent=1))
