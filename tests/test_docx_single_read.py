"""inspect_docx must read the container once, for both parts and the source
hash (B13 F3: the file used to be scanned twice per inspection)."""

from __future__ import annotations

from pathlib import Path

from docx import Document

from fundlex.docx import inspect_docx


def test_inspect_docx_reads_source_once(tmp_path, monkeypatch):
    target = tmp_path / "contract.docx"
    document = Document()
    document.add_paragraph("单读盘回归测试文档。")
    document.save(target)

    original_read = Path.read_bytes
    reads: list[str] = []

    def counting_read(path_self, *args, **kwargs):
        if Path(path_self) == target:
            reads.append(str(path_self))
        return original_read(path_self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", counting_read)
    inspection = inspect_docx(target, full=True)
    assert len(reads) == 1
    assert inspection.source_sha256
    before = inspect_docx(target, full=False)
    again = inspect_docx(target, full=False)
    assert before.source_sha256 == again.source_sha256
