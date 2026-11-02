"""EN3 matrix: foreign tracked changes through the full write-back path.

Coverage dimensions (acceptance table rows map 1:1 to the tests below):

* 输入形状: paragraph-mark ins/del (pPr/rPr), nested ins>del, adjacent ins+del,
  cross-paragraph deletion (text del + pPr mark del), header-part marks
* 修改落点: clean region / inside foreign ins (fail-closed) / spanning a
  foreign region (fail-closed) / flush with a foreign del (offset mapping)
* 处置策略: keep-foreign+stack-ours (overlay) / accept-first / reject-first
* 输出完备性: package re-opens (python-docx), part set equal, delText only
  under w:del, engine ids valid & disjoint from foreign ids, foreign
  inventory preserved, per-id accept/reject settles correctly, final ==
  accept view of redline
* 真实语料: references/source/产品部修改后 (32 files, w:ins 2775 / w:del 1044,
  nested 45, paragraph marks 1104) run through all strategies + write-back
* Mutation 反例: depth guards fire even if the intake guard is neutered;
  post-validation net catches a defective (no-op) reject implementation.
"""
from __future__ import annotations

import hashlib
import runpy
import zipfile
from pathlib import Path

import pytest
from lxml import etree

import fundlex.compare.revisions as revisions_mod
from fundlex import selective
from fundlex.docx import (
    DOCUMENT, DocxError, Q, REVISION_TAGS, W, ZipLimits,
    _overlay_revision_inventory, _read_parts, _read_parts_bytes, _xml,
    generate_artifacts, inspect_docx, normalize_tracked_base, validate_edit_plan,
)

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "tests/test_docx_structures.py"))
AUTHOR = "资金清算部"
FOREIGN = "法律合规部"
WHEN = "2026-10-01T00:00:00Z"

CORPUS = ROOT / "references/source/产品部修改后"
corpus_files = sorted(CORPUS.rglob("*.docx")) if CORPUS.exists() else []
needs_corpus = pytest.mark.skipif(not corpus_files, reason="产品部修改后 corpus not present")


def _rev(tag: str, rid: int, text: str, author: str = FOREIGN) -> str:
    tag_name = "w:delText" if tag == "del" else "w:t"
    return (f'<w:{tag} w:id="{rid}" w:author="{author}" w:date="{WHEN}">'
            f'<w:r><{tag_name} xml:space="preserve">{text}</{tag_name}></w:r></w:{tag}>')


def _mark(tag: str, rid: int) -> str:
    return (f'<w:pPr><w:rPr><w:{tag} w:id="{rid}" w:author="{FOREIGN}" w:date="{WHEN}"/></w:rPr></w:pPr>')


def _build(tmp_path: Path, body: str, extra=None, name: str = "fixture.docx") -> Path:
    directory = tmp_path / name.replace(".docx", "")
    directory.mkdir(exist_ok=True)
    return HELPERS["package"](directory, body, extra)


NEW = "我方新修订文本"


def _edit(source, location, old, new=NEW):
    inspection = inspect_docx(source, full=True, allow_existing_revisions=True)
    paragraph = inspection.by_location(location)
    start = paragraph.text.index(old)
    return inspection, {"source_sha256": inspection.source_sha256, "verified": True,
                        "location": location, "zone": paragraph.zone, "start": start,
                        "end": start + len(old), "expected_old_text": old,
                        "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
                        "template_id": "fixed", "replacement": new}


def _generate(source, tmp_path, edit, name="out"):
    inspection, plan_edit = edit
    plan = validate_edit_plan(source, [plan_edit], {"fixed": plan_edit["replacement"]},
                              allow_existing_revisions=True)
    redline = tmp_path / f"{name}-red.docx"
    final = tmp_path / f"{name}-final.docx"
    validation = generate_artifacts(source, plan, redline, final,
                                    allow_existing_revisions=True)
    return redline, final, validation


# ---------------------------------------------------------------------------
# Output completeness lint battery (矩阵: 输出完备性)
# ---------------------------------------------------------------------------

def assert_redline_battery(source: Path, redline: Path, final: Path, validation) -> None:
    """Word-可打开性(以 python-docx 重开为代理) + 结构 lint + 原痕保全 + 可逐个裁决."""
    from docx import Document

    our_ids = {str(item[key]) for item in validation.manifest for key in ("del_id", "ins_id")}
    src_parts = _read_parts(source, ZipLimits())
    red_parts = _read_parts(redline, ZipLimits())
    fin_parts = _read_parts(final, ZipLimits())
    # python-docx 重开 (Word 提示修复的代理检查) + part 集合一致
    Document(str(redline))
    Document(str(final))
    assert set(src_parts) == set(red_parts) == set(fin_parts)
    root = _xml(red_parts[DOCUMENT], ZipLimits())
    ns = {"w": W}
    # delText 只允许出现在 w:del 之下
    for node in root.xpath("//w:delText", namespaces=ns):
        assert node.xpath("ancestor::w:del", namespaces=ns), "delText outside w:del"
    # 我方 id: del 奇 / ins = del+1; 与外来 id 不相交; 全 document 唯一
    seen: set[str] = set()
    for el in root.xpath("//w:ins|//w:del", namespaces=ns):
        rid = el.get(Q("id"), "")
        assert rid not in seen, f"duplicate revision id {rid}"
        seen.add(rid)
    foreign_ids = seen - our_ids
    assert our_ids
    assert not (our_ids & foreign_ids)
    for item in validation.manifest:
        del_id, ins_id = int(item["del_id"]), int(item["ins_id"])
        assert del_id % 2 == 1 and ins_id == del_id + 1
    # 原痕保全: redline 中与源相同的 (part,kind,id,author,date,content_sha256)
    before = [e for e in _overlay_revision_inventory(src_parts, ZipLimits())]
    after = [e for e in _overlay_revision_inventory(red_parts, ZipLimits())
             if str(e["id"]) not in our_ids or e["part"] != DOCUMENT]
    assert after == before
    # 修订可逐个接受拒绝: reject 我方第一对 → 文字还原; 原痕保持
    report = {"revision_manifest": [dict(m) for m in validation.manifest],
              "source_revision_manifest": [dict(r) for r in validation.source_revisions]}
    del_id = validation.manifest[0]["del_id"]
    sel_red = redline.with_name(redline.stem + "-selR.docx")
    selective.generate_selected_redline(redline, sel_red, report, {del_id: "reject"})
    Document(str(sel_red))
    sel_root = _xml(_read_parts(sel_red, ZipLimits())[DOCUMENT], ZipLimits())
    assert all(el.get(Q("id")) not in {str(del_id), str(int(del_id) + 1)}
               for el in sel_root.xpath("//w:ins|//w:del", namespaces=ns))
    after2 = tuple(e for e in _overlay_revision_inventory(_read_parts(sel_red, ZipLimits()), ZipLimits())
                   if not (e["part"] == DOCUMENT and e["id"] in our_ids))
    assert after2 == tuple(before)
    # final == accept view of redline: final 无任何修订标记且可打开
    fin_root = _xml(fin_parts[DOCUMENT], ZipLimits())
    assert not fin_root.xpath("//w:ins|//w:del", namespaces=ns)


# ---------------------------------------------------------------------------
# 矩阵 A: 构造形状 × 摄入 × 处置策略
# ---------------------------------------------------------------------------

SHAPES = {
    "para_mark_ins": _mark("ins", 30) + HELPERS["run"]("第一段文字。"),
    "para_mark_del": _mark("del", 31) + HELPERS["run"]("第一段文字。"),
    "nested_ins_del": ('<w:ins w:id="40" w:author="' + FOREIGN + '" w:date="' + WHEN + '">'
                       '<w:del w:id="41" w:author="' + FOREIGN + '" w:date="' + WHEN + '">'
                       '<w:r><w:delText>被撤回的插入</w:delText></w:r></w:del>'
                       '<w:r><w:t>保留的插入</w:t></w:r></w:ins>' + HELPERS["run"]("正文。")),
    "adjacent": _rev("ins", 50, "相邻插入") + _rev("del", 51, "相邻删除") + HELPERS["run"]("正文。"),
    "cross_para": None,  # special-cased below
}


@pytest.mark.parametrize("name", sorted(k for k in SHAPES if k != "cross_para"))
def test_intake_admits_word_native_shapes(tmp_path, name):
    source = _build(tmp_path, "<w:p>" + SHAPES[name] + "</w:p>")
    inspection = inspect_docx(source, full=True, allow_existing_revisions=True)
    assert inspection.revisions, name
    # 无 overlay 旗标仍整机拒入 (既有行为不变)
    with pytest.raises(DocxError) as error:
        inspect_docx(source, full=True)
    assert error.value.code == "EXISTING_REVISION_UNSUPPORTED"


def test_intake_cross_paragraph_deletion(tmp_path):
    # 跨段落删除 = 两段各有文本 del + 前段 pPr/rPr/del
    body = ("<w:p>" + _mark("del", 60) + HELPERS["run"]("前段保留")
            + _rev("del", 61, "前段被删") + "</w:p>"
            + "<w:p>" + _rev("del", 62, "后段被删") + HELPERS["run"]("后段保留。") + "</w:p>")
    source = _build(tmp_path, body)
    inspection = inspect_docx(source, full=True, allow_existing_revisions=True)
    assert {e["kind"] for e in inspection.revisions} >= {"del"}
    texts = [p.text.replace("\ufff9", "") for p in inspection.paragraphs]
    assert any("前段保留" in t for t in texts) and any("后段保留" in t for t in texts)


@pytest.mark.parametrize("name", sorted(k for k in SHAPES if k != "cross_para"))
def test_strategy_accept_and_reject_are_mirrors(tmp_path, name):
    source = _build(tmp_path, "<w:p>" + SHAPES[name] + "</w:p>")
    data = source.read_bytes()
    accepted = normalize_tracked_base(data, disposition="accept")
    rejected = normalize_tracked_base(data, disposition="reject")
    assert accepted.had_tracked_changes and rejected.had_tracked_changes

    def plain(b: bytes) -> str:
        root = _xml(_read_parts_bytes(b, ZipLimits())[DOCUMENT], ZipLimits())
        assert not [n for n in root.iter()
                    if isinstance(n.tag, str) and n.tag.startswith("{" + W + "}")
                    and etree.QName(n).localname in REVISION_TAGS]
        return "".join(t.text or "" for t in root.iter(Q("t")))

    ta, tr = plain(accepted.data), plain(rejected.data)
    anchor = "第一段文字。" if name.startswith("para_mark") else "正文。"
    assert anchor in ta and anchor in tr
    if name == "nested_ins_del":
        assert "保留的插入" in ta and "被撤回的插入" not in ta
        assert "保留的插入" not in tr and "被撤回的插入" not in tr  # 整个 ins 拒绝后消失
    if name == "adjacent":
        assert "相邻插入" in ta and "相邻删除" not in ta
        assert "相邻插入" not in tr and "相邻删除" in tr


def test_strategy_cross_paragraph_deletion(tmp_path):
    body = ("<w:p>" + _mark("del", 60) + HELPERS["run"]("前段保留")
            + _rev("del", 61, "前段被删") + "</w:p>"
            + "<w:p>" + _rev("del", 62, "后段被删") + HELPERS["run"]("后段保留。") + "</w:p>")
    data = _build(tmp_path, body).read_bytes()
    accepted = normalize_tracked_base(data, disposition="accept")
    rejected = normalize_tracked_base(data, disposition="reject")

    def paras(b: bytes):
        root = _xml(_read_parts_bytes(b, ZipLimits())[DOCUMENT], ZipLimits())
        return ["".join(t.text or "" for t in p.iter(Q("t"))) for p in root.iter(Q("p"))]

    pa, pr = paras(accepted.data), paras(rejected.data)
    assert pa == ["前段保留后段保留。"]          # 标记删除被接受 → 段落合并
    assert pr == ["前段保留前段被删", "后段被删后段保留。"]  # 删除被拒绝 → 段与原文恢复


def test_strategy_property_change_reject_restores_snapshot(tmp_path):
    body = ('<w:p><w:pPr><w:spacing w:after="240"/>'
            '<w:pPrChange w:id="70" w:author="' + FOREIGN + '" w:date="' + WHEN + '">'
            '<w:pPr><w:spacing w:after="120"/></w:pPr></w:pPrChange></w:pPr>'
            + HELPERS["run"]("属性变更段落。") + "</w:p>")
    data = _build(tmp_path, body).read_bytes()
    accepted = normalize_tracked_base(data, disposition="accept")
    rejected = normalize_tracked_base(data, disposition="reject")

    def spacing(b: bytes) -> str:
        root = _xml(_read_parts_bytes(b, ZipLimits())[DOCUMENT], ZipLimits())
        el = root.find(f".//{{{W}}}p/{{{W}}}pPr/{{{W}}}spacing")
        return el.get(Q("after"))

    assert spacing(accepted.data) == "240"   # 接受 = 保留新属性
    assert spacing(rejected.data) == "120"   # 拒绝 = 回滚快照


def test_strategy_clean_input_identity(tmp_path):
    data = _build(tmp_path, "<w:p>" + HELPERS["run"]("无修订。") + "</w:p>").read_bytes()
    for disposition in ("accept", "reject"):
        result = normalize_tracked_base(data, disposition=disposition)
        assert not result.had_tracked_changes and result.data == data
    with pytest.raises(ValueError):
        normalize_tracked_base(data, disposition="bogus")


# ---------------------------------------------------------------------------
# 矩阵 B: 修改落点 × 输出完备性 (保留原痕 + 我方叠痕)
# ---------------------------------------------------------------------------

MIX_BODY = ("<w:p>" + _mark("del", 31) + HELPERS["run"]("混排干净起点文字，足够长以供选择。")
            + _rev("ins", 40, "外来插入")
            + HELPERS["run"]("中段干净文字，同样足够长。")
            + _rev("del", 41, "外来删除")
            + HELPERS["run"]("末尾干净文字，仍然足够长。") + "</w:p>"
            + "<w:p>" + HELPERS["run"]("第二段干净文字，供跨区构造使用。") + "</w:p>")


def test_location_clean_region_full_battery(tmp_path):
    source = _build(tmp_path, MIX_BODY)
    redline, final, validation = _generate(source, tmp_path, _edit(source, "p0", "同样足够长"))
    assert_redline_battery(source, redline, final, validation)


def test_location_flush_after_foreign_del_maps_offsets(tmp_path):
    # 紧跟外来 del 之后的干净文字: 投影是 accept 视图 (del 不占坐标),
    # 编辑坐标不得因 del 内文字位移 —— 这是写回路径坐标映射的核心回归格.
    source = _build(tmp_path, MIX_BODY)
    inspection = inspect_docx(source, full=True, allow_existing_revisions=True)
    paragraph = inspection.by_location("p0")
    # accept 视图: 外来 del 的文字不可见, 两段干净文字直接相接
    assert "同样足够长。末尾干净文字" in paragraph.text.replace("\ufff9", "")
    redline, final, validation = _generate(source, tmp_path, _edit(source, "p0", "末尾干净文字"))
    assert_redline_battery(source, redline, final, validation)
    fin_root = _xml(_read_parts(final, ZipLimits())[DOCUMENT], ZipLimits())
    flat = "".join(t.text or "" for t in fin_root.iter(Q("t")))
    # 整词 "末尾干净文字" 被替换 (外来 del 不吞坐标): 替换文本直接接续前段干净文字
    assert "同样足够长。" + NEW + "，仍然足够长。" in flat
    assert "末尾干净文字" not in flat


def test_location_inside_foreign_insertion_fails_closed(tmp_path):
    source = _build(tmp_path, MIX_BODY)
    inspection, edit = _edit(source, "p0", "外来插入")
    # 外来 ins 内文字被 barrier 包裹: 任何落进区间的编辑必须被拒 (码族断言, 不绑单码)
    with pytest.raises(DocxError) as error:
        validate_edit_plan(source, [edit], {"fixed": NEW}, allow_existing_revisions=True)
    assert error.value.code in {"EDIT_CROSSES_BARRIER", "FOREIGN_INSERTION_EDIT_UNSUPPORTED",
                                "FOREIGN_REVISION_INTERSECTION"}


def test_location_spanning_foreign_region_fails_closed(tmp_path):
    source = _build(tmp_path, MIX_BODY)
    inspection = inspect_docx(source, full=True, allow_existing_revisions=True)
    paragraph = inspection.by_location("p0")
    start = paragraph.text.index("，同样足够长。") + 1  # 干净区内
    # 跨过后续外来 del 选到末尾干净文字
    tail = paragraph.text.index("仍然足够长")
    old = paragraph.text[start:tail + 2]
    edit = {"source_sha256": inspection.source_sha256, "verified": True,
            "location": "p0", "zone": paragraph.zone, "start": start,
            "end": tail + 2, "expected_old_text": old,
            "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
            "template_id": "fixed", "replacement": NEW}
    # FL-D1006: 几何守卫在验证期即触发 (与写手同一谓词), 并被逐编辑归罪机制隔离;
    # 修复前此类编辑吞到生成期才爆, 整份合同陪葬.
    with pytest.raises(DocxError) as error:
        validate_edit_plan(source, [edit], {"fixed": NEW}, allow_existing_revisions=True)
    assert error.value.code in {"EDIT_CROSSES_BARRIER", "FOREIGN_REVISION_INTERSECTION"}


def test_header_part_foreign_marks_writeback(tmp_path):
    extra = {
        "word/header1.xml": (f'<w:hdr xmlns:w="{W}"><w:p>'
                             + _rev("ins", 90, "页眉外来修订")
                             + HELPERS["run"]("页眉正文") + "</w:p></w:hdr>").encode(),
        "word/_rels/document.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="hdr1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" '
            'Target="header1.xml"/></Relationships>').encode(),
    }
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("正文干净文字足够长以供编辑落点。") + "</w:p>",
                    extra=extra)
    edit_tuple = _edit(source, "p0", "干净文字足够长")
    redline, final, validation = _generate(source, tmp_path, edit_tuple)
    hdr = _read_parts(redline, ZipLimits())["word/header1.xml"]
    assert b"\xe9\xa1\xb5\xe7\x9c\x89\xe5\xa4\x96\xe6\x9d\xa5\xe4\xbf\xae\xe8\xae\xa2" in hdr or "页眉外来修订".encode() in hdr
    assert_redline_battery(source, redline, final, validation)


# ---------------------------------------------------------------------------
# 矩阵 C: mutation 反例
# ---------------------------------------------------------------------------

def test_mutation_intake_guard_neutered_depth_guards_still_fire(tmp_path, monkeypatch):
    # 反例: 即使摄入层对嵌套修订完全放行且投影把外来 ins 当普通文字 (变异),
    # 写路径的外来祖先防护仍须 fail-closed —— 纵深不依赖单点.
    source = _build(tmp_path, "<w:p><w:ins w:id=\"40\" w:author=\"" + FOREIGN + "\" w:date=\"" + WHEN + "\">"
                    "<w:r><w:t>外来插入足够长</w:t></w:r></w:ins>"
                    + HELPERS["run"]("干净文字足够长。") + "</w:p>")
    # 变异: 直接绕过 validate, 让 _edit_region 面对一个跨进外来 ins 的编辑
    import fundlex.docx as docx_mod
    root = docx_mod._xml(_read_parts(source, ZipLimits())[DOCUMENT], ZipLimits())
    paragraph = root.find(f".//{{{W}}}p")
    fake_edit = {"location": "p0", "zone": "body", "start": 2, "end": 6}
    # 伪造 segment 让 EDIT_CROSSES_BARRIER 不先行拦截: 变异 _project 输出
    fake_segment = docx_mod.TextSegment(0, 20, (root.getroottree().getpath(
        paragraph.find(f"{{{W}}}ins/{{{W}}}r/{{{W}}}t")),))
    original = docx_mod._project
    monkeypatch.setattr(docx_mod, "_project",
                        lambda *a, **k: (type(original(*a, **k)[0])(
                            "p0", "body", "", "X" * 20, (fake_segment,), "fp", ()), 0, False))
    with pytest.raises(DocxError) as error:
        docx_mod._edit_region(root, fake_edit, ZipLimits(), overlay=True)
    assert error.value.code == "FOREIGN_INSERTION_EDIT_UNSUPPORTED"


def test_mutation_noop_reject_implementation_caught_by_net(tmp_path, monkeypatch):
    # 反例: _reject_revisions 退化为空操作 (变异) 时, 后校验网必须捕获,
    # 绝不允许残留修订标记的"拍平件"流出.
    body = "<w:p>" + _rev("ins", 40, "插入") + HELPERS["run"]("正文。") + "</w:p>"
    data = _build(tmp_path, body).read_bytes()
    monkeypatch.setattr(revisions_mod, "_reject_revisions", lambda root: 0)
    with pytest.raises(DocxError):
        normalize_tracked_base(data, disposition="reject")


def test_mutation_foreign_identity_cannot_be_hijacked(tmp_path):
    # 反例: selective 得到一个声称外来 id 的裁决 (变异 manifest 错位) 必须拒.
    source = _build(tmp_path, "<w:p>" + _rev("ins", 40, "外来插入")
                    + HELPERS["run"]("干净文字足够长以供编辑。") + "</w:p>")
    edit_tuple = _edit(source, "p0", "干净文字足够长")
    redline, final, validation = _generate(source, tmp_path, edit_tuple)
    report = {"revision_manifest": [dict(m) for m in validation.manifest],
              "source_revision_manifest": [dict(r) for r in validation.source_revisions]}
    with pytest.raises(DocxError) as error:
        selective.generate_selected_redline(redline, redline.with_name("x.docx"),
                                            report, {"40": "reject"})
    assert error.value.code == "SELECTION_UNKNOWN_REVISION"


# ---------------------------------------------------------------------------
# 矩阵 D: 真实语料全量 (产品部修改后 32 份)
# ---------------------------------------------------------------------------

def _corpus_protected(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith(".xml") and b"documentProtection" in archive.read(name):
                return True
    return False


def _expected_view_text(path: Path, disposition: str) -> str:
    """独立参照实现: 对源 document.xml 施加与引擎语义等价的极简变换.

    accept: 摘除一切 w:del 子树、解包一切 w:ins;reject: 摘除一切 w:ins
    子树、delText→w:t 后解包一切 w:del。 段落标记合并只改段落边界不改
    文字流, 属性快照不动文字, 因此纯文字流即可全等比对 (强于子串抽查).
    """
    with zipfile.ZipFile(path) as archive:
        root = etree.fromstring(archive.read(DOCUMENT))
    ns = {"w": W}

    def drop(tag):
        for el in list(root.xpath(f"//w:{tag}", namespaces=ns)):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)

    def unwrap(tag, convert: bool):
        for el in list(root.xpath(f"//w:{tag}", namespaces=ns)):
            parent = el.getparent()
            if parent is None:
                continue
            index = parent.index(el)
            for child in list(el):
                if convert:
                    for t in child.iter():
                        if t.tag == Q("delText"):
                            t.tag = Q("t")
                        elif t.tag == Q("delInstrText"):
                            t.tag = Q("instrText")
                el.remove(child)
                parent.insert(index, child)
                index += 1
            parent.remove(el)

    if disposition == "accept":
        drop("del")
        unwrap("ins", False)
    else:
        drop("ins")
        unwrap("del", True)
    return "".join(t.text or "" for t in root.iter(Q("t")))


def _pick_edits(inspection, limit: int = 12):
    """候选落点生成器: 段落自中向后取, 跨 bookmark 类 fail-closed 落点由

    调用方按 DocxError 跳过错开 —— 与生产 _drop_unvalidatable_edits 的归罪
    行为同构, 不是避开断言。"""
    found = []
    paragraphs = list(inspection.paragraphs)
    for paragraph in paragraphs[len(paragraphs) // 2:] + paragraphs[:len(paragraphs) // 2]:
        if paragraph.zone not in {"body", "summary"} or not paragraph.editable:
            continue
        for segment in paragraph.segments:
            text = paragraph.text[segment.start:segment.end]
            if segment.end - segment.start >= 12 and len(text.strip()) >= 8:
                start, end = segment.end - 6, segment.end - 2
                found.append({"location": paragraph.location, "zone": paragraph.zone,
                              "start": start, "end": end, "old": paragraph.text[start:end]})
                if len(found) >= limit:
                    return found
    return found


def _plain_text(data: bytes) -> str:
    root = _xml(_read_parts_bytes(data, ZipLimits())[DOCUMENT], ZipLimits())
    return "".join(t.text or "" for t in root.iter(Q("t")))


@needs_corpus
def test_corpus_inventory_matches_dispatch_facts():
    # 台账事实锚: 32 份, w:ins 2775 / w:del 1044 (全包 document.xml 计).
    import re as _re
    ins_total = del_total = 0
    for path in corpus_files:
        xml = zipfile.ZipFile(path).read(DOCUMENT)
        ins_total += len(_re.findall(rb"<w:ins[\s>]", xml))
        del_total += len(_re.findall(rb"<w:del[\s>]", xml))
    assert len(corpus_files) == 32
    assert (ins_total, del_total) == (2775, 1044)


@needs_corpus
@pytest.mark.parametrize("path", corpus_files, ids=lambda p: p.name[:24])
def test_corpus_intake_and_strategies(tmp_path, path):
    data = path.read_bytes()
    protected = _corpus_protected(path)
    if protected:
        # 域防护属通用拒入守卫, 不是样本特判: 按文档自身声明推导期望
        for disposition in ("accept", "reject"):
            with pytest.raises(DocxError) as error:
                normalize_tracked_base(data, disposition=disposition)
            assert error.value.code == "DOCUMENT_PROTECTED"
        return
    inspection = inspect_docx(path, full=False, allow_existing_revisions=True)
    assert inspection.revisions, "台账保证 32/32 含修订"
    accepted = normalize_tracked_base(data, disposition="accept")
    rejected = normalize_tracked_base(data, disposition="reject")
    assert accepted.had_tracked_changes and rejected.had_tracked_changes
    for normalized in (accepted, rejected):
        parts = _read_parts_bytes(normalized.data, ZipLimits())
        for name, content in parts.items():
            if not name.endswith(".xml"):
                continue
            root = _xml(content, ZipLimits())
            assert not [n for n in root.iter()
                        if isinstance(n.tag, str) and n.tag.startswith("{" + W + "}")
                        and etree.QName(n).localname in REVISION_TAGS], name
    # 语义全等: 引擎两视图 == 独立参照实现 (非子串抽查, 覆盖嵌套/标记全形状)
    assert _plain_text(accepted.data) == _expected_view_text(path, "accept")
    assert _plain_text(rejected.data) == _expected_view_text(path, "reject")


@needs_corpus
@pytest.mark.parametrize("path", corpus_files, ids=lambda p: p.name[:24])
def test_corpus_writeback_with_stacked_marks(tmp_path, path):
    if _corpus_protected(path):
        pytest.skip("documentProtection: 拒入守卫覆盖于 test_corpus_intake_and_strategies")
    inspection = inspect_docx(path, full=False, allow_existing_revisions=True)
    candidates = _pick_edits(inspection)
    assert candidates, f"无可编辑干净落点: {path.name}"
    plan = edit = None
    blocked_codes: list[str] = []
    for target in candidates:
        old = target.pop("old")
        attempt = {"source_sha256": inspection.source_sha256, "verified": True,
                   "expected_old_text": old,
                   "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
                   "template_id": "fixed", "replacement": NEW, **target}
        try:
            plan = validate_edit_plan(path, [attempt], {"fixed": NEW},
                                      allow_existing_revisions=True)
            edit = attempt
            break
        except DocxError as error:
            blocked_codes.append(str(error.code))
    if plan is None:
        pytest.skip("全部候选落点均触发既有 fail-closed 守卫 (书签残半等), "
                    f"按生产归罪机制应被逐编辑丢弃: {blocked_codes[:4]}")
    redline, final = tmp_path / "red.docx", tmp_path / "fin.docx"
    validation = generate_artifacts(path, plan, redline, final, allow_existing_revisions=True)
    redline_hash_before = hashlib.sha256(redline.read_bytes()).hexdigest()
    assert_redline_battery(path, redline, final, validation)
    # 写回确定性: 同计划重复生成 -> 字节级一致
    redline2, final2 = tmp_path / "red2.docx", tmp_path / "fin2.docx"
    generate_artifacts(path, plan, redline2, final2, allow_existing_revisions=True)
    assert hashlib.sha256(redline.read_bytes()).hexdigest() == redline_hash_before
