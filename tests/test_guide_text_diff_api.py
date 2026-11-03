"""指引原文比对端点契约（FL-D770）：与合同比对页同套算法链、确定性、零模型。"""
from __future__ import annotations

import io

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex import guide_store

ALICE = {"X-FundLex-User": "alice"}
BOB = {"X-FundLex-User": "bob"}


def docx_bytes(paragraphs: list[str]) -> bytes:
    stream = io.BytesIO()
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    from fundlex.api import create_app
    return TestClient(create_app(tmp_path / "state"))


def uploaded_version(client, name: str, paragraphs: list[str], *, owner: str = "alice") -> dict:
    store = client.app.state.store
    return guide_store.create_custom_version(store, owner, name, docx_bytes(paragraphs))


def test_text_diff_contract_summary_rows_and_rendered_html(client):
    base = uploaded_version(client, "指引A.docx", ["第一章 总则", "赎回费由持有人承担", "第七章 附则"])
    target = uploaded_version(client, "指引B.docx", ["第一章 总则", "赎回费全额计入基金财产", "第七章 附则"])
    url = f"/api/guides/{target['id']}/text-diff"
    response = client.get(url, params={"against": base["id"]}, headers=ALICE)
    assert response.status_code == 200
    payload = response.json()
    assert payload["version_id"] == target["id"] and payload["against"] == base["id"]
    diff = payload["text_diff"]
    assert diff["algorithm"] == "guide-text-diff-v1"
    assert diff["identical"] is False and diff["summary"]["diffs"] >= 1
    assert (diff["summary"]["modify"] + diff["summary"]["insert"]
            + diff["summary"]["delete"]) == diff["summary"]["diffs"]
    joined = "".join(row["old_text"] + row["new_text"] for row in diff["diffs"])
    assert "赎回费" in joined
    for row in diff["diffs"]:
        # 每条差异给人读类型标签与段落定位，前端无需再翻译 engine 值。
        assert row["type_label"] in {"修改", "新增", "删除"}
        assert row["location"]  # 段落定位非空（pN）
    # 三段渲染与合同比对页同套高亮类名，前端拼接即所见。
    for key in ("left_html", "right_html", "merged_html"):
        assert diff[key] and "赎回费" in diff[key]
    assert "compare-ins" in diff["merged_html"] or "compare-del" in diff["merged_html"]
    assert diff["summary"]["coverage"]["status"] == "complete"
    # 确定性：同参两次字节一致。
    again = client.get(url, params={"against": base["id"]}, headers=ALICE)
    assert again.content == response.content


def test_text_diff_insert_delete_and_identical(client):
    base = uploaded_version(client, "指引A.docx", ["第一条", "第二条"])
    target = uploaded_version(client, "指引B.docx", ["第一条", "新增的一整条", "第二条改"])
    diff = client.get(f"/api/guides/{target['id']}/text-diff",
                      params={"against": base["id"]}, headers=ALICE).json()["text_diff"]
    assert diff["summary"]["diffs"] >= 1
    joined = "".join(row["old_text"] + row["new_text"] for row in diff["diffs"])
    assert "新增的一整条" in joined
    same = client.get(f"/api/guides/{target['id']}/text-diff",
                      params={"against": target["id"]}, headers=ALICE).json()["text_diff"]
    assert same["identical"] is True and same["summary"]["diffs"] == 0


def test_text_diff_guards(client):
    base = uploaded_version(client, "指引A.docx", ["甲"])
    target = uploaded_version(client, "指引B.docx", ["乙"])
    url = f"/api/guides/{target['id']}/text-diff"
    # 缺 against → 422；未知版本 → 404；跨 owner → 404（不泄露存在性）。
    assert client.get(url, headers=ALICE).status_code == 422
    assert client.get("/api/guides/nope/text-diff", params={"against": base["id"]},
                      headers=ALICE).status_code == 404
    assert client.get(url, params={"against": base["id"]}, headers=BOB).status_code == 404
    # FL-D1051：内置默认指引以服务端 canonical 原文参与比对（两侧方向均可），
    # 且版本标注 origin=builtin；上传侧仍 origin=uploaded。
    builtin = guide_store.BUILTIN_GUIDE_ID
    for version_id, against in ((builtin, target["id"]), (target["id"], builtin)):
        response = client.get(f"/api/guides/{version_id}/text-diff",
                              params={"against": against}, headers=ALICE)
        assert response.status_code == 200
        diff = response.json()["text_diff"]
        assert diff["from_version"]["origin"] == ("builtin" if against == builtin else "uploaded")
        assert diff["to_version"]["origin"] == ("builtin" if version_id == builtin else "uploaded")
        assert diff["summary"]["diffs"] >= 0
        assert "FundLex 内置默认指引" in diff["left_html"] + diff["right_html"]


def test_text_diff_unreadable_source_is_422_not_500(client):
    version = uploaded_version(client, "损坏.docx", ["甲"])
    path = guide_store.guide_source_path(client.app.state.store, version["id"])
    path.write_bytes(b"not a docx")
    other = uploaded_version(client, "正常.docx", ["乙"])
    response = client.get(f"/api/guides/{other['id']}/text-diff",
                          params={"against": version["id"]}, headers=ALICE)
    assert response.status_code == 422
    assert response.json()["detail"] == "GUIDE_TEXT_DIFF_UNREADABLE"


def _seed_cards_v2_builtin(client) -> None:
    """FL-D1052：插一条生产同形的卡片版内置（id=builtin-cards-v2）。"""
    import json, time
    from pathlib import Path
    store = client.app.state.store
    guide_store.ensure_builtin_guide(store)  # 建库表后再插卡片版内置
    cards_path = Path(__file__).resolve().parents[1] / "guides" / "builtin_cards_v2.json"
    doc = json.loads(cards_path.read_text(encoding="utf-8"))
    now = time.time()
    with store._connect() as db:
        db.execute("""INSERT OR REPLACE INTO guide_versions
            (id,owner,built_in,filename,source_sha256,document_sha256,parser_version,schema_version,
             prompt_versions,rules_json,rules_sha256,status,issues_json,qualification_status,
             created_at,updated_at,released_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("builtin-cards-v2", "", 1, "builtin_cards_v2.json", "",
             "cards-sha", "cards", "card_v1", "{}",
             json.dumps(doc, ensure_ascii=False), "cards-sha", "released", "{}", "converted_builtin",
             now, now, now))


def test_guide_detail_card_schema_exposes_cards_overview_with_action_text(client):
    """FL-D1078：卡版指引详情挂 cards_overview（含操作正文 action_text），供卡表直上人读。"""
    _seed_cards_v2_builtin(client)
    response = client.get("/api/guides/builtin-cards-v2", headers=ALICE)
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("guide_schema") == "guide_card_v1"
    cards = payload.get("cards_overview")
    assert isinstance(cards, list) and cards, "cards_overview must be populated for card-schema docs"
    first = cards[0]
    assert first["card_id"] and first["title"]
    assert first["action_type"] == "insert_after"
    assert "投资者通过直销机构" in first["action_text"]
    assert first["source_paragraphs"]

    # 组版指引（普通旧格式）返回空卡表，不串内容。
    target = uploaded_version(client, "指引A.docx", ["甲"])
    plain = client.get(f"/api/guides/{target['id']}", headers=ALICE).json()
    assert plain.get("cards_overview") == []
