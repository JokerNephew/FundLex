"""Regression tests for the qa-gg-audit hardening round (FL-D821~826).

Covers corpus configuration failure semantics, the discovery window fill
order, repair failure visibility and the evidence HTML residual count.
"""
from __future__ import annotations

import os

import pytest
from docx import Document

from fundlex.guide_generation import cli
from fundlex.guide_generation.corpus_catalog import CorpusConfigError, sync_corpus
from fundlex.guide_generation.discovery import DiscoveryConfig, path_b_contract_sweep
from fundlex.guide_generation.export import render_evidence_html
from fundlex.guide_generation.models import (
    ClauseUnit, ContractVersion, GuideItem, PolicyRequirement,
)
from fundlex.guide_generation.pipeline import GuidePipeline, PipelineConfig
from fundlex.guide_generation.repair import repair_items
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.store import RunStore

from guide_generation_fakes import FakeGuideRouter


def _contract(path, fund: str, date: str):
    doc = Document()
    doc.add_paragraph("基金管理人：测试基金管理有限公司")
    doc.add_paragraph(f"{fund}基金合同")
    doc.add_paragraph("第一部分  前言")
    doc.add_paragraph("第二部分  基金费用与税收")
    doc.add_paragraph("本基金A类基金份额不收取销售服务费。")
    doc.save(path)


def _gg(tmp_path):
    return GuideGenerationStore(RunStore(tmp_path / "run"))


# ---------------------------------------------------------------- FL-D900 --
def test_segmenter_body_ellipsis_does_not_silently_drop_clauses(tmp_path):
    """A body paragraph that trails off with "……" is not a TOC entry; the
    parser must not enter a state that skips the following clauses."""
    from fundlex.guide_generation.corpus_segmenter import segment_contract
    path = tmp_path / "陷阱基金基金合同_20240101.docx"
    doc = Document()
    doc.add_paragraph("基金管理人：测试基金管理有限公司")
    doc.add_paragraph("陷阱基金基金合同")
    doc.add_paragraph("第一部分  前言")
    doc.add_paragraph("本基金的投资范围包括具有良好流动性的金融工具，如国债、央行票据……")
    doc.add_paragraph("基金管理人应当在定期报告中披露投资组合的具体情况。")
    doc.add_paragraph("第二部分  基金费用与税收")
    doc.add_paragraph("本基金A类基金份额不收取销售服务费。")
    doc.save(path)
    segmented = segment_contract(path, contract_version_id="CV-toc-trap")
    body = "\n".join(clause.text for clause in segmented.clauses)
    assert "披露投资组合的具体情况" in body
    assert "销售服务费" in body


def test_segmenter_real_toc_with_page_numbers_is_skipped(tmp_path):
    from fundlex.guide_generation.corpus_segmenter import segment_contract
    path = tmp_path / "目录基金基金合同_20240101.docx"
    doc = Document()
    doc.add_paragraph("基金管理人：测试基金管理有限公司")
    doc.add_paragraph("目录基金基金合同")
    doc.add_paragraph("目录")
    doc.add_paragraph("第一部分 前言……………………1")
    doc.add_paragraph("第二部分 基金费用与税收……………………5")
    doc.add_paragraph("第一部分  前言")
    doc.add_paragraph("订立本基金合同的目的是保护投资人合法权益。")
    doc.add_paragraph("第二部分  基金费用与税收")
    doc.add_paragraph("本基金A类基金份额不收取销售服务费。")
    doc.save(path)
    segmented = segment_contract(path, contract_version_id="CV-toc-real")
    body = "\n".join(clause.text for clause in segmented.clauses)
    assert "……………………" not in body
    assert "销售服务费" in body


# ---------------------------------------------------------------- FL-D821 --
def test_sync_corpus_missing_directory_is_explicit(tmp_path):
    with pytest.raises(CorpusConfigError) as excinfo:
        sync_corpus(_gg(tmp_path), tmp_path / "does-not-exist")
    assert excinfo.value.code == "CORPUS_DIR_MISSING"


def test_sync_corpus_blank_directory_is_explicit(tmp_path):
    with pytest.raises(CorpusConfigError) as excinfo:
        sync_corpus(_gg(tmp_path), "")
    assert excinfo.value.code == "CORPUS_DIR_MISSING"


def test_sync_corpus_file_path_is_not_a_corpus(tmp_path):
    path = tmp_path / "some.docx"
    _contract(path, "测试基金", "20240101")
    with pytest.raises(CorpusConfigError) as excinfo:
        sync_corpus(_gg(tmp_path), path)
    assert excinfo.value.code == "CORPUS_DIR_MISSING"


def test_sync_corpus_unreadable_directory_is_explicit(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _contract(corpus / "测试基金基金合同_20240101.docx", "测试基金", "20240101")
    corpus.chmod(0)
    try:
        with pytest.raises(CorpusConfigError) as excinfo:
            sync_corpus(_gg(tmp_path), corpus)
    finally:
        corpus.chmod(0o755)
    assert excinfo.value.code == "CORPUS_DIR_UNREADABLE"


def test_sync_corpus_empty_directory_yields_empty_snapshot_not_error(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    result = sync_corpus(_gg(tmp_path), corpus)
    assert result.eligible_files == 0
    assert result.snapshot.contract_version_ids == []


def test_sync_corpus_records_eligible_files_before_limit(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _contract(corpus / "甲基金基金合同_20240101.docx", "甲基金", "20240101")
    _contract(corpus / "乙基金基金合同_20240101.docx", "乙基金", "20240101")
    result = sync_corpus(_gg(tmp_path), corpus, limit=1)
    assert result.eligible_files == 2
    assert len(result.snapshot.contract_version_ids) == 1


def test_pipeline_snapshot_stage_propagates_corpus_config_error(tmp_path):
    gg = _gg(tmp_path)
    run = gg.create_run(owner="t", filename="reg.docx", source_type="docx",
                        source_sha256="x", title="t", payload={})
    pipeline = GuidePipeline(
        gg, run["id"], FakeGuideRouter(),
        PipelineConfig(corpus_dir=str(tmp_path / "missing-corpus")))
    with pytest.raises(CorpusConfigError) as excinfo:
        pipeline.stage_snapshot()
    assert excinfo.value.code == "CORPUS_DIR_MISSING"


def test_cli_sync_corpus_exit_codes(tmp_path, capsys):
    data_dir = tmp_path / "data"
    missing = cli.main(["--data-dir", str(data_dir), "sync-corpus",
                        "--corpus-dir", str(tmp_path / "missing")])
    assert missing == 2
    assert "CORPUS_DIR_MISSING" in capsys.readouterr().err

    empty = tmp_path / "empty"
    empty.mkdir()
    assert cli.main(["--data-dir", str(data_dir), "sync-corpus",
                     "--corpus-dir", str(empty)]) == 3
    assert "no eligible contracts" in capsys.readouterr().err

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _contract(corpus / "测试基金基金合同_20240101.docx", "测试基金", "20240101")
    assert cli.main(["--data-dir", str(data_dir), "sync-corpus",
                     "--corpus-dir", str(corpus)]) == 0


def test_cli_default_corpus_dir_is_absolute_repo_fallback(monkeypatch):
    monkeypatch.delenv("FUNDLEX_GUIDE_CORPUS_DIR", raising=False)
    assert os.path.isabs(cli._default_corpus_dir())
    assert cli._default_corpus_dir().endswith("funds_word")


# ---------------------------------------------------------------- FL-D823 --
def test_sweep_window_keeps_related_tail_before_rotating(monkeypatch):
    """Related requirements ranked 9+ must enter the window when there is
    room; only remaining slots are filled by rotation (FL-D823)."""
    from fundlex.guide_generation import discovery

    requirements = [
        PolicyRequirement(
            requirement_id=f"R-{index:04d}", source_block_ids=[], source_quote="q",
            article="第一条", norm_type="obligation", subject="s", object="o",
            requirement=f"要求{index}")
        for index in range(12)
    ]
    monkeypatch.setattr(discovery, "_sweep_requirements",
                        lambda reqs, batch, max_requirements: reqs[:12])
    clause = ClauseUnit(
        clause_id="CL-1", contract_version_id="CV-1", section_path=["基金费用与税收"],
        paragraph_start=0, paragraph_end=0, text="本基金A类基金份额不收取销售服务费。")
    version = ContractVersion(
        contract_version_id="CV-1", contract_id="C-1", fund_identity="测试基金",
        display_name="测试基金", version_date="20240101", source_sha256="x",
        source_path="x", source_size=1, parser_version="p")

    contexts: list[str] = []

    class SweepRouter(FakeGuideRouter):
        def call(self, *, task_type, bounded_context, **kwargs):
            contexts.append(bounded_context)
            from guide_generation_fakes import _Result
            return _Result({"findings": [], "uncovered_suspicions": [],
                            "batch_status": "not_affected"})

    impacts, suspicions, batches, calls = path_b_contract_sweep(
        SweepRouter(), None, requirements, [version], {"CV-1": [clause]},
        DiscoveryConfig(path_b_max_requirements=12))
    swept = "\n".join(contexts)
    for requirement in requirements:
        assert requirement.requirement_id in swept


# ---------------------------------------------------------------- FL-D825 --
def test_evidence_html_renders_persisted_new_impacts_count():
    html = render_evidence_html({
        "run": {"stats": {}},
        "residual_rounds": [{"round_no": 1, "status": "new_patterns",
                             "new_patterns": 2, "new_impacts": 3}],
    })
    assert "<td>3</td>" in html


# ---------------------------------------------------------------- FL-D826 --
def _critical_finding(item_id: str) -> dict:
    return {
        "finding_id": "F-critical-1", "guide_item_id": item_id,
        "category": "regulation_fidelity", "severity": "critical", "status": "open",
        "description": "changed subject", "evidence_quote": "证据",
    }


def _repair_target() -> GuideItem:
    return GuideItem(
        guide_item_id="G-repair-fail", requirement_ids=["R-1"], impact_ids=[],
        clause_family_ids=[], section="费用", title="直销收费",
        business_requirement="调整收费条款", instruction="调整收费条款",
        new_text="原文案", new_text_origin="model_drafted")


def test_repair_model_failure_records_visible_finding():
    router = FakeGuideRouter()
    router.fail_task_types.add("guide_repair")
    item = _repair_target()
    repaired, findings, calls = repair_items(
        router, [item], requirements=[], impacts=[], clauses={},
        findings=[_critical_finding(item.guide_item_id)])
    assert repaired == []
    assert calls == 0
    failures = [value for value in findings
                if value.get("category") == "repair" and value.get("severity") == "major"]
    assert failures and failures[0]["guide_item_id"] == item.guide_item_id


def test_stage_repair_persists_failure_findings_when_nothing_repaired(tmp_path):
    gg = _gg(tmp_path)
    run = gg.create_run(owner="t", filename="reg.docx", source_type="docx",
                        source_sha256="x", title="t", payload={})
    item = _repair_target()
    gg.replace_guide_items(run["id"], [item])
    gg.replace_findings(run["id"], [_critical_finding(item.guide_item_id)])
    router = FakeGuideRouter()
    router.fail_task_types.add("guide_repair")
    pipeline = GuidePipeline(gg, run["id"], router, PipelineConfig(
        corpus_dir=str(tmp_path), repair_rounds=1))
    result = pipeline.stage_repair()
    assert result["repaired"] == 0
    stored = gg.get_findings(run["id"])
    assert any(value.get("category") == "repair" and value.get("severity") == "major"
               for value in stored)
