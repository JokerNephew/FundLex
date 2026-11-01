"""FL-D924 集成测试：修订清单配对依赖 revision_manifest，而非奇偶假设。

判词 B4b：外来修订无奇偶保证，manifest 是唯一权威配对源；同时裁决 B4a：
manifest 必须携带 rule_id/section，投影端修订清单须能呈现规则标签。
"""
from __future__ import annotations

import hashlib
import runpy
from pathlib import Path

from fundlex import docx as editor
from fundlex.html_view import project_docx

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "tests/test_docx_structures.py"))
FOREIGN = "法律部"
AUTHOR = "资金清算部"


def _revision(tag: str, revision_id: int, author: str, text: str) -> str:
    child = "w:delText" if tag == "del" else "w:t"
    return (f'<w:{tag} w:id="{revision_id}" w:author="{author}" '
            f'w:date="2026-10-01T00:00:00Z"><w:r><{child} xml:space="preserve">'
            f"{text}</{child}></w:r></w:{tag}>")


def _build(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "fixture"
    directory.mkdir(exist_ok=True)
    return HELPERS["package"](directory, body)


def _plan(source: Path, location: str, old: str, new: str) -> dict:
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    paragraph = inspection.by_location(location)
    start = paragraph.text.index(old)
    return {
        "source_sha256": inspection.source_sha256, "verified": True,
        "location": location, "zone": paragraph.zone, "start": start,
        "end": start + len(old), "expected_old_text": old,
        "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
        "template_id": "fixed", "replacement": new,
        "rule_id": "G01", "section": "申购费用",
    }


def test_foreign_even_insert_and_engine_pair_do_not_cross_pair(tmp_path):
    # 外来 ins 用偶数 id（无 del 前驱）——正是奇偶配对最容易误吞/错配的形状。
    source = _build(tmp_path,
                    "<w:p>" + _revision("ins", 2, FOREIGN, "外方补充")
                    + HELPERS["run"]("甲条款旧文乙条款旧文") + "</w:p>")
    plan = editor.validate_edit_plan(source, [_plan(source, "p0", "旧文", "新文")],
                                     {"fixed": "新文"}, allow_existing_revisions=True)
    redline = tmp_path / "redline.docx"
    final = tmp_path / "final.docx"
    validation = editor.generate_artifacts(source, plan, redline, final,
                                           allow_existing_revisions=True, author=AUTHOR)

    # B4a：manifest 条目必须携带规则标签字段
    entry = validation.manifest[0]
    assert entry["rule_id"] == "G01" and entry["section"] == "申购费用"

    report = {"revision_manifest": [dict(item) for item in validation.manifest]}
    projection = project_docx(redline, report=report)
    revisions = projection["revisions"]
    engine_pairs = [item for item in revisions if item["mapped"]]
    foreign = [item for item in revisions if not item["mapped"]]

    # B4a：引擎修订对按 manifest 分组且规则标签须出现在清单
    assert len(engine_pairs) == 1
    pair = engine_pairs[0]
    assert pair["del_id"] == 3 and pair["ins_id"] == 4
    assert pair["rule_id"] == "G01" and pair["section"] == "申购费用"
    assert "新文" in pair["after"] and "旧文" in pair["before"]

    # B4b：外来 ins id=2 独立成条，不被吞、不被错配进引擎对
    assert len(foreign) == 1
    assert "外方补充" in foreign[0]["after"] or "外方补充" in "|".join(
        foreign[0]["before"] + foreign[0]["after"])
    assert foreign[0]["revision_ids"] == [2]


def test_manifest_pairing_wins_over_parity_assumption(tmp_path):
    # 反例形状：外来修订把 id 空间用到 10，引擎对从 11 起（11/12 非奇偶关系的最小形态）。
    source = _build(tmp_path,
                    "<w:p>" + _revision("del", 10, FOREIGN, "外方删除")
                    + HELPERS["run"]("旧文") + "</w:p>")
    plan = editor.validate_edit_plan(source, [_plan(source, "p0", "旧文", "新文")],
                                     {"fixed": "新文"}, allow_existing_revisions=True)
    redline = tmp_path / "redline.docx"
    final = tmp_path / "final.docx"
    validation = editor.generate_artifacts(source, plan, redline, final,
                                           allow_existing_revisions=True, author=AUTHOR)
    report = {"revision_manifest": [dict(item) for item in validation.manifest]}
    projection = project_docx(redline, report=report)
    revisions = projection["revisions"]
    mapped = [item for item in revisions if item["mapped"]]
    assert len(mapped) == 1
    assert mapped[0]["del_id"] == 11 and mapped[0]["ins_id"] == 12
    assert mapped[0]["rule_id"] == "G01"
    # 外来 del 独立呈现
    foreign = [item for item in revisions if not item["mapped"]]
    assert len(foreign) == 1 and foreign[0]["revision_ids"] == [10]
