"""Compare viewer scroll/splitter performance harness (FL-D840/FL-D841).

Drives the *real* repository compare.js through Chromium against fixture API
payloads (650-block unequal-length contract pair with 120 diffs) and records:
  * longtask count / total blocking time during scripted activity
  * rAF frame-gap p95 and share of frames above 25 ms
  * number of SVG connector rebuilds (drawLines churn)
  * number and total duration of forced VirtualDocument.refresh(true) passes
  * cross-pane alignment after splitter driven width changes (index equality)

Results are written as JSON to var/qa-compare-scroll-perf/. The test always
asserts functional sanity (no page errors, alignment correct); the numeric
measurements are compared across code revisions by the line owner.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                                reason="opt-in V1 Chromium suite")

CAP = {
    "auth_mode": "dev",
    "login_required": False,
    "registration_open": False,
    "app_version": "scroll-perf",
    "upload_limits": {"max_file_bytes": 64 * 1024 * 1024},
    "engine": {"id": "test-engine", "delivery_mode": "formal", "guide": None, "actions_total": 0},
}

OUT_DIR = Path(os.getenv("COMPARE_PERF_OUT", "var/qa-compare-scroll-perf"))
RUN_LABEL = os.getenv("COMPARE_PERF_LABEL", "run")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=os.getenv("FUNDLEX_BROWSER_HEADLESS", "1") != "0")
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def live_dev(tmp_path_factory, monkeypatch_module):
    base_dir = tmp_path_factory.mktemp("compare-perf")
    import uvicorn
    from fundlex.api import create_app
    app = create_app(base_dir / "data", auth_db=str(base_dir / "auth.sqlite3"))
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.02)
    assert server.started
    yield base
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    patcher = MonkeyPatch()
    patcher.setenv("FUNDLEX_AUTH_MODE", "dev")
    yield patcher
    patcher.undo()


def respond(route, body, status=200, headers=None):
    route.fulfill(status=status, content_type="application/json",
                  body=json.dumps(body, ensure_ascii=False), headers=headers or {})


def install_api(page, handler):
    def dispatch(route):
        parts = urlsplit(route.request.url)
        if not parts.path.startswith("/api/"):
            return route.continue_()
        handler(parts.path, parse_qs(parts.query), route)
    page.route("**/api/**", dispatch)


COUNT = 650
DIFF_EVERY = 5


def block(index: int, side: str) -> str:
    text = f"第{index + 1}条 " + ("本合同双方应当按照约定履行义务。" * (3 + index % 4))
    if index % DIFF_EVERY == 0 and index < COUNT - 1:
        text += f'<ins class="compare-ins" data-diff-id="D{index}">新增内容{index}</ins>'
    return f'<p class="compare-block" data-block-id="{side}{index}">{text}</p>'


INSERTED = ''.join(f'<p class="compare-block" data-block-id="R-extra-{i}">新增独立条款{i}</p>' for i in range(15))
RIGHT_IDS = [i for i in range(COUNT) if not (280 <= i < 300)]
MERGED = '<div class="compare-document compare-merged-document">' + INSERTED + "".join(
    block(index, "L" if 280 <= index < 300 else "R") for index in range(COUNT)) + "</div>"
LEFT_HTML = '<div class="compare-document">' + "".join(block(index, "L") for index in range(COUNT)) + "</div>"
RIGHT_HTML = '<div class="compare-document">' + INSERTED + "".join(block(index, "R") for index in RIGHT_IDS) + "</div>"
ALIGNMENT = [{"id": f"G{i}", "left": [f"L{i}"], "right": [f"R{i}"] if i in RIGHT_IDS else []} for i in range(COUNT)]
DIFFS = [{"id": f"D{i}", "type": "insert", "section": "正文",
          "left": None, "left_anchor": {"block_id": f"L{i}"},
          "right": {"text": f"新增内容{i}", "block_id": f"R{i}"},
          "right_spans": [{"block_id": f"R{i}"}]} for i in range(0, COUNT - 1, DIFF_EVERY)]


def scenario(path, query, route):
    if path == "/api/capabilities":
        return respond(route, CAP)
    if path == "/api/tasks":
        return respond(route, {"items": [], "total": 0, "page": 1, "page_size": 20})
    if path == "/api/tasks/stats":
        return respond(route, {"total": 0, "counts": {}, "daily": []})
    if path == "/api/guides":
        return respond(route, {"items": []})
    if path == "/api/integrations/feishu/binding":
        return respond(route, {"bound": False})
    pair = {"id": "P5", "label": "perf", "status": "succeeded",
            "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
            "summary": {"total": len(DIFFS)}}
    if path == "/api/compare/tasks":
        return respond(route, {"items": [{"id": "T5", "name": "scroll-perf", "status": "succeeded", "total": 1, "pairs": [pair]}]})
    if path == "/api/compare/tasks/T5":
        return respond(route, {"id": "T5", "name": "scroll-perf", "status": "succeeded", "total": 1, "pairs": [pair]})
    if path == "/api/compare/pairs/P5/view":
        return respond(route, {"pair": {"id": "P5", "label": "perf"}, "result_sha256": "a" * 64,
                               "left": {"name": "原文档.docx", "html": LEFT_HTML},
                               "right": {"name": "修订文档.docx", "html": RIGHT_HTML},
                               "merged": {"name": "修订文档.docx", "html": MERGED},
                               "summary": {"total": len(DIFFS), "insert": len(DIFFS), "modify": 0, "delete": 0},
                               "coverage": {"status": "complete", "warnings": []},
                               "diffs": DIFFS, "alignment": ALIGNMENT})
    if path == "/api/compare/pairs/P5/selection":
        return respond(route, {"pair_id": "P5", "result_sha256": "a" * 64,
                               "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                               "selection_epoch": 0,
                               "draft": {"selection_epoch": 0, "decisions": {}, "decision_hash": "d" * 64},
                               "decisions": {},
                               "assessment": {"pending_ids": [], "issues": [], "can_generate": False},
                               "diffs": DIFFS, "artifacts": []})
    return respond(route, {})


INSTRUMENT = """() => {
  const perf = {longtasks: [], frames: [], lineRebuilds: 0, forceRefreshCalls: 0, forceRefreshMs: 0};
  window.__perf = perf;
  try {
    new PerformanceObserver(list => {
      for (const entry of list.getEntries()) perf.longtasks.push(entry.duration);
    }).observe({entryTypes: ['longtask']});
  } catch (e) {}
  let last;
  const step = t => {
    if (last !== undefined) perf.frames.push(t - last);
    last = t;
    requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
  perf.refreshCalls = 0; perf.refreshMs = 0;
  const svg = document.getElementById('compare-lines');
  if (svg) {
    const orig = svg.replaceChildren.bind(svg);
    svg.replaceChildren = (...args) => { perf.lineRebuilds++; const t0 = performance.now(); const out = orig(...args); perf.lineRebuildMs = (perf.lineRebuildMs || 0) + performance.now() - t0; return out; };
  }
  for (const id of ['compare-word-merged-pane','compare-word-left-pane','compare-word-right-pane','compare-left-pane','compare-right-pane']) {
    const pane = document.getElementById(id), doc = pane && pane._virtualDoc;
    if (!doc) continue;
    const refresh = doc.refresh.bind(doc);
    doc.refresh = (force, range) => {
      const t0 = performance.now(); const out = refresh(force, range);
      const dt = performance.now() - t0;
      perf.refreshCalls++; perf.refreshMs += dt;
      if (force) { perf.forceRefreshCalls++; perf.forceRefreshMs += dt; }
      return out;
    };
  }
}"""

SCROLL_PUMP = """([paneId, frames, delta]) => new Promise(done => {
  const pane = document.getElementById(paneId);
  let n = 0;
  const step = () => {
    pane.scrollTop += delta;
    if (++n < frames) requestAnimationFrame(step);
    else setTimeout(done, 400);
  };
  requestAnimationFrame(step);
})"""

COLLECT = """() => {
  const perf = window.__perf || {longtasks: [], frames: [], lineRebuilds: 0, forceRefreshCalls: 0, forceRefreshMs: 0};
  const frames = perf.frames.filter(v => v < 1000);
  const sorted = [...frames].sort((a, b) => a - b);
  const p95 = sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * .95))] : 0;
  return {
    longtaskCount: perf.longtasks.length,
    longtaskTotalMs: Math.round(perf.longtasks.reduce((a, b) => a + b, 0) * 10) / 10,
    frames: frames.length,
    frameGapP95Ms: Math.round(p95 * 10) / 10,
    framesOver25msPct: frames.length ? Math.round(frames.filter(v => v > 25).length / frames.length * 1000) / 10 : 0,
    lineRebuilds: perf.lineRebuilds,
    lineRebuildMs: Math.round((perf.lineRebuildMs || 0) * 10) / 10,
    refreshCalls: perf.refreshCalls,
    refreshMs: Math.round(perf.refreshMs * 10) / 10,
    forceRefreshCalls: perf.forceRefreshCalls,
    forceRefreshMs: Math.round(perf.forceRefreshMs * 10) / 10,
  };
}"""

VISIBLE_BLOCK = """(paneId) => {
  // First numbered block inside (or just above/below) the viewport.
  // Inserted 'R-extra-*' blocks have no left counterpart; skip them and
  // read the first [LR]<n> block near the pane top instead.
  const pane = document.getElementById(paneId), doc = pane && pane._virtualDoc;
  if (!pane || !doc) return null;
  const rect = pane.getBoundingClientRect();
  for (let ci = doc.first; ci < doc.last; ci++) {
    const chunk = doc.chunks[ci];
    if (!chunk || !chunk.el) continue;
    for (let i = 0; i < chunk.el.children.length; i++) {
      const node = chunk.el.children[i], r = node.getBoundingClientRect();
      if (r.bottom <= rect.top + 1) continue;
      if (r.top > rect.top + 240) return null;
      const id = node.getAttribute('data-block-id') || '';
      if (/^[LR]\\d+$/.test(id)) return id;
    }
  }
  return null;
}"""


def visible_number(page, pane_id):
    """Numeric block-id suffix of the first visible block (L17/R17 -> 17).

    The merged and right panes carry 15 leading inserted blocks, so raw
    mount positions are not comparable across panes; block ids are.
    """
    block_id = page.evaluate(VISIBLE_BLOCK, pane_id)
    if not block_id:
        return None
    match = re.match(r"^[LR](\d+)$", block_id)
    return int(match.group(1)) if match else None


def run_scroll_scenario(page, pane_id, frames=240, delta=48):
    page.evaluate(INSTRUMENT)
    page.evaluate(SCROLL_PUMP, [pane_id, frames, delta])
    return page.evaluate(COLLECT)


def test_compare_scroll_perf_baseline(browser, live_dev):
    base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-scroll-perf')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    install_api(page, scenario)
    results: dict = {}
    try:
        page.goto(base + "/#compare?mode=detail&id=T5&pair=P5", wait_until="networkidle")
        page.locator("#compare-word-merged-pane .compare-block").first.wait_for(state="visible")
        page.locator("#compare-show-sources").check()
        page.locator("#compare-word-left-pane .compare-block").first.wait_for(state="visible")
        page.wait_for_timeout(600)

        results["word_merged_scroll"] = run_scroll_scenario(page, "compare-word-merged-pane")
        assert page.locator("#compare-word-merged-pane").evaluate("e => e.scrollTop") > 0

        page.locator('[data-compare-view-mode="classic"]').click()
        page.locator("#compare-left-pane .compare-block").first.wait_for(state="visible")
        page.wait_for_timeout(400)
        results["classic_left_scroll"] = run_scroll_scenario(page, "compare-left-pane")

        # Splitter drag (word view, sources rail): continuous pointer movement.
        page.locator('[data-compare-view-mode="word"]').click()
        page.wait_for_timeout(400)
        page.evaluate(INSTRUMENT)
        splitter = page.locator("#compare-word-splitter")
        box = splitter.bounding_box()
        assert box
        x, y = box["x"] + box["width"] / 2, box["y"] + min(240, box["height"] / 2)
        page.mouse.move(x, y)
        page.mouse.down()
        for step in range(1, 25):
            page.mouse.move(x - step * 6, y)
            page.wait_for_timeout(40)
        page.mouse.up()
        page.wait_for_timeout(600)
        results["word_splitter_drag"] = page.evaluate(COLLECT)

        # Alignment must stay block-correct after the width change (FL-D841).
        merged_index = visible_number(page, "compare-word-merged-pane")
        left_index = visible_number(page, "compare-word-left-pane")
        right_index = visible_number(page, "compare-word-right-pane")
        results["post_splitter_visible_index"] = {"merged": merged_index, "left": left_index, "right": right_index}
        assert merged_index is not None and left_index is not None and right_index is not None
        assert abs(merged_index - right_index) <= 4 and abs(left_index - right_index) <= 4, results["post_splitter_visible_index"]

        # Classic gutter drag must also re-align both panes (FL-D841).
        page.locator('[data-compare-view-mode="classic"]').click()
        page.wait_for_timeout(400)
        page.locator("#compare-left-pane").evaluate("e => e.scrollTop += 6000")
        page.wait_for_timeout(700)
        gutter = page.locator("#compare-gutter")
        gbox = gutter.bounding_box()
        assert gbox
        gx, gy = gbox["x"] + gbox["width"] / 2, gbox["y"] + min(240, gbox["height"] / 2)
        page.mouse.move(gx, gy)
        page.mouse.down()
        page.mouse.move(gx - 120, gy, steps=8)
        page.mouse.up()
        page.wait_for_timeout(700)
        left_index = visible_number(page, "compare-left-pane")
        right_index = visible_number(page, "compare-right-pane")
        results["post_gutter_visible_index"] = {"left": left_index, "right": right_index}
        assert left_index is not None and right_index is not None
        assert abs(left_index - right_index) <= 4, results["post_gutter_visible_index"]
    finally:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"{RUN_LABEL}.json"
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        context.close()
    assert page_errors == []


def test_compare_fold_and_source_toggles_relayout_virtual_blocks(browser, live_dev):
    """FL-D1092（FL-D1084 体检缺陷②）：折叠钮/源文档开关切宽后虚拟块必须重排，
    实证=scrollHeight 实测随宽度变化（未修补时代码仅 drawLines→spacer 沿旧高卡排），
    把手真拖后滚动泵依旧活跃、内容可视不卡。"""
    base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-relayout')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    install_api(page, scenario)
    try:
        page.goto(base + "/#compare?mode=detail&id=T5&pair=P5", wait_until="networkidle")
        page.locator("#compare-word-merged-pane .compare-block").first.wait_for(state="visible")
        page.wait_for_timeout(500)

        def probe():
            return page.evaluate(
                "() => ({sh: document.getElementById('compare-word-merged-pane').scrollHeight,"
                "       w: document.getElementById('compare-word-merged-pane').getBoundingClientRect().width})")

        p0 = probe()
        assert p0["sh"] > 5000, "大文档虚拟块未生效（scrollHeight 过低）"

        # 折叠章节栏 → pane 变宽 → 同文重排应变矮
        page.locator(".section-nav .section-collapse-toggle").click()
        page.wait_for_timeout(600)
        p1 = probe()
        assert p1["w"] > p0["w"], "章节栏折叠未释放宽度"
        assert p1["sh"] < p0["sh"], f"切宽未重测：{p0} -> {p1}"

        # 折叠修订栏 → 更宽 → 更矮
        page.locator("#compare-rail-collapse").click()
        page.wait_for_timeout(600)
        p2 = probe()
        assert p2["w"] > p1["w"]
        assert p2["sh"] < p1["sh"], f"修订栏折叠未重测：{p1} -> {p2}"

        # 双双恢复 → 宽度与高都回原样（±3% 容忍滚动锚定位移）
        page.locator("#compare-rail-collapse").click()
        page.locator(".section-nav .section-collapse-toggle").click()
        page.wait_for_timeout(700)
        p3 = probe()
        assert abs(p3["w"] - p0["w"]) <= 2, f"恢复态宽度不齐：{p0} vs {p3}"
        assert abs(p3["sh"] - p0["sh"]) / p0["sh"] <= 0.03, f"恢复态高回不来：{p0} vs {p3}"

        # 把手真拖（修订栏 splitter 左移 150px：rail 变宽同列反递进）→必须重排
        splitter = page.locator("#compare-rail-splitter")
        box = splitter.bounding_box()
        assert box, "rail splitter 缺失"
        x, y = box["x"] + box["width"] / 2, box["y"] + min(240, box["height"] / 2)
        page.mouse.move(x, y)
        page.mouse.down()
        for step in range(1, 16):
            page.mouse.move(x - step * 10, y)
            page.wait_for_timeout(30)
        page.mouse.up()
        page.wait_for_timeout(700)
        p4 = probe()
        assert p4["w"] != p3["w"], "把手拖动未改变布局"
        # 把手链早有 onEnd 重测（非本缺目标）——宽度变化即可，重测差幅受
        # chunk 整数取整支配，不作 sh 断言；紧盯“不卡”是靠后续滚动泵段。

        # 源文档照开切回宽度路径——开着前后各测一次
        page.locator("#compare-show-sources").check()
        page.wait_for_timeout(700)
        p5 = probe()
        assert p5["w"] < p4["w"], "源文档开启未分栏"
        assert p5["sh"] > p4["sh"], "源文档开启后 merged 未按新窄度重测"

        # 内容“不卡”：滚动泵到位——首可视块推进且润度可控
        run_scroll_scenario(page, "compare-word-merged-pane")
        assert page.locator("#compare-word-merged-pane").evaluate("e => e.scrollTop") > 0
        assert visible_number(page, "compare-word-merged-pane") is not None
    finally:
        context.close()
    assert page_errors == []


def test_compare_empty_diff_copy_gated(browser, live_dev):
    """FL-D1091：空差异文案按 COMPARE_COVERAGE_CHECKS 门——build 口径（门=false）
    一律「两份合同没有文字差异。」，不得再出「已覆盖范围内」（即便 coverage=incomplete）。"""
    base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-empty-copy')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    try:
        # 手造 diff=0 的 pair 视图：覆盖 status 为 incomplete 也不过门
        def scenario_empty(path, query, route):
            handled_prefixes = ("/api/compare/tasks/T5", "/api/compare/tasks",
                                "/api/compare/pairs/P5/view", "/api/compare/pairs/P5/selection")
            if not any(path == p for p in handled_prefixes):
                return scenario(path, query, route)
            if path == "/api/compare/tasks/T5":
                return respond(route, {"id": "T5", "name": "empty", "status": "succeeded", "total": 1,
                                       "pairs": [{"id": "P5", "label": "空差异", "status": "succeeded",
                                                  "left": {"name": "a.docx"}, "right": {"name": "b.docx"},
                                                  "summary": {"total": 0}}]})
            if path == "/api/compare/tasks":
                return respond(route, {"items": [{"id": "T5", "name": "empty", "status": "succeeded", "total": 1,
                                                  "pairs": [{"id": "P5", "label": "空差异", "status": "succeeded",
                                                             "left": {"name": "a.docx"}, "right": {"name": "b.docx"},
                                                             "summary": {"total": 0}}]}],
                                                  "total": 1, "page": 1, "page_size": 20})
            if path == "/api/compare/pairs/P5/view":
                html = '<div class="compare-document compare-merged-document"><p class="compare-block" data-block-id="R1">共同条款</p></div>'
                return respond(route, {"pair": {"id": "P5", "label": "空差异"}, "result_sha256": "a" * 64,
                                       "left": {"name": "a.docx", "html": '<p data-block-id="L1">共同条款</p>'},
                                       "right": {"name": "b.docx", "html": '<p data-block-id="R1">共同条款</p>'},
                                       "merged": {"name": "b.docx", "html": html},
                                       "summary": {"total": 0, "modify": 0, "insert": 0, "delete": 0},
                                       "coverage": {"status": "incomplete",
                                                    "warnings": ["UNSUPPORTED_VISIBLE_CONTENT:header"]},
                                       "diffs": []})
            if path == "/api/compare/pairs/P5/selection":
                return respond(route, {"pair_id": "P5", "result_sha256": "a" * 64,
                                       "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                                       "selection_epoch": 0,
                                       "draft": {"selection_epoch": 0, "decisions": {}, "decision_hash": "d" * 64},
                                       "decisions": {},
                                       "assessment": {"pending_ids": [], "issues": [], "can_generate": False},
                                       "diffs": [], "artifacts": []})
            return respond(route, {})

        install_api(page, scenario_empty)
        page.goto(base + "/#compare?mode=detail&id=T5&pair=P5", wait_until="networkidle")
        page.locator("#compare-word-merged-pane .compare-block").first.wait_for(state="visible")
        message = page.locator("#compare-diff-list .empty").inner_text()
        assert message == "两份合同没有文字差异。", f"FL-D1091 门漏泄：{message!r}"
        assert "已覆盖范围内" not in message
    finally:
        context.close()
    assert page_errors == []
