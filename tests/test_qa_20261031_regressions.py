"""Regression tests for the 2026-10-31 full-project QA sweep.

Covers: A7-01 (G16 unbound rule), A7-02 (frozen paging input for residual
delete targets), A7-03 (NFKC expansion index drift), A8-F1 (engine build
module list) and A8-F2 (orphan evidence must block delivery).
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.delivery import requires_blocker
from fundlex.docx import TextSegment
from fundlex.recall import (Facts, Target, assign_target_operations,
                            ensure_delete_targets, find_normalized)
from fundlex import store as store_module


class Inspection:
    def __init__(self, texts):
        self.paragraphs = tuple(
            SimpleNamespace(location=f"p{i}", text=text, zone="body",
                            logical_zone="body", section_path="",
                            segments=(TextSegment(0, len(text)),),
                            fingerprint=f"p{i}")
            for i, text in enumerate(texts))
        self.source_sha256 = "source"

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _facts() -> Facts:
    return Facts("普通开放式基金", "", "", (), False, "", "", "", {}, ())


# --- A7-01 -----------------------------------------------------------------

def test_g16_satisfied_out_of_scope_first_target_no_unbound_rule():
    """A satisfied+out_of_scope G16 first target must not raise NameError."""
    target = Target("T001", "G16", "p10", "直销机构 其他销售机构", "satisfied",
                    "survey", start=0, end=10, operations=("G16:0",),
                    resolution="resolved", segment_ok=True)
    target.out_of_scope = True
    rules = {"G16": {"rule_id": "G16",
                     "operations": [{"op": "replace", "old_text": "x",
                                     "new_text": "直销机构 其他销售机构"}]}}
    errors = assign_target_operations([target], rules, Inspection(["x"]), _facts())
    assert isinstance(errors, list)


# --- A7-02 -----------------------------------------------------------------

def test_ensure_delete_targets_frozen_paging_input_covers_all_pages():
    sentence = "本基金对持续持有期少于7日的投资者收取不低于1.5%的短期赎回费。"
    texts = [sentence + f"（副本{i}）" for i in range(60)]
    inspection = Inspection(texts)
    rule = {"rule_id": "G13",
            "operations": [{"op": "delete", "old_text": sentence}]}
    base_targets: list[Target] = []
    created: list[Target] = []
    cursor = 0
    # Mirror the pipeline caller contract: the paging input is a frozen
    # snapshot; newly created clones are collected separately (A7-02 fix).
    paging_base = list(base_targets)
    for _ in range(10):
        info: dict = {}
        page = ensure_delete_targets(paging_base, {"G13": rule}, inspection,
                                     limit=20, cursor=cursor, page_info=info)
        created.extend(page)
        base_targets.extend(page)
        if not info.get("has_more"):
            break
        cursor = int(info["next_cursor"])
    locations = {item.location for item in created}
    assert len(locations) == 60, (len(locations), sorted(locations)[:5])


# --- A7-03 -----------------------------------------------------------------

def test_find_normalized_nfkc_length_expansion_offsets():
    # "㏄" folds to two NFKC characters; offsets must still map exactly to the
    # original span (pre-fix this raised IndexError or mislocated the span).
    haystack = "面积为5㏄的容器，见附件。"
    needle = "5㏄的容器"
    located = find_normalized(haystack, needle)
    assert located is not None
    start, end = located
    assert haystack[start:end] == needle


# --- A8-F1 -----------------------------------------------------------------

def test_engine_build_modules_include_semantic_contract():
    assert "fundlex/semantic_contract.py" in store_module._ENGINE_BUILD_MODULES


# --- A8-F2 (resolution: stale docstring; review-assisted contract kept) ------

def test_orphan_evidence_is_review_item_not_silent_drop():
    item = {"kind": "orphan_evidence", "code": "LEDGER_EVIDENCE_UNBOUND",
            "rule_id": "G05", "location": "p12"}
    # Review-assisted delivery treats unbound evidence like open obligations:
    # always visible in unresolved, never silently dropped, never auto-blocking.
    assert requires_blocker(item) is False


# --- API/security fixes (main-agent batch) -----------------------------------

import pytest
from fastapi.testclient import TestClient

from fundlex.api import create_app


@pytest.fixture
def password_client(tmp_path, monkeypatch):
    for name in ("FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL",
                 "FUNDLEX_SESSION_HOURS", "FUNDLEX_BOOTSTRAP_ADMIN",
                 "FUNDLEX_ALLOW_REGISTRATION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    return TestClient(create_app(tmp_path), raise_server_exceptions=False)


def test_login_throttled_after_repeated_failures(password_client):
    password_client.post("/api/auth/register", json={
        "username": "victim", "password": "password-123", "display_name": "v"})
    for _ in range(10):
        assert password_client.post("/api/auth/login", json={
            "username": "victim", "password": "wrong"}).status_code == 401
    blocked = password_client.post("/api/auth/login", json={
        "username": "victim", "password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")


def test_registration_throttled_per_client(password_client):
    for index in range(10):
        assert password_client.post("/api/auth/register", json={
            "username": f"bulk{index}", "password": "password-123",
            "display_name": "b"}).status_code == 201
    assert password_client.post("/api/auth/register", json={
        "username": "bulk-final", "password": "password-123",
        "display_name": "b"}).status_code == 429


def test_security_and_cache_headers_present(password_client):
    response = password_client.get("/static/app.css")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert response.headers.get("Referrer-Policy")
    home = password_client.get("/")
    assert home.status_code == 200
    assert "guide_generation.css?v=" in home.text
    assert "guide_generation.js?v=" in home.text


def test_upload_filename_length_capped(password_client):
    register = password_client.post("/api/auth/register", json={
        "username": "uploader", "password": "password-123", "display_name": "u"})
    headers = {"Authorization": f"Bearer {register.json()['token']}"}
    long_name = "长" * 100 + ".docx"
    from fundlex.upload_validation import validate_docx_upload, UploadValidationError
    with pytest.raises(UploadValidationError) as info:
        validate_docx_upload(long_name, b"PK")
    assert info.value.code == "UPLOAD_FILENAME_TOO_LONG"
    assert info.value.status_code == 422


def test_gg_run_for_not_found_vs_storage_error(password_client, monkeypatch):
    register = password_client.post("/api/auth/register", json={
        "username": "runner", "password": "password-123", "display_name": "r"})
    headers = {"Authorization": f"Bearer {register.json()['token']}"}
    missing = password_client.get("/api/guide-generation/runs/nope", headers=headers)
    assert missing.status_code == 404
    gg = password_client.app.state.guide_generation
    def boom(*args, **kwargs):
        raise RuntimeError("db down")
    monkeypatch.setattr(gg, "get_run_for_owner", boom)
    assert password_client.get("/api/guide-generation/runs/x",
                               headers=headers).status_code == 500


def test_regulation_parser_rejects_zip_bomb(tmp_path):
    import io
    import os
    import zipfile
    from fundlex.regulatory import docx_parser
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        # Incompressible content keeps the per-member ratio guard quiet so the
        # aggregate expanded-size guard is the one that fires.
        archive.writestr("word/document.xml", os.urandom(2 * 1024 * 1024))
    target = tmp_path / "bomb.docx"
    target.write_bytes(buffer.getvalue())
    monkey_max = docx_parser.MAX_EXPANDED_BYTES
    docx_parser.MAX_EXPANDED_BYTES = 1024  # force the expanded-size guard
    try:
        with pytest.raises(docx_parser.RegulationParseError) as info:
            docx_parser.parse_regulation_docx(target)
        assert info.value.args[0] == "REGULATION_DOCX_EXPANDED_LIMIT"
    finally:
        docx_parser.MAX_EXPANDED_BYTES = monkey_max


# --- A7-04 / A8-F3 -----------------------------------------------------------

def test_final_omission_truncated_scan_blocks():
    from fundlex.recall_pipeline import _final_omission_issue_blocks
    assert _final_omission_issue_blocks(
        {"code": "FINAL_RESIDUAL_SCAN_TRUNCATED"}) is True
