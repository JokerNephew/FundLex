"""Human guide editing, AI→Human diff and version persistence."""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any
from ..store import Conflict

from .export import build_evidence_package, export_guide_docx, render_evidence_html
from .models import GuideItem, sha256_json, stable_id, utc_now
from .store import GuideGenerationStore

EDITABLE_FIELDS = ("title", "business_requirement", "instruction", "applicability",
                   "conditions", "exceptions", "old_text_patterns", "new_text",
                   "new_text_origin")


def _clean_value(field: str, value: Any) -> Any:
    if field in {"conditions", "exceptions", "old_text_patterns"}:
        if isinstance(value, str):
            return [item.strip() for item in value.splitlines() if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("FIELD_MUST_BE_LIST")
    if field == "new_text_origin":
        if value not in {"regulation_verbatim", "model_drafted", "contract_pattern_adapted"}:
            raise ValueError("NEW_TEXT_ORIGIN_INVALID")
        return value
    return str(value or "").strip()


def update_guide_item(store: GuideGenerationStore, run_id: str, item_id: str,
                      changes: dict[str, Any], author: str, *,
                      expected_current_version_id: str | None = None) -> dict[str, Any]:
    with store.candidate_transaction(run_id):
        candidate = store.get_candidate(run_id)
        if (expected_current_version_id is not None
                and expected_current_version_id != candidate["current_version_id"]):
            raise Conflict("CANDIDATE_VERSION_CONFLICT")
        return _update_guide_item(store, run_id, item_id, changes, author)


def _update_guide_item(store: GuideGenerationStore, run_id: str, item_id: str,
                       changes: dict[str, Any], author: str) -> dict[str, Any]:
    run = store.get_run(run_id)
    if run.get("status") not in {"complete", "complete_with_unresolved", "completed"}:
        raise ValueError("RUN_NOT_COMPLETE")
    candidate = store.get_candidate(run_id)
    if candidate.get("status") == "published":
        raise ValueError("CANDIDATE_PUBLISHED_IMMUTABLE")
    items = store.get_guide_items(run_id)
    baseline_items = next((version["payload"].get("guide_items")
                           for version in candidate["versions"]
                           if version["payload"].get("guide_items")), [])
    ai_item = next((item for item in baseline_items if item["guide_item_id"] == item_id), {})
    target = next((item for item in items if item.guide_item_id == item_id), None)
    if target is None:
        raise KeyError("guide item not found")
    change_records: list[dict[str, Any]] = []
    for field in EDITABLE_FIELDS:
        if field not in changes:
            continue
        new_value = _clean_value(field, changes[field])
        old_value = getattr(target, field)
        if old_value == new_value:
            continue
        setattr(target, field, new_value)
        change_records.append({
            "change_id": f"HC-{uuid.uuid4().hex}",
            "guide_item_id": item_id,
            "change_type": "rewrite",
            "field": field,
            "ai_value": ai_item.get(field, old_value),
            "previous_value": old_value,
            "human_value": new_value,
            "requirement_ids": list(target.requirement_ids),
            "impact_ids": list(target.impact_ids),
            "created_at": utc_now(),
            "author": author,
        })
    if not change_records:
        return {"item": target.to_dict(), "changes": [], "version_no": 0}
    target.version += 1
    target.status = "human_edited"
    target.quality_status = "human_review_pending"
    store.replace_guide_items(run_id, items)
    for change in change_records:
        store.add_human_change(run_id, change)
    versions = store.list_human_versions(run_id)
    version_no = (max((item.get("version_no", 0) for item in versions), default=0) + 1)
    store.save_human_version(run_id, version_no, author, {
        "version_no": version_no, "author": author, "created_at": utc_now(),
        "items": [item.to_dict() for item in items],
        "change_ids": [change["change_id"] for change in change_records],
        "base_ai_items_sha256": sha256_json(baseline_items),
    })
    # Preserve the AI-only artifact on the first human edit, then regenerate the
    # current business DOCX from the human-edited items.
    ai_artifact = store.get_artifact(run_id, "guide_ai")
    current_artifact = store.get_artifact(run_id, "guide")
    run_dir = store.store.objects / "guide_generation" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    if not ai_artifact and current_artifact:
        source = store.store.object_path(current_artifact["object_key"])
        target_path = run_dir / "generated_guide_ai.docx"
        if source.is_file():
            target_path.write_bytes(source.read_bytes())
            data = target_path.read_bytes()
            store.put_artifact(run_id, "guide_ai",
                               str(target_path.relative_to(store.store.objects)),
                               hashlib.sha256(data).hexdigest(), len(data))
    docx_path = run_dir / f"human-{version_no}-{uuid.uuid4().hex}.docx"
    export = export_guide_docx(items, docx_path,
                               title="新法规候选修改指引（人工修订版）",
                               regulation_title=run.get("title") or "")
    store.put_artifact(run_id, "guide", str(docx_path.relative_to(store.store.objects)),
                       export["sha256"], export["size"])
    store.update_run(run_id, guide_sha256=export["sha256"],
                     payload={**(run.get("payload") or {}), "human_edited": True,
                              "human_version": version_no})
    candidate_version = store.create_candidate_version(
        run_id, status="human_draft",
        payload={
            "schema_version": "candidate-guide-version-1",
            "run_id": run_id,
            "guide_items": [item.to_dict() for item in items],
            "human_version_no": version_no,
            "human_review_override": run.get("qualification_status") != "candidate_ready",
            "source_qualification_status": run.get("qualification_status"),
            "base_ai_items_sha256": sha256_json(baseline_items),
            "finalize": (run.get("payload") or {}).get("finalize", {}),
            "human_change_ids": [change["change_id"] for change in change_records],
            "guide_artifact": {"kind": "guide", "sha256": export["sha256"],
                               "size": export["size"],
                               "object_key": str(docx_path.relative_to(store.store.objects))},
        },
        content_sha256=sha256_json([item.to_dict() for item in items]),
        human_version_no=version_no,
        expected_current_version_id=candidate["current_version_id"])
    store.update_run(run_id, payload={**(store.get_run(run_id).get("payload") or {}),
                                      "candidate_version_id": candidate_version["candidate_version_id"],
                                      "candidate_version_no": candidate_version["version_no"]})
    rebuild_evidence(store, run_id)
    return {"item": target.to_dict(), "changes": change_records, "version_no": version_no,
            "guide_sha256": export["sha256"], "candidate_version": candidate_version}


def rebuild_evidence(store: GuideGenerationStore, run_id: str) -> dict[str, Any]:
    run = store.get_run(run_id)
    payload = run.get("payload") or {}
    blocks = [block.to_dict() for block in store.get_blocks(run_id)]
    requirements = [item.to_dict() for item in store.get_requirements(run_id)]
    impacts = [item.to_dict() for item in store.get_impacts(run_id)]
    items = [item.to_dict() for item in store.get_guide_items(run_id)]
    findings = store.get_findings(run_id)
    coverage = store.get_coverage(run_id)
    applicability = store.get_applicability(run_id)
    residual_rounds = store.get_residual_rounds(run_id)
    model_calls = store.get_model_calls(run_id)
    local = [item.to_dict() for item in store.get_local(run_id)]
    families = store.get_families(run_id)
    model_identity = payload.get("model_identity") or {}
    engine_package = {"status": run.get("engine_status", "not_run"),
                      "runs": store.get_engine_runs(run_id),
                      "results": store.get_engine_results(run_id)}
    package = build_evidence_package(
        run={**run, "stats": store.stats(run_id)}, regulation={
            "document_id": run.get("regulation_document_id"), "title": run.get("title"),
            "source_type": run.get("source_type"), "source_sha256": run.get("source_sha256"),
            "document_sha256": run.get("regulation_document_sha256"), "blocks": blocks},
        requirements=requirements, impacts=impacts, local_candidates=local,
        families=families, guide_items=items, findings=findings, coverage=coverage,
        applicability=applicability, residual_rounds=residual_rounds,
        model_calls=model_calls, model_identity=model_identity,
        engine_compatibility=engine_package,
        human_versions=store.list_human_versions(run_id),
        human_changes=store.list_human_changes(run_id))
    run_dir = store.store.objects / "guide_generation" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    export_id = uuid.uuid4().hex
    evidence_path = run_dir / f"evidence-{export_id}.json"
    evidence_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")
    html_path = run_dir / f"evidence-{export_id}.html"
    html_path.write_text(render_evidence_html(package), encoding="utf-8")
    evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    report_sha = hashlib.sha256(html_path.read_bytes()).hexdigest()
    store.put_artifact(run_id, "evidence_json",
                       str(evidence_path.relative_to(store.store.objects)),
                       evidence_sha, evidence_path.stat().st_size)
    store.put_artifact(run_id, "evidence_html",
                       str(html_path.relative_to(store.store.objects)),
                       report_sha, html_path.stat().st_size)
    store.update_run(run_id, evidence_sha256=evidence_sha, report_sha256=report_sha,
                     payload={**(run.get("payload") or {}), "evidence_rebuilt_for_human_edit": True})
    return {"evidence_sha256": evidence_sha, "report_sha256": report_sha}
