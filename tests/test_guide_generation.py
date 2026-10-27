from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from docx import Document

from fundlex.guide_generation.corpus_catalog import parse_contract_filename, sync_corpus
from fundlex.guide_generation.corpus_segmenter import segment_contract
from fundlex.guide_generation.lexical import LexicalIndex, deterministic_query
from fundlex.guide_generation.authoring import induce_families
from fundlex.guide_generation.quality import run_quality_gate
from fundlex.guide_generation.models import (
    ClauseUnit,
    GuideItem,
    ImpactCandidate,
    LocalGuideCandidate,
    PolicyRequirement,
    RegulationBlock,
    RegulationDocument,
)
from fundlex.guide_generation.requirements import extract_requirements
from fundlex.regulatory.docx_parser import parse_regulation_docx
from fundlex.regulatory.ingestion import ingest_regulation
from fundlex.regulatory.pdf_parser import parse_regulation_pdf
from fundlex.store import RunStore
from fundlex.guide_generation.store import GuideGenerationStore

from guide_generation_fakes import FakeGuideRouter


def _contract(path: Path, fund: str, date: str, *, service_fee: str = "0.40%"):
    doc = Document()
    doc.add_paragraph("基金管理人：测试基金管理有限公司")
    doc.add_paragraph("基金托管人：测试银行")
    doc.add_paragraph(f"{fund}基金合同")
    doc.add_paragraph("第一部分  前言")
    doc.add_paragraph("订立本基金合同的目的是保护投资人合法权益。")
    doc.add_paragraph("第二部分  基金费用与税收")
    doc.add_paragraph("一、基金费用的种类")
    doc.add_paragraph("本基金的管理费按前一日基金资产净值的1.2%年费率计提。")
    doc.add_paragraph("二、基金销售服务费")
    doc.add_paragraph("本基金A类基金份额不收取销售服务费，C类基金份额的销售服务费按前一日C类基金份额资产净值的"
                      f"{service_fee}年费率计提。")
    doc.add_paragraph("C类基金份额的销售服务费每日计提，按月支付。")
    doc.add_paragraph("第三部分  基金份额的申购与赎回")
    doc.add_paragraph("六、申购和赎回的价格、费用及其用途")
    doc.add_paragraph("本基金A类基金份额的申购费率由基金管理人决定，并在招募说明书中列示。")
    doc.add_paragraph("赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。")
    doc.add_paragraph("第四部分  基金合同")
    doc.add_paragraph("本基金合同自基金份额持有人、基金管理人和基金托管人盖章之日起生效。")
    doc.save(path)


def _regulation_docx(path: Path):
    doc = Document()
    doc.add_paragraph("测试销售费用管理规定")
    doc.add_paragraph("第一条")
    doc.add_paragraph("基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。")
    doc.add_paragraph("第二条")
    doc.add_paragraph("对于投资者持续持有期限少于七日的基金份额，应当收取不低于赎回金额1.5%的赎回费，"
                      "并将上述赎回费全额计入基金财产。")
    doc.add_paragraph("第三条")
    doc.add_paragraph("基金管理人应当在基金合同、基金销售协议等法律文件中与相关主体约定上述费用的收取标准。")
    doc.save(path)


def test_docx_regulation_parse(tmp_path):
    path = tmp_path / "reg.docx"
    _regulation_docx(path)
    document = parse_regulation_docx(path)
    assert document.source_type == "docx"
    assert any(block.article_no == "第一条" for block in document.blocks)
    assert any("不得收取" in block.text for block in document.blocks)
    assert document.document_sha256


def test_reference_pdf_parse():
    path = Path("references/source/附件1：公开募集证券投资基金销售费用管理规定.pdf")
    if not path.is_file():
        pytest.skip("reference regulation pdf is not present")
    document = parse_regulation_pdf(path)
    assert document.page_count == 10
    assert len(document.blocks) > 50
    assert any(block.article_no == "第一条" for block in document.blocks)
    assert "销售费用" in document.title
    assert any("不得收取认" in block.text for block in document.blocks)


def test_contract_segmentation_and_sections(tmp_path):
    path = tmp_path / "fund_20240101.docx"
    _contract(path, "测试基金", "20240101")
    segmented = segment_contract(path, contract_version_id="CV-test")
    assert segmented.clauses
    assert any("基金费用与税收" in " ".join(clause.section_path) for clause in segmented.clauses)
    fee = next(clause for clause in segmented.clauses if "销售服务费" in clause.text)
    assert fee.paragraph_start >= 0
    assert fee.paragraph_end >= fee.paragraph_start
    assert fee.source_anchor.get("paragraph_start") is not None


def test_corpus_versioning(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    _contract(root / "测试基金基金合同_20230101.docx", "测试基金", "20230101")
    _contract(root / "测试基金基金合同_20240101.docx", "测试基金", "20240101")
    _contract(root / "另一基金基金合同_20240101.docx", "另一基金", "20240101")
    store = RunStore(tmp_path / "run")
    gg = GuideGenerationStore(store)
    result = sync_corpus(gg, root)
    versions = gg.list_contract_versions()
    assert len(versions) == 3
    assert result.snapshot.counts["latest"] == 2
    same_fund = [item for item in versions if item.fund_identity == "测试基金"]
    assert len(same_fund) == 2
    assert same_fund[0].contract_id == same_fund[1].contract_id
    assert any(item.previous_version_id for item in same_fund)
    assert any(item.latest_known_version for item in same_fund)
    assert not any(item.latest_known_version for item in same_fund if item.version_date == "20230101")
    clauses = gg.get_clauses(same_fund[-1].contract_version_id)
    assert clauses


def test_lexical_index_finds_rare_fee_clause(tmp_path):
    path = tmp_path / "c.docx"
    _contract(path, "测试基金", "20240101")
    segmented = segment_contract(path, contract_version_id="CV-test")
    index = LexicalIndex(segmented.clauses)
    requirement = PolicyRequirement(
        requirement_id="R-test", source_block_ids=["B1"], source_quote="不得收取销售服务费",
        article="第一条", norm_type="prohibition", subject="基金管理人", object="销售服务费",
        requirement="基金管理人不得收取销售服务费", conditions=[], exceptions=[],
        candidate_contract_domains=["基金费用与税收"], disposition="modify_contract")
    hits = index.search(deterministic_query(requirement))
    assert hits
    assert any("销售服务费" in segmented.clauses[hit.clause_index].text for hit in hits[:20])


def test_requirement_extraction_quote_validation(tmp_path):
    path = tmp_path / "reg.docx"
    _regulation_docx(path)
    document = ingest_regulation(path, original_filename=path.name)
    router = FakeGuideRouter()
    result = extract_requirements(router, document)
    assert result.requirements
    assert all(item.disposition for item in result.requirements)
    assert all(item.source_quote for item in result.requirements)
    by_id = {block.block_id: block.text for block in document.blocks}
    for requirement in result.requirements:
        joined = "\n".join(by_id[block_id] for block_id in requirement.source_block_ids)
        assert requirement.source_quote[:20] in joined or joined[:20] in requirement.source_quote

    class InventedRouter(FakeGuideRouter):
        def _value(self, task_type, context):
            value = super()._value(task_type, context)
            if task_type == "guide_req_extract":
                for item in value.get("requirements", []):
                    item["source_quote"] = "这是模型编造的法规原文"
            return value

    invented = extract_requirements(InventedRouter(), document)
    assert not any("编造" in item.source_quote for item in invented.requirements)
    assert all(item.disposition for item in invented.requirements)
    assert any(item.adjudication_status == "unresolved_article" for item in invented.requirements)
    assert any(item["severity"] == "critical" for item in invented.findings)


def test_requirement_source_supplement_only_repairs_cited_partial_span():
    blocks = [
        RegulationBlock("B0001", 0, "heading", "第一条", article_no="第一条", heading_level=3),
        RegulationBlock("B0002", 1, "paragraph", "前端收费方式可以按认（申）购金额（份额）数量适用不同费率。",
                        article_no="第一条"),
        RegulationBlock("B0003", 2, "paragraph", "后端收费方式可以按持有期限适用不同费率标准。",
                        article_no="第一条"),
        RegulationBlock("B0004", 3, "paragraph", "基金销售机构应当保存销售业务资料。",
                        article_no="第一条"),
    ]
    document = RegulationDocument("REG-SUPPLEMENT", "docx", "sha", "测试规定", blocks)

    class PartialSpanRouter(FakeGuideRouter):
        def _value(self, task_type, context):
            if task_type == "guide_req_extract":
                return {
                    "requirements": [{
                        "source_block_ids": ["B0002", "B0003"],
                        "source_quote": blocks[1].text,
                        "article": "第一条", "norm_type": "permission", "subject": "基金销售机构",
                        "object": "收费方式", "requirement": blocks[1].text,
                        "conditions": [], "exceptions": [], "applicable_scope": {},
                        "effective_time": "", "candidate_contract_domains": ["费用条款"],
                        "external_dependencies": [], "disposition": "modify_contract",
                        "disposition_reason": "partial span",
                    }],
                    "article_dispositions": [{
                        "article": "第一条", "disposition": "modify_contract", "reason": "partial span",
                    }],
                    "notes": "",
                }
            if task_type == "guide_req_review":
                return {"missing_requirements": [], "corrections": [],
                        "article_assessment": [], "notes": ""}
            return super()._value(task_type, context)

    result = extract_requirements(PartialSpanRouter(), document)
    supplement = next(item for item in result.requirements
                       if item.source_block_ids == ["B0003"])
    assert supplement.payload["source_supplement"] is True
    assert supplement.source_quote == blocks[2].text
    # B0004 was never cited by the model and must remain on normal coverage
    # paths instead of being silently manufactured as a source supplement.
    assert not any(item.source_block_ids == ["B0004"] for item in result.requirements)


def test_direct_sale_prohibition_qualifies_historical_fee_pattern():
    requirement = PolicyRequirement(
        requirement_id="R-direct", source_block_ids=["B1"],
        source_quote="基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。",
        article="第七条", norm_type="prohibition", subject="基金管理人",
        object="认（申）购费、销售服务费",
        requirement="基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。",
        disposition="modify_contract",
    )
    impact = ImpactCandidate(
        impact_id="IC-direct", requirement_id="R-direct", contract_version_id="CV-direct",
        clause_ids=["CL-direct"], source_text="A类及D类基金份额收取申购费用。",
        context="费用条款", impact_status="definite", discovery_sources=["lexical"],
    )
    candidate = LocalGuideCandidate(
        local_id="LG-direct", impact_ids=["IC-direct"], requirement_ids=["R-direct"],
        needs_modification="yes", business_goal="调整费用条款",
        new_text=("基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。"
                  "本基金A类及D类基金份额收取申购费用，不计提销售服务费。"),
    )
    family_result = induce_families(
        FakeGuideRouter(), [candidate], [requirement],
        {"CL-direct": ClauseUnit("CL-direct", "CV-direct", ["基金费用"], 1, 1,
                                  impact.source_text)},
    )
    family = family_result.families[0]
    assert "基金管理人销售其管理的基金，不得收取" in family["new_text"]
    assert "通过其他基金销售机构销售" in family["new_text"]
    assert any("直销" in value for value in family["conditions"])


def test_quality_gate_blocks_unqualified_direct_sale_fee_pattern():
    requirement = PolicyRequirement(
        requirement_id="R-quality-direct", source_block_ids=["B1"],
        source_quote="基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。",
        article="第七条", norm_type="prohibition", subject="基金管理人",
        object="认（申）购费、销售服务费",
        requirement="基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。",
        disposition="modify_contract",
    )
    impact = ImpactCandidate(
        impact_id="IC-quality-direct", requirement_id="R-quality-direct",
        contract_version_id="CV-quality-direct", clause_ids=["CL-quality-direct"],
        source_text="A类基金份额收取申购费用。", context="费用条款",
        impact_status="definite", discovery_sources=["lexical"],
    )
    item = GuideItem(
        guide_item_id="G-quality-direct", requirement_ids=["R-quality-direct"],
        impact_ids=["IC-quality-direct"], clause_family_ids=["CF-quality-direct"],
        section="基金费用", title="直销收费", business_requirement="调整收费条款",
        instruction="调整收费条款", new_text=(
            "基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。"
            "A类基金份额收取申购费用，不计提销售服务费。"
        ), new_text_origin="contract_pattern_adapted",
    )
    result = run_quality_gate(
        FakeGuideRouter(), [item], [requirement], [impact],
        {"CL-quality-direct": ClauseUnit("CL-quality-direct", "CV-quality-direct",
                                          ["基金费用"], 1, 1, impact.source_text)},
    )
    assert result.run_status == "fail"
    assert any(value["severity"] == "critical" and "渠道边界" in value["description"]
               for value in result.findings)


def test_article_disposition_prevents_silent_omission(tmp_path):
    blocks = [
        RegulationBlock(block_id="B0001", ordinal=0, type="heading", text="第一条", article_no="第一条",
                                heading_level=3),
        RegulationBlock(block_id="B0002", ordinal=1, type="paragraph",
                                text="基金管理人应当在基金合同中约定销售费用。", article_no="第一条"),
        RegulationBlock(block_id="B0003", ordinal=2, type="heading", text="第二条", article_no="第二条",
                                heading_level=3),
        RegulationBlock(block_id="B0004", ordinal=3, type="paragraph",
                                text="中国证监会对基金销售业务实施监督管理。", article_no="第二条"),
    ]
    document = RegulationDocument(document_id="REG", source_type="docx", source_sha256="x",
                                  title="测试规定", blocks=blocks)

    class SparseRouter(FakeGuideRouter):
        def _value(self, task_type, context):
            if task_type == "guide_req_extract":
                return {
                    "requirements": [{
                        "source_block_ids": ["B0002"], "source_quote": "基金管理人应当在基金合同中约定销售费用。",
                        "article": "第一条", "norm_type": "obligation", "subject": "基金管理人",
                        "object": "销售费用", "requirement": "基金合同应约定销售费用",
                        "conditions": [], "exceptions": [],
                        "applicable_scope": {"fund_types": [], "channels": [], "share_classes": [],
                                             "investor_types": [], "notes": ""},
                        "effective_time": "", "candidate_contract_domains": ["基金费用与税收"],
                        "external_dependencies": [], "disposition": "modify_contract",
                        "disposition_reason": "fake",
                    }],
                    "article_dispositions": [{
                        "article": "第一条", "source_block_ids": ["B0001", "B0002"],
                        "disposition": "modify_contract", "reason": "fake",
                    }, {
                        "article": "第二条", "source_block_ids": ["B0003", "B0004"],
                        "disposition": "out_of_contract_scope", "reason": "监管职责",
                    }],
                    "notes": "",
                }
            return super()._value(task_type, context)

    result = extract_requirements(SparseRouter(), document)
    assert result.requirements
    assert all(item.disposition for item in result.requirements)
    assert not any(item["category"] == "requirement_coverage" and item["severity"] == "critical"
                   for item in result.findings)
