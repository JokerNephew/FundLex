#!/usr/bin/env python3
"""FundLex 全站走查截图+性能骨架（阶段一交付，阶段二全量执行）。v1.1（双盲复查整改后）

对应文书：docs/qa/FULLSITE_CHECKLIST.md（编号一一对应 manifest.json）。
功能：
  1. 读 manifest.json 逐条打开页面（V1 hash SPA / V2 React Router 通用）。
  2. 采样点采集 P-TTFB/P-DCL/P-LOAD/P-READY/P-CLICK/P-LTASK，
     按 perf_budget.json 判定 ✅/⚠/❌（verdict 一律按 samples 中位数重算）。
  3. 截图（含样本序号、双视口），写 results.json + PERF.csv + console-errors.json。
  4. 307 深链探测：expect_redirects 断言 status+Location。
凭据纪律：只从环境变量取（FUNDLEX_QA_TOKEN 或 FUNDLEX_QA_USER/FUNDLEX_QA_PASSWORD），绝不落盘；
  token 仅经 localStorage 同源注入，不向请求头外发（防第三方域名泄露）。
种子占位符：url_template 的 {TASK_ID|DOC_ID|CMP_ID|PAIR_ID|RUN_ID|GUIDE_ID}
  由环境变量 FUNDLEX_SEED_<名> 替换；缺失则该条 ⛔ skipped。

用法：
  .venv/bin/python tools/qa/fullsite/shots.py --base-url https://fundlex.club \
      [--site v1|v2|lc] [--only FS-V1-01 ...] [--samples 3] [--no-mobile] [--no-auth] [--headful]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

SEED_ENV = {
    "TASK_ID": "FUNDLEX_SEED_TASK_ID",
    "DOC_ID": "FUNDLEX_SEED_DOC_ID",
    "CMP_ID": "FUNDLEX_SEED_CMP_ID",
    "PAIR_ID": "FUNDLEX_SEED_PAIR_ID",
    "RUN_ID": "FUNDLEX_SEED_RUN_ID",
    "GUIDE_ID": "FUNDLEX_SEED_GUIDE_ID",
}

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844, "is_mobile": True, "has_touch": True},
}

# 导航前注入：longtask 带 startTime 记录；同源 localStorage 注入 token（不发请求头）。
INIT_SCRIPT = r"""
(() => {
  window.__qaLongtasks = [];
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries())
        window.__qaLongtasks.push({startTime: e.startTime, duration: e.duration});
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) {}
  const t = __QA_TOKEN__;
  if (t) { try { localStorage.setItem('fundlex-auth-token', t); } catch (e) {} }
})();
"""


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def round_budget(v: float) -> float:
    return float(int(round(v / 100.0)) * 100)


def verdict(metric: str, value: float | None, perf_class: str, budget: dict, mobile: bool) -> str:
    """✅ / ⚠ / ❌ / '-'（未定义带）"""
    if value is None:
        return "-"
    band = budget["classes"].get(perf_class, {}).get(metric)
    if not band:
        return "-"
    warn, fail = band
    if mobile:
        mult = float(budget["_meta"].get("mobile_multiplier", 1.5))
        warn, fail = round_budget(warn * mult), round_budget(fail * mult)
    if value > fail:
        return "❌"
    if value > warn:
        return "⚠"
    return "✅"


def login_wall(page) -> bool:
    """V1 #login-view overlay 或 V2 login-layout 任一可见即登录墙。"""
    try:
        return bool(page.evaluate(
            """() => {
              const v1 = document.querySelector('#login-view');
              if (v1 && !v1.hidden && getComputedStyle(v1).display !== 'none') return true;
              const v2 = document.querySelector('.login-layout form');
              return !!v2;
            }"""))
    except Exception:
        return False


def auth_bootstrap(base_url: str) -> bool:
    """跑录前鉴权引导：token→同源注入探测；user/pw→V1 表单登录探测。返回是否获得登录态。"""
    if os.environ.get("FUNDLEX_QA_TOKEN", "").strip():
        return True  # 注入式在每条目 context 内生效；错误的 token 会被登录墙探测兜住
    user = os.environ.get("FUNDLEX_QA_USER", "").strip()
    pw = os.environ.get("FUNDLEX_QA_PASSWORD", "").strip()
    if not (user and pw):
        return False
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--ignore-certificate-errors"])
        page = browser.new_context(ignore_https_errors=True).new_page()
        ok = False
        try:
            page.goto(urljoin(base_url, "/#workspace"), wait_until="domcontentloaded")
            page.wait_for_selector("#login-view", timeout=8000)
            page.fill("#login-username", user)
            page.fill("#login-password", pw)
            page.click("#login-form button[type=submit], #login-form .primary")
            page.wait_for_timeout(2500)
            ok = not login_wall(page)
        except PwTimeout:
            ok = False
        browser.close()
        return ok


def resolve_url(entry: dict, base_url: str) -> tuple[str | None, str | None]:
    url = entry.get("url") or entry.get("url_template")
    if not url:
        return None, "no-url"
    for ph, env in SEED_ENV.items():
        if "{" + ph + "}" in url:
            val = os.environ.get(env, "").strip()
            if not val:
                return None, f"missing-seed:{env}"
            url = url.replace("{" + ph + "}", val)
    return urljoin(base_url, url), None


def run_actions(page, base_url: str, actions: list, redirects: list) -> dict:
    """动作 DSL：goto(支持相对)/click/wait_for/sleep/evaluate/measure_click。
    measure_click 超时记为超阈值值（❌），不炸行。"""
    extra = {}
    for step in actions or []:
        if "goto" in step:
            page.goto(urljoin(base_url, step["goto"]), wait_until="domcontentloaded")
        elif "click" in step:
            page.click(step["click"], timeout=step.get("timeout", 5000))
        elif "wait_for" in step:
            page.wait_for_selector(step["wait_for"], timeout=step.get("timeout", 15000))
        elif "sleep" in step:
            page.wait_for_timeout(int(step["sleep"]))
        elif "evaluate" in step:
            page.evaluate(step["evaluate"])
        elif "measure_click" in step:
            spec = step["measure_click"]
            until_timeout = spec.get("until_timeout", 10000)
            t0 = time.monotonic()
            page.click(spec["click"], timeout=spec.get("timeout", 5000))
            try:
                page.wait_for_selector(spec["until"], state="visible", timeout=until_timeout)
                extra["P-CLICK"] = round((time.monotonic() - t0) * 1000.0, 1)
            except PwTimeout:
                extra["P-CLICK"] = float(until_timeout)  # 超阈值记为超时值 → 必然 ❌
                extra["_CLICK_TIMEOUT"] = True
            if spec.get("heavy"):
                extra["_CLICK_BAND"] = "P-CLICK-HEAVY"
    return extra


def shoot_one(pw, browser, entry: dict, base_url: str, vp_name: str, outdir: Path,
              budget: dict, sample_i: int, cold: bool) -> dict:
    ctx_args = {"viewport": {k: v for k, v in VIEWPORTS[vp_name].items() if k in ("width", "height")},
                "ignore_https_errors": True}
    if vp_name == "mobile":
        ctx_args.update({"is_mobile": True, "has_touch": True})
    context = browser.new_context(**ctx_args)
    token = os.environ.get("FUNDLEX_QA_TOKEN", "").strip()
    context.add_init_script(INIT_SCRIPT.replace("__QA_TOKEN__", json.dumps(token) if token else "null"))
    page = context.new_page()
    console_errors: list[str] = []
    redirects: list[dict] = []
    page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
    page.on("response", lambda r: redirects.append(
        {"url": r.url, "status": r.status, "location": r.headers.get("location", "")}) if 300 <= r.status < 400 else None)

    url, seed_err = resolve_url(entry, base_url)
    rec = {"id": entry["id"], "viewport": vp_name, "url": url, "cache_mode": "cold" if cold else "warm",
           "sample": sample_i, "metrics": {}, "verdicts": {}, "console_errors": [], "redirects": []}
    if seed_err:
        rec["skipped"] = seed_err
        context.close()
        return rec
    perf_class = entry.get("perf", "A")
    mobile = vp_name == "mobile"
    try:
        if not cold:  # warm 口径：先同 URL 预载一次，测第二次（对齐检查单§2『默认记录默认缓存』）
            page.goto(url, wait_until="load", timeout=45000)
        t0 = time.monotonic()
        page.goto(url, wait_until="load", timeout=45000)
        nav = page.evaluate(
            """() => { const n = performance.getEntriesByType('navigation')[0] || {};
               return {ttfb: n.responseStart ?? null, dcl: n.domContentLoadedEventEnd ?? null, load: n.loadEventEnd ?? null}; }""")
        # P-READY：ready_any 首选行级、回落容器；记录命中的选择器
        ready_ms, ready_hit = None, None
        cands = entry.get("ready_any") or ([entry["ready"]] if entry.get("ready") else [])
        deadline = time.monotonic() + float(entry.get("ready_timeout", 30000)) / 1000.0
        while ready_hit is None and time.monotonic() < deadline and cands:
            for sel in cands:
                try:
                    if page.locator(sel).first.is_visible():
                        ready_ms, ready_hit = (time.monotonic() - t0) * 1000.0, sel
                        break
                except Exception:
                    pass
            if ready_hit is None:
                page.wait_for_timeout(250)
        if ready_hit is None and cands:
            rec["ready_timeout"] = True
        # 登录墙判定（该条目要求登录态时）
        if entry.get("auth", True) and login_wall(page):
            rec["login_wall"] = True

        extra = run_actions(page, base_url, entry.get("actions"), redirects)
        # P-LTASK：P-READY 时刻起 5s 窗口内 longtask(>50ms) 总耗时
        ready_mark = page.evaluate("() => performance.now()")
        page.wait_for_timeout(5000)
        lt = page.evaluate(
            """(mark) => (window.__qaLongtasks || [])
                 .filter(e => e.startTime >= mark - 200 && e.startTime <= mark + 5200)
                 .reduce((a, e) => a + e.duration, 0)""", ready_mark)
        metrics = {"P-TTFB": nav.get("ttfb"), "P-DCL": nav.get("dcl"), "P-LOAD": nav.get("load"),
                   "P-READY": ready_ms, "P-LTASK": round(float(lt or 0), 1)}
        metrics.update(extra)
        shot_rel = f"shots/{entry['id']}-{vp_name}-s{sample_i}.png"
        page.screenshot(path=str(outdir / shot_rel), full_page=bool(entry.get("full_page", False)))
        v = {m: verdict(m, val, perf_class, budget, mobile) for m, val in metrics.items() if not m.startswith("_")}
        if metrics.get("P-CLICK") is not None:
            v["P-CLICK"] = verdict(extra.get("_CLICK_BAND", "P-CLICK"), metrics["P-CLICK"], perf_class, budget, mobile)
        if rec.get("ready_timeout"):
            v["P-READY"] = "❌"
        if rec.get("login_wall"):
            v["_auth"] = "⛔"
        if console_errors:
            v["_console"] = "⚠"
        # 307 断言
        exp = entry.get("expect_redirects") or []
        if exp:
            bad = []
            for e in exp:
                hit = [r for r in redirects
                       if e["from"] in r["url"] and r["status"] == e.get("status", 307)
                       and e.get("location_contains", "") in r["location"]]
                if not hit:
                    bad.append(e)
            v["_redirects"] = "✅" if not bad else "❌"
            rec["redirect_misses"] = bad
        rec.update({"metrics": metrics, "verdicts": v, "shot": shot_rel, "ready_hit": ready_hit,
                    "console_errors": console_errors[:50], "redirects": redirects[:20]})
    except Exception as exc:  # noqa: BLE001 - 走查记录失败本身
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        context.close()
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="FundLex fullsite walkthrough screenshot+perf skeleton v1.1")
    ap.add_argument("--base-url", default=os.environ.get("FUNDLEX_QA_BASE", "https://fundlex.club"))
    ap.add_argument("--manifest", type=Path, default=Path(__file__).with_name("manifest.json"))
    ap.add_argument("--budget", type=Path, default=Path(__file__).with_name("perf_budget.json"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--site", choices=["v1", "v2", "lc"], default=None)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--no-mobile", action="store_true")
    ap.add_argument("--cold", action="store_true", help="禁用 warm 预载（默认 warm 口径）")
    ap.add_argument("--no-auth", action="store_true", help="不要求登录态（登录/未登录态条目专用）")
    ap.add_argument("--headful", action="store_true")
    args = ap.parse_args()

    manifest = load_json(args.manifest)
    budget = load_json(args.budget)
    entries = manifest["entries"]
    if args.only:
        wanted = set(args.only)
        entries = [e for e in entries if e["id"] in wanted]
    if args.site:
        entries = [e for e in entries if e.get("site") == args.site]
    if not entries:
        print("no entries selected", file=sys.stderr)
        return 2

    # P0-1 整改：跑录前鉴权引导；要求登录态却拿不到 → 中止（除非显式 --no-auth）
    need_auth = any(e.get("auth", True) for e in entries) and not args.no_auth
    if need_auth and not auth_bootstrap(args.base_url):
        print("⛔ auth bootstrap failed: 无 FUNDLEX_QA_TOKEN 且 FUNDLEX_QA_USER/PASSWORD 表单登录失败；"
              "整 run 中止（避免未登录失真证据）。如确需未登录态条目请显式 --no-auth。", file=sys.stderr)
        return 3

    run_id = time.strftime("%Y%m%d-%H%M%S")
    outdir = args.out or Path("/tmp/opencode/qa/fullsite") / run_id
    (outdir / "shots").mkdir(parents=True, exist_ok=True)

    viewports = ["desktop"] + ([] if args.no_mobile else ["mobile"])
    samples: list[dict] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headful, args=["--ignore-certificate-errors"])
        for entry in entries:
            if entry.get("mode") == "staged" and not entry.get("url") and not entry.get("url_template"):
                samples.append({"id": entry["id"], "viewport": "-", "skipped": "staged(需种子/编排,阶段二执行)",
                                "metrics": {}, "verdicts": {}})
                continue
            for sample_i in range(args.samples):
                for vp in viewports:
                    rec = shoot_one(pw, browser, entry, args.base_url, vp, outdir, budget, sample_i, args.cold)
                    samples.append(rec)
                    print(json.dumps({"id": rec["id"], "vp": vp, "i": sample_i,
                                      "verdicts": rec.get("verdicts"),
                                      "err": rec.get("error"), "skip": rec.get("skipped")},
                                     ensure_ascii=False))

    # 聚合：同 id+viewport 取中位数；verdict 按中位数重算（P1-2 整改）
    by_id = {e["id"]: e for e in manifest["entries"]}
    agg: dict[str, dict] = {}
    for r in samples:
        key = f"{r['id']}|{r['viewport']}"
        slot = agg.setdefault(key, {"id": r["id"], "viewport": r["viewport"], "cache_mode": r.get("cache_mode"),
                                    "metrics": {}, "shots": [], "console_errors": set(), "errors": [],
                                    "ready_timeout": 0, "login_wall": 0})
        for m, val in (r.get("metrics") or {}).items():
            if isinstance(val, (int, float)):
                slot["metrics"].setdefault(m, []).append(val)
        if r.get("shot"):
            slot["shots"].append(r["shot"])
        slot["console_errors"].update(r.get("console_errors") or [])
        if r.get("error"):
            slot["errors"].append(r["error"])
        slot["ready_timeout"] += 1 if r.get("ready_timeout") else 0
        slot["login_wall"] += 1 if r.get("login_wall") else 0
        if r.get("skipped"):
            slot["skipped"] = r["skipped"]

    results = []
    for slot in agg.values():
        entry = by_id.get(slot["id"], {})
        perf_class = entry.get("perf", "A")
        mobile = slot["viewport"] == "mobile"
        med = {m: round(statistics.median(vals), 1) for m, vals in slot["metrics"].items()}
        v = {m: verdict(m, val, perf_class, budget, mobile) for m, val in med.items() if not m.startswith("_")}
        if slot["ready_timeout"]:
            v["P-READY"] = "❌"
        if slot["login_wall"]:
            v["_auth"] = "⛔"
        if slot["console_errors"]:
            v["_console"] = "⚠"
        results.append({"id": slot["id"], "viewport": slot["viewport"], "cache_mode": slot.get("cache_mode"),
                        "metrics_median": med, "verdicts": v, "shots": slot["shots"],
                        "ready_timeout_samples": slot["ready_timeout"], "login_wall_samples": slot["login_wall"],
                        "console_errors": sorted(slot["console_errors"]), "errors": slot["errors"],
                        **({"skipped": slot["skipped"]} if slot.get("skipped") else {})})

    covered_ids = sorted({r["id"] for r in results})
    counts = {"manifest_entries": len(manifest["entries"]), "selected": len(entries),
              "covered_ids": len(covered_ids), "coverage_ok": len(covered_ids) == len(entries)}
    (outdir / "results.json").write_text(json.dumps({
        "run_id": run_id, "base_url": args.base_url, "samples": args.samples,
        "cache_mode": "cold" if args.cold else "warm", "budget_version": budget["_meta"]["version"],
        "counts": counts, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")

    with (outdir / "PERF.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "viewport", "cache", "P-TTFB", "P-DCL", "P-LOAD", "P-READY", "P-CLICK", "P-LTASK", "verdicts", "errors"])
        for r in results:
            m = r["metrics_median"]
            w.writerow([r["id"], r["viewport"], r.get("cache_mode"), m.get("P-TTFB"), m.get("P-DCL"),
                        m.get("P-LOAD"), m.get("P-READY"), m.get("P-CLICK"), m.get("P-LTASK"),
                        json.dumps(r["verdicts"], ensure_ascii=False), ";".join(r["errors"])])

    ce = {r["id"]: r["console_errors"] for r in results if r.get("console_errors")}
    (outdir / "console-errors.json").write_text(json.dumps(ce, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] out={outdir} counts={json.dumps(counts)}")
    return 0 if counts["coverage_ok"] else 4


if __name__ == "__main__":
    sys.exit(main())
