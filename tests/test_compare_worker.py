import io
import threading

import pytest
from docx import Document

from fundlex.compare.service import CompareService
from fundlex.compare.store import CompareStore
from fundlex.compare.worker import CompareWorker
from fundlex.db import DatabaseError
from fundlex.docx import DocxError
from fundlex.store import RunStore


def _docx(text):
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


def _queued(tmp_path, left=b"", right=b""):
    left = left or _docx("left")
    right = right or _docx("right")
    store = CompareStore(RunStore(tmp_path))
    task = store.create("alice", "compare", [{
        "client_pair_id": "pair", "label": "pair",
        "left": {"client_id": "left", "name": "left.docx", "size": len(left)},
        "right": {"client_id": "right", "name": "right.docx", "size": len(right)},
    }])
    store.upload("alice", task["id"], [
        {"client_id": "left", "name": "left.docx", "data": left},
        {"client_id": "right", "name": "right.docx", "data": right},
    ])
    store.seal("alice", task["id"])
    return store, task


def _valid_result(left, right):
    return CompareService().compare_bytes(left, right, left_filename="left.docx",
                                          right_filename="right.docx") | {}


def test_finish_rejects_missing_type_spans(tmp_path):
    left, right = _docx("left"), _docx("right")
    store, task = _queued(tmp_path, left, right)
    job = store.claim()
    result = _valid_result(left, right)
    result["diffs"] = [{"id": "D0001", "type": "modify"}]
    result["summary"] = {"total": 1, "modify": 1, "insert": 0, "delete": 0}
    with pytest.raises(ValueError, match="COMPARE_RESULT_INVALID"):
        store.finish(job["id"], job["fencing_token"], result)
    assert store.get_pair("alice", job["id"])["status"] == "leased"


def test_finish_rejects_overlapping_spans_before_publish(tmp_path):
    left, right = _docx("left"), _docx("right")
    store, task = _queued(tmp_path, left, right)
    job = store.claim()
    result = _valid_result(left, right)
    block = "L000000"
    result["diffs"] = [
        {"id": "D0001", "type": "delete",
         "left": {"block_id": block, "start": 0, "end": 3, "text": "lef"},
         "left_spans": [{"block_id": block, "start": 0, "end": 3, "text": "lef"}],
         "right": None,
         "right_anchor": {"block_id": "R000000", "start": 0, "end": 0, "text": ""}},
        {"id": "D0002", "type": "delete",
         "left": {"block_id": block, "start": 2, "end": 4, "text": "ft"},
         "left_spans": [{"block_id": block, "start": 2, "end": 4, "text": "ft"}],
         "right": None,
         "right_anchor": {"block_id": "R000000", "start": 0, "end": 0, "text": ""}},
    ]
    result["summary"] = {"total": 2, "modify": 0, "insert": 0, "delete": 2}
    with pytest.raises(ValueError, match="COMPARE_RESULT_INVALID"):
        store.finish(job["id"], job["fencing_token"], result)


class _TransientThenSuccess:
    def __init__(self):
        self.calls = 0

    def compare(self, *args, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise OSError("temporary object read failure with sensitive path")
        return CompareService().compare(*args, **kwargs)


def test_worker_retries_transient_pair_failure_with_bounded_policy(tmp_path):
    store, task = _queued(tmp_path)
    processor = _TransientThenSuccess()
    worker = CompareWorker(store, processor, max_attempts=2)
    assert worker.run_once()
    pair_id = task["pairs"][0]["id"]
    assert store.get_pair("alice", pair_id)["status"] == "retry_wait"
    with store._connect() as db:
        db.execute("UPDATE compare_pairs SET lease_until=0 WHERE id=?", (pair_id,))
    assert worker.run_once()
    assert processor.calls == 2
    assert store.get_pair("alice", pair_id)["status"] == "succeeded"


def test_worker_retries_parse_oserror_then_succeeds(tmp_path, monkeypatch):
    store, task = _queued(tmp_path)
    calls = {"count": 0}
    from fundlex.compare import parser
    original = parser.parse_compare_document

    def flaky_parse(source, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("temporary storage read failure")
        return original(source, **kwargs)

    monkeypatch.setattr(parser, "parse_compare_document", flaky_parse)
    worker = CompareWorker(store, max_attempts=2)
    pair_id = task["pairs"][0]["id"]
    assert worker.run_once()
    assert store.get_pair("alice", pair_id)["status"] == "retry_wait"
    with store._connect() as db:
        db.execute("UPDATE compare_pairs SET lease_until=0 WHERE id=?", (pair_id,))
    assert worker.run_once()
    assert calls["count"] >= 3
    assert store.get_pair("alice", pair_id)["status"] == "succeeded"


def test_finish_maps_docx_parse_error_to_worker_fixed_code(tmp_path, monkeypatch):
    store, task = _queued(tmp_path)
    from fundlex.compare import parser

    def invalid_parse(*args, **kwargs):
        raise DocxError("MAIN_DOCUMENT_INVALID")

    monkeypatch.setattr(parser, "parse_compare_document", invalid_parse)
    assert CompareWorker(store).run_once()
    pair = store.get_pair("alice", task["pairs"][0]["id"])
    assert pair["status"] == "failed"
    assert pair["error_code"] == "COMPARE_PARSE_FAILED"


@pytest.mark.parametrize("error", [DocxError("XML_INVALID"), RuntimeError("secret path")])
def test_worker_persists_fixed_codes_for_permanent_or_unknown_errors(tmp_path, error):
    store, task = _queued(tmp_path)

    class Processor:
        def compare(self, *args, **kwargs):
            raise error

    assert CompareWorker(store, Processor()).run_once()
    pair = store.get_pair("alice", task["pairs"][0]["id"])
    assert pair["status"] == "failed"
    assert pair["error_code"] in {"COMPARE_PARSE_FAILED", "COMPARE_PROCESSING_FAILED"}
    assert "secret path" not in str(pair)


def test_worker_uses_max_attempts_for_retry_exhaustion(tmp_path):
    store, task = _queued(tmp_path)

    class Processor:
        def compare(self, *args, **kwargs):
            raise DatabaseError("temporary db outage")

    worker = CompareWorker(store, Processor(), max_attempts=2)
    pair_id = task["pairs"][0]["id"]
    assert worker.run_once()
    with store._connect() as db:
        db.execute("UPDATE compare_pairs SET lease_until=0 WHERE id=?", (pair_id,))
    assert worker.run_once()
    pair = store.get_pair("alice", pair_id)
    assert pair["status"] == "failed"
    assert pair["error_code"] == "COMPARE_TRANSIENT_FAILURE"


def test_run_forever_survives_transient_claim_failure():
    class Store:
        def __init__(self):
            self.calls = 0
            self.stop = threading.Event()

        def claim(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise DatabaseError("connection details must not be logged")
            self.stop.set()
            return None

    store = Store()
    CompareWorker(store).run_forever(poll_seconds=0, stop_event=store.stop)
    assert store.calls == 2


@pytest.mark.parametrize("side,anchor", [
    ("right", {"block_id": "BOGUS", "start": 0, "end": 0, "text": ""}),
    ("right", {"block_id": "R000000", "start": 100, "end": 100, "text": ""}),
    ("right", {"block_id": "R000000", "start": 0, "end": 1, "text": "r"}),
])
def test_finish_rejects_illegal_anchors(tmp_path, side, anchor):
    left, right = _docx("left"), _docx("right")
    store, _ = _queued(tmp_path, left, right)
    job = store.claim()
    result = _valid_result(left, right)
    span = {"block_id": "L000000", "start": 0, "end": 4, "text": "left"}
    result["diffs"] = [{"id": "D0001", "type": "delete", "left": span,
                        "right_anchor": anchor}]
    result["summary"] = {"total": 1, "modify": 0, "insert": 0, "delete": 1}
    with pytest.raises(ValueError, match="COMPARE_RESULT_INVALID"):
        store.finish(job["id"], job["fencing_token"], result)


def test_finish_rejects_projection_that_drops_an_anchor(tmp_path, monkeypatch):
    left, right = _docx("left"), _docx("right")
    store, _ = _queued(tmp_path, left, right)
    job = store.claim()
    result = _valid_result(left, right)
    from fundlex.compare import render
    original = render.render_compare_document

    def omit_one_marker(document, diffs, *, side):
        html = original(document, diffs, side=side)
        if side == "right":
            html = html.replace('data-diff-id="D0001"', 'data-omitted="D0001"')
        return html

    monkeypatch.setattr(render, "render_compare_document", omit_one_marker)
    with pytest.raises(ValueError, match="COMPARE_RESULT_INVALID"):
        store.finish(job["id"], job["fencing_token"], result)


def test_terminal_failure_persistence_outage_keeps_lease_for_reclaim(tmp_path, monkeypatch, caplog):
    store, task = _queued(tmp_path)

    class Processor:
        def compare(self, *args, **kwargs):
            raise RuntimeError("credential-or-contract-text")

    def unavailable(*args, **kwargs):
        raise DatabaseError("credential-or-contract-text")

    monkeypatch.setattr(store, "finish", unavailable)
    assert CompareWorker(store, Processor()).run_once()
    assert store.get_pair("alice", task["pairs"][0]["id"])["status"] == "running"
    assert "credential-or-contract-text" not in caplog.text


def test_source_corruption_is_permanent_with_fixed_code(tmp_path):
    store, task = _queued(tmp_path)
    pair_id = task["pairs"][0]["id"]
    entry = store.pair_inputs(pair_id)[0]
    path = store.store.object_path(entry["object_key"])
    data = path.read_bytes()
    path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    assert CompareWorker(store).run_once()
    pair = store.get_pair("alice", pair_id)
    assert pair["status"] == "failed"
    assert pair["error_code"] == "COMPARE_INPUT_INTEGRITY_FAILED"
