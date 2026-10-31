"""app.js revision-review render must not re-query the whole DOM per revision
on every decision (B13 F8 / FL-D557).

A browser-level frame-time check needs a full Playwright document; these source
pins lock the three invariants the fix introduced: renderReview builds the
node/item index once, syncReview resolves entries through the index, and
accept-all/reject-all sync classes instead of rebuilding the whole review
layout (which re-parses the entire projected contract HTML).
"""

from pathlib import Path


def test_render_review_builds_dom_index():
    source = Path("frontend/app.js").read_text(encoding="utf-8")
    assert "const nodeMap=new Map();" in source
    assert "const itemMap=new Map();" in source
    assert "review.index={nodeMap,itemMap};" in source
    built = source.index("review.index={nodeMap,itemMap};")
    assert "syncReview();" in source[built:built + 120]


def test_sync_review_uses_index_entries():
    source = Path("frontend/app.js").read_text(encoding="utf-8")
    assert "state.review?.index?.nodeMap" in source
    assert "review.index?.itemMap.get(String(r.del_id))" in source
    assert "entry?entry.item:document.querySelector" in source


def test_accept_all_syncs_classes_without_full_rerender():
    source = Path("frontend/app.js").read_text(encoding="utf-8")
    marker = "for(const r of review.revisions)review.chosen[r.del_id]=verdict;"
    body = source[source.index(marker):source.index(marker) + 600]
    assert "syncReview();" in body
    assert "renderReview();" not in body
