"""EN3 anchor-semantics evidence over the 产品部修改后 corpus (32 files).

硬实证（用户承诺口径）——对每份带痕合同逐项验证：
A. 我方编辑锚点按「接受原痕后的文本视图」定位：
   plain[start:end] == expected_old_text（_accepted_offsets 显式换算）；
   且我方 del/ins 直接挂在段落下，绝不落进任何外来 w:ins/w:del 节点中间。
B. 接受全部后 = 纯净成品：final 无任何修订标记且可打开；
   accept-all(redline) 与 final c14n 全等（引擎外独立复算）；
   final 文本 == 源接受视图文本施加编辑后的独立参照。
C. 两层痕迹独立可操作：
   C1 selective 全部拒绝我方 → 我方成对消失且原文恢复、外来清单逐项不变；
   C2 selective 默认（全接受我方）→ selected_final 与 final c14n 全等；
   w:id 命名空间隔离：我方 id⊥外来 id、奇 del/偶 ins+1 成对、全文唯一。

输出：docs/engine/en3/evidence/anchor_semantics_20261102.json
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lxml import etree  # noqa: E402

from fundlex import selective  # noqa: E402
from fundlex.docx import (  # noqa: E402
    BARRIER, DOCUMENT, Q, REVISION_TAGS, W, DocxError, ZipLimits,
    _accepted_offsets, _overlay_revision_inventory, _read_parts, _read_parts_bytes,
    _xml, generate_artifacts, inspect_docx, validate_edit_plan,
)

CORPUS = ROOT / "references/source/产品部修改后"
OUT = ROOT / "docs/engine/en3/evidence/anchor_semantics_20261102.json"
NEW = "我方锚点实证修订文本"


def _protected(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        return any(name.endswith(".xml") and b"documentProtection" in archive.read(name)
                   for name in archive.namelist())


def _candidates(inspection, limit=12):
    paragraphs = list(inspection.paragraphs)
    out = []
    for paragraph in paragraphs[len(paragraphs) // 2:] + paragraphs[:len(paragraphs) // 2]:
        if paragraph.zone not in {"body", "summary"} or not paragraph.editable:
            continue
        for segment in paragraph.segments:
            text = paragraph.text[segment.start:segment.end]
            if segment.end - segment.start >= 12 and len(text.strip()) >= 8:
                start, end = segment.end - 6, segment.end - 2
                out.append({"location": paragraph.location, "zone": paragraph.zone,
                            "start": start, "end": end, "old": paragraph.text[start:end]})
                if len(out) >= limit:
                    return out
    return out


def _plain_text(root) -> dict[str, str]:
    from fundlex.docx import _enumerate_paragraphs
    return {span.location: span.text for span in
            _enumerate_paragraphs(root, ZipLimits())[0]}


def check_file(path: Path, workdir: Path) -> dict:
    row = {"file": path.name, "protected": _protected(path)}
    if row["protected"]:
        row.update(status="BOUNDARY_PROTECTED")
        return row
    inspection = inspect_docx(path, full=False, allow_existing_revisions=True)
    candidates = _candidates(inspection)
    plan = None
    for target in candidates:
        old = target["old"]
        attempt = {"source_sha256": inspection.source_sha256, "verified": True,
                   "expected_old_text": old,
                   "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
                   "template_id": "fixed", "replacement": NEW,
                   **{k: v for k, v in target.items() if k != "old"}}
        try:
            plan = validate_edit_plan(path, [attempt], {"fixed": NEW},
                                      allow_existing_revisions=True)
            break
        except DocxError:
            continue
    if plan is None:
        row.update(status="BOUNDARY_NO_CLEAN_ANCHOR")
        return row

    edit = dict(plan.edits[0])
    redline, final = workdir / "red.docx", workdir / "fin.docx"
    validation = generate_artifacts(path, plan, redline, final,
                                    allow_existing_revisions=True)
    ns = {"w": W}
    red_root = _xml(_read_parts(redline, ZipLimits())[DOCUMENT], ZipLimits())
    fin_root = _xml(_read_parts(final, ZipLimits())[DOCUMENT], ZipLimits())
    src_root = _xml(_read_parts(path, ZipLimits())[DOCUMENT], ZipLimits())
    our_ids = {str(m[k]) for m in validation.manifest for k in ("del_id", "ins_id")}

    # A1 锚点=接受视图坐标
    paragraph = inspection.by_location(edit["location"])
    plain = paragraph.text.replace(BARRIER, "")
    s, e = _accepted_offsets(paragraph.text, int(edit["start"]), int(edit["end"]))
    a1 = plain[s:e] == edit["expected_old_text"]

    # A2 不落进外来修订节点中间：我方 wrapper 直接挂段落 + 无修订祖先
    ours = [el for el in red_root.xpath("//w:ins|//w:del", namespaces=ns)
            if el.get(Q("id"), "") in our_ids]
    a2 = bool(ours) and all(
        etree.QName(el.getparent()).localname == "p"
        and not el.xpath("ancestor::w:ins|ancestor::w:del|ancestor::w:moveFrom|ancestor::w:moveTo",
                         namespaces=ns)
        for el in ours)

    # B1 final 纯净: 整个 document 无修订标记
    b1 = not [n for n in fin_root.iter()
              if isinstance(n.tag, str) and n.tag.startswith("{" + W + "}")
              and etree.QName(n).localname in REVISION_TAGS]

    # B2 accept-all(redline) 与 final c14n 全等（独立复算）
    from fundlex.compare.revisions import _accept_revisions
    settled = etree.fromstring(etree.tostring(red_root))
    _accept_revisions(settled)
    b2 = etree.tostring(settled, method="c14n") == etree.tostring(fin_root, method="c14n")

    # B3 final 全文 == 源接受视图全文 + 编辑施加（独立参照，全文拼接序）：
    # 段落标合并只改段落边界不改字符序（B2 已 c14n 锁结构），故全文拼接比对
    # 即独立的文本正确性再推导。
    from fundlex.docx import _enumerate_paragraphs
    src_spans = _enumerate_paragraphs(src_root, ZipLimits())[0]
    proj_by_loc = {sp.location: sp.text for sp in inspection.paragraphs}
    pieces = []
    for span in src_spans:
        plain = span.text.replace(BARRIER, "")
        if span.location == edit["location"]:
            xs, xe = _accepted_offsets(proj_by_loc[span.location],
                                       int(edit["start"]), int(edit["end"]))
            plain = plain[:xs] + str(edit["replacement"]) + plain[xe:]
        pieces.append(plain)
    expected_join = "".join(pieces)
    final_join = "".join(sp.text
                         for sp in _enumerate_paragraphs(fin_root, ZipLimits())[0]
                         ).replace(BARRIER, "")
    b3 = expected_join == final_join

    # C 两层独立: 全拒我方 → 外来清单不变且我方消失; 预选全接受 → 与 final 全等
    report = {"revision_manifest": [dict(m) for m in validation.manifest],
              "source_revision_manifest": [dict(r) for r in validation.source_revisions]}
    before = _overlay_revision_inventory(_read_parts(path, ZipLimits()), ZipLimits())
    sel_rej = workdir / "selR.docx"
    selective.generate_selected_redline(redline, sel_rej, report,
                                        {m["del_id"]: "reject" for m in validation.manifest})
    sel_root_rej = _xml(_read_parts(sel_rej, ZipLimits())[DOCUMENT], ZipLimits())
    after_rej = tuple(x for x in _overlay_revision_inventory(_read_parts(sel_rej, ZipLimits()),
                                                             ZipLimits())
                      if not (x["part"] == DOCUMENT and x["id"] in our_ids))
    c1 = (after_rej == before) and not [el for el in
                                        sel_root_rej.xpath("//w:ins|//w:del", namespaces=ns)
                                        if el.get(Q("id"), "") in our_ids]
    sel_fin = workdir / "selF.docx"
    selective.generate_selected_artifact(redline, sel_fin, report, decisions={})
    sel_fin_root = _xml(_read_parts(sel_fin, ZipLimits())[DOCUMENT], ZipLimits())
    c2 = etree.tostring(sel_fin_root, method="c14n") == etree.tostring(fin_root, method="c14n")

    # id 命名空间隔离 + 成对 + 全文唯一
    foreign_ids = {el.get(Q("id"), "") for el in red_root.xpath("//w:ins|//w:del", namespaces=ns)
                   } - our_ids
    iso = not (our_ids & foreign_ids)
    parity = all(int(m["del_id"]) % 2 == 1 and int(m["ins_id"]) == int(m["del_id"]) + 1
                 for m in validation.manifest)
    all_ids = [el.get(Q("id"), "") for el in red_root.xpath("//w:ins|//w:del", namespaces=ns)]
    uniq = len(all_ids) == len(set(all_ids))

    from docx import Document
    Document(str(redline)); Document(str(final)); Document(str(sel_rej)); Document(str(sel_fin))
    checks = {"anchor_accept_view_coords": a1, "anchor_outside_foreign_nodes": a2,
              "final_pure": b1, "accept_all_equals_final_c14n": b2,
              "final_text_equals_reference": b3,
              "layer_reject_restores_foreign_intact": c1,
              "layer_default_equals_final_c14n": c2,
              "id_namespace_isolated": iso and parity and uniq}
    row.update(status="PASS" if all(checks.values()) else "FAIL",
               location=edit["location"], foreign_marks=len(before),
               checks=checks)
    return row


def main() -> int:
    files = sorted(CORPUS.rglob("*.docx"))
    rows = []
    started = time.time()
    for index, path in enumerate(files):
        with tempfile.TemporaryDirectory(prefix="en3-anchor-") as tmp:
            try:
                rows.append(check_file(path, Path(tmp)))
            except Exception as exc:
                rows.append({"file": path.name, "status": "ERROR",
                             "error": f"{type(exc).__name__}: {exc}"[:300]})
        print(f"[{index + 1}/{len(files)}] {rows[-1]['file'][:20]} -> {rows[-1]['status']}",
              flush=True)
    summary = {}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
    totals = {}
    for key in ("anchor_accept_view_coords", "anchor_outside_foreign_nodes", "final_pure",
                "accept_all_equals_final_c14n", "final_text_equals_reference",
                "layer_reject_restores_foreign_intact", "layer_default_equals_final_c14n",
                "id_namespace_isolated"):
        totals[key] = sum(1 for r in rows if r.get("checks", {}).get(key))
    OUT.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                               "elapsed_s": round(time.time() - started, 1),
                               "files": len(files), "status_counts": summary,
                               "check_totals": totals, "rows": rows},
                              ensure_ascii=False, indent=2))
    return 0 if set(summary) <= {"PASS", "BOUNDARY_PROTECTED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
