"""Phase 8 tests: artifact claim replay + completion mutation suite (plan v4 §28).

Each mutation the plan lists must be rejected by the replay: a dropped edit, a
missing replacement, a changed number, an unauthorized insertion.
"""
from fundlex.generation.claim_replay import replay_claims


class _Span:
    def __init__(self, location: str, text: str) -> None:
        self.location = location
        self.text = text


class _Inspection:
    def __init__(self, texts: list[str]) -> None:
        self._map = {f"p{index}": _Span(f"p{index}", text)
                     for index, text in enumerate(texts)}

    def by_location(self, location: str) -> _Span:
        return self._map[location]


RULES = {
    "G14": {
        "rule_id": "G14",
        "operations": [{"op": "replace",
                        "old_text": "基金管理人可以适当调低基金申购费率、赎回费率、转换费率和销售服务费率。",
                        "new_text": "基金管理人可以适当调低基金申购费率和销售服务费率。"}],
        "old_text_variants": ["基金管理人可以适当调低基金申购费率、赎回费率和转换费率。"],
    },
}

BEFORE = "基金管理人可以适当调低基金申购费率、赎回费率、转换费率和销售服务费率。"
AFTER_OK = "基金管理人可以适当调低基金申购费率和销售服务费率。"


def _edit(replacement: str = AFTER_OK, location: str = "p0") -> dict:
    return {"rule_id": "G14", "location": location, "start": 0, "end": len(BEFORE),
            "operation_keys": ["G14:0"],
            "replacement": replacement, "content_source": "tier1_template", "evidence": {}}


def test_claim_replay_accepts_correct_artifact():
    result = replay_claims([_edit()], _Inspection([BEFORE]), _Inspection([AFTER_OK]),
                           rules_by_id=RULES)
    assert result["verified"] is True
    assert result["checked"] == 1


def test_mutation_no_change_applied_is_caught():
    result = replay_claims([_edit()], _Inspection([BEFORE]), _Inspection([BEFORE]),
                           rules_by_id=RULES)
    assert result["verified"] is False
    assert result["failures"][0]["code"] == "CLAIM_NO_CHANGE_APPLIED"


def test_mutation_replacement_missing_is_caught():
    result = replay_claims([_edit()], _Inspection([BEFORE]),
                           _Inspection(["基金管理人可以适当调低其他费率。"]),
                           rules_by_id=RULES)
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert codes & {"CLAIM_REPLACEMENT_MISSING", "CLAIM_VALIDATION_FAILED"}


def test_mutation_number_change_is_caught():
    rules = {"G16": {"rule_id": "G16",
                     "operations": [{"op": "replace",
                                     "old_text": "C类基金份额的销售服务费按前一日资产净值的0.40%年费率计提。",
                                     "new_text": "C类基金份额的销售服务费每日计提。"}],
                     "old_text_variants": []}}
    before = "C类基金份额的销售服务费按前一日资产净值的0.40%年费率计提。"
    after_ok = "C类基金份额的销售服务费每日计提。"
    edit = {"rule_id": "G16", "location": "p0", "replacement": after_ok,
            "operation_keys": ["G16:0"], "start": 0, "end": len(before),
            "content_source": "composed", "evidence": {"fixed_text": after_ok}}
    assert replay_claims([edit], _Inspection([before]), _Inspection([after_ok]),
                         rules_by_id=rules)["verified"] is True
    mutated = "C类基金份额的销售服务费按前一日资产净值的0.60%年费率计提。"
    result = replay_claims([edit], _Inspection([before]), _Inspection([mutated]),
                           rules_by_id=rules)
    assert result["verified"] is False


def test_mutation_unauthorized_insertion_is_caught():
    rules = {"G05": {"rule_id": "G05",
                     "operations": [{"op": "replace", "old_text": "调低赎回费率",
                                     "new_text": "调低销售服务费率"}],
                     "old_text_variants": []}}
    before = "基金管理人可以适当调低赎回费率。"
    after_ok = "基金管理人可以适当调低销售服务费率。"
    edit = {"rule_id": "G05", "location": "p0", "replacement": after_ok,
            "operation_keys": ["G05:0"], "start": 0, "end": len(before),
            "content_source": "fragment_replace", "evidence": {}}
    assert replay_claims([edit], _Inspection([before]), _Inspection([after_ok]),
                         rules_by_id=rules)["verified"] is True
    tampered = after_ok + "并最迟应于2030年12月31日前公告。"
    result = replay_claims([edit], _Inspection([before]), _Inspection([tampered]),
                           rules_by_id=rules)
    assert result["verified"] is False
