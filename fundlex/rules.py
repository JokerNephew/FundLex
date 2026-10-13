"""Versioned, fail-closed rule catalogue and contract-evidence classification."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .qualification_evidence import category_value, investment_spans, basic_spans, QualificationEvidenceError
from .fee_evidence import fee_value


class RuleError(ValueError):
    def __init__(self, code: str, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


PROMPT_VERSIONS = {"fund_type": "fund_type_v3", "profile": "profile_v3",
                   "old_candidate": "candidate_v1", "new_candidate": "candidate_new_v1"}
NORMALIZER_VERSION = "trigger-whitespace-terminal-punctuation-v1"


def _normalized_text(text: str, *, terminal_punctuation: bool = False) -> tuple[str, list[int]]:
    """Ignore inline spacing only; line breaks and structural barriers survive."""
    positions = [i for i, char in enumerate(text) if not char.isspace() or char in "\r\n"]
    value = "".join(text[i] for i in positions)
    if terminal_punctuation and value.endswith(("。", ".")):
        value, positions = value[:-1], positions[:-1]
    return value, positions


def _normalized_matches(text: str, trigger: str) -> list[tuple[int, int]]:
    value, positions = _normalized_text(text)
    needle, _ = _normalized_text(trigger, terminal_punctuation=True)
    if not needle:
        return []
    result, offset = [], 0
    while (at := value.find(needle, offset)) >= 0:
        stop = at + len(needle)
        literal, _ = _normalized_text(trigger)
        if literal.endswith(("。", ".")) and stop < len(value) and value[stop] == literal[-1]:
            stop += 1
        result.append((positions[at], positions[stop - 1] + 1))
        offset = stop
    return result


def _old_text_equal(source: str, reference: str) -> bool:
    return _normalized_text(source, terminal_punctuation=True)[0] == _normalized_text(reference, terminal_punctuation=True)[0]


def release_runtime_context(gateway: Any, actual_model: str | None = None) -> dict[str, Any]:
    """Fingerprint write-relevant transport settings, without credentials."""
    from .store import engine_build
    required = ("base_url", "model", "request_options", "max_context_chars", "max_completion_tokens", "timeout_s", "retries")
    if any(not hasattr(gateway, key) for key in required):
        raise RuleError("RELEASE_CONTEXT_UNVERIFIED")
    transport = {key: getattr(gateway, key) for key in required}
    transport.update(provider=getattr(gateway, "provider", ""), gateway_type=type(gateway).__module__ + "." + type(gateway).__qualname__)
    fingerprint = hashlib.sha256(json.dumps(transport, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    return {"engine_build": engine_build(), "model_transport_sha256": fingerprint,
            "actual_model": actual_model or gateway.model, "prompt_versions": dict(PROMPT_VERSIONS)}


def _validate_context_shape(context: Any) -> None:
    if not isinstance(context, dict) or any(not isinstance(context.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", context[key]) for key in ("engine_build", "model_transport_sha256")):
        raise RuleError("RELEASE_CONTEXT_UNVERIFIED")
    if not isinstance(context.get("actual_model"), str) or not context["actual_model"] or context.get("prompt_versions") != PROMPT_VERSIONS:
        raise RuleError("RELEASE_CONTEXT_UNVERIFIED")


def verify_release_context(ruleset: Any, gateway: Any, actual_model: str, *, events_start: int = 0) -> dict[str, Any]:
    runtime = release_runtime_context(gateway, actual_model)
    expected = ruleset.release_policy.get("evaluation_context")
    _validate_context_shape(expected)
    if expected != runtime:
        raise RuleError("RELEASE_CONTEXT_UNVERIFIED")
    for action in ruleset.actions:
        measured = action.get("evaluation_metrics")
        if action["auto_write"] and (not isinstance(measured, dict) or measured.get("tested_context") != runtime):
            raise RuleError("RELEASE_CONTEXT_UNVERIFIED")
    for event in getattr(gateway, "events", [])[events_start:]:
        if not event.get("error_code") and (event.get("actual_model") != actual_model or event.get("prompt_version") not in PROMPT_VERSIONS.values()):
            raise RuleError("RELEASE_CONTEXT_UNVERIFIED")
    return runtime


def validate_release_gate(action: dict[str, Any], policy: dict[str, Any]) -> None:
    """Require measured results for every preregistered action/profile gate."""
    if not action.get("approved") or policy.get("status") != "released":
        raise ValueError("release approval missing")
    if not policy.get("evaluation_report_id") or not policy.get("approval_record") or not action.get("evaluation_report_id") or not action.get("approval_record"):
        raise ValueError("release evidence missing")
    threshold, actual = action.get("release_threshold"), action.get("evaluation_metrics")
    if not isinstance(threshold, dict) or not threshold.get("registration_id") or threshold.get("registered_before_full_evaluation") is not True or not isinstance(actual, dict):
        raise ValueError("preregistered evaluation missing")
    _validate_context_shape(policy.get("evaluation_context"))
    if actual.get("tested_context") != policy["evaluation_context"]:
        raise RuleError("RELEASE_CONTEXT_UNVERIFIED")
    if actual.get("action_id") != action["action_id"] or actual.get("evaluation_report_id") != action["evaluation_report_id"] or actual.get("threshold_registration_id") != threshold["registration_id"]:
        raise ValueError("evaluation provenance mismatch")
    def check(gates: dict[str, Any], measured: dict[str, Any]) -> None:
        if not isinstance(gates, dict) or not gates or not isinstance(measured, dict):
            raise ValueError("metrics missing")
        for name, bounds in gates.items():
            value = measured.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("metric missing or invalid")
            if (name.endswith("cases") or name == "unsafe_edits") and (not isinstance(value, int)):
                raise ValueError("count metric invalid")
            if name in {"location_precision", "location_recall", "template_exactness", "accuracy", "precision", "recall"} and value > 1:
                raise ValueError("rate metric invalid")
            if not isinstance(bounds, dict) or not bounds or not set(bounds).issubset({"min", "max"}):
                raise ValueError("threshold invalid")
            for operator, target in bounds.items():
                if not isinstance(target, (int, float)) or isinstance(target, bool) or not math.isfinite(target):
                    raise ValueError("threshold invalid")
                if (operator == "min" and value < target) or (operator == "max" and value > target):
                    raise ValueError("release metric below threshold")
    check(threshold.get("metrics"), actual.get("metrics"))
    dependencies = threshold.get("profile_metrics", {})
    if set(dependencies) != set(action.get("requires_profile", [])):
        raise ValueError("profile gates missing")
    for field, gates in dependencies.items():
        check(gates, actual.get("profile_metrics", {}).get(field))


@dataclass(frozen=True)
class RuleSet:
    version: str
    sha256: str
    templates: dict[str, str]
    actions: tuple[dict[str, Any], ...]
    release_policy: dict[str, Any]

    @property
    def auto_write_enabled(self) -> bool:
        return any(action["auto_write"] for action in self.actions)


def load_ruleset(version: str) -> RuleSet:
    if not re.fullmatch(r"v[0-9]+", version):
        raise RuleError("RULESET_NOT_FOUND")
    path = Path(__file__).resolve().parent.parent / "rules" / f"rules_{version}.json"
    if not path.is_file():
        raise RuleError("RULESET_NOT_FOUND")
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
        if data["version"] != version or data["schema_version"] != "1":
            raise ValueError("version")
        templates = {key: item["text"] for key, item in data["templates"].items()}
        if not templates or not all(isinstance(value, str) for value in templates.values()):
            raise ValueError("templates")
        actions = data["actions"]
        if not actions or len({item["action_id"] for item in actions}) != len(actions):
            raise ValueError("actions")
        required = {"rule_id", "action_id", "section_anchor", "subsection_anchor", "regions",
                    "scope", "old_triggers", "new_triggers", "operation", "template_id", "order",
                    "risk_class", "requires_profile", "condition", "on_unknown", "auto_write", "release_threshold", "approved", "recognition_kind"}
        for action in actions:
            if not required.issubset(action) or action["template_id"] not in templates:
                raise ValueError("action fields")
            if action["scope"] not in {"phrase", "sentence", "paragraph"}:
                raise ValueError("scope")
            if action["operation"] not in {"replace", "delete", "append"}:
                raise ValueError("operation")
            if action["condition"] not in {"always", "single_class", "multi_class", "has_service_fee", "no_service_fee", "fee_groups", "floating_single", "floating_multi", "nonfloating_service_multi"}:
                raise ValueError("condition")
            if action.get('recognition_kind','literal') not in {'literal','conversion_prohibition','short_holding_redemption'}:
                raise ValueError('recognition kind')
            if action['recognition_kind']=='short_holding_redemption' and action.get('host_policy')!='fee_rate_or_adjustment':
                raise ValueError('host policy')
            if not isinstance(action.get('subsection_aliases',[]),list) or any(not isinstance(v,str) or not v for v in action.get('subsection_aliases',[])):
                raise ValueError('subsection aliases')
            if not isinstance(action.get('section_aliases',[]),list) or any(not isinstance(v,str) or not v for v in action.get('section_aliases',[])):
                raise ValueError('section aliases')
            if not action["section_anchor"] or not action["subsection_anchor"]:
                raise ValueError("anchors")
            if not action["old_triggers"] or not set(action["regions"]).issubset({"body", "summary"}):
                raise ValueError("target")
            if action["auto_write"]:
                # A release is a separate, explicit offline act. Merely editing a
                # Boolean in a draft package cannot enable write operations.
                validate_release_gate(action, data["release_policy"])
                if any(token in templates[action["template_id"]] for token in action.get("template_slots", {})):
                    raise ValueError("unapproved concrete template variant")
            if action.get("on_unknown") != "failed" or not isinstance(action["auto_write"], bool):
                raise ValueError("fail closed policy")
            if action["operation"] == "delete" and templates[action["template_id"]] != "":
                raise ValueError("deletion template")
        return RuleSet(version, hashlib.sha256(raw).hexdigest(), templates,
                       tuple(actions), data["release_policy"])
    except RuleError:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuleError("RULESET_INVALID") from exc


def _category_value(paragraphs: tuple[Any, ...]) -> tuple[str, Any, int] | None:
    try:
        return category_value(paragraphs)
    except QualificationEvidenceError as exc:
        raise RuleError(exc.code) from None


def classify_document_identity(inspection: Any) -> dict[str, Any]:
    """Verify this file's operative type, independent of filename/fund name."""
    paragraphs = tuple(getattr(inspection, "evidence_paragraphs", inspection.paragraphs))
    cover: list[tuple[Any, str, str]] = []
    for span in paragraphs[:64]:
        if span.zone != "body" or not span.segments:
            continue
        compact = re.sub(r"\s+", "", span.text)
        if re.match(r"^第[一二三四五六七八九十\d]+(?:部分|章|节)", compact):
            break
        if not compact or len(compact) > 180:
            continue
        contract = bool(re.search(r"基金合同(?:[（(][^()（）]{0,35}[)）])?$", compact))
        other = re.search(r"(招募说明书|托管协议|公告|决议)(?:[（(][^()（）]{0,35}[)）])?$", compact)
        if span.section_path and not (contract or other):
            break
        if contract and any(t in compact for t in ("依据", "根据", "依照", "本基金", "本合同", "定义", "签订", "履行")):
            contract = False
        if contract or other:
            cover.append((span, span.text, "fund_contract" if contract else other.group(1)))
    kinds = {kind for _, _, kind in cover}
    if kinds - {"fund_contract"}:
        identity = {"status": "failed", "document_type": next(iter(kinds)) if len(kinds) == 1 else "conflicting_types",
                    "basis": "current_cover_title", "evidence": [_evidence(span, quote) for span, quote, _ in cover]}
        raise RuleError("DOCUMENT_TYPE_CONFLICT" if "fund_contract" in kinds else "NON_CONTRACT_DOCUMENT", {"document_identity": identity})
    if "fund_contract" in kinds:
        return {"status": "verified", "document_type": "fund_contract", "basis": "current_cover_title",
                "evidence": [_evidence(span, quote) for span, quote, _ in cover]}
    operative, rights = [], []
    in_preamble = False
    for span in paragraphs:
        plain = re.sub(r"\s+", "", span.text)
        if plain in {"前言", "绪言"} or any(t in span.section_path for t in ("前言", "绪言")):
            in_preamble = True
        elif re.match(r"^第[一二三四五六七八九十\d]+(?:部分|章|节)", plain):
            in_preamble = False
        if span.zone != "body" or not span.segments or not in_preamble:
            continue
        for quote in re.split(r"(?<=[。；;])", span.text):
            compact = re.sub(r"\s+", "", quote)
            if not all(t in compact for t in ("基金管理人", "基金托管人", "基金份额持有人")):
                continue
            if re.search(r"(?:订立|签订|达成|制定)本基金合同", compact):
                operative.append(_evidence(span, quote))
            if compact.startswith("本基金合同") and "权利义务" in compact:
                rights.append(_evidence(span, quote))
    if operative and rights:
        return {"status": "verified", "document_type": "fund_contract", "basis": "operative_contract_preamble", "evidence": operative + rights}
    raise RuleError("DOCUMENT_IDENTITY_EVIDENCE_MISSING")


def classify_fund_type(inspection: Any) -> dict[str, Any]:
    """Classify only from a locatable current-product category clause."""
    identity = classify_document_identity(inspection)
    paragraphs = getattr(inspection, "evidence_paragraphs", inspection.paragraphs)
    try:
        found = category_value(tuple(paragraphs))
    except QualificationEvidenceError as exc:
        raise RuleError(exc.code) from None
    if found is None:
        raise RuleError("FUND_TYPE_EVIDENCE_MISSING")
    quote, span, category_index = found
    compact = re.sub(r"\s+", "", quote)
    operation_quote = ""
    operation_span = None
    for index in range(category_index + 1, min(category_index + 9, len(paragraphs))):
        candidate_span = paragraphs[index]
        value = re.sub(r"\s+", "", candidate_span.text)
        if "基金的运作方式" not in value:
            continue
        after = value.split("基金的运作方式", 1)[1].strip("：:")
        if not after and index + 1 < len(paragraphs):
            candidate_span = paragraphs[index + 1]
            after = re.sub(r"\s+", "", candidate_span.text)
        operation_quote, operation_span = after[:100], candidate_span
        break
    types: set[str] = set()
    if "同业存单" in compact:
        types.add("interbank_cd")
    if "货币市场基金" in compact or re.search(r"货币(?:型|市场).*基金", compact):
        types.add("money_market")
    if ("交易型开放式" in compact or "交易型开放式" in operation_quote) and "联接" not in compact and "联接" not in operation_quote:
        types.add("etf")
    if "联接" in compact or ("交易型开放式" not in operation_quote and "交易型开放式" not in compact and any(x in compact for x in ("混合型", "债券型", "股票型", "指数型", "基金中基金", "FOF"))):
        types.add("ordinary")
    # A generic category (even 混合型) is not proof against a specialised CD
    # product. Identify the CURRENT investment mandate, never the fund name.
    selected_investment = investment_spans(tuple(paragraphs))
    selected_basic = basic_spans(tuple(paragraphs))
    cd_targets: list[tuple[Any, str]] = []
    cd_positive: list[tuple[Any, str]] = []
    cd_ratios: list[float] = []
    cd_unresolved = False
    for candidate in selected_investment + selected_basic:
        for clause in re.split(r"(?<=[。；])", candidate.text):
            if re.search(r"本基金(?:的)?标的指数(?:为|是).*同业存单.*指数", re.sub(r"\s+", "", clause)):
                cd_targets.append((candidate, clause))
    for candidate in selected_investment + selected_basic:
        for clause in re.split(r"(?<=[。；])", candidate.text):
            normalized = re.sub(r"\s+", "", clause)
            if candidate not in selected_investment:
                continue
            match = re.search(r"本基金投资于同业存单(?:指数成份券(?:和|及|与)备选成份券)?的比例不低于(?:非现金)?基金资产(?:净值)?的?(\d+(?:\.\d+)?)[%％]", normalized)
            if match:
                ratio = float(match.group(1))
                cd_ratios.append(ratio)
                if 80 <= ratio <= 100:
                    cd_positive.append((candidate, clause))
            elif re.search(r"本基金(?:主要)?投资于同业存单(?:的比例|指数|[。；])", normalized):
                cd_unresolved = True
            # An index explicitly identified as CD needs its own >=80% mandate.
            if cd_targets and re.search(r"本基金投资于标的指数成份券.*比例不低于(?:非现金)?基金资产(?:净值)?的?80[%％]", normalized):
                cd_positive.append((candidate, clause))
    if cd_positive:
        if any(r < 80 or r > 100 for r in cd_ratios):
            raise RuleError("FUND_TYPE_INVESTMENT_EVIDENCE_CONFLICT")
        types.discard("ordinary")
        types.add("interbank_cd")
    elif (cd_targets or cd_unresolved) and "interbank_cd" not in types:
        raise RuleError("FUND_TYPE_CD_MANDATE_EVIDENCE_MISSING")
    elif types == {"ordinary"} and not selected_investment:
        raise RuleError("FUND_TYPE_INVESTMENT_EVIDENCE_MISSING")
    if "中国证监会认可的其他基金" in compact:
        types = {"other_excluded"} if not (types - {"ordinary"}) else types | {"other_excluded"}
    if len(types) != 1:
        raise RuleError("FUND_TYPE_EVIDENCE_AMBIGUOUS")
    kind = next(iter(types))
    start = span.text.find(quote)
    if start < 0:
        positions = [i for i, char in enumerate(span.text) if not char.isspace()]
        compact_text = "".join(span.text[i] for i in positions)
        at = compact_text.find(re.sub(r"\s+", "", quote))
        if at < 0:
            raise RuleError("FUND_TYPE_EVIDENCE_INVALID")
        start = positions[at]
        quote = span.text[start:positions[at + len(re.sub(r"\s+", "", quote)) - 1] + 1]
    result = {"fund_type": kind, "document_identity": identity, "evidence": {
        "field": "fund_type", "quote": quote, "part_uri": span.part_uri,
        "section_path": span.section_path, "paragraph_id": span.location,
        "char_start": start, "char_end": start + len(quote),
        "text_view": "accepted", "mapping_version": span.mapping_version,
        "source_kind": "deterministic", "verification": "verified"}}
    if operation_quote and operation_span is not None:
        positions = [i for i,c in enumerate(operation_span.text) if not c.isspace()]
        normalized = ''.join(operation_span.text[i] for i in positions)
        at = normalized.find(operation_quote)
        if at < 0:
            raise RuleError("FUND_TYPE_OPERATION_EVIDENCE_INVALID")
        literal = operation_span.text[positions[at]:positions[at+len(operation_quote)-1]+1]
        result["operation_evidence"] = {**_evidence(operation_span,literal), "field":"operation_form"}
    support = ([(p, q) for p, q in cd_positive if "同业存单" in q] + cd_targets
               + [(p, q) for p, q in cd_positive if "同业存单" not in q]) if kind == "interbank_cd" else []
    if kind == "ordinary":
        # Return a mandate paragraph as independent contextual support, rather
        # than generic name/filename features or a list of investable instruments.
        support = [(p, p.text) for p in selected_investment if "本基金" in p.text and
                   any(t in p.text for t in ("比例", "投资目标", "投资于"))][:2]
        if not support:
            raise RuleError("FUND_TYPE_INVESTMENT_EVIDENCE_MISSING")
    result["supporting_evidence"] = [_evidence(p, q) for p, q in support[:4]]
    return result


def _evidence(span: Any, quote: str) -> dict[str, Any]:
    start = span.text.find(quote)
    return {"quote": quote, "paragraph_id": span.location, "part_uri": span.part_uri,
            "section_path": span.section_path, "char_start": start, "char_end": start + len(quote),
            "text_view":"accepted", "mapping_version":span.mapping_version,
            "verification": "verified", "source_kind": "deterministic"}


def _class_names(text: str) -> set[str]:
    return set(re.findall(r"([A-ZＡ-Ｚ])类", re.sub(r"\s+", "", text)))


def _count_declaration(quote: str) -> tuple[int, set[str]] | None:
    text = re.sub(r"\s+", "", quote)
    if any(t in text for t in ("未来", "可以", "拟设", "新增", "有权")):
        return None
    if re.search(r"本基金(?:不区分(?:基金)?份额类别|(?:仅|只)(?:设有|设置|有)?(?:一种|一个|一类)(?:基金)?份额)", text):
        return 1, set()
    names = _class_names(text)
    if names and "本基金" in text and re.search(r"(?:分为|设置|设立).*类", text) and "等" not in text:
        return len(names), names
    return None


def _fee_value(quote: str, field: str, name: str, *, single_bound: bool = False) -> bool | None:
    """Verify explicit same-property class groups; reject mixed attribution."""
    return fee_value(quote,field,name,single_bound=single_bound)


def _count_facts(classes: list[dict[str, Any]], declarations: list[tuple[Any, str]], *, model_count: dict[str, Any] | None = None) -> dict[str, Any]:
    names = {c["name"] for c in classes if c.get("name_evidence") or c.get("evidence")}
    parsed = [(span, quote, _count_declaration(quote)) for span, quote in declarations]
    parsed = [(span, quote, value) for span, quote, value in parsed if value is not None]
    candidates = [(span, quote, value) for span, quote, value in parsed if
                  (value[1] and value[1] == names) or (value[0] == 1 and names == {"__single__"})]
    if model_count and model_count.get("value") is not None:
        candidates = [(span, quote, value) for span, quote, value in parsed if
                      model_count.get("quote") and model_count["quote"] in quote and value[0] == model_count["value"]]
    counts = {value[0] for _, _, value in candidates}
    all_declared_counts = {value[0] for _, _, value in parsed}
    conflict = len(all_declared_counts) > 1 or (1 in all_declared_counts and len(names - {"__single__"}) > 1)
    count = next(iter(counts)) if len(counts) == 1 and not conflict else None
    minimum = max(len(names - {"__single__"}), count or 0) if not conflict else 0
    return {"share_class_count": count, "share_class_count_min": minimum,
            "share_class_count_verified": count is not None or minimum >= 2,
            "share_class_count_evidence": [_evidence(span, quote) for span, quote, _ in candidates] if count is not None else
                [e for c in classes for e in c.get("name_evidence", c.get("evidence", []))],
            "share_class_count_conflict": conflict,
            "share_class_universe_complete": count is not None and len(names) == count}


def extract_profile(inspection: Any) -> dict[str, Any]:
    """Independent evidence comparison; it does not substitute for model facts."""
    classes: dict[str, dict[str, Any]] = {}
    floating: list[dict[str, Any]] = []
    declarations: list[tuple[Any, str]] = []
    sentences: list[tuple[Any, str]] = []
    for span in inspection.paragraphs:
        if span.zone not in {"body", "summary"} or not span.segments or not any(x in span.section_path for x in ("释义", "基本情况", "申购", "费用", "收益", "清算")):
            continue
        for sentence in re.split(r"(?<=[。；;])", span.text):
            sentences.append((span, sentence))
            if _count_declaration(sentence):
                declarations.append((span, sentence))
    single = bool(declarations) and {_count_declaration(q)[0] for _, q in declarations} == {1}
    for span, sentence in sentences:
        if "直销机构" in sentence or "持续持有" in sentence:
            continue
        names = _class_names(sentence)
        if not names and single and "本基金" in sentence and any(t in sentence for t in ("申购费", "销售服务费")):
            names = {"__single__"}
        for name in names:
            item = classes.setdefault(name, {"name": name, "subscription_fee": None, "sales_service_fee": None, "evidence": [], "name_evidence": []})
            if name != "__single__":
                item["name_evidence"].append(_evidence(span, sentence))
            else:
                item["name_evidence"] = [_evidence(p, q) for p, q in declarations]
            for key in ("subscription_fee", "sales_service_fee"):
                value = _fee_value(sentence, key, name, single_bound=single)
                if value is None:
                    continue
                previous = [e["value"] for e in item["evidence"] if e["field"] == key]
                item[key] = value if not previous or all(v == value for v in previous) else None
                item["evidence"].append({**_evidence(span, sentence), "field": key, "value": value})
        if "或有管理费" in sentence or "超额管理费" in sentence:
            floating.append(_evidence(span, sentence))
    if single and not classes:
        classes["__single__"] = {"name": "__single__", "subscription_fee": None, "sales_service_fee": None, "evidence": [], "name_evidence": [_evidence(p, q) for p, q in declarations]}
    complete = bool(classes) and all(c[k] is not None for c in classes.values() for k in ("subscription_fee", "sales_service_fee"))
    facts = _count_facts(list(classes.values()), declarations)
    return {"share_classes": sorted(classes), "classes": list(classes.values()), **facts,
            "fee_groups": {"subscription_group": [n for n, c in classes.items() if c["subscription_fee"] is True and c["sales_service_fee"] is False], "service_group": [n for n, c in classes.items() if c["subscription_fee"] is False and c["sales_service_fee"] is True]},
            "fee_groups_verified": complete, "class_universe_verified": bool(classes) and not facts["share_class_count_conflict"],
            "floating_management_fee": True if floating else None, "management_fee_evidence": floating, "source": "deterministic_comparison"}


def applicability(action: dict[str, Any], profile: dict[str, Any]) -> tuple[str, str]:
    """Evaluate only the predicate's necessary verified facts, with three values."""
    condition = action.get("condition")
    if condition is None:
        raise RuleError("RULE_CONDITION_UNKNOWN")
    if condition == "always" and not action.get("requires_profile"):
        return "true", "unconditional_rule"
    count = profile.get("share_class_count") if profile.get("share_class_count_verified") else None
    minimum = profile.get("share_class_count_min", 0) if profile.get("share_class_count_verified") else 0
    single = count == 1 if count is not None else False if minimum >= 2 else None
    multi = count > 1 if count is not None else True if minimum >= 2 else None
    classes = profile.get("classes", [])
    service_values = [c.get("sales_service_fee") for c in classes]
    service = True if any(v is True for v in service_values) else False if classes and profile.get("class_universe_verified") and all(v is False for v in service_values) else None
    floating = profile.get("floating_management_fee")
    def conjunction(*values):
        return False if False in values else None if None in values else True
    predicates = {"always": True, "single_class": single, "multi_class": multi,
                  "has_service_fee": service, "no_service_fee": None if service is None else not service,
                  "fee_groups": bool(profile.get("fee_groups", {}).get("subscription_group") and profile.get("fee_groups", {}).get("service_group")) if profile.get("fee_groups_verified") else None,
                  "floating_single": conjunction(floating, single), "floating_multi": conjunction(floating, multi),
                  "nonfloating_service_multi": conjunction(None if floating is None else not floating, multi, service)}
    if condition not in predicates:
        raise RuleError("RULE_CONDITION_UNKNOWN")
    value = predicates[condition]
    # A verified false conjunct already proves non-applicability. Additional
    # template/profile dependencies cannot turn that proof into uncertainty.
    if value is False:
        return "false", "verified_predicate_evidence"
    requirements = {"share_classes": single is not None or multi is not None,
                    "share_class_count": single is not None or multi is not None,
                    "sales_service_fee_by_class": service is not None if condition in {"has_service_fee", "no_service_fee"} else bool(classes) and profile.get("class_universe_verified") and all(v is not None for v in service_values),
                    "subscription_fee_by_class": bool(classes) and profile.get("class_universe_verified") and all(c.get("subscription_fee") is not None for c in classes),
                    "floating_management_fee": floating is not None,
                    "fee_groups": profile.get("fee_groups_verified", False)}
    if value is None or any(not requirements.get(field, False) for field in action.get("requires_profile", [])):
        return "unknown", "PROFILE_EVIDENCE_INCOMPLETE"
    return "true", "verified_predicate_evidence"


def resolve_profile(inspection: Any, gateway: Any) -> dict[str, Any]:
    comparison = extract_profile(inspection)
    if not hasattr(gateway, "call"):
        return comparison
    # Scan every allowed paragraph before allocating the budget. Long unrelated
    # definitions are not profile evidence and cannot crowd out fee clauses.
    fragments: dict[str, dict[str, Any]] = {}
    for span in inspection.paragraphs:
        if span.zone not in {"body", "summary"} or not span.segments or not any(x in span.section_path for x in ("释义", "基本情况", "申购", "费用", "清算")):
            continue
        for sentence in re.split(r"(?<=[。；;])", span.text):
            if not sentence.strip():
                continue
            own_class = bool(re.search(r"[A-ZＡ-Ｚ]\s*类", sentence))
            fee_clause = any(t in sentence for t in ("申购费", "认购费", "认购、申购", "销售服务费"))
            management = "管理费" in sentence
            class_intro = _count_declaration(sentence) is not None or bool(re.search(r"基金份额类别|(?:分为|设置|设立).{0,60}[A-ZＡ-Ｚ]\s*类|不区分份额类别|[A-ZＡ-Ｚ]\s*类基金份额[：:]", sentence))
            if not (fee_clause or management or class_intro):
                continue
            priority = 0 if own_class and fee_clause else 1 if management else 2 if class_intro else 3
            item = fragments.setdefault(sentence, {"quote": sentence, "priority": priority, "sources": [],
                                                   "fee_clause": fee_clause, "own_class": own_class,
                                                   "management_clause": management, "class_intro": class_intro})
            item["sources"].append(span)
    chosen, size = [], 0
    truncated = False
    for item in sorted(fragments.values(), key=lambda item: item["priority"]):
        required = len(item["quote"]) + bool(chosen)
        if size + required > 11000:
            truncated = True
            continue
        chosen.append(item)
        size += required
    context = "\n".join(item["quote"] for item in chosen)
    selected_quotes: dict[str, list[str]] = {}
    selected: dict[str, Any] = {}
    for item in chosen:
        for span in item["sources"]:
            selected[span.location] = span
            selected_quotes.setdefault(span.location, []).append(item["quote"])
    selection = {"prompt_version": "profile_v3", "context_chars": len(context),
                 "relevant_unique_clauses": len(fragments), "selected_unique_clauses": len(chosen),
                 "selected_class_fee_clauses": sum(item["fee_clause"] and item["own_class"] for item in chosen),
                 "selected_management_clauses": sum(item["management_clause"] for item in chosen),
                 "selected_source_paragraphs": len(selected),
                 "class_fee_evidence": [_evidence(span, item["quote"]) for item in chosen if item["fee_clause"] and item["own_class"] for span in item["sources"]]}
    field_schema = {"type": "object", "properties": {"value": {"type": ["boolean", "null"]}, "quote": {"type": "string"}}, "required": ["value", "quote"], "additionalProperties": False}
    schema = {"type": "object", "properties": {
        "classes": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "subscription_fee": field_schema, "sales_service_fee": field_schema}, "required": ["name", "subscription_fee", "sales_service_fee"], "additionalProperties": False}},
        "share_class_count": {"type": "object", "properties": {"value": {"type": ["integer", "null"], "minimum": 1}, "quote": {"type": "string"}}, "required": ["value", "quote"], "additionalProperties": False},
        "floating_management_fee": field_schema}, "required": ["classes", "floating_management_fee"], "additionalProperties": False}
    from .model import ModelError
    try:
        result = gateway.call(task_type="profile", bounded_context=context, response_schema=schema,
                              instruction="从当前基金条款独立提取实际类别及各自申购/销售服务费属性。每字段quote必须是包含对应类别与收费属性的逐字原文，不可按A/C字母推断。明确C/E共同同属性可分别引用同句，不能借另一类不同属性。share_class_count仅用明确单类声明或封闭类别列表引文，缺失用null；明确不区分类别且无字母名称时classes中name用__single__，其收费引文须为本基金一般收费条款。不确定或缺证据用null、空quote；不同渠道优惠不代表类别一般属性。管理费浮动属性也必须引文证明，未提及不能推断false。禁止生成条文。", prompt_version="profile_v3")
    except ModelError as exc:
        return {"share_classes": [], "classes": [], "fee_groups": {"subscription_group": [], "service_group": []},
                "fee_groups_verified": False, "floating_management_fee": None, "management_fee_evidence": [],
                "source": "model_profile_failed", "comparison": comparison, "errors": [{"code": exc.code}], "context_truncated": truncated, "context_selection": selection}
    errors: list[dict[str, Any]] = []
    declarations = [(span, clause) for location, span in selected.items() for clause in selected_quotes[location] if _count_declaration(clause)]
    declared_counts = {_count_declaration(quote)[0] for _, quote in declarations}
    single_bound = declared_counts == {1}
    model_count = result.value.get("share_class_count")
    if model_count and model_count.get("value") is not None and not any(model_count.get("quote") and model_count["quote"] in quote and _count_declaration(quote)[0] == model_count["value"] for _, quote in declarations):
        errors.append({"code": "PROFILE_CLASS_COUNT_EVIDENCE_INVALID", "field": "share_class_count"})
        model_count = None
    def verify(field: dict[str, Any], key: str, name: str | None = None) -> dict[str, Any] | None:
        if field["value"] is None:
            return None
        quote = field["quote"]
        matches = [span for location, span in selected.items() if quote and any(quote in clause for clause in selected_quotes[location])]
        error = None
        if not matches:
            error = "PROFILE_EVIDENCE_INVALID"
        elif name:
            polarity = _fee_value(quote, key, name, single_bound=single_bound)
            if polarity is None or polarity != field["value"]:
                error = "PROFILE_FEE_POLARITY_UNVERIFIED"
        else:
            negative = any(t in quote for t in ("不实行浮动管理费", "不采用浮动管理费", "管理费不浮动", "采用固定管理费"))
            positive = any(t in quote for t in ("浮动管理费", "或有管理费", "超额管理费")) and not negative
            if (field["value"] is True and not positive) or (field["value"] is False and not negative):
                error = "PROFILE_MANAGEMENT_FEE_POLARITY_UNVERIFIED"
        if error:
            record={"code": error, "class": name, "field": key,'proposed_value':field.get('value')}
            if matches:
                record['source_evidence']=_evidence(matches[0],quote)
            errors.append(record)
            return None
        return {**_evidence(matches[0], quote), "value": field["value"], "occurrences": [_evidence(span, quote) for span in matches]}
    classes = []
    deterministic = {c["name"]: c for c in comparison["classes"]}
    for incoming in result.value["classes"]:
        name = re.sub(r"\s+", "", incoming["name"]).removesuffix("类基金份额").removesuffix("类")
        if (not re.fullmatch(r"[A-ZＡ-Ｚ]", name) and not (name == "__single__" and single_bound)) or any(c["name"] == name for c in classes):
            errors.append({"code": "PROFILE_CLASS_INVALID", "class": name})
            continue
        name_evidence = [_evidence(span, clause) for location, span in selected.items() for clause in selected_quotes[location] if name in _class_names(clause)] if name != "__single__" else [_evidence(span, quote) for span, quote in declarations]
        if not name_evidence:
            errors.append({"code": "PROFILE_CLASS_NAME_EVIDENCE_MISSING", "class": name})
        item = {"name": name, "evidence": [], "name_evidence": name_evidence}
        for key in ("subscription_fee", "sales_service_fee"):
            evidence = verify(incoming[key], key, name)
            value = incoming[key]["value"] if evidence else None
            contrast = deterministic.get(name, {}).get(key)
            conflicting_comparison = len({e["value"] for e in deterministic.get(name, {}).get("evidence", []) if e["field"] == key}) > 1
            if conflicting_comparison or (contrast is not None and value is not None and contrast != value):
                errors.append({"code": "PROFILE_COMPARISON_CONFLICT", "class": name, "field": key})
                value = None
            item[key] = value
            if evidence:
                item["evidence"].append({**evidence, "field": key, "source_kind": "model"})
        classes.append(item)
    if set(deterministic) != {c["name"] for c in classes}:
        errors.append({"code": "PROFILE_CLASS_SET_CONFLICT"})
    floating = verify(result.value["floating_management_fee"], "floating_management_fee")
    floating_value = result.value["floating_management_fee"]["value"] if floating else None
    if comparison["floating_management_fee"] is True and floating_value is False:
        errors.append({"code": "PROFILE_MANAGEMENT_FEE_CONFLICT"})
        floating_value = None
    fee_errors = [e for e in errors if e.get("field") != "floating_management_fee" and e["code"] != "PROFILE_MANAGEMENT_FEE_CONFLICT"]
    complete = bool(classes) and not fee_errors and not truncated and all(c[k] is not None for c in classes for k in ("subscription_fee", "sales_service_fee"))
    facts = _count_facts(classes, declarations, model_count=model_count)
    if facts["share_class_count_conflict"] or any(e.get("field") == "share_class_count" for e in errors):
        facts.update(share_class_count=None, share_class_count_min=0, share_class_count_verified=False, share_class_universe_complete=False)
        errors.append({"code": "PROFILE_CLASS_COUNT_CONFLICT", "field": "share_class_count"})
    if truncated:
        facts.update(share_class_count=None, share_class_count_verified=False, share_class_universe_complete=False)
    universe_verified = not truncated and not facts["share_class_count_conflict"] and not any(e["code"] in {"PROFILE_CLASS_SET_CONFLICT", "PROFILE_CLASS_INVALID", "PROFILE_CLASS_NAME_EVIDENCE_MISSING", "PROFILE_CLASS_COUNT_CONFLICT"} for e in errors) and facts["share_class_count_verified"]
    return {"share_classes": sorted(c["name"] for c in classes), "classes": classes,
            "fee_groups": {"subscription_group": [c["name"] for c in classes if c["subscription_fee"] is True and c["sales_service_fee"] is False], "service_group": [c["name"] for c in classes if c["subscription_fee"] is False and c["sales_service_fee"] is True]},
            "fee_groups_verified": complete and universe_verified, "class_universe_verified": universe_verified, **facts, "floating_management_fee": floating_value,
            "management_fee_evidence": [floating] if floating else [], "source": "verified_model_with_independent_comparison",
            "comparison": comparison, "errors": errors, "context_truncated": truncated, "context_selection": selection}


def instantiate_template(action: dict[str, Any], ruleset: RuleSet, profile: dict[str, Any]) -> str:
    """Select only a rule-package literal. Evidence never creates write text."""
    text = ruleset.templates[action["template_id"]]
    if any(token in text for token in action.get("template_slots", {})):
        raise RuleError("TEMPLATE_VARIANT_UNAPPROVED")
    return text


def _instantiate_old(text: str, action: dict[str, Any], profile: dict[str, Any]) -> str:
    for token, group in action.get("template_slots", {}).items():
        names = profile.get("fee_groups", {}).get(group, [])
        if token in text and profile.get("fee_groups_verified") and names:
            text = text.replace(token, "、".join(n + "类" for n in names) + "基金份额")
    return text


def _subsection_title(text: str, action: dict[str, Any]) -> bool:
    compact, _ = _normalized_text(text.strip())
    compact = re.sub(r'^(?:[一二三四五六七八九十\d]+[、．.]|[（(][一二三四五六七八九十\d]+[）)])', '', compact)
    names = [action['subsection_anchor']] + action.get('subsection_aliases', [])
    return any(compact == name or compact.startswith(name+'：') or compact.startswith(name+':')
               or compact.startswith(name+'\n') for name in names)


_CONVERSION = (r'(?:除非[^。；\n\ufff9]{1,80}[，,])?(?:本基金(?:的)?)?'
    r'(?:不同(?:基金)?份额类别|不同类别(?:的)?基金份额|各类基金份额|不同基金份额类别)'
    r'(?:之间)?(?:暂)?(?:不得|不能|不允许|不可)(?:互相|相互)?转换[。；]?')
_SHORT_HOLDING = (r'(?:本基金)?(?:对|对于|针对)持续持有(?:期|时间)?(?:少于|不足|不满)7(?:日|天)的'
    r'(?:投资者|基金份额持有人)收取(?:不低于)?1[.．]5(?:0)?[%％]的赎回费[，,]'
    r'并(?:将上述赎回费)?(?:全额|全部)计入基金财产[。；]?')
_FEE_HOST = r'(?:调整(?:费率|收费方式)|申购费率[^。；\n\ufff9]*?赎回费率|赎回费率按照持有时间|实际执行的赎回费率)'


def _recognized_literals(text: str, kind: str) -> list[str]:
    pattern = {'conversion_prohibition':_CONVERSION,'short_holding_redemption':_SHORT_HOLDING}.get(kind)
    if pattern is None:
        return []
    normalized, positions = _normalized_text(text)
    return [text[positions[m.start()]:positions[m.end()-1]+1] for m in re.finditer(pattern, normalized)]


def _recognition_guard(quote: str, kind: str, host: Any, previous: Any) -> tuple[bool,str | None]:
    normalized, _ = _normalized_text(quote)
    if kind == 'conversion_prohibition':
        return bool(re.fullmatch(_CONVERSION,normalized)), 'CONVERSION_SCOPE_UNVERIFIED'
    if kind != 'short_holding_redemption':
        return False, None
    if '\ufff9' in host.text:
        return False, 'SHORT_HOLDING_HOST_STRUCTURE_UNVERIFIED'
    own_host=re.sub(r'\s+','',host.text)
    if any(t in own_host for t in ('赎回费用由','未归入基金财产的部分','赎回费用归入基金财产的比例')):
        return False, 'SHORT_HOLDING_NON_TARGET_HOST'
    if not re.fullmatch(_SHORT_HOLDING,normalized):
        return False, 'SHORT_HOLDING_VARIANT_UNVERIFIED'
    context = [host]
    if previous is not None and previous.zone==host.zone and previous.section_path==host.section_path:
        context.append(previous)
    texts=[p.text[s.start:s.end] for p in context for s in p.segments]
    # Fee-ownership paragraphs belong to the separate whole-paragraph action.
    fee_context=any(re.search(_FEE_HOST,_normalized_text(t)[0]) for t in texts)
    return fee_context, None if fee_context else 'SHORT_HOLDING_HOST_UNVERIFIED'


def _fragmented_phrase(previous: Any, current: Any, triggers: list[str]) -> list[dict[str, Any]]:
    if previous is None or previous.zone != current.zone or previous.section_path != current.section_path:
        return []
    left, left_positions = _normalized_text(previous.text)
    right, right_positions = _normalized_text(current.text)
    matches=[]
    for trigger in triggers:
        needle,_ = _normalized_text(trigger)
        for split in range(1,min(len(needle),120)):
            if left.endswith(needle[:split]) and right.startswith(needle[split:]):
                ls,le=left_positions[len(left)-split],left_positions[-1]+1
                rs,re=right_positions[0],right_positions[len(needle)-split-1]+1
                matches.append({'trigger':trigger,'location':current.location,'char_start':rs,'char_end':re,
                    'quote':current.text[rs:re],'evidence_spans':[
                        {'location':previous.location,'start':ls,'end':le,'quote':previous.text[ls:le]},
                        {'location':current.location,'start':rs,'end':re,'quote':current.text[rs:re]}]})
    return matches


def evaluate_candidates(inspection: Any, ruleset: RuleSet, profile: dict[str, Any] | None = None,
                        gateway: Any = None) -> list[dict[str, Any]]:
    profile = profile or extract_profile(inspection)
    results: list[dict[str, Any]] = []
    for action in ruleset.actions:
        applies, basis = applicability(action, profile)
        found: list[dict[str, Any]] = []
        scope_seen = False
        unsupported_scope = False
        try:
            fixed_template = instantiate_template(action, ruleset, profile)
            template_error = None
        except RuleError as exc:
            fixed_template, template_error = None, exc.code
        subsection = ""
        previous_section = None
        previous_span = None
        for span in inspection.paragraphs:
            logical_zone = getattr(span, "logical_zone", None) or span.zone
            current_section = (logical_zone, span.section_path)
            if current_section != previous_section:
                subsection, previous_section, previous_span = "", current_section, None
            heading = re.sub(r"^(?:[一二三四五六七八九十\d]+[、．.]|[（(][一二三四五六七八九十\d]+[）)])\s*", "", span.text.strip())
            explicit_label = _subsection_title(span.text, action)
            if explicit_label:
                subsection = span.text
                previous_span = None
            elif len(span.text) < 100 and re.match(r"^[一二三四五六七八九十\d]+[、．.]", span.text):
                subsection = ""
                previous_span = None
            sections=[action['section_anchor']]+action.get('section_aliases',[])
            if logical_zone not in action["regions"] or not any(title in span.section_path for title in sections):
                continue
            if not subsection:
                continue
            scope_seen = True
            if applies == "false":
                continue
            if span.zone == "unsupported_table":
                unsupported_scope = True
                found.append({"location": span.location, "region": logical_zone, "section_path": span.section_path,
                              "trigger": next((t for t in action["old_triggers"] if _normalized_matches(span.text, t)), None),
                              "char_start": 0, "char_end": len(span.text), "quote": span.text,
                              "mapping_safe": False, "status": "failed", "reason": "UNSUPPORTED_TARGET_STRUCTURE",
                              "structure_reasons": list(span.reasons), "template_id": action["template_id"],
                              "normalizer_version": NORMALIZER_VERSION,
                              "source_sha256": inspection.source_sha256})
                continue
            old_triggers = [_instantiate_old(t, action, profile) for t in action["old_triggers"]]
            if action['scope']=='phrase':
                for fragmented in _fragmented_phrase(previous_span,span,old_triggers):
                    found.append({**fragmented,'region':logical_zone,'section_path':span.section_path,
                        'mapping_safe':False,'status':'failed','reason':'CROSS_PARAGRAPH_TARGET_UNSUPPORTED',
                        'template_id':action['template_id'],'source_sha256':inspection.source_sha256,
                        'normalizer_version':NORMALIZER_VERSION})
            old_hits = [t for t in old_triggers if _normalized_matches(span.text, t)]
            kind = action.get('recognition_kind','literal')
            old_hits += [t for t in _recognized_literals(span.text,kind) if t not in old_hits]
            new_triggers = [_instantiate_old(t, action, profile) for t in action["new_triggers"]]
            appended = action["operation"] == "append" and applies == "true" and fixed_template is not None and fixed_template in span.text
            if appended:
                old_hits = []
            triggers = old_hits or [t for t in new_triggers if _normalized_matches(span.text, t)]
            occupied: list[tuple[int, int]] = []
            for trigger in sorted(triggers, key=len, reverse=True):
                for start, end in _normalized_matches(span.text, trigger):
                    if any(start < hi and end > lo for lo, hi in occupied):
                        continue
                    if action["scope"] == "sentence":
                        start = max(span.text.rfind(mark,0,start) for mark in ('。','；','\n','\ufff9')) + 1
                        if span.text[end - 1] not in "。；":
                            stops = [(i,mark) for mark in ('。','；','\n','\ufff9') if (i := span.text.find(mark,end)) >= 0]
                            stop = min(stops) if stops else None
                            end = stop[0] + (stop[1] in ('。','；')) if stop else len(span.text)
                        while start < end and span.text[start].isspace(): start += 1
                        while end > start and span.text[end-1].isspace(): end -= 1
                    elif action["scope"] == "paragraph":
                        start, end = 0, len(span.text)
                    if any(start < hi and end > lo for lo, hi in occupied):
                        continue
                    occupied.append((start, end))
                    quote = span.text[start:end]
                    safe = span.editable and any(s.start <= start and end <= s.end for s in span.segments)
                    candidate = {"location": span.location, "region": logical_zone, "section_path": span.section_path,
                                 "trigger": trigger, "char_start": start, "char_end": end, "quote": quote,
                                 "mapping_safe": safe, "status": "failed", "reason": None,
                                 "normalizer_version": NORMALIZER_VERSION,
                                 "template_id": action["template_id"], "source_sha256": inspection.source_sha256}
                    recognized, recognition_reason = _recognition_guard(quote,kind,span,previous_span)
                    candidate['recognition_kind']=kind
                    if recognized and kind=='short_holding_redemption':
                        contexts=[span]+([previous_span] if previous_span is not None else [])
                        evidence=[]
                        for host_span in contexts:
                            for segment in host_span.segments:
                                text=host_span.text[segment.start:segment.end]
                                compact,positions=_normalized_text(text)
                                match=re.search(_FEE_HOST,compact)
                                if match:
                                    lo=segment.start+positions[match.start()]
                                    hi=segment.start+positions[match.end()-1]+1
                                    literal=host_span.text[lo:hi]
                                    evidence.append({**_evidence(host_span,literal),'char_start':lo,'char_end':hi})
                        candidate['host_evidence']=evidence
                    if applies == "unknown":
                        candidate["reason"] = basis
                    elif template_error:
                        candidate["reason"] = template_error
                    elif not safe and old_hits:
                        candidate["reason"] = "UNSAFE_TEXT_MAPPING"
                    elif old_hits and kind=='short_holding_redemption' and not recognized:
                        candidate.update(status='excluded' if recognition_reason=='SHORT_HOLDING_NON_TARGET_HOST' else 'failed',reason=recognition_reason)
                    elif old_hits and kind=='conversion_prohibition' and not recognized:
                        candidate.update(status='failed',reason='CONVERSION_SCOPE_UNVERIFIED')
                    elif not old_hits:
                        template = fixed_template
                        if template and template in quote:
                            candidate.update(status="satisfied", reason="EXACT_TEMPLATE")
                        else:
                            candidate["reason"] = "LOCAL_SEMANTIC_JUDGMENT_REQUIRED"
                            if gateway is not None and hasattr(gateway, "call"):
                                try:
                                    result = gateway.call(task_type="judge_candidate", bounded_context=quote,
                                        response_schema={"type": "object", "properties": {"decision": {"type": "string", "enum": ["satisfied", "unsatisfied", "unknown"]}, "quote": {"type": "string"}}, "required": ["decision", "quote"], "additionalProperties": False},
                                        instruction="仅判断原文语义是否满足固定规则模板要求，禁止写作。模板：" + template,
                                        prompt_version="candidate_new_v1")
                                    candidate["model_judgment"] = result.value
                                    if not result.value.get("quote") or result.value["quote"] not in quote:
                                        raise RuleError("MODEL_CANDIDATE_EVIDENCE_INVALID")
                                    if result.value["decision"] == "satisfied":
                                        candidate.update(status="satisfied", reason="VERIFIED_LOCAL_SEMANTICS")
                                except Exception as exc:
                                    candidate["reason"] = getattr(exc, "code", "MODEL_CANDIDATE_FAILED")
                    else:
                        exact = recognized or any(_old_text_equal(quote, _instantiate_old(t, action, profile)) for t in action.get("old_texts", old_triggers if action["scope"] == "phrase" else []))
                        if not exact and gateway is not None and hasattr(gateway, "call"):
                            try:
                                result = gateway.call(task_type="judge_candidate", bounded_context=quote,
                                    response_schema={"type": "object", "properties": {"decision": {"type": "string", "enum": ["target", "non_target", "unknown"]}, "quote": {"type": "string"}}, "required": ["decision", "quote"], "additionalProperties": False},
                                    instruction="判断局部原文是否属于此规则目标旧条款；禁止生成条文。规则：" + action.get("description", action["action_id"]), prompt_version="candidate_v1")
                                value = result.value
                                candidate["model_judgment"] = value
                                if value.get("quote") not in quote or not value.get("quote"):
                                    raise RuleError("MODEL_CANDIDATE_EVIDENCE_INVALID")
                                exact = value.get("decision") == "target" and action["scope"] != "paragraph"
                                if value.get("decision") == "target" and action["scope"] == "paragraph":
                                    candidate["reason"] = "PARAGRAPH_SCOPE_BOUNDARY_UNVERIFIED"
                                if value.get("decision") == "non_target":
                                    candidate.update(status="excluded", reason="LOCAL_NON_TARGET")
                            except Exception as exc:
                                candidate["reason"] = getattr(exc, "code", "MODEL_CANDIDATE_FAILED")
                        if exact:
                            candidate["target_verified"] = True
                            candidate["replacement"] = fixed_template
                            if action["operation"] == "append":
                                candidate.update(operation="insert", anchor={"start": start, "end": end, "text": quote,
                                    "sha256": hashlib.sha256(quote.encode()).hexdigest()}, char_start=end, char_end=end)
                            candidate["reason"] = "RELEASE_GATE_CLOSED" if not action["auto_write"] else None
                            if action["auto_write"]:
                                candidate["status"] = "applied"
                        elif candidate["reason"] is None and candidate["status"] == "failed":
                            candidate["reason"] = "LOCAL_TARGET_VERIFICATION_REQUIRED"
                    found.append(candidate)
            previous_span = span
        failure_reason = None if applies == "false" else ("UNSUPPORTED_TARGET_STRUCTURE" if unsupported_scope else "TARGET_SCOPE_UNRESOLVED" if not scope_seen else template_error)
        status = "not_applicable" if applies == "false" else ("failed" if failure_reason or applies == "unknown" or any(c["status"] == "failed" for c in found) else "applied" if any(c["status"] == "applied" for c in found) else "satisfied_no_change" if any(c["status"] == "satisfied" for c in found) else "not_matched")
        results.append({"rule_id": action["rule_id"], "action_id": action["action_id"],
                        "applicability": applies, "applicability_basis": basis, "status": status,
                        "auto_write": action["auto_write"], "candidates": found,
                        "failure_reason": failure_reason, "scope_verified": scope_seen and not unsupported_scope,
                        "normalizer_version": NORMALIZER_VERSION,
                        "release_gate": "open" if action["auto_write"] else "closed"})
    return results
