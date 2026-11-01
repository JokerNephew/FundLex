"""指引版本**原文**比对：两个指引 DOCX 源文件的确定性文本差异。

与 :mod:`fundlex.guide_diff`（解析规则的字段级 diff）互补：用户上传过多个指引
版本后，既想看「规则变了哪几条」，也想像合同比对页一样看「原文哪里改了」。

本模块直接复用合同比对的算法链（
:func:`fundlex.compare.text_diff.compare_docx` +
:func:`fundlex.compare.render.render_compare_document` /
:func:`render_merged_document`），前端三板（左右并排/合并稿）拿到即可渲染，
视觉与合同比对页一致。全程确定性、零模型调用；同两份输入永远产出同一份结果。
"""
from __future__ import annotations

from typing import Any

from .compare.render import render_compare_document, render_merged_document
from .compare.text_diff import compare_docx
from .docx import DocxError
from . import guide_store

ALGORITHM = "guide-text-diff-v1"

_TYPE_LABELS = {"modify": "修改", "insert": "新增", "delete": "删除"}


class TextDiffUnavailable(Exception):
    """一侧指引没有可比对的原文文件（内置指引或源缺失）。"""


def _version_label(version: dict[str, Any]) -> dict[str, Any]:
    return {"version_id": version["id"], "filename": version.get("filename") or "指引",
            "built_in": bool(version.get("built_in")),
            "created_at": version.get("created_at")}


def _load_source(store, owner: str, version_id: str) -> tuple[dict[str, Any], bytes]:
    # get_version 负责可见性：跨 owner 直接 KeyError（404，不泄露存在性）。
    version = guide_store.get_version(store, owner, version_id)
    if version.get("built_in"):
        # 内置指引只有冻结的规则 JSON，没有用户上传的原文 DOCX。
        raise TextDiffUnavailable("BUILTIN_SOURCE_UNAVAILABLE")
    path = guide_store.guide_source_path(store, version_id)  # KeyError -> 404
    if not path.is_file() or path.suffix.lower() != ".docx":
        raise TextDiffUnavailable("GUIDE_SOURCE_UNAVAILABLE")
    return version, path.read_bytes()


def _diff_row(item, blocks: dict[str, Any]) -> dict[str, Any]:
    old_text = "".join(span.text for span in (item.left_spans or ()))
    if not old_text and item.left:
        old_text = item.left.text
    new_text = "".join(span.text for span in (item.right_spans or ()))
    if not new_text and item.right:
        new_text = item.right.text
    anchor = item.left_anchor or item.right_anchor
    location = ""
    if anchor and anchor.block_id in blocks:
        location = blocks[anchor.block_id].location
    return {"id": item.diff_id, "type": item.type,
            "type_label": _TYPE_LABELS.get(item.type, "修改"),
            "section": item.section or "", "location": location,
            "old_text": old_text, "new_text": new_text}


def guide_text_diff(store, owner: str, version_id: str, against_id: str) -> dict[str, Any]:
    """两个可见指引版本的原文差异；``against`` 是基准（旧）版。

    Raises
    ------
    ValueError
        ``against`` 缺失（``GUIDE_DIFF_AGAINST_REQUIRED``，422）或源文件无法
        被合同比对解析器读取（``GUIDE_TEXT_DIFF_UNREADABLE``，422）。
    KeyError
        任一侧版本不可见/不存在（404）。
    TextDiffUnavailable
        内置指引或源文件缺失（404，人读码在载荷里）。
    """
    if not isinstance(against_id, str) or not against_id.strip():
        raise ValueError("GUIDE_DIFF_AGAINST_REQUIRED")
    base, left_bytes = _load_source(store, owner, against_id.strip())
    target, right_bytes = _load_source(store, owner, version_id)
    try:
        result = compare_docx(left_bytes, right_bytes,
                              left_filename=base.get("filename") or "基准版本",
                              right_filename=target.get("filename") or "对比版本")
    except DocxError as exc:
        raise ValueError("GUIDE_TEXT_DIFF_UNREADABLE") from exc
    left_blocks = {block.block_id: block for block in result.left.blocks}
    right_blocks = {block.block_id: block for block in result.right.blocks}
    blocks = left_blocks | right_blocks
    summary = result.summary
    return {"algorithm": ALGORITHM,
            "identical": summary.total == 0,
            "summary": {"diffs": summary.total, "modify": summary.modify,
                        "insert": summary.insert, "delete": summary.delete,
                        "coverage": result.coverage.to_dict()},
            "from_version": _version_label(base),
            "to_version": _version_label(target),
            "diffs": [_diff_row(item, blocks) for item in result.diffs],
            "left_html": render_compare_document(result.left, result.diffs, side="left"),
            "right_html": render_compare_document(result.right, result.diffs, side="right"),
            "merged_html": render_merged_document(result.right, result.diffs,
                                                  left_document=result.left)}
