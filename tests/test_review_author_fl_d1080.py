"""FL-D1080：修订审查「改动清单」显示修改人——后端从 w:ins/w:del 的 w:author 采集并出库。"""
from __future__ import annotations

import zipfile
from pathlib import Path

from fundlex.html_view import project_docx

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_DOC_XML = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{_W}"><w:body>
<w:p><w:r><w:t>第一章 总则</w:t></w:r></w:p>
<w:p><w:r><w:t>赎回费按</w:t></w:r><w:del w:id="1" w:author="张编辑"><w:r><w:delText>原费率 1.5%</w:delText></w:r></w:del><w:ins w:id="2" w:author="张编辑"><w:r><w:t>新费率 0%</w:t></w:r></w:ins><w:r><w:t>收取。</w:t></w:r></w:p>
<w:p><w:r><w:t>第二条</w:t></w:r><w:ins w:id="3" w:author="李法务"><w:r><w:t>新增条款一款。</w:t></w:r></w:ins></w:p>
</w:body></w:document>"""


def _revision_docx(tmp_path: Path) -> Path:
    path = tmp_path / "redline.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr("word/document.xml", _DOC_XML)
    return path


def test_review_projection_carries_w_author(tmp_path):
    projected = project_docx(_revision_docx(tmp_path))
    rows = projected["revisions"]
    authors = {row.get("author") for row in rows}
    assert "张编辑" in authors, f"ins/del 配对的 w:author 必须入库：{authors}"
    assert "李法务" in authors, f"单独插入的 w:author 必须入库：{authors}"
    # 行内 Html 仍只挂 data-rev（界面签名由清单层承担）
    assert 'data-rev="2"' in projected["html"]
