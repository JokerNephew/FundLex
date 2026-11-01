"""FL-D930 谓词等价性测试：canary 准入谓词与 recall 路由谓词必须恒等。

判词 B8（等价性测试先行；共享实现重构排到引擎稳定窗口）：本测试锁住
``guide_canary._declared_key`` 与 ``recall._declared_operation_key`` 的镜像
关系——任何一侧先行改版都会在这里红灯。
"""
from __future__ import annotations

import pytest

from fundlex.guide_canary import _declared_key
from fundlex.recall import _declared_operation_key

CASES = [
    ("G01", 0, {}),
    ("G01", 0, None),
    ("G02", 1, {"operation_id": "G02:CUSTOM"}),
    ("g02", 1, {"operation_id": "g02:custom"}),  # 大小写归一
    ("G05", 2, {"operation_id": "  G05:B1  "}),  # 前后空白
    ("G14", 5, {"operation_id": ""}),            # 空串派生
    ("G20", 1, {"operation_id": "G20:X", "other": 1}),
    ("G21", 0, {"operation_id": None}),
]

RULE_IDS = {"G01": 1, "G02": 2, "G05": 3, "G14": 6, "G20": 2, "G21": 1}


@pytest.mark.parametrize("rule_id,index,operation", CASES)
def test_declared_key_parity(rule_id, index, operation):
    canary = _declared_key(rule_id, index, operation)
    recall = _declared_operation_key(rule_id, index, operation)
    assert canary == recall, f"谓词漂移: canary={canary!r} recall={recall!r}"


def test_parity_across_registered_inventory():
    """全部已注册操作逐一比对（映射侧恒等是全量性质，不是抽查）。"""
    for rule_id, count in RULE_IDS.items():
        for index in range(count):
            operation = {"operation_id": f"{rule_id}:{index}"}
            assert _declared_key(rule_id, index, operation) == \
                _declared_operation_key(rule_id, index, operation)
