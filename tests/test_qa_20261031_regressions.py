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


# --- FL-D568 (B16 EDIT_BOOKMARK_RANGE_BROKEN → per-edit degradation) ---------

import hashlib
import runpy
from pathlib import Path

from fundlex import docx as docx_editor
from fundlex.recall_pipeline import _drop_unvalidatable_edits

DOCX_HELPERS = runpy.run_path(str(Path(__file__).resolve().parent
                                   / "test_docx_structures.py"))


def _fl568_source(tmp_path) -> Path:
    """p0 carries a ranged bookmark half inside the to-be-edited span; its
    partner lives inside p1 (true cross-paragraph) — geometry the writer must
    keep rejecting — while p2 hosts a plain legal edit."""
    body = ("<w:p>" + DOCX_HELPERS["run"]("甲") + '<w:bookmarkStart w:id="7" w:name="bm7"/>'
            + DOCX_HELPERS["run"]("乙") + "</w:p>"
            + "<w:p>" + DOCX_HELPERS["run"]("尾") + '<w:bookmarkEnd w:id="7"/>'
            + "</w:p><w:p>" + DOCX_HELPERS["run"]("合法目标") + "</w:p>")
    directory = tmp_path / "fl568"
    directory.mkdir(exist_ok=True)
    return DOCX_HELPERS["package"](directory, body, None)


def _fl568_edit(source, location, old, new, target_id):
    inspection = docx_editor.inspect_docx(source, full=True)
    paragraph = inspection.by_location(location)
    start = paragraph.text.index(old)
    return {
        "source_sha256": inspection.source_sha256, "verified": True,
        "location": location, "zone": paragraph.zone, "start": start,
        "end": start + len(old), "expected_old_text": old,
        "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
        "operation": "replace", "content_source": "generated",
        "replacement": new, "rule_id": "G22", "target_id": target_id,
    }


def test_drop_unvalidatable_edits_keeps_legal_edits_and_unresolves_target(tmp_path):
    source = _fl568_source(tmp_path)
    guilty = _fl568_edit(source, "p0", "甲乙", "新文", "T001")
    clean = _fl568_edit(source, "p2", "合法目标", "新文", "T002")
    planned = {"edits": [dict(guilty), dict(clean)],
               "ledger": [{"target_id": "T001", "status": "planned"},
                          {"target_id": "T002", "status": "planned"}]}
    with pytest.raises(docx_editor.DocxError) as error:
        docx_editor.validate_edit_plan(source, [guilty, clean], {},
                                       content_check=lambda edit: True)
    assert error.value.code == "EDIT_BOOKMARK_RANGE_BROKEN"
    kept = _drop_unvalidatable_edits(source, [guilty, clean], planned,
                                     content_check=lambda edit: True)
    assert kept == [clean]
    assert [record["target_id"] for record in planned["edits"]] == ["T002"]
    assert planned["ledger"][0] == {"target_id": "T001", "status": "unresolved",
                                    "reason": "RECALL_EDIT_VALIDATE_REJECTED"}
    assert planned["ledger"][1]["status"] == "planned"
    # The reduced plan validates strictly and generates.
    plan = docx_editor.validate_edit_plan(source, kept, {},
                                          content_check=lambda edit: True)
    redline, final = tmp_path / "r.docx", tmp_path / "f.docx"
    validation = docx_editor.generate_artifacts(source, plan, redline, final)
    assert validation.checks
    # A contract-level failure outside single-edit attribution stays fail-closed.
    assert _drop_unvalidatable_edits(source, [guilty],
                                     {"edits": [dict(guilty)], "ledger": []},
                                     content_check=lambda edit: True) is None


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


# --- API review follow-ups (round-2 adversarial findings) --------------------

def test_login_throttle_key_normalized(password_client):
    """Whitespace/case variants of one account share the throttle key (A1-2)."""
    password_client.post("/api/auth/register", json={
        "username": "victim2", "password": "password-123", "display_name": "v"})
    for _ in range(10):
        assert password_client.post("/api/auth/login", json={
            "username": "victim2", "password": "wrong"}).status_code == 401
    for variant in (" victim2", "  victim2  ", "VICTIM2", "Victim2"):
        blocked = password_client.post("/api/auth/login", json={
            "username": variant, "password": "wrong"})
        assert blocked.status_code == 429, f"throttle bypassed via {variant!r}"


def test_throttled_login_envelope_and_retry_after(password_client):
    password_client.post("/api/auth/register", json={
        "username": "victim3", "password": "password-123", "display_name": "v"})
    for _ in range(10):
        password_client.post("/api/auth/login", json={
            "username": "victim3", "password": "wrong"})
    blocked = password_client.post("/api/auth/login", json={
        "username": "victim3", "password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.json()["error_code"] == "RATE_LIMITED"
    assert blocked.headers.get("Retry-After")


def test_guidance_run_filename_length_capped(password_client):
    """POST /api/guide-generation/runs enforces the filename cap (A4-F01)."""
    register = password_client.post("/api/auth/register", json={
        "username": "gguploader", "password": "password-123", "display_name": "g"})
    headers = {"Authorization": f"Bearer {register.json()['token']}"}
    long_name = "长" * 100 + ".docx"  # 300 UTF-8 bytes > 200-byte cap
    rejected = password_client.post(
        "/api/guide-generation/runs", headers=headers,
        files={"file": (long_name, b"PK\x03\x04" + b"0" * 64)})
    assert rejected.status_code == 422
    assert rejected.json()["error_code"] == "UPLOAD_FILENAME_TOO_LONG"


def test_unversioned_static_not_cached_longterm(password_client):
    versioned = password_client.get("/static/app.css?v=abcdef0123456789")
    assert "immutable" in versioned.headers.get("Cache-Control", "")
    plain = password_client.get("/static/app.css")
    cache = plain.headers.get("Cache-Control", "")
    assert "no-cache" in cache
    assert "31536000" not in cache


def test_success_responses_carry_correlation_id(password_client):
    for path in ("/", "/api/capabilities"):
        response = password_client.get(path)
        assert response.headers.get("X-Correlation-ID"), f"{path} lost the header"


# --- R2 security-fix regressions (F-01/F-02/F-03/F-04/F-06/F-08) -------------

import asyncio
import hashlib
import io
import json
import os
import time
import zipfile

from starlette.datastructures import Headers

from fundlex.proxy_headers import client_host
from fundlex.upload_guard import UploadGuardSettings, UploadResourceMiddleware


def _tiny_docx() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml",
                   '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body/></w:document>')
    return buffer.getvalue()


def _password_client_at(tmp_path, monkeypatch, **client_kwargs):
    for name in ("FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL",
                 "FUNDLEX_SESSION_HOURS", "FUNDLEX_BOOTSTRAP_ADMIN",
                 "FUNDLEX_ALLOW_REGISTRATION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    return TestClient(create_app(tmp_path), raise_server_exceptions=False, **client_kwargs)


def _register(client, username, password="password-123", extra_headers=None):
    return client.post("/api/auth/register", json={
        "username": username, "password": password, "display_name": "u"},
        headers=extra_headers or {})


def test_login_throttle_shared_across_workers(tmp_path, monkeypatch):
    """R2-F01: two app instances (simulated uvicorn workers) share one login budget."""
    first = _password_client_at(tmp_path, monkeypatch)
    second = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    _register(first, "sharedvictim")
    for _ in range(10):
        assert first.post("/api/auth/login", json={
            "username": "sharedvictim", "password": "wrong"}).status_code == 401
    # The second worker must already be throttled instead of getting a fresh budget.
    blocked = second.post("/api/auth/login", json={
        "username": "sharedvictim", "password": "wrong"})
    assert blocked.status_code == 429


def test_register_throttle_survives_restart(tmp_path, monkeypatch):
    """R2-F01: throttle events persist in the auth DB across app restarts."""
    first = _password_client_at(tmp_path, monkeypatch)
    for index in range(10):
        assert _register(first, f"restart{index}").status_code == 201
    restarted = TestClient(create_app(tmp_path), raise_server_exceptions=False)
    assert _register(restarted, "restartfinal").status_code == 429


def test_x_forwarded_for_not_trusted_without_config(tmp_path, monkeypatch):
    """R2-F01/F02: spoofed XFF must not hand an attacker fresh throttle buckets."""
    monkeypatch.delenv("FUNDLEX_TRUSTED_PROXY_HOSTS", raising=False)
    client = _password_client_at(tmp_path, monkeypatch)
    for index in range(10):
        assert _register(client, f"spoof{index}",
                         extra_headers={"X-Forwarded-For": f"192.0.2.{index}"}).status_code == 201
    blocked = _register(client, "spoofedeleventh",
                        extra_headers={"X-Forwarded-For": "198.51.100.9"})
    assert blocked.status_code == 429


def test_x_forwarded_for_trusted_when_configured(tmp_path, monkeypatch):
    """R2-F01/F02: with a trusted proxy, buckets follow XFF per real client IP."""
    monkeypatch.setenv("FUNDLEX_TRUSTED_PROXY_HOSTS", "10.0.0.1")
    for name in ("FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL",
                 "FUNDLEX_SESSION_HOURS", "FUNDLEX_BOOTSTRAP_ADMIN",
                 "FUNDLEX_ALLOW_REGISTRATION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    client = TestClient(create_app(tmp_path), raise_server_exceptions=False,
                        client=("10.0.0.1", 11))
    for index in range(10):
        assert _register(client, f"proxy{index}",
                         extra_headers={"X-Forwarded-For": "192.0.2.10"}).status_code == 201
    assert _register(client, "proxyextra",
                     extra_headers={"X-Forwarded-For": "192.0.2.10"}).status_code == 429
    # A different real client behind the same proxy gets its own bucket.
    assert _register(client, "proxyother",
                     extra_headers={"X-Forwarded-For": "192.0.2.11"}).status_code == 201


def test_client_host_unit(monkeypatch):
    headers = Headers({"x-forwarded-for": "192.0.2.7, 10.0.0.2"})
    monkeypatch.delenv("FUNDLEX_TRUSTED_PROXY_HOSTS", raising=False)
    assert client_host(headers, "10.0.0.1") == "10.0.0.1"
    monkeypatch.setenv("FUNDLEX_TRUSTED_PROXY_HOSTS", "10.0.0.1, 10.0.0.0/24")
    assert client_host(headers, "10.0.0.2") == "192.0.2.7"
    # A client-injected leading hop is ignored: the rightmost untrusted hop wins.
    spoof = Headers({"x-forwarded-for": "1.1.1.1, 192.0.2.7, 10.0.0.2"})
    assert client_host(spoof, "10.0.0.1") == "192.0.2.7"
    # Malformed trust entries never widen the trust set.
    monkeypatch.setenv("FUNDLEX_TRUSTED_PROXY_HOSTS", "not-an-ip")
    assert client_host(headers, "10.0.0.1") == "10.0.0.1"
    assert client_host(Headers({}), None) == "unknown"


def test_upload_guard_client_key_honours_trusted_proxy(monkeypatch):
    """R2-F02: the guard keys per-IP quotas on XFF only from configured proxies."""
    def scope(headers=()):
        return {
            "type": "http", "http_version": "1.1", "method": "POST",
            "path": "/api/tasks/t/uploads", "raw_path": b"/api/tasks/t/uploads",
            "query_string": b"", "scheme": "http", "client": ("10.0.0.1", 5),
            "server": ("test", 80),
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        }

    monkeypatch.delenv("FUNDLEX_TRUSTED_PROXY_HOSTS", raising=False)
    assert (UploadResourceMiddleware._client_key(scope((("x-forwarded-for", "192.0.2.7"),)))
            == "10.0.0.1")
    monkeypatch.setenv("FUNDLEX_TRUSTED_PROXY_HOSTS", "10.0.0.1")
    assert (UploadResourceMiddleware._client_key(scope((("x-forwarded-for", "192.0.2.7"),)))
            == "192.0.2.7")


def test_upload_guard_recent_keys_are_pruned():
    """R2-F08: idle client keys must not accumulate in the minute-window map."""
    middleware = UploadResourceMiddleware(lambda scope, receive, send: asyncio.sleep(0),
                                          settings=UploadGuardSettings())
    asyncio.run(middleware._admit("203.0.113.7"))
    stale = middleware._recent["203.0.113.7"]
    while stale:
        stale.popleft()
    stale.append(time.monotonic() - 61.0)
    asyncio.run(middleware._release("203.0.113.7"))
    assert "203.0.113.7" not in middleware._recent
    # A fresh (still within the window) entry must survive the release.
    asyncio.run(middleware._admit("203.0.113.9"))
    asyncio.run(middleware._release("203.0.113.9"))
    assert "203.0.113.9" in middleware._recent


def test_multipart_part_cap_matches_product_batches(tmp_path, monkeypatch):
    """R2-F03: 40-file batches pass; the (env-overridable) ceiling still trips floods."""
    monkeypatch.delenv("FUNDLEX_MULTIPART_MAX_PARTS", raising=False)
    client = _password_client_at(tmp_path, monkeypatch)
    token = _register(client, "parts40").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    docx = _tiny_docx()
    manifest = [{"client_id": f"c{i}", "name": f"f{i}.docx", "size": len(docx)}
                for i in range(40)]
    created = client.post("/api/tasks", json={
        "name": "parts", "engine_id": "recall_first", "files": manifest}, headers=headers)
    task_id = created.json()["id"]
    uploads = [("files", (f"f{i}.docx", docx, "application/octet-stream")) for i in range(40)]
    response = client.post(f"/api/tasks/{task_id}/uploads", headers=headers,
                           files=uploads,
                           data={"client_ids": json.dumps([f["client_id"] for f in manifest])})
    assert response.status_code == 200, response.text[:200]

    monkeypatch.setenv("FUNDLEX_MULTIPART_MAX_PARTS", "4")
    small = [{"client_id": f"s{i}", "name": f"s{i}.docx", "size": len(docx)} for i in range(5)]
    created = client.post("/api/tasks", json={
        "name": "small", "engine_id": "recall_first", "files": small}, headers=headers)
    task_id = created.json()["id"]
    blocked = client.post(f"/api/tasks/{task_id}/uploads", headers=headers,
                          files=[("files", (f"s{i}.docx", docx, "application/octet-stream"))
                                 for i in range(5)],
                          data={"client_ids": json.dumps([f["client_id"] for f in small])})
    assert blocked.status_code == 400


def test_405_reports_method_not_allowed(password_client):
    """R2-F06: unmapped status codes must not masquerade as INTERNAL_ERROR."""
    response = password_client.post("/api/auth/me")
    assert response.status_code == 405
    assert response.json()["error_code"] == "METHOD_NOT_ALLOWED"


def test_archive_csv_cells_escape_formulas():
    """R2-F04: exported CSV text cells starting with = + - @ TAB CR are quoted."""
    from fundlex.api import csv_safe_cell
    assert csv_safe_cell("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    for prefix in ("+", "-", "@", "\t", "\r"):
        assert csv_safe_cell(prefix + "1+1") == "'" + prefix + "1+1"
    assert csv_safe_cell("正常合同.docx") == "正常合同.docx"
    assert csv_safe_cell("") == ""
    assert csv_safe_cell(123) == 123


def test_task_archive_csv_prefixes_malicious_filename(tmp_path, monkeypatch):
    """R2-F04 end-to-end: a '=cmd.docx' contract lands quoted in 结果清单.csv."""
    client = _password_client_at(tmp_path, monkeypatch)
    token = _register(client, "csvowner").json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    docx = _tiny_docx()
    created = client.post("/api/tasks", json={
        "name": "form", "engine_id": "recall_first",
        "files": [{"client_id": "f1", "name": "=cmd.docx", "size": len(docx)}]},
        headers=headers)
    task_id = created.json()["id"]
    uploaded = client.post(f"/api/tasks/{task_id}/uploads", headers=headers,
                           files=[("files", ("=cmd.docx", docx, "application/octet-stream"))],
                           data={"client_ids": json.dumps(["f1"])})
    receipt = uploaded.json()["receipts"][0]
    document_id = receipt["document_id"]
    # Simulate a failed worker run so the archive has at least one artifact row.
    store = client.app.state.store
    report_bytes = json.dumps({"engine_id": "recall_first",
                               "delivery_status": "incomplete",
                               "unresolved": [{"kind": "target"}]}).encode()
    obj = store.root / "objects" / "sim" / f"{document_id}-report.json"
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(report_bytes)
    with store._connect() as db:
        db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?)",
                   (document_id, "report_json", f"sim/{document_id}-report.json",
                    hashlib.sha256(report_bytes).hexdigest(), len(report_bytes)))
        db.execute("UPDATE documents SET report_json=?,status='failed',"
                   "error_code='PROCESSING_FAILED',delivery_status='not_generated' WHERE id=?",
                   (json.dumps({"engine_id": "recall_first"}), document_id))
    archive = client.get(f"/api/tasks/{task_id}/download/all", headers=headers)
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        csv_text = z.read("结果清单.csv").decode("utf-8-sig")
    assert "'=cmd.docx" in csv_text
    assert not any(line.startswith(("=", "+", "-", "@"))
                   for line in csv_text.replace("\ufeff", "").splitlines())


# --- R2-F1: FUND_TYPE_UNVERIFIED must block delivery under every policy ------

def test_fund_type_unverified_blocks_delivery_both_policies():
    """FL-D114 / R2-F1: an excluded fund type with an unverifiable quote is a
    whole-contract qualification gap.  It used to slip through three layers
    (FUND_TYPE known-item prefix, reason-field business markers it never
    carried, ledger-only hard gate) and publish as complete under the default
    review_assisted policy."""
    from fundlex.recall_pipeline import _classify_delivery_items, _delivery_complete
    item = {"kind": "qualification", "code": "FUND_TYPE_UNVERIFIED",
            "reason": "FUND_TYPE_UNVERIFIED", "fund_type": "money_market"}
    assert requires_blocker(item)
    blockers, review, business = _classify_delivery_items([item])
    assert blockers == [item] and not review and not business
    assert not _delivery_complete([item], policy="review_assisted")
    assert not _delivery_complete([item], policy="strict")
    # The same identity on code *and* reason (LOW-5) keeps the legacy
    # reason-field code path consistent too.
    legacy = {"kind": "qualification", "reason": "FUND_TYPE_UNVERIFIED"}
    _b, _r, _c = _classify_delivery_items([legacy])
    assert legacy not in _b  # no code on old reports -> business bucket, but...
    assert requires_blocker({**legacy, "code": "FUND_TYPE_UNVERIFIED"})


def test_fund_type_unverified_summary_describes_eligibility_not_clause():
    """LOW-1: the qualification gap must not render as a failed clause edit."""
    from fundlex.delivery import build_user_summary
    item = {"kind": "qualification", "code": "FUND_TYPE_UNVERIFIED",
            "reason": "FUND_TYPE_UNVERIFIED"}
    summary = build_user_summary({
        "delivery_status": "incomplete", "delivery_policy": "review_assisted",
        "unresolved": [item], "delivery_blockers": [item],
        "review_items": [], "business_pending": [], "errors": [], "notices": []})
    assert summary["status"] == "partial"
    issue = next(entry for entry in summary["issues"]
                 if entry["code"] == "FUND_TYPE_UNVERIFIED")
    assert "产品类型" in issue["title"]
    assert "资格" in issue["title"]
    assert "修订痕迹" not in issue["review_note"]


# --- R2-F2: missing artifact location must not fabricate "residual absent" ---

def _orphan_finding_doc(tmp_path, body_text):
    from docx import Document
    from fundlex.docx import inspect_docx
    document = Document()
    document.add_paragraph(body_text)
    path = tmp_path / "contract.docx"
    document.save(path)
    return inspect_docx(path)


def test_orphan_finding_missing_location_stays_pending_with_evidence(tmp_path):
    """R2-F2: a stale location made body="" and turned every residual check
    into a vacuous pass, silently resolving REAL residuals as
    claimed_residual_absent / REMOVAL_UNCONFIRMED."""
    from fundlex import recall_pipeline as rp
    actual = _orphan_finding_doc(
        tmp_path, "托管费仍按百分之零点二五收取，此处残留旧条款未被删除。")
    finding = {"status": "pending", "rule_id": "G01", "location": "p9999",
               "quote": "托管费仍按百分之零点二五收取",
               "issue": "residual_old_policy",
               "reason": "旧条款“托管费仍按百分之零点二五收取”仍存在于合同中"}
    rp._apply_artifact_proof_to_findings(
        [finding], {"obligations": {}}, actual, None, {"G01": {"operations": []}})
    assert finding.get("status") != "resolved"
    assert finding.get("resolution") is None
    assert finding.get("proof_kind") == "SEMANTIC_UNCERTAIN"
    assert finding.get("resolution_evidence") == "LOCATION_NOT_FOUND"


def test_orphan_finding_valid_location_still_resolves_when_absent(tmp_path):
    """Control for R2-F2: a findable location with a truly absent claimed old
    clause still resolves as claimed_residual_absent (behavior unchanged)."""
    from fundlex import recall_pipeline as rp
    actual = _orphan_finding_doc(tmp_path, "管理费按固定费率每日计提并按月支付。")
    finding = {"status": "pending", "rule_id": "G01", "location": "p0",
               "quote": "托管费按百分之零点二五收取",
               "issue": "residual_old_policy",
               "reason": "旧条款“托管费按百分之零点二五收取”仍存在于合同中"}
    rp._apply_artifact_proof_to_findings(
        [finding], {"obligations": {}}, actual, None, {"G01": {"operations": []}})
    assert finding.get("status") == "resolved"
    assert finding.get("resolution_evidence") == "claimed_residual_absent"


# --- LOW-4: Chinese single quotes ‘’ are a claimed-quote style ----------------

def test_orphan_finding_chinese_single_quoted_claim_resolves_when_absent(tmp_path):
    from fundlex import recall_pipeline as rp
    actual = _orphan_finding_doc(tmp_path, "管理费按固定费率每日计提并按月支付。")
    finding = {"status": "pending", "rule_id": "G01", "location": "p0",
               "quote": "托管费按百分之零点二五收取",
               "issue": "residual_old_policy",
               "reason": "旧条款‘托管费按百分之零点二五收取且逐日计提’仍存在于合同中"}
    rp._apply_artifact_proof_to_findings(
        [finding], {"obligations": {}}, actual, None, {"G01": {"operations": []}})
    assert finding.get("status") == "resolved"
    assert finding.get("resolution_evidence") == "claimed_residual_absent"


# --- LOW-3: template-mode replacements must instantiate class slots ----------

def _class_facts(subscription_names=(), service_names=()):
    from fundlex.recall import ClassFact, Facts
    classes = tuple(
        ClassFact(name=f"{letter}类基金份额", subscription_fee=letter in subscription_names,
                  service_fee=letter not in subscription_names,
                  current=True, rate="0.4%", quote=letter)
        for letter in (*subscription_names, *service_names))
    return Facts(fund_type="open_regular", fund_type_quote="某基金合同", fund_type_basis="标题",
                 classes=classes, floating_management_fee=False, floating_quote="",
                 floating_basis="", notes="", quotes_verified={}, problems=())


def test_template_policy_instantiates_slots_with_facts(tmp_path):
    """LOW-3: template mode must not publish the guide's raw slot text."""
    import json
    from pathlib import Path
    from fundlex.semantic_contract import (load_semantic_policies,
                                           parse_semantic_targets)
    guide = json.loads((Path(__file__).resolve().parents[1]
                        / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    rule = next(item for item in guide["groups"] if item["rule_id"] == "G16")
    old = "D类基金份额的销售服务费每日计提，按月支付。"
    actual = _orphan_finding_doc(tmp_path, old)
    policy = load_semantic_policies()["G16"]
    accepted, rejected = parse_semantic_targets({"targets": [{
        "location": "p0", "quote": old, "operation_id": "G16:0",
        "replacement": "模型给的任意文本", "preserved_text": [], "reason": "payment clause",
    }]}, rule, actual, ["p0"], policy, facts=_class_facts(subscription_names=("A",),
                                                          service_names=("D",)))
    assert not rejected, rejected
    assert len(accepted) == 1
    # The guide template names the generic "C类" service slot; with a D-class
    # service group the instantiated text must not keep it.
    assert "C类基金份额" not in accepted[0].replacement
    assert accepted[0].replacement != str(rule["operations"][0]["new_text"])


def test_template_policy_fails_closed_when_slots_cannot_fill(tmp_path):
    """No service-fee class in facts -> the slot stays unresolved and the
    target is rejected instead of shipping raw template text."""
    import json
    from pathlib import Path
    from fundlex.semantic_contract import (load_semantic_policies,
                                           parse_semantic_targets)
    guide = json.loads((Path(__file__).resolve().parents[1]
                        / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    rule = next(item for item in guide["groups"] if item["rule_id"] == "G16")
    old = "基金份额的销售服务费每日计提，按月支付。"
    actual = _orphan_finding_doc(tmp_path, old)
    policy = load_semantic_policies()["G16"]
    accepted, rejected = parse_semantic_targets({"targets": [{
        "location": "p0", "quote": old, "operation_id": "G16:0",
        "replacement": "", "preserved_text": [], "reason": "payment clause",
    }]}, rule, actual, ["p0"], policy, facts=_class_facts())
    assert not accepted
    assert any(entry.get("reason") == "template_slots_unresolved" for entry in rejected)


# ==========================================================================
# FL-D553 B14-03 / FL-D555 A3-F5 / A3-F6 / A3-F7 (2026-10-31 backend fixes)
# ==========================================================================

def _qa_bound_store(tmp_path):
    from fundlex import guide_store
    from fundlex.store import RunStore
    store = RunStore(tmp_path / "state-b1403")
    guide_store.ensure_builtin_guide(store)
    version = guide_store.get_version(store, "qa-owner", guide_store.BUILTIN_GUIDE_ID)
    return store, version


def _qa_contract_bytes() -> bytes:
    import io

    from docx import Document
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph("公开合同正文示例")
    document.save(stream)
    return stream.getvalue()


def _qa_submit_task(store, version):
    from fundlex.tasks import TaskStore
    payload = _qa_contract_bytes()
    tasks = TaskStore(store)
    task = tasks.create("qa-owner", "暂停位回归任务", {"version": "v1", "sha256": ""},
                        [{"client_id": "c1", "name": "contract.docx", "size": len(payload)}],
                        engine_id="recall_first", guide_version_id=version["id"],
                        guide_rules_sha256=version.get("sha256") or version["rules_sha256"],
                        mode="delivery")
    receipts = tasks.uploads("qa-owner", task["id"],
                             [{"client_id": "c1", "name": "contract.docx", "data": payload}])
    assert receipts["receipts"][0]["status"] == "accepted"
    first = receipts["receipts"][0]
    return tasks, task["id"], first["batch_id"], first["document_id"], payload


def _qa_complete_report(source, final_path, redline_path):
    from fundlex.docx import generate_unchanged_artifacts, validate_edit_plan
    plan = validate_edit_plan(source, [], {})
    validation = generate_unchanged_artifacts(source, plan, redline_path, final_path)
    return {"engine_id": "recall_first", "schema_version": "3", "execution_mode": "delivery",
            "qualification_status": "eligible", "delivery_status": "complete",
            "output_validation": {"kind": "recall_validated_unchanged",
                                  "checks": list(validation.checks),
                                  "final_sha256": validation.final_sha256,
                                  "redline_sha256": validation.redline_sha256}}


def test_task_pause_stale_bit_healed_when_last_batch_completes(tmp_path):
    """B14-03: pause during an in-flight run must not leave tasks.paused=1
    next to a completed batch once the running document finishes."""
    from fundlex.store import RunStore
    store: RunStore
    store, version = _qa_bound_store(tmp_path)
    tasks, task_id, batch_id, document_id, payload = _qa_submit_task(store, version)
    source = tmp_path / "input.docx"
    source.write_bytes(payload)
    claimed = store.claim(lease_seconds=300)
    assert claimed is not None
    snapshot = tasks.control("qa-owner", task_id, "pause")
    assert snapshot["status"] == "paused"
    with store._connect() as db:
        assert db.execute("SELECT paused FROM tasks WHERE id=?", (task_id,)).fetchone()["paused"] == 1
    report = _qa_complete_report(source, tmp_path / "final.docx", tmp_path / "redline.docx")
    store.finish(document_id, claimed["fencing_token"], report=report,
                 artifacts={"final": tmp_path / "final.docx", "redline": tmp_path / "redline.docx"})
    with store._connect() as db:
        batch = db.execute("SELECT status FROM batches WHERE id=?", (batch_id,)).fetchone()
        task_row = db.execute("SELECT paused,pause_reason FROM tasks WHERE id=?", (task_id,)).fetchone()
    assert batch["status"] == "completed"
    assert task_row["paused"] == 0 and not task_row["pause_reason"]
    assert tasks.get("qa-owner", task_id)["status"] == "completed"


def test_task_pause_on_fully_terminal_task_does_not_stick(tmp_path):
    """B14-03: pausing an already-completed task must not leave a stale bit,
    while pausing a task that still has pending work must keep it."""
    store, version = _qa_bound_store(tmp_path)
    tasks, task_id, _batch_id, _doc_id, payload = _qa_submit_task(store, version)
    # Still pending: the bit must stay.
    tasks.control("qa-owner", task_id, "pause")
    with store._connect() as db:
        assert db.execute("SELECT paused FROM tasks WHERE id=?", (task_id,)).fetchone()["paused"] == 1
        db.execute("UPDATE documents SET status='succeeded',finished_at=1,updated_at=1")
        db.execute("UPDATE batches SET status='completed'")
    snapshot = tasks.control("qa-owner", task_id, "pause")
    assert snapshot["status"] == "completed"
    with store._connect() as db:
        assert db.execute("SELECT paused FROM tasks WHERE id=?", (task_id,)).fetchone()["paused"] == 0


def test_terminal_pause_required_retry_clears_task_pause(tmp_path):
    """B14-03: a terminal pause-required failure leaves no batch to pause,
    so the stale task bit must be healed in the same transaction."""
    store, version = _qa_bound_store(tmp_path)
    tasks, task_id, batch_id, document_id, payload = _qa_submit_task(store, version)
    source = tmp_path / "input.docx"
    source.write_bytes(payload)
    claimed = store.claim(lease_seconds=300, max_attempts=1)
    assert claimed is not None
    store.retry(document_id, claimed["fencing_token"], error_code="MODEL_CIRCUIT_OPEN",
                max_attempts=1, report={"execution_mode": "delivery"})
    with store._connect() as db:
        assert db.execute("SELECT status FROM batches WHERE id=?", (batch_id,)).fetchone()["status"] == "completed"
        assert db.execute("SELECT paused FROM tasks WHERE id=?", (task_id,)).fetchone()["paused"] == 0


def _qa_recall_edits_report(validation, *, manifest_edit_id, status="complete", kind="recall_validated_edits"):
    report = {"engine_id": "recall_first", "schema_version": "3", "execution_mode": "delivery",
              "delivery_status": status,
              "output_validation": {"kind": kind,
                                    "checks": sorted(store_module._RECALL_EDIT_CHECKS),
                                    "final_sha256": validation["final"],
                                    "redline_sha256": validation["redline"]},
              "plan": {"count": 1, "edits": [{"rule_id": "G01", "target_id": "T1"}]},
              "revision_manifest": [{"edit_id": manifest_edit_id, "location": "p0"}]}
    if status == "incomplete":
        report["unresolved"] = [{"kind": "target", "rule_id": "G01"}]
    return report


def test_delivery_cross_checks_revision_manifest_against_plan_edits(tmp_path):
    """A3-F5: a manifest entry without a matching planned edit must fail
    closed; a bound manifest must be accepted for both produced-pair kinds."""
    from fundlex.store import sha256_file, validate_delivery
    final, redline = tmp_path / "final.bin", tmp_path / "redline.bin"
    final.write_bytes(b"final")
    redline.write_bytes(b"redline")
    validation = {"final": sha256_file(final), "redline": sha256_file(redline)}
    pair = {"final": final, "redline": redline}
    ok = _qa_recall_edits_report(validation, manifest_edit_id="G01:T1")
    validate_delivery(ok, pair)
    drifted = _qa_recall_edits_report(validation, manifest_edit_id="G01:GHOST")
    with pytest.raises(ValueError, match="REVISION_MANIFEST_PLAN_MISMATCH"):
        validate_delivery(drifted, pair)
    working_pair = {"working_final": final, "working_redline": redline}
    working = _qa_recall_edits_report(validation, manifest_edit_id="G01:GHOST",
                                      status="incomplete", kind="recall_working_edits")
    with pytest.raises(ValueError, match="REVISION_MANIFEST_PLAN_MISMATCH"):
        validate_delivery(working, working_pair)


def test_document_download_urls_filtered_by_execution_mode(tmp_path):
    """A3-F6: download_urls must mirror the get_artifact mode binding —
    no evaluation URLs on delivery documents, no selected URLs on
    evaluation documents."""
    store, version = _qa_bound_store(tmp_path)
    tasks, _task_id, batch_id, document_id, payload = _qa_submit_task(store, version)
    with store._connect() as db:
        db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?)",
                   (document_id, "final", "objects/x", "0" * 64, 1))
        db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?)",
                   (document_id, "evaluation_final", "objects/y", "0" * 64, 1))
    doc = store.get_document("qa-owner", batch_id, document_id)
    assert "final" in doc["download_urls"]
    assert "evaluation_final" not in doc["download_urls"]
    with store._connect() as db:
        db.execute("UPDATE documents SET execution_mode='evaluation' WHERE id=?", (document_id,))
        db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?)",
                   (document_id, "selected_final", "objects/z", "0" * 64, 1))
    doc = store.get_document("qa-owner", batch_id, document_id)
    assert "evaluation_final" in doc["download_urls"]
    assert "selected_final" not in doc["download_urls"]


def test_finish_mode_fence_applies_without_task_binding(tmp_path):
    """A3-F7: a report may never relabel batches.mode, even for a batch not
    bound to a first-class task."""
    from fundlex.store import Conflict, RunStore
    store = RunStore(tmp_path / "state-a3f7")
    store.create_batch(owner="qa-owner", ruleset_version="v1",
                       uploads=[("contract.docx", _qa_contract_bytes())])
    claimed = store.claim(lease_seconds=300)
    assert claimed is not None
    report = {"execution_mode": "evaluation", "delivery_status": "excluded",
              "engine_id": "v2", "schema_version": "2"}
    with pytest.raises(Conflict, match="EXECUTION_MODE_MISMATCH"):
        store.finish(claimed["id"], claimed["fencing_token"], report=report, artifacts={})


# --- FL-D570: DUPLICATE_SITE_DIVERGED span-boundary false positive ------------

def _fl_d570_setup():
    """Rebuild the B04 p854/p1261 shape: one duplicated numbered clause edited
    with different spans.  The body edit starts after the "4、" marker, the
    summary edit covers the whole paragraph; the new clause content is identical
    in both copies."""
    clause_old = ("由于本基金A类基金份额不收取销售服务费，而C类基金份额收取销售服务费，"
                  "各基金份额类别对应的可分配收益将有所不同。")
    tail = "本基金同一类别的每一基金份额享有同等分配权；"
    before = "4、" + clause_old + tail
    clause_new = ("由于本基金A类基金份额和C类基金份额费用收取不同，"
                  "各基金份额类别对应的可分配收益将有所不同。")
    body_edit = {"rule_id": "G18", "location": "p0", "start": 2,
                 "end": 2 + len(clause_old), "replacement": clause_new}
    summary_edit = {"rule_id": "G18", "location": "p1", "start": 0,
                    "end": len(before), "replacement": clause_new + tail}
    after_body = "4、" + clause_new + tail
    rules = {"G18": {"rule_id": "G18", "operations": [
        {"op": "replace", "old_text": clause_old, "new_text": clause_new}]}}
    return before, body_edit, summary_edit, after_body, rules


def test_duplicate_site_span_boundary_difference_is_not_diverged():
    """FL-D570: identical clause copies edited with different span boundaries —
    one final paragraph keeps only the list-item enumeration prefix, the clause
    content is identical — must NOT be blocked by DUPLICATE_SITE_DIVERGED."""
    from fundlex.generation.claim_replay import replay_claims
    before, body_edit, summary_edit, after_body, rules = _fl_d570_setup()
    # summary replacement == clause_new + tail; body keeps the "4、" prefix.
    after_summary = summary_edit["replacement"]
    replay = replay_claims(
        [body_edit, summary_edit], Inspection([before, before]),
        Inspection([after_body, after_summary]), rules_by_id=rules)
    codes = {failure["code"] for failure in replay["failures"]}
    assert "DUPLICATE_SITE_DIVERGED" not in codes, replay["failures"]


def test_duplicate_site_true_divergence_still_fails_closed():
    """FL-D570 mutation self-check: copies genuinely edited to different clause
    wording must still be blocked by DUPLICATE_SITE_DIVERGED (fail-closed)."""
    from fundlex.generation.claim_replay import replay_claims
    before, body_edit, summary_edit, after_body, rules = _fl_d570_setup()
    diverged_clause = ("由于本基金A类基金份额和C类基金份额费用收取比例不同，"
                       "各基金份额类别对应的可分配收益将有所不同。")
    summary_edit = dict(summary_edit,
                        replacement=diverged_clause + summary_edit["replacement"][
                            len(body_edit["replacement"]):])
    after_summary = diverged_clause + after_body[len("4、" + body_edit["replacement"]):]
    replay = replay_claims(
        [body_edit, summary_edit], Inspection([before, before]),
        Inspection([after_body, after_summary]), rules_by_id=rules)
    codes = {failure["code"] for failure in replay["failures"]}
    assert "DUPLICATE_SITE_DIVERGED" in codes


def test_duplicate_site_dropped_business_tail_still_fails_closed():
    """FL-D570 adverse mutation: enumeration-prefix normalization must NOT mask a
    copy that deleted a whole business sentence from the duplicated paragraph."""
    from fundlex.generation.claim_replay import replay_claims
    before, body_edit, summary_edit, after_body, rules = _fl_d570_setup()
    # The summary copy's edit covers the whole paragraph but drops the tail
    # sentence entirely: a real divergence of disposition, not a boundary diff.
    summary_edit = dict(summary_edit, replacement=body_edit["replacement"])
    replay = replay_claims(
        [body_edit, summary_edit], Inspection([before, before]),
        Inspection([after_body, body_edit["replacement"]]), rules_by_id=rules)
    codes = {failure["code"] for failure in replay["failures"]}
    assert "DUPLICATE_SITE_DIVERGED" in codes


# ==========================================================================
# FL-D571: ONE_OF canonical-equivalence coalescing in merge_edits (B03 G14)
# FL-D572: G08 disclosure tail / G09+B15 / G18+B01 / G13+B12 excise
# ==========================================================================

from fundlex.recall import PlannedEdit, merge_edits


class _G14Obligations:
    """Minimal obligations stub: G14:3/4/5 share one ONE_OF group + new_text."""

    CANONICAL = "基金管理人可以适当调低基金申购费率和销售服务费率。"

    def __init__(self, new_texts=None):
        self._records = {}
        for key in ("G14:3", "G14:4", "G14:5"):
            self._records[key] = SimpleNamespace(
                spec=SimpleNamespace(one_of_group="G14:history:multiple",
                                     new_text=(new_texts or {}).get(key, self.CANONICAL)))

    def record(self, key):
        return self._records.get(key)


def _g14_edit(target_id, key, start, end, replacement):
    return PlannedEdit(target_id=target_id, rule_id="G14", location="p0",
                       start=start, end=end, replacement=replacement,
                       operation="replace", content_source="tier1_template",
                       evidence={}, operation_keys=(key,), obligation_ids=())


_G14_SOURCE = "基金管理人可以适当调低基金申购费率、基金赎回费率、基金转换费率和基金销售服务费率。"


def test_one_of_canonical_drift_coalesces_instead_of_double_drop():
    """B03 replay: Y004 (canonical minus 。), Y005+T014 (canonical, one wider
    span) used to collapse into RECALL_EDIT_OVERLAP and drop BOTH sides, leaving
    G14:3/4/5 unplanned.  Canonical equivalence must coalesce them into one
    edit that carries every operation key."""
    obligations = _G14Obligations()
    canonical = obligations.CANONICAL
    y004 = _g14_edit("Y004", "G14:3", 0, 24, canonical.removesuffix("。"))
    t014 = _g14_edit("T014", "G14:5", 0, len(_G14_SOURCE), canonical)
    y005 = _g14_edit("Y005", "G14:4", 0, len(_G14_SOURCE), canonical)
    merged, conflicts, covered = merge_edits([y004, t014, y005],
                                             Inspection([_G14_SOURCE]), obligations)
    assert conflicts == []
    assert len(merged) == 1
    edit, _components = merged[0]
    assert edit.replacement == canonical
    assert set(edit.operation_keys) == {"G14:3", "G14:4", "G14:5"}
    assert set(covered) == {"Y004", "Y005"}


def test_one_of_double_drift_stays_an_honest_conflict():
    """Abuse guard: when NEITHER side matches the shared canonical new_text the
    overlap is a real conflict — coalescing must not become a silent picker."""
    obligations = _G14Obligations()
    drifted_a = _g14_edit("Y004", "G14:3", 0, len(_G14_SOURCE),
                          "基金管理人可以适当调低基金申购费率和基金销售服务费率。")
    drifted_b = _g14_edit("Y005", "G14:4", 0, len(_G14_SOURCE),
                          "基金管理人可以适当调低申购费率和销售服务费率。")
    merged, conflicts, covered = merge_edits([drifted_a, drifted_b],
                                             Inspection([_G14_SOURCE]), obligations)
    assert covered == []
    assert any(item["code"] == "RECALL_EDIT_OVERLAP" for item in conflicts)
    # Both sides stay in the plan and the conflict is reported — nothing is
    # silently picked or silently dropped.
    assert {edit.target_id for edit, _components in merged} == {"Y004", "Y005"}


# --- FL-D572 / B12: contained delete excised from an outer replacement -------

_B12_SENTENCE = "对于持续持有期少于7日的投资者收取不低于1.5%的赎回费，并将上述赎回费全额计入基金财产。"
_B12_PARAGRAPH = ("赎回费由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
                  "赎回费率在基金合同、招募说明书中列示；" + _B12_SENTENCE)


def _b12_edits(outer_replacement):
    start = _B12_PARAGRAPH.index(_B12_SENTENCE)
    outer = PlannedEdit(target_id="Y002", rule_id="G12", location="p0",
                        start=0, end=len(_B12_PARAGRAPH), replacement=outer_replacement,
                        operation="replace", content_source="survey_replace",
                        evidence={}, operation_keys=("G12:0",), obligation_ids=())
    delete = PlannedEdit(target_id="T013", rule_id="G13", location="p0",
                         start=start, end=start + len(_B12_SENTENCE), replacement="",
                         operation="replace", content_source="tier1_delete",
                         evidence={}, operation_keys=("G13:0",), obligation_ids=())
    return outer, delete


def test_replace_keeps_covered_delete_by_excising_the_sentence():
    """B12: the G12 wide-span replacement still carried the 7-day/1.5% sentence
    while the G13 delete vanished from the ledger (fake complete).  The merge
    must cut the sentence out of the replacement and normalise the seam, not
    swallow the delete or fail the whole contract."""
    outer_replacement = _B12_PARAGRAPH  # retains the to-be-deleted sentence
    outer, delete = _b12_edits(outer_replacement)
    merged, conflicts, covered = merge_edits([outer, delete],
                                             Inspection([_B12_PARAGRAPH]), None)
    assert conflicts == []
    assert len(merged) == 1
    edit, _components = merged[0]
    assert _B12_SENTENCE not in edit.replacement
    assert edit.replacement.endswith("列示。")  # "；。" seam normalised
    assert set(edit.operation_keys) == {"G12:0", "G13:0"}
    assert covered == ["T013"]


def test_excise_ambiguous_slice_stays_an_honest_conflict():
    """A slice appearing twice in the replacement cannot be cut safely; the
    overlap must stay a reported conflict."""
    outer_replacement = _B12_PARAGRAPH + _B12_SENTENCE
    outer, delete = _b12_edits(outer_replacement)
    merged, conflicts, covered = merge_edits([outer, delete],
                                             Inspection([_B12_PARAGRAPH]), None)
    assert covered == []
    assert any(item["code"] == "RECALL_EDIT_OVERLAP" for item in conflicts)


# --- FL-D572 / B05: G08 keeps a wider disclosure enumeration -----------------

def test_g08_preserves_wider_disclosure_vehicle_enumeration():
    """B05 label: the contract enumerates 招募说明书及基金产品资料概要; the
    template only says 招募说明书.  The edit must keep the source enumeration."""
    from fundlex.generation.template import plan_policy_replacement
    before = "本基金的申购费率由基金管理人决定，并在招募说明书及基金产品资料概要中列示。"
    instantiated = "申购费率由基金管理人决定，并在招募说明书中列示。"
    result = plan_policy_replacement(before, instantiated, "G08")
    assert result is not None
    assert result.replacement == "申购费率由基金管理人决定，并在招募说明书及基金产品资料概要中列示。"
    assert result.evidence["disclosure_tail_preserved"] is True


def test_g08_disclosure_tail_untouched_when_source_matches_template():
    """Control: an enumeration identical to (or narrower/disjoint vs) the
    template must NOT rewrite the template wording."""
    from fundlex.generation.template import plan_policy_replacement
    instantiated = "申购费率由基金管理人决定，并在基金合同、招募说明书中列示。"
    # Clause already matches the template verbatim -> nothing to change.
    assert plan_policy_replacement(instantiated, instantiated, "G08") is None
    narrower = "本基金的申购费率由基金管理人决定，并在招募说明书中列示。"
    result = plan_policy_replacement(narrower, instantiated, "G08")
    assert result is not None
    assert result.replacement == instantiated
    assert result.evidence["disclosure_tail_preserved"] is False


# --- FL-D572 / B15: G09 net-redemption formula variant -----------------------

_B15_BEFORE = ("赎回金额为按实际确认的有效赎回份额乘以申请当日基金份额净值的金额，"
               "净赎回金额为赎回金额扣除相应的费用的金额")


def test_g09_net_redemption_formula_splices_both_kernels():
    """B15 label: formula-wording contracts need BOTH the class-qualified NAV
    and the 扣除或加上 fee kernel; the half-changed composed edit was scored
    as partial.  The new variant pairs produce the complete splice."""
    from fundlex.generation.template import plan_g09_splice
    result = plan_g09_splice(_B15_BEFORE, [])
    assert result is not None
    assert "当日该类基金份额的基金份额净值" in result.replacement
    assert "扣除或加上相应的费用" in result.replacement
    assert "扣除相应的费用的金额" not in result.replacement


def test_g09_partial_splice_still_refused():
    """A contract wording whose fee kernel is unknown must NOT ship a NAV-only
    half change — the completeness gate stays fail-closed."""
    from fundlex.generation.template import plan_g09_splice
    only_nav = "赎回金额为按实际确认的有效赎回份额乘以申请当日基金份额净值的金额确定"
    assert plan_g09_splice(only_nav, []) is None


# --- FL-D572 / B01: G18 reason-clause splice keeps the contract subject ------

def test_g18_reason_splice_without_subject_insertion():
    """B01 label: “由于A类基金份额不收取而C类基金份额收取销售服务费” must become
    “由于A类基金份额和C类基金份额费用收取不同” — no template-injected 本基金."""
    from fundlex.generation.template import _G18_REASON_PAIRS, plan_g18_splice
    before = ("由于A类基金份额不收取而C类基金份额收取销售服务费，"
              "各基金份额类别对应的可分配收益将有所不同。")
    result = plan_g18_splice(before, list(_G18_REASON_PAIRS))
    assert result is not None
    assert "由于A类基金份额和C类基金份额费用收取不同" in result.replacement
    assert "本基金" not in result.replacement
    assert "不收取而C类基金份额收取销售服务费" not in result.replacement


def test_g18_reason_splice_preserves_existing_subject():
    """B02-type contracts already carry 本基金 as the subject: the splice must
    preserve it verbatim instead of rewriting the whole clause to template text."""
    from fundlex.generation.template import _G18_REASON_PAIRS, plan_g18_splice
    before = ("由于本基金A类基金份额不收取销售服务费，而C类基金份额收取销售服务费，"
              "各基金份额类别对应的可分配收益将有所不同。")
    result = plan_g18_splice(before, list(_G18_REASON_PAIRS))
    assert result is not None
    assert "由于本基金A类基金份额和C类基金份额费用收取不同" in result.replacement
    assert "不收取销售服务费，而C类基金份额收取销售服务费" not in result.replacement


def test_g18_unrelated_clause_refused():
    from fundlex.generation.template import _G18_REASON_PAIRS, plan_g18_splice
    assert plan_g18_splice("本基金的收益分配原则由基金管理人拟订。",
                           list(_G18_REASON_PAIRS)) is None


# --- FL-D571/FL-D572: guide certification stays valid after the G13 variant --

def test_guide_recertified_with_g13_variant():
    """The G13:0 delete gained the B12 contract wording as a rule-level
    old_text_variant; the document must still certify against its own hash
    (operation_count unchanged at 34)."""
    import json as _json
    from fundlex import guide as guide_module
    root = Path(__file__).resolve().parents[1]
    doc = guide_module.load_guide_document(root / "guides/builtin_guide_v1.json")
    result = guide_module.validate_runtime_guide(doc)
    assert result["state"] == "CERTIFIED"
    assert result["rule_count"] == 22
    assert result["operation_count"] == 34
    assert (doc["certification"]["guide_document_sha256"]
            == guide_module.guide_document_sha256(doc))
    g13 = next(rule for rule in doc["groups"] if rule["rule_id"] == "G13")
    assert any("不低于1.5%的赎回费" in variant
               for variant in g13.get("old_text_variants") or [])
    del _json
