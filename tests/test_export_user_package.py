"""用户视角导出包契约（FL-D700 段）：

- 结果清单.csv：序号/合同文件/处理结果（人读）/修改处数/修改内容摘要/备注；
- 逐份修改说明/<合同>/<合同>（修改说明）.csv：一修改一行（类型/位置/前/后/对应指引）；
- 结果总览.md 与两个 CSV 不得泄露 engine 键名、错误码、哈希等技术信息；
- report_json/report_md 不入包。
"""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from fundlex.jobs import Worker

from test_tasks_api import ALICE, client, create, manifest, package, upload  # noqa: F401


def _edit_report():
    return {
        "execution_mode": "delivery",
        "delivery_status": "incomplete",
        "guide": {"groups": [
            {"rule_id": "G12", "title": "赎回费归属改为全额计入基金财产：",
             "requirement": "赎回费应全额计入基金财产"},
            {"rule_id": "G15", "title": "删除销售服务费支付旧条款：", "requirement": "删除旧句"},
        ]},
        "plan": {"edits": [
            {"rule_id": "G12", "location": "p42", "operation": "replace",
             "components": [{"expected_old_text": "赎回费由基金份额持有人承担"}],
             "replacement": "赎回费全额计入基金财产"},
            {"rule_id": "G15", "location": "p77", "operation": "replace",
             "components": [{"expected_old_text": "旧的销售服务费支付条款"}],
             "replacement": ""},
        ]},
        "unresolved": [{"rule_id": "G15", "reason": "RECALL_TARGET_UNRESOLVED"}],
    }


def test_archive_contains_per_edit_csv_row_and_readable_cells(client, tmp_path):
    data = package()
    files = manifest(1, data)
    task = create(client, files).json()["id"]
    upload(client, task, files, data)
    store = client.app.state.store
    worker = Worker(store, lambda *_: _edit_report())
    assert worker.run_once()

    response = client.get(f"/api/tasks/{task}/download/all", headers=ALICE)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        detail_name = "逐份修改说明/合同000/合同000（修改说明）.csv"
        assert detail_name in names
        # 报告 JSON/MD（内部技术件）不进包。
        assert not any("report_json" in n or "report_md" in n for n in names)

        detail = archive.read(detail_name).decode("utf-8-sig")
        lines = detail.splitlines()
        assert lines[0] == "序号,修改类型,位置,修改前,修改后,对应指引"
        assert "1,替换,p42,赎回费由基金份额持有人承担,赎回费全额计入基金财产,G12：赎回费归属改为全额计入基金财产" in lines[1]
        # replace 空 replacement 如实标为删除。
        assert lines[2].startswith("2,删除,p77,旧的销售服务费支付条款,（删除该句）")
        assert "G15：删除销售服务费支付旧条款" in lines[2]
        # 引擎原始键名/技术字段不得出现在用户 CSV。
        for leaked in ("expected_old_text", "rule_id", "engine", "sha256", "replacement"):
            assert leaked not in detail

        listing = archive.read("结果清单.csv").decode("utf-8-sig")
        header, row = listing.splitlines()[:2]
        assert header == "序号,合同文件,处理结果,修改处数,修改内容摘要,备注"
        assert "部分条款未修改（详见修改说明）" in row
        assert ",2," in row  # 修改处数
        assert "赎回费归属改为全额计入基金财产" in row
        assert "1 项条款按安全规则保持原文，详见修改说明" in row
        for leaked in ("job_status", "incomplete", "RECALL_TARGET_UNRESOLVED", "engine"):
            assert leaked not in listing

        overview = archive.read("结果总览.md").decode("utf-8")
        assert "部分修改 1 份" in overview
        assert "（修改说明）.csv" in overview
        for leaked in ("RECALL_TARGET_UNRESOLVED", "incomplete", "engine_build", "sha256"):
            assert leaked not in overview


def test_archive_clips_long_cells_and_points_to_redline(client, tmp_path):
    long_text = "长" * 500
    report = _edit_report()
    report["plan"]["edits"] = [{
        "rule_id": "G12", "location": "p9", "operation": "replace",
        "components": [{"expected_old_text": long_text}], "replacement": long_text}]
    data = package()
    files = manifest(1, data)
    task = create(client, files).json()["id"]
    upload(client, task, files, data)
    store = client.app.state.store
    worker = Worker(store, lambda *_: report)
    assert worker.run_once()

    response = client.get(f"/api/tasks/{task}/download/all", headers=ALICE)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        detail = archive.read("逐份修改说明/合同000/合同000（修改说明）.csv").decode("utf-8-sig")
    assert "（全文见同目录「（全量痕迹版）」文件）" in detail
    assert "长" * 201 not in detail.replace("（全文见同目录「（全量痕迹版）」文件）", "")


def test_failed_task_archive_still_explains_instead_of_409(client, tmp_path):
    """失败任务没有可交付文件，但清单/总览必须能下载并给出人读说明。"""
    data = package()
    files = manifest(1, data)
    task = create(client, files).json()["id"]
    upload(client, task, files, data)
    store = client.app.state.store
    job = store.claim()
    store.finish(job["id"], job["fencing_token"],
                 report={"delivery_status": "not_generated"}, artifacts={},
                 failed=True, error_code="PROCESSING_FAILED")

    response = client.get(f"/api/tasks/{task}/download/all", headers=ALICE)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        listing = archive.read("结果清单.csv").decode("utf-8-sig")
        overview = archive.read("结果总览.md").decode("utf-8")
        assert "PROCESSING_FAILED" not in listing and "PROCESSING_FAILED" not in overview
        assert "处理未完成，未生成可交付文件；建议重新上传该合同再试一次" in listing
        assert "失败 1 份" in overview
        assert "需要重新提交或人工处理的合同" in overview
        assert "error_code" not in overview
