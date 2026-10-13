from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def test_catalogue_covers_all_guide_actions_and_stays_unreleased():
    rules = json.loads((ROOT / "rules/rules_v1.json").read_text(encoding="utf-8"))
    assert len(rules["actions"]) == 22
    assert {a["rule_id"] for a in rules["actions"]} == {f"R{i:02}" for i in range(1, 18)}
    assert rules["release_policy"]["status"] == "unreleased"
    assert len({a["action_id"] for a in rules["actions"]}) == 22
    for action in rules["actions"]:
        assert action["auto_write"] is False and action["approved"] is False
        assert action["release_threshold"]["registered_before_full_evaluation"] is True
        assert action["release_threshold"]["metrics"]["location_precision"]["min"] == 0.99
        assert action["evaluation_metrics"] is None and action["evaluation_report_id"] is None
        assert action["approval_record"] is None
        assert action["old_texts"] and action["on_unknown"] == "failed"
        assert action["condition"] in {
            "always", "multi_class", "single_class", "has_service_fee", "no_service_fee",
            "fee_groups", "floating_single", "floating_multi", "nonfloating_service_multi",
        }
        assert action["template_id"] in rules["templates"]
    branches = {a["action_id"]: a for a in rules["actions"] if a["rule_id"] == "R03"}
    assert branches["R03-A1"]["condition"] == "has_service_fee"
    assert branches["R03-A2"]["condition"] == "no_service_fee"
    assert branches["R03-A2"]["old_texts"] == ["、调低赎回费率"]
    assert branches["R03-A3"]["condition"] == "always"


def test_source_provenance_and_reproducible_compilation():
    spec = importlib.util.spec_from_file_location("catalogue", ROOT / "rules/compile_catalogue.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rules = json.loads((ROOT / "rules/rules_v1.json").read_text(encoding="utf-8"))
    assert module.compile_catalogue() == rules
    source = ROOT / rules["source"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == rules["source_sha256"]
    with ZipFile(source) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = {i: "".join(t.text or "" for t in p.findall(".//w:t", ns))
                  for i, p in enumerate(root.findall("w:body/w:p", ns), 1)}
    for template in rules["templates"].values():
        for provenance in template["source_provenance"]:
            assert provenance["sha256"] == hashlib.sha256(
                paragraphs[provenance["paragraph"]].encode()).hexdigest()
        for token, group in template["template_slots"].items():
            assert group in {"subscription_group", "service_group"}
            assert token in {"A类基金份额", "C类基金份额"}
    assert rules["templates"]["R14-A1"]["text"] == "\n".join(paragraphs[n] for n in range(79, 86))
    assert rules["templates"]["R08-A1"]["text"] == paragraphs[45].split("：", 1)[1]
    assert rules["templates"]["R17-A3"]["text"] == paragraphs[106].split("：", 1)[1]


def test_release_requires_actual_results_not_threshold_presence():
    from copy import deepcopy
    import pytest
    from fundlex.rules import load_ruleset, validate_release_gate
    action = deepcopy(load_ruleset("v1").actions[0])
    action.update(approved=True, evaluation_report_id="fixture-eval", approval_record="fixture-approval")
    policy = {"status": "released", "evaluation_report_id": "fixture-eval", "approval_record": "fixture-approval"}
    with pytest.raises(ValueError):
        validate_release_gate(action, policy)
    gates = action["release_threshold"]
    values = lambda items: {k: v.get("min", v.get("max")) for k, v in items.items()}
    from fundlex.rules import PROMPT_VERSIONS
    tested_context = {"engine_build": "1" * 64, "model_transport_sha256": "2" * 64, "actual_model": "independent-fixture", "prompt_versions": dict(PROMPT_VERSIONS)}
    policy["evaluation_context"] = tested_context
    action["evaluation_metrics"] = {"tested_context": tested_context, "action_id": action["action_id"], "evaluation_report_id": "fixture-eval", "threshold_registration_id": gates["registration_id"], "metrics": values(gates["metrics"]), "profile_metrics": {f: values(g) for f, g in gates["profile_metrics"].items()}}
    validate_release_gate(action, policy)
    action["evaluation_metrics"]["metrics"]["location_precision"] = 0.98
    with pytest.raises(ValueError, match="below threshold"):
        validate_release_gate(action, policy)
    action["evaluation_metrics"]["metrics"]["location_precision"] = 0.99
    del action["evaluation_metrics"]["profile_metrics"]["share_classes"]["accuracy"]
    with pytest.raises(ValueError, match="missing or invalid"):
        validate_release_gate(action, policy)


def test_missing_condition_is_rejected_not_defaulted_to_always(tmp_path, monkeypatch):
    import pytest
    import fundlex.rules as module
    raw = json.loads((ROOT / "rules/rules_v1.json").read_text(encoding="utf-8"))
    del raw["actions"][0]["condition"]
    folder = tmp_path / "rules"
    folder.mkdir()
    (folder / "rules_v1.json").write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(tmp_path / "fundlex" / "rules.py"))
    with pytest.raises(module.RuleError, match="RULESET_INVALID"):
        module.load_ruleset("v1")
    with pytest.raises(module.RuleError, match="RULE_CONDITION_UNKNOWN"):
        module.applicability({}, {})
