"""Independent semantic review of actual, validated DOCX output.

Review authorization binds the complete plan and both artifacts, rather than a
generator's proposal. No context is silently truncated. Long sections are split
at paragraph boundaries with one paragraph of overlap, within a fixed bound.
"""
from __future__ import annotations

import re
from typing import Any

from .docx import DocumentInspection
from .model import ModelError
from .v2 import canonical_sha, profile_facts_text, _rule_text, _event_summary, _check_requirement, _compact, _instantiate_slots
from .rules_v2 import PROMPT_VERSIONS_V2

MAX_WINDOWS_PER_ACTION = 3
# Shape-invalid answers are evidence failures for one window; budget, service and
# transport stops must keep propagating so a stopped run never keeps delivering.
CONTAINED_MODEL_CODES = {"MODEL_SCHEMA_INVALID"}
# Positive content checks are applied to the actual edited region of the artifact
# (not to the model's chosen quote); negative checks follow the quoted evidence.
REGION_CHECK_KINDS = {"template_exact", "contains_all", "direct_sales_clause"}
# Digit/condition checks govern the text this action writes; pre-existing fee
# rates and list numbers in the paragraph are preserved content, not violations.
DIGIT_CHECK_KINDS = {"classes_within_profile_and_no_digits", "no_digits_and_no_conditions"}
# Paragraph text keeps its list numbering ("5."/"57、") in DOCX; numbering is not
# policy content and must not trip digit or condition checks on the region.
_LIST_NUMBER = re.compile(r"(?m)^\s*\d{1,3}\s*[.、]")


def _region_text(region: str) -> str:
    """Artifact region without list numbering, for content checks."""
    return _LIST_NUMBER.sub("", region)


REVIEW_INSTRUCTION = (
    "独立核对实际DOCX产物。BEFORE为原件，AFTER为从生成文件重新读取的实际原文。"
    "必须返回且仅返回REQUIRED_IDS列出的requirement_id，每个恰好一次；"
    "逐项如实判定 satisfied/unsatisfied/unknown，缺少证据必须unknown；任何未通过项都会导致该动作被撤销。"
    "证据规则：satisfied一律引用AFTER的逐字连续原文；删除动作的delete_only要求引用BEFORE中被删除的完整业务目标（逐字），"
    "或引用AFTER中的邻近原文（代码将核验该目标已从产物编辑区域消失）；所有引文不得为空；"
    "不得为“不得保留/已被替换”类要求引用BEFORE旧文，应引用AFTER中替代后的原文；所有条目的引文均不得为空；"
    "若目标段落在AFTER已为空或被删除，可引用同窗口邻近段落的AFTER原文作为PRESERVATION/COVERAGE证据。"
    "本动作自身授权的删除或替换目标不计入PRESERVATION损失；PRESERVATION只评估授权范围之外的文字。"
    "BEFORE中除PUBLISHED_OLD_TEXT（规则旧句，允许类别前缀/措辞差异）及其他动作授权修改覆盖的内容外，"
    "其余文字必须原样保留在AFTER；缺失即为PRESERVATION不通过。"
    "OTHER_AUTHORIZED_EDITS列出同一窗口内其他动作的已授权修改（含授权删除）；由这些授权造成的差异不构成本动作的PRESERVATION失败，"
    "但本动作不得删除或改动自身授权范围之外的任何内容。"
    "要求只对本动作目标适用，不要求修改其他业务条款。"
    "“不得含数字/条件”类要求以本动作新写入的改写文字为准；合同原有的费率数字、编号与保留文字不属于违反。"
    "PRESERVATION：未丢失必须保留的内容、无无依据新增、余文与指引不矛盾；"
    "COVERAGE：所见范围内本动作所有应改位置均已处理，不能只核对新文。"
    "窗口间有重叠，coverage_locations为本窗口所见范围；EDIT_LOCATIONS为空的窗口仅核对PRESERVATION。"
    "不得信任生成者的解释；输出action_id、requirement_id、result、evidence_quote、evidence_source。"
    "REQUIRED_IDS："
)


def _window_items(gateway: Any, context: str, required_ids: list[str],
                  prompt_version: str, extra_notes: str = "") -> tuple[list[dict], list[dict], str | None]:
    """Ask once, then repair missing ids with one bounded follow-up request.

    A schema-invalid answer (``ModelError``) is contained here: it fails this
    window closed so the action is revoked instead of aborting the contract.
    """
    suffix = ("；" + extra_notes if extra_notes else "") + "。"
    instruction = REVIEW_INSTRUCTION + "、".join(required_ids) + suffix
    items: list[dict] = []
    events: list[dict] = []
    error: str | None = None
    try:
        response = gateway.verify_artifact(context, instruction=instruction, prompt_version=prompt_version,
                                           requirement_ids=required_ids)
        events.append(_event_summary(gateway))
        items = list(response.value.get("items", []))
    except ModelError as exc:
        code = getattr(exc, "code", "MODEL_ERROR")
        if code not in CONTAINED_MODEL_CODES:
            raise
        error = code
        events.append(_event_summary(gateway) or {"task_type": "verify_artifact", "error_code": error})
    identifiers = [item.get("requirement_id") for item in items]
    missing = [identifier for identifier in required_ids if identifier not in identifiers]
    if missing and len(identifiers) == len(set(identifiers)) and set(identifiers).issubset(set(required_ids)):
        repair = REVIEW_INSTRUCTION + "只返回以下缺失ID，其他规则不变：" + "、".join(missing) + suffix
        try:
            extra = gateway.verify_artifact(context, instruction=repair, prompt_version=prompt_version,
                                            requirement_ids=missing)
            events.append(_event_summary(gateway))
            items.extend(extra.value.get("items", []))
        except ModelError as exc:
            code = getattr(exc, "code", "MODEL_ERROR")
            if code not in CONTAINED_MODEL_CODES:
                raise
            error = error or code
            events.append(_event_summary(gateway) or {"task_type": "verify_artifact", "error_code": code})
    return items, events, error


def _contexts(before: DocumentInspection, after: DocumentInspection, action: dict,
              edits: list[dict], profile: dict, limit: int,
              other_edits: list[dict] | None = None) -> list[dict]:
    """Cover entire edited sections; reject overlarge individual paragraphs.

    ``other_edits`` are edits of other actions in the same paragraphs; they are
    disclosed to the reviewer so an authorized deletion by another action is not
    mistaken for a preservation loss of this action.
    """
    keys = {(before.by_location(edit["location"]).section_path,
             before.by_location(edit["location"]).logical_zone or before.by_location(edit["location"]).zone)
            for edit in edits}
    spans = [span for span in before.paragraphs
             if (span.section_path, span.logical_zone or span.zone) in keys]
    head = (f"[ACTION {action['action_id']}]\n[RULE_REQUIREMENTS]\n{_rule_text(action)}\n"
            "PRESERVATION: 保留要求保留的合同内容，不新增无依据事实，余文不得与指引矛盾。\n"
            "COVERAGE: 所见范围内本动作所有应改目标均已处理。\n"
            f"[PROFILE_FACTS]\n{profile_facts_text(profile)}\n")
    published = []
    for old in (action.get("locate") or {}).get("old_texts", [])[:3]:
        instantiated, error, _slots = _instantiate_slots(old, action, profile)
        if not error and instantiated:
            published.append(instantiated)
    if published:
        head += "[PUBLISHED_OLD_TEXT]\n" + "\n".join(published) + "\n"
    annotations: dict[str, list[str]] = {}
    for edit in other_edits or []:
        annotations.setdefault(edit["location"], []).append(
            f"{edit.get('operation', 'replace')} action={edit['action_id']} "
            f"目标原文={(edit.get('expected_old_text') or '')[:80]}")
    blocks = []
    extra: dict[str, int] = {}
    for span in spans:
        actual = after.by_location(span.location)
        if actual.section_path != span.section_path or actual.zone != span.zone:
            raise ValueError("V3_ARTIFACT_SCOPE_DRIFT")
        block = (f"[BEFORE location={span.location}]\n{span.text}\n"
                 f"[AFTER location={span.location}]\n{actual.text}\n")
        extra[span.location] = sum(len(line) + 1 for line in annotations.get(span.location, []))
        if len(head) + len(block) + extra[span.location] + 256 > limit:
            raise ValueError("V3_ARTIFACT_CONTEXT_LIMIT")
        blocks.append((span.location, block))
    if not blocks:
        raise ValueError("V3_ARTIFACT_SCOPE_EMPTY")
    windows, current = [], []
    size = len(head)
    for block in blocks:
        if current and size + len(block[1]) + extra[block[0]] + 256 > limit:
            windows.append(current)
            previous = current[-1]
            if len(head) + len(previous[1]) + len(block[1]) + extra[block[0]] + 256 > limit:
                raise ValueError("V3_ARTIFACT_WINDOW_BOUNDARY")
            current = [previous]
            size = len(head) + sum(len(item[1]) for item in current)
        current.append(block)
        size += len(block[1])
    if current:
        windows.append(current)
    if len(windows) > MAX_WINDOWS_PER_ACTION:
        raise ValueError("V3_ARTIFACT_WINDOW_LIMIT")
    edited_locations = {edit["location"] for edit in edits}
    contexts = []
    for window in windows:
        locations = [location for location, _block in window]
        window_edits = [location for location in locations if location in edited_locations]
        lines = [line for location in locations for line in annotations.get(location, [])]
        other_block = "[OTHER_AUTHORIZED_EDITS]\n" + ("\n".join(lines) if lines else "无") + "\n"
        context = (head + other_block + "[EDIT_LOCATIONS]\n" +
                   ",".join(window_edits) + "\n" +
                   "".join(block for _location, block in window))
        contexts.append({"context": context, "locations": locations,
                         "edit_locations": window_edits,
                         "before": "\n".join(before.by_location(location).text for location in locations),
                         "after": "\n".join(after.by_location(location).text for location in locations),
                         "after_edited": "\n".join(after.by_location(location).text for location in window_edits),
                         "rule": _rule_text(action) + "\nPRESERVATION: 保留要求保留的合同内容，不新增无依据事实，余文不得与指引矛盾。"
                                 "\nCOVERAGE: 所见范围内本动作所有应改目标均已处理。"})
    if any(len(window["context"]) > limit for window in contexts):
        raise ValueError("V3_ARTIFACT_CONTEXT_LIMIT")
    return contexts


MODEL_JUDGED = {"PRESERVATION", "COVERAGE"}


def _deleted_targets(action: dict, window: dict, selected: list[dict]) -> list[str]:
    return [edit.get("expected_old_text", "") for edit in selected
            if edit["location"] in window["edit_locations"] and edit.get("expected_old_text")]


def _evaluate_window(action: dict, window: dict, items: list[dict], expected: set[str],
                     selected: list[dict], profile: dict) -> tuple[bool, set[str], set[str], list[str]]:
    """Return (passed, structural_failures, model_only_failures, model_dissents).

    Structural failures are policy or code-determined (missing/duplicate ids,
    unverifiable quotes, failed code checks). Model-only failures are purely the
    reviewer's semantic verdict on items the code cannot decide (PRESERVATION,
    COVERAGE, semantic_review). Dissents record items where the model claimed a
    failure but the code proves the artifact satisfies the requirement.
    """
    structural: set[str] = set()
    model_only: set[str] = set()
    dissents: list[str] = []
    requirements = {requirement["id"]: requirement for requirement in action["requirements"]}
    edited_after = window.get("after_edited") or window["after"]
    deleted_targets = _deleted_targets(action, window, selected)
    seen: set[str] = set()
    for item in items:
        requirement = item.get("requirement_id")
        source, quote = item.get("evidence_source"), item.get("evidence_quote")
        quote_text = quote if isinstance(quote, str) else ""
        if not isinstance(requirement, str) or requirement not in expected:
            structural.add(str(requirement))
            continue
        if requirement in seen:
            structural.add(requirement)
            continue
        seen.add(requirement)
        if item.get("action_id") != action["action_id"]:
            structural.add(requirement)
        requirement_data = requirements.get(requirement)
        check = (requirement_data or {}).get("check") or {}
        kind = check.get("kind")
        model_judged = (requirement in MODEL_JUDGED or requirement_data is None
                        or kind in {"semantic_review", "boundary_scope"})
        if source not in {"before", "after"}:
            structural.add(requirement)
        elif not quote_text or quote_text not in window[source]:
            # Unusable evidence on a model-judged item is retryable (consensus);
            # on a code-provable item it is a hard failure.
            (model_only if model_judged else structural).add(requirement)
        elif source == "before":
            survives = quote_text in window["after"]
            if requirement in MODEL_JUDGED:
                if not survives and not any(_compact(quote_text) == _compact(old)
                                            for old in deleted_targets if old):
                    structural.add(requirement)
            elif action.get("operation") != "delete":
                structural.add(requirement)
        code_ok: bool | None = None
        if requirement_data is not None:
            if kind == "delete_only":
                if source == "before":
                    code_ok = bool(quote_text) and any(_compact(quote_text) == _compact(old)
                                                       for old in deleted_targets if old)
                else:
                    code_ok = bool(quote_text) and bool(deleted_targets) and not any(
                        _compact(old) in _compact(edited_after) for old in deleted_targets if old)
            elif kind in DIGIT_CHECK_KINDS:
                written = "\n".join(str(edit.get("replacement", "")) for edit in selected
                                    if edit["location"] in window["edit_locations"])
                satisfied, _detail = _check_requirement(check, written, profile, action)
                code_ok = satisfied is True
            elif kind in REGION_CHECK_KINDS:
                region = _region_text(edited_after)
                if kind == "template_exact":
                    template = action["generation"].get("template_text") or ""
                    instantiated, error, _slots = _instantiate_slots(template, action, profile)
                    code_ok = (not error and bool(instantiated)
                               and (_compact(instantiated) in _compact(region)
                                    or _compact(instantiated) in _compact(quote_text)))
                else:
                    related = True
                    if kind == "contains_all":
                        related = any(_compact(str(value)) in _compact(quote_text)
                                      for value in check.get("values", []))
                    satisfied, _detail = _check_requirement(check, region, profile, action)
                    code_ok = satisfied is True and related
            elif kind and kind not in {"semantic_review", "boundary_scope"}:
                satisfied, _detail = _check_requirement(check, quote_text, profile, action)
                code_ok = satisfied is True
        if code_ok is False:
            structural.add(requirement)
        if item.get("result") != "satisfied":
            if model_judged:
                model_only.add(requirement)
            elif code_ok is True:
                # The artifact provably satisfies the requirement; record the
                # model's dissent instead of revoking on a false negative.
                dissents.append(requirement)
                item["model_result"] = item.get("result")
                item["result"] = "satisfied"
            else:
                structural.add(requirement)
    for missing in expected - seen:
        requirement_data = requirements.get(missing)
        if missing in MODEL_JUDGED or requirement_data is None or (
                (requirement_data or {}).get("check") or {}).get("kind") in {"semantic_review", "boundary_scope"}:
            model_only.add(missing)
        else:
            structural.add(missing)
    return (not structural and not model_only), structural, model_only, dissents


def review_artifacts(before: DocumentInspection, after: DocumentInspection, actions: list[dict],
                     edits: list[dict], profile: dict, gateway: Any, *, plan_sha256: str,
                     redline_sha256: str, final_sha256: str, round_number: int) -> dict:
    """Return an action-level authorization bound to this exact artifact pair."""
    result = {"source_sha256": before.source_sha256, "plan_sha256": plan_sha256,
              "redline_sha256": redline_sha256, "final_sha256": final_sha256,
              "round": round_number, "prompt_version": PROMPT_VERSIONS_V2["artifact_verify"],
              "actions": [], "passed": True}
    if after.source_sha256 != final_sha256:
        raise ValueError("V3_ARTIFACT_HASH_MISMATCH")
    binding = (f"[ARTIFACT_BINDING]\nsource_sha256={before.source_sha256}\n"
               f"plan_sha256={plan_sha256}\nredline_sha256={redline_sha256}\n"
               f"final_sha256={final_sha256}\nround={round_number}\n")
    for action in actions:
        selected = [edit for edit in edits if edit["action_id"] == action["action_id"]]
        if not selected:
            continue
        entry = {"action_id": action["action_id"], "passed": False, "windows": [], "reason": None}
        result["actions"].append(entry)
        try:
            windows = _contexts(before, after, action, selected, profile,
                                gateway.max_context_chars - len(binding),
                                other_edits=[edit for edit in edits
                                             if edit["action_id"] != action["action_id"]])
        except (ValueError, KeyError) as exc:
            entry["reason"] = str(exc)
            result["passed"] = False
            continue
        for window in windows:
            window["context"] = binding + window["context"]
            expected = {"PRESERVATION"}
            extra_notes = []
            if window["edit_locations"]:
                expected |= {requirement["id"] for requirement in action["requirements"]}
                expected |= {"COVERAGE"}
                deleted = _deleted_targets(action, window, selected)
                if action.get("operation") == "delete" and deleted:
                    extra_notes.append("被删除目标（delete_only：引用BEFORE该目标或AFTER邻近原文）："
                                       + "；".join(deleted[:3]))
            required_ids = [requirement["id"] for requirement in action["requirements"]
                            if requirement["id"] in expected]
            required_ids += [identifier for identifier in ("PRESERVATION", "COVERAGE")
                             if identifier in expected]
            items, events, model_error = _window_items(gateway, window["context"], required_ids,
                                                       PROMPT_VERSIONS_V2["artifact_verify"],
                                                       extra_notes="；".join(extra_notes))
            passed, structural, model_only, dissents = _evaluate_window(
                action, window, items, expected, selected, profile)
            consensus_event = None
            if not passed and not structural and model_only:
                # One bounded second opinion when the only failures are model
                # verdicts on items the code cannot decide; code failures never
                # reach this branch.
                retry_items, retry_events, _retry_error = _window_items(
                    gateway, window["context"], required_ids,
                    PROMPT_VERSIONS_V2["artifact_verify"], extra_notes="；".join(extra_notes))
                consensus_event = retry_events[0] if retry_events else None
                retry_passed, retry_structural, _retry_model, retry_dissents = _evaluate_window(
                    action, window, retry_items, expected, selected, profile)
                if retry_passed and not retry_structural:
                    items, passed, dissents = retry_items, True, retry_dissents
            entry["windows"].append({"coverage_locations": window["locations"],
                                     "edit_locations": window["edit_locations"],
                                     "context_sha256": canonical_sha(window["context"]),
                                     "model_event": events[0],
                                     "repair_event": events[1] if len(events) > 1 else None,
                                     "consensus_event": consensus_event,
                                     "model_error": model_error,
                                     "model_dissents": dissents,
                                     "items": items, "passed": passed})
        entry["passed"] = all(window["passed"] for window in entry["windows"])
        if not entry["passed"]:
            entry["reason"] = "V3_ARTIFACT_SEMANTIC_REJECTED"
            result["passed"] = False
    result["record_sha256"] = canonical_sha(result)
    return result
