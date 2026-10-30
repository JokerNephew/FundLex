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
