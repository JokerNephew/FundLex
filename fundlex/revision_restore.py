"""FL-D1133 基础档：把原合同的修订痕迹盖回红线产物（观感恢复 FL-D1115 之前）。

背景：FL-D1115 治「修订盲」=进件先接受全部修订再编辑，红线只剩 FundLex 痕迹
（FL-D1132 实证：原件王悦棋 19 条→红线 0 条）。恢复策略不动归一——
可见文字在归一前后逐字相同（接受修订只去标记），所以把**原文件里含修订
标记的段落整体盖回**红线中「文本一致且没有 FundLex 痕迹」的对应段落：

铁律（保守降级，宁缺毋错）：
1. 只盖回「可见文字逐字相同」的落位段落（difflib 对齐全文段落流）；
2. 红线段落自身带 w:ins/w:del（FundLex 动过）一律不盖（我方痕迹绝不丢失）；
3. 盖回的修订另发不撞号新 w:id（FundLex manifest 编号体系不受影响，
   选择/一键接受链路照旧只认自己的编号）；
4. 写回前硬校验：回补后全文可见文字必须与回补前逐字相同，不齐=整单放弃，
   红线保持回补前字节（事务性，绝不半残）；
5. v1 只处理 word/document.xml 正文段落；页眉页脚不盖（如实报 skipped）。

返回报告 dict（restored_paragraphs/restored_marks/skipped_*），调用方落进
任务 report 供核查。
"""

from __future__ import annotations

import copy
import difflib
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

from .docx import DOCUMENT, Q, ZipLimits, _read_parts

_REVISION_TAGS = (Q("ins"), Q("del"), Q("moveFrom"), Q("moveTo"),
                  Q("rPrChange"), Q("pPrChange"), Q("tblPrChange"),
                  Q("tcPrChange"), Q("trPrChange"))


def _visible_text(paragraph: etree._Element) -> str:
    """Word 规则可见文字：w:t 全收（含 w:ins 内），w:del 内的 w:delText 不算。"""
    chars: list[str] = []
    for node in paragraph.iter():
        if node.tag == Q("t"):
            if any(ancestor.tag == Q("del") for ancestor in node.iterancestors()):
                continue
            chars.append(node.text or "")
    return "".join(chars)


def _has_revision_marks(paragraph: etree._Element) -> bool:
    return any(paragraph.find(f".//{tag}") is not None for tag in _REVISION_TAGS[:4])


def _next_free_id(root: etree._Element) -> int:
    highest = 0
    for node in root.iter():
        raw = node.get(Q("id"))
        if raw is None:
            continue
        try:
            highest = max(highest, int(raw))
        except ValueError:
            continue
    return highest + 1000


def _remap_ids(paragraph: etree._Element, start_id: int) -> tuple[int, int]:
    """给盖回段落内的修订另发新 id；返回 (下 id, 修订条数)。"""
    marks = 0
    next_id = start_id
    for node in paragraph.iter():
        if node.tag in _REVISION_TAGS and node.get(Q("id")) is not None:
            node.set(Q("id"), str(next_id))
            next_id += 1
            if node.tag in (Q("ins"), Q("del")):
                marks += 1
    return next_id, marks


def _paragraphs(root: etree._Element) -> list[etree._Element]:
    return [node for node in root.iter(Q("p"))]


def restore_source_revisions(redline_path: str | Path, original_docx: bytes,
                             *, now_id_base: int | None = None) -> dict[str, Any]:
    """Graft original revision-marked paragraphs into the redline (in place).

    ``redline_path`` 原地改写（通过整体重打包，校验失败则不落盘）。
    """
    redline_path = Path(redline_path)
    report: dict[str, Any] = {
        "attempted": True,
        "restored_paragraphs": 0,
        "restored_marks": 0,
        "skipped_unaligned": 0,
        "skipped_marked_target": 0,
        "ids_remapped_to": None,
        "rolled_back": False,
    }
    try:
        red_parts = _read_parts(redline_path, ZipLimits())
        org_root = etree.fromstring(_read_parts_bytes(original_docx)[DOCUMENT])
        red_root = etree.fromstring(red_parts[DOCUMENT])
    except Exception as exc:  # noqa: BLE001 - 解析不通=放弃回补,红线原样交付
        report.update(rolled_back=True, reason=f"parse failed: {type(exc).__name__}")
        return report

    org_paras = _paragraphs(org_root)
    red_paras = _paragraphs(red_root)
    org_texts = [_visible_text(p) for p in org_paras]
    red_texts = [_visible_text(p) for p in red_paras]

    before_visible = "".join(red_texts)

    matcher = difflib.SequenceMatcher(None, org_texts, red_texts, autojunk=False)
    next_id = now_id_base if now_id_base is not None else _next_free_id(red_root)
    report["ids_remapped_to"] = next_id

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            report["skipped_unaligned"] += (i2 - i1)
            continue
        for offset in range(i2 - i1):
            org_p = org_paras[i1 + offset]
            red_p = red_paras[j1 + offset]
            if not _has_revision_marks(org_p):
                continue
            if _has_revision_marks(red_p):
                report["skipped_marked_target"] += 1
                continue
            grafted = copy.deepcopy(org_p)
            next_id, marks = _remap_ids(grafted, next_id)
            parent = red_p.getparent()
            parent.replace(red_p, grafted)
            report["restored_paragraphs"] += 1
            report["restored_marks"] += marks

    # 硬校验：回补后可见文字必须与回补前逐字相同（任何分支失败=整体放弃）。
    after_texts = [_visible_text(p) for p in _paragraphs(red_root)]
    if "".join(after_texts) != before_visible:
        report.update(rolled_back=True, reason="visible text drift rejected",
                      restored_paragraphs=0, restored_marks=0)
        return report
    report["ids_remapped_to"] = next_id

    if report["restored_paragraphs"] == 0:
        return report

    new_document = etree.tostring(red_root, encoding="UTF-8",
                                  xml_declaration=True, standalone=True)
    parts_out = dict(red_parts)
    parts_out[DOCUMENT] = new_document
    _rewrite_package(redline_path, parts_out)
    return report


def _read_parts_bytes(data: bytes) -> dict[str, bytes]:
    parts: dict[str, bytes] = {}
    import io as _io
    with zipfile.ZipFile(_io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if not info.is_dir():
                parts[info.filename] = archive.read(info.filename)
    return parts


def _rewrite_package(path: Path, parts: dict[str, bytes]) -> None:
    temp = path.with_suffix(path.suffix + ".restore-tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    temp.replace(path)
