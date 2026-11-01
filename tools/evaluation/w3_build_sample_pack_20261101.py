#!/usr/bin/env python3
"""W3 盲抽对照包生成器（总攻令验收口径：主线抽验≥10份的备料）。

分层确定性抽样 12 案，覆盖：多类别长文/缺陷案/货币市场/已改 satisfied/无服务费单类/
unknown 保留/零目标/清算条款 NA 惯例/编号伪影案/holdout 斜切。
对每案的每个 target：并排展示 标签 old_text ✂ 合同原文实际段落文本，
并附 W3 独立重验判词（old_text 是否逐字命中、冻结位置哈希是否一致）。
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import docx

ROOT = Path(__file__).resolve().parents[2]
LABELS = ROOT / "docs/evidence/labels-second-batch-20261031-v1.json"
SOURCE_ROOT = Path("/home/opencode/fundlex/funds_word")
OUT_MD = ROOT / "docs/evidence/w3-reverify/sample-pack.md"
OUT_JSON = ROOT / "docs/evidence/w3-reverify/sample-pack.json"

# 分层确定性 12 案（理由见 pack 内注记）
SAMPLE = [
    ("W2D01", "多类别A/C/F·ETF联接·长文正文+摘要（基准案）"),
    ("W2D11", "♦实伤案之一：G05引文模板混入（target本身须另验）"),
    ("W2D33", "♦实伤案之二：G09引文掺入『对应份额类别的』"),
    ("W2D52", "货币市场（明确排除类型分层，盲读裁 eligible=true+10目标）"),
    ("W2D61", "A1/A2/A3 无销售服务费多类别（G08/G11 条件不成立惯例）"),
    ("W2D65", "unknown 保留 4 条之唯一案（单一类别文本变体）"),
    ("W2D04", "零目标保留分母代表"),
    ("W2D30", "顺序清单清算条款→not_applicable 惯例代表"),
    ("W2D43", "♦『（2）』编号伪影+pi 错位案"),
    ("W2H01", "holdout 斜切代表"),
    ("W2H13", "holdout·超一年返还句引文软差异邻案"),
    ("W2H25", "♦实伤案：G14『赎回费[率]』单字脱落"),
]

norm = lambda s: re.sub(r"\s+", "", s or "")


def main() -> int:
    labels = json.load(open(LABELS))
    cases = {c["case_id"]: c for c in labels["cases"]}
    pack = []
    md = ["# W3 盲抽对照包（12 案，labels-second-batch-20261031-v1 ↔ 合同原文）",
          "",
          "生成器：`tools/evaluation/w3_build_sample_pack_20261101.py`。",
          "判词来源：W3 独立重验（docs/evidence/w3-reverify/summary.json）+ 本包现场重算。",
          ""]
    for cid, why in SAMPLE:
        c = cases[cid]
        doc = docx.Document(str(SOURCE_ROOT / c["file"]))
        paras = doc.paragraphs
        full = norm("".join(p.text for p in paras))
        entry = {"case_id": cid, "group": c["group"], "file": c["file"], "why": why,
                 "stratum": c.get("stratum"), "n_targets": len(c["targets"]),
                 "eligible": c["fund"].get("eligible"), "targets": [], "uncertain": c.get("uncertain", [])}
        md += [f"\n## {cid}（{c['group']}）{c['file']}", f"- 抽样理由：{why}",
               f"- stratum：`{c.get('stratum')}`；eligible={c['fund'].get('eligible')}；targets={len(c['targets'])}，uncertain={len(c.get('uncertain') or [])}"]
        for t in c["targets"]:
            pi = t.get("paragraph_index")
            para_txt = paras[pi].text if isinstance(pi, int) and 0 <= pi < len(paras) else ""
            ot = t.get("old_text") or ""
            ot_ok = (norm(ot) in full) if ot else (t["op"] == "append")
            sha_pos = hashlib.sha256(para_txt.encode()).hexdigest()
            pos_ok = sha_pos == t.get("paragraph_text_sha256")
            sha_ot = hashlib.sha256(norm(ot).encode()).hexdigest()
            ot_hash_ok = sha_ot == t.get("old_text_sha256")
            tid = t.get("target_id")
            entry["targets"].append({
                "target_id": tid, "rule_id": t["rule_id"], "op": t["op"],
                "paragraph_index": pi, "old_text_verbatim": ot_ok,
                "position_hash_ok": pos_ok, "old_text_hash_ok": ot_hash_ok,
                "label_old_text_excerpt": ot[:160],
                "actual_paragraph_excerpt": para_txt[:200],
                "required_text_excerpt": (t.get("required_text") or "")[:160],
            })
            verdict = "✅" if (ot_ok and pos_ok and ot_hash_ok) else "❌"
            md.append(f"\n### {cid} {tid} {t['rule_id']} op={t['op']} p={pi} {verdict}")
            md.append(f"- 判词：old_text逐字={'在' if ot_ok else '不在'}场（append特例={'是' if not ot else '否'}）·"
                      f"位置哈希={'✓' if pos_ok else '✗'}·old_hash={'✓' if ot_hash_ok else '✗'}")
            if ot:
                md.append(f"- 标签 old_text〔excerpt〕：>{ot[:160]}")
            if para_txt:
                md.append(f"- 原文 p{pi}〔excerpt〕：>{para_txt[:200]}")
            if t.get("required_text"):
                md.append(f"- 标签 required_text〔excerpt〕：>{t['required_text'][:160]}")
        pack.append(entry)
    OUT_MD.write_text("\n".join(md) + "\n")
    OUT_JSON.write_text(json.dumps({"sample_order": [s for s, _ in SAMPLE], "pack": pack},
                                   ensure_ascii=False, indent=1))
    n_bad = sum(1 for e in pack for t in e["targets"]
                if not (t["old_text_verbatim"] and t["position_hash_ok"] and t["old_text_hash_ok"]))
    print(f"sample-pack: {len(pack)} cases, {sum(len(e['targets']) for e in pack)} targets, bad={n_bad}")
    return 0 if n_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
