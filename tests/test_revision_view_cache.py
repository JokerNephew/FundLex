"""Pins for the revision-view projection cache (FL-D557 F3④).

The cache lives in ``fundlex.api`` and keys projections on
(path, size, mtime_ns, report digest); these tests verify hits, invalidation
on artifact/report drift and the LRU bound without standing up the app.
"""
from __future__ import annotations

import os

import pytest

import fundlex.api as api


class Recorder:
    def __init__(self):
        self.calls = 0

    def __call__(self, path, *, report=None):
        self.calls += 1
        return {"html": f"<p>html-{self.calls}</p>", "revisions": [self.calls],
                "meta": {"call": self.calls}, "extra": "dropped"}


@pytest.fixture()
def recorder(monkeypatch):
    api._REVISION_VIEW_CACHE.clear()
    rec = Recorder()
    monkeypatch.setattr(api, "project_docx", rec)
    yield rec
    api._REVISION_VIEW_CACHE.clear()


def report(n: int = 0) -> dict:
    return {"revision_manifest": [{"id": f"r{n}"}], "n": n}


def test_repeat_view_projects_once(tmp_path, recorder):
    path = tmp_path / "redline.docx"
    path.write_bytes(b"bytes-v1")
    first = api._project_revision_view(path, report())
    second = api._project_revision_view(path, report())
    assert recorder.calls == 1
    assert second == first
    assert set(first) == {"html", "revisions", "meta"}


def test_changed_artifact_bytes_reproject(tmp_path, recorder):
    path = tmp_path / "redline.docx"
    path.write_bytes(b"bytes-v1")
    api._project_revision_view(path, report())
    path.write_bytes(b"bytes-v2-longer")
    api._project_revision_view(path, report())
    assert recorder.calls == 2


def test_changed_mtime_same_size_reprojects(tmp_path, recorder):
    path = tmp_path / "redline.docx"
    path.write_bytes(b"same-size!")
    api._project_revision_view(path, report())
    os.utime(path, ns=(1_000_000_000, 2_000_000_000))
    api._project_revision_view(path, report())
    assert recorder.calls == 2


def test_changed_report_reprojects(tmp_path, recorder):
    path = tmp_path / "redline.docx"
    path.write_bytes(b"bytes-v1")
    api._project_revision_view(path, report(1))
    api._project_revision_view(path, report(2))
    assert recorder.calls == 2


def test_lru_bound_and_recency(tmp_path, recorder):
    paths = []
    for index in range(api._REVISION_VIEW_CACHE_MAX):
        path = tmp_path / f"redline-{index}.docx"
        path.write_bytes(f"bytes-{index}".encode())
        api._project_revision_view(path, report())
        paths.append(path)
    assert len(api._REVISION_VIEW_CACHE) == api._REVISION_VIEW_CACHE_MAX
    # Touch the oldest entry so the next eviction skips it.
    api._project_revision_view(paths[0], report())
    assert recorder.calls == api._REVISION_VIEW_CACHE_MAX
    extra = tmp_path / "redline-extra.docx"
    extra.write_bytes(b"bytes-extra")
    api._project_revision_view(extra, report())
    assert len(api._REVISION_VIEW_CACHE) == api._REVISION_VIEW_CACHE_MAX
    # paths[1] was evicted, paths[0] survived.
    api._project_revision_view(paths[0], report())
    assert recorder.calls == api._REVISION_VIEW_CACHE_MAX + 1
    api._project_revision_view(paths[1], report())
    assert recorder.calls == api._REVISION_VIEW_CACHE_MAX + 2


def test_real_projection_end_to_end_smoke(tmp_path):
    api._REVISION_VIEW_CACHE.clear()
    docx = tmp_path / "redline.docx"
    from docx import Document

    document = Document()
    document.add_paragraph("第一条 真实的合同段落。")
    document.save(docx)
    view = api._project_revision_view(docx, {"revision_manifest": []})
    assert view["html"] and isinstance(view["revisions"], list)
    api._REVISION_VIEW_CACHE.clear()
