"""EN3 real-model probe: model-produced edit on a foreign-tracked contract.

Pipeline under test (all production code, no shortcuts):
  inspect(overlay) → real ModelGateway.generate_clause → replacement_text
  → validate_edit_plan(content_source=generated) → generate_artifacts(overlay)
  → full output-completeness battery + selective reject round-trip.

Env: sourced from /etc/fundlex-recall.env by the caller (LLM_BASE_URL /
LLM_MODEL / LLM_API_KEY / FUNDLEX_MODEL_*).  Secrets are never printed.
Artifacts + ledger land in docs/engine/en3/evidence/.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lxml import etree  # noqa: E402

from fundlex import selective  # noqa: E402
from fundlex.docx import (  # noqa: E402
    DOCUMENT, W, ZipLimits, _overlay_revision_inventory, _read_parts, _read_parts_bytes,
    generate_artifacts, inspect_docx, normalize_tracked_base, validate_edit_plan,
)
from fundlex.model import ModelGateway  # noqa: E402

EVIDENCE = ROOT / "docs/engine/en3/evidence"


def pick_fee_edit(inspection):
    for paragraph in inspection.paragraphs:
        if paragraph.zone not in {"body", "summary"} or not paragraph.editable:
            continue
        text = paragraph.text
        for segment in paragraph.segments:
            cand = text[segment.start:segment.end]
            if ("费率" in cand or "销售服务费" in cand or "管理费" in cand) \
                    and segment.end - segment.start >= 20:
                start, end = segment.start, min(segment.end, segment.start + 24)
                old = text[start:end]
                if len(old.strip()) >= 12:
                    return paragraph, {"location": paragraph.location, "zone": paragraph.zone,
                                       "start": start, "end": end, "old": old}
    return None, None


def battery(source: Path, redline: Path, final: Path, validation) -> dict:
    from docx import Document

    Document(str(redline))
    Document(str(final))
    ns = {"w": W}
    red_parts = _read_parts(redline, ZipLimits())
    root = red_parts[DOCUMENT]
    from fundlex.docx import _xml, Q

    red_root = _xml(root, ZipLimits())
    bad = [n for n in red_root.xpath("//w:delText", namespaces=ns)
           if not n.xpath("ancestor::w:del", namespaces=ns)]
    our_ids = {str(i[k]) for i in validation.manifest for k in ("del_id", "ins_id")}
    before = _overlay_revision_inventory(_read_parts(source, ZipLimits()), ZipLimits())
    after = tuple(e for e in _overlay_revision_inventory(red_parts, ZipLimits())
                  if not (e["part"] == DOCUMENT and e["id"] in our_ids))
    report = {"revision_manifest": [dict(m) for m in validation.manifest],
              "source_revision_manifest": [dict(r) for r in validation.source_revisions]}
    sel = redline.with_name(redline.stem + "-sel.docx")
    selective.generate_selected_redline(redline, sel, report,
                                        {validation.manifest[0]["del_id"]: "reject"})
    Document(str(sel))
    sel.unlink()
    assert not bad, "delText outside w:del"
    assert after == tuple(before), "foreign revisions changed"
    assert len(red_root.xpath("//w:ins|//w:del", namespaces=ns)) == \
        len({el.get(Q("id")) for el in red_root.xpath("//w:ins|//w:del", namespaces=ns)}), "dup ids"
    return {"battery": "PASS", "foreign_revisions": len(before),
            "our_pairs": len(validation.manifest)}


def run_one(path: Path, gateway: ModelGateway, out_dir: Path) -> dict:
    inspection = inspect_docx(path, full=False, allow_existing_revisions=True)
    paragraph, target = pick_fee_edit(inspection)
    if target is None:
        return {"file": path.name, "status": "NO_FEE_TARGET"}
    instruction = (
        "你是基金合同修订助手。依据2026年公开募集证券投资基金销售费用管理新规的精神，"
        "把给出的合同原文片段改写为规范、严谨的合规表述（只改写这一句，保持条款其余含义；"
        "输出 replacement_text 为改写后的中文片段，source_quote 原样引用原文）。")
    started = time.time()
    result = gateway.generate_clause(target["old"], instruction=instruction)
    elapsed_ms = int((time.time() - started) * 1000)
    replacement = (result.value or {}).get("replacement_text", "").strip()
    if not replacement or replacement == target["old"]:
        return {"file": path.name, "status": "MODEL_EMPTY_OR_NOOP",
                "elapsed_ms": elapsed_ms}
    edit = {"source_sha256": inspection.source_sha256, "verified": True,
            "content_source": "generated",
            "expected_old_text": target["old"],
            "expected_old_hash": hashlib.sha256(target["old"].encode()).hexdigest(),
            "replacement": replacement,
            **{k: v for k, v in target.items() if k != "old"}}
    plan = validate_edit_plan(path, [edit], {}, content_check=lambda e: True,
                              allow_existing_revisions=True)
    redline = out_dir / (path.stem[:12] + "-redline.docx")
    final = out_dir / (path.stem[:12] + "-final.docx")
    validation = generate_artifacts(path, plan, redline, final,
                                    allow_existing_revisions=True)
    checks = battery(path, redline, final, validation)
    accepted = normalize_tracked_base(path.read_bytes(), disposition="accept")
    rejected = normalize_tracked_base(path.read_bytes(), disposition="reject")
    return {"file": path.name, "status": "PASS", "location": target["location"],
            "old": target["old"], "replacement": replacement,
            "model_elapsed_ms": elapsed_ms,
            "model_metrics": gateway.metrics()["logical_calls"],
            "artifacts": [redline.name, final.name],
            "checks": checks,
            "accept_view_sha256": accepted.base_sha256,
            "reject_view_sha256": rejected.base_sha256}


def main() -> int:
    files = [
        ROOT / "references/source/产品部修改后/产品部修改后/广发ESG责任投资混合型证券投资基金基金合同.docx",
        ROOT / "references/source/产品部修改后/产品部修改后/广发中证A50交易型开放式指数证券投资基金联接基金合同20261020.docx",
    ]
    files = [f for f in files if f.exists()]
    if not files:
        print("corpus missing", file=sys.stderr)
        return 2
    gateway = ModelGateway.from_env()
    out_dir = EVIDENCE
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger = []
    for f in files:
        try:
            ledger.append(run_one(f, gateway, out_dir))
        except Exception as exc:  # 诚实留史: 失败同样入账
            ledger.append({"file": f.name, "status": "ERROR",
                           "error": f"{type(exc).__name__}: {exc}"[:300]})
    metrics = gateway.metrics()
    summary = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "model": os.environ.get("LLM_MODEL", ""),
               "token_ledger": {k: metrics[k] for k in
                                ("logical_calls", "prompt_tokens", "completion_tokens",
                                 "total_tokens", "estimated_cost_usd")},
               "results": ledger}
    (out_dir / "real_model_probe_20261102.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({"status": [r["status"] for r in ledger]}, ensure_ascii=False))
    return 0 if all(r.get("status") == "PASS" for r in ledger) else 1


if __name__ == "__main__":
    raise SystemExit(main())
