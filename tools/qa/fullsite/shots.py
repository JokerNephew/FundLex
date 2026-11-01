#!/usr/bin/env python3
"""FundLex 全站走查截图+性能骨架（阶段一交付，阶段二全量执行）。

对应文书：docs/qa/FULLSITE_CHECKLIST.md（编号一一对应 manifest.json）。
功能：
  1. 读 manifest.json 逐条打开页面（V1 hash SPA / V2 React Router 通用，url 为 path+hash/query 原样拼接）。
  2. 每采样点采集 P-TTFB/P-DCL/P-LOAD/P-READY/P-LTASK，可选 P-CLICK 交互测量。
  3. 按 perf_budget.json 分页级(A/B/C)判定 ✅/⚠/❌；控制台 error 级日志即 ⚠ 起步。
  4. 每行每视口截图，写 results.json + PERF.csv + console-errors.json。
凭据：只从环境变量取（FUNDLEX_QA_TOKEN 或 FUNDLEX_QA_USER/FUNDLEX_QA_PASSWORD），绝不落盘。

用法：
  .venv/bin/python tools/qa/fullsite/shots.py --base-url https://fundlex.club \
      [--only FS-V1-01 FS-LC-01] [--samples 3] [--no-mobile] [--headful]
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

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

REPO = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = Path(__file__).with_name("manifest.json")
DEFAULT_BUDGET = Path(__file__).with_name("perf_budget.json")

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844, "is_mobile": True, "has_touch": True},
}

# 在导航前注入：收集 longtask；注入 auth token（如有）。
INIT_SCRIPT = r"""
(() => {
  window.__qaLongtasks = [];
  try {
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__qaLongtasks.push(e.duration);
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) { /* 旧内核无 longtask，留空数组 */ }
  const t = window.__qaAuthToken;
  if (t) { try { localStorage.setItem('fundlex-auth-token', t); } catch (e) {} }
})();
"""


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verdict(metric: str, value: float | None, perf_class: str, budget: dict, mobile: bool) -> str:
    """✅ / ⚠ / ❌ / '-'（未测或豁免）"""
    if value is None:
        return "-"
    band = budget["classes"].get(perf_class, {}).get(metric)
    if not band:
        return "-"
    warn, fail = band
    if mobile:
        mult = float(budget["_meta"].get("mobile_multiplier", 1.5))
        warn, fail = warn * mult, fail * mult
    if value > fail:
        return "❌"
    if value > warn:
        return "⚠"
    return "✅"


def auth_context_args() -> dict:
    """V1/V2 都认 localStorage 'fundlex-auth-token' + Authorization Bearer。"""
    token = os.environ.get("FUNDLEX_QA_TOKEN", "").strip()
    if not token:
        return {}
    return {"extra_http_headers": {"Authorization": f"Bearer {token}"}}


def v1_form_login(page, base_url: str) -> bool:
    """无 token 时用帐号密码走 V1 登录弹层（凭据仅取自环境变量）。"""
    user = os.environ.get("FUNDLEX_QA_USER", "").strip()
    pw = os.environ.get("FUNDLEX_QA_PASSWORD", "").strip()
    if not (user and pw):
        return False
    page.goto(base_url + "/#workspace", wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#login-view:not([hidden]), #login-view", timeout=8000)
        page.fill("#login-username", user)
        page.fill("#login-password", pw)
        page.click("#login-form button[type=submit], #login-form .primary")
        page.wait_for_selector("#login-view[hidden]", timeout=15000)
        return True
    except PwTimeout:
        return False


def nav_metrics(page) -> dict:
    raw = page.evaluate(
        """() => {
          const n = performance.getEntriesByType('navigation')[0] || {};
          return {ttfb: n.responseStart ?? null, dcl: n.domContentLoadedEventEnd ?? null, load: n.loadEventEnd ?? null};
        }"""
    )
    return raw


def longtask_total(page) -> float | None:
    try:
        arr = page.evaluate("() => window.__qaLongtasks || []")
        return float(sum(arr)) if isinstance(arr, list) else None
    except Exception:
        return None


def run_actions(page, actions: list, console_errors: list, budget_class: str, budget: dict) -> dict:
    """动作 DSL：goto/click/wait_for/sleep/evaluate/measure_click。返回 {metric: ms}。"""
    extra = {}
    for step in actions or []:
        if "goto" in step:
            page.goto(step["goto"], wait_until="domcontentloaded")
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
            t0 = time.monotonic()
            page.click(spec["click"], timeout=spec.get("timeout", 5000))
            page.wait_for_selector(spec["until"], state="visible", timeout=spec.get("until_timeout", 10000))
            extra["P-CLICK"] = (time.monotonic() - t0) * 1000.0
            if spec.get("heavy"):
                extra["_CLICK_BAND"] = "P-CLICK-HEAVY"
    return extra


def shoot_one(pw, entry: dict, base_url: str, vp_name: str, outdir: Path, budget: dict, headful: bool) -> dict:
    browser = pw.chromium.launch(headless=not headful, args=["--ignore-certificate-errors"])
    ctx_args = {"viewport": VIEWPORTS[vp_name], "ignore_https_errors": True, **auth_context_args()}
    if vp_name == "mobile":
        ctx_args.update({k: v for k, v in VIEWPORTS["mobile"].items() if k not in ("width", "height")})
    context = browser.new_context(**ctx_args)
    token = os.environ.get("FUNDLEX_QA_TOKEN", "").strip()
    context.add_init_script(INIT_SCRIPT.replace("window.__qaAuthToken", json.dumps(token) if token else "null"))
    page = context.new_page()
    console_errors: list[str] = []
    page.on("console", lambda m: console_errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

    rec = {"id": entry["id"], "viewport": vp_name, "url": entry.get("url"), "verdicts": {}, "metrics": {}, "console_errors": []}
    t0 = time.monotonic()
    try:
        page.goto(base_url + entry["url"], wait_until="load", timeout=45000)
        nav = nav_metrics(page)
        ready_ms = None
        sel = entry.get("ready")
        if sel:
            try:
                page.wait_for_selector(sel, state="visible", timeout=int(entry.get("ready_timeout", 30000)))
                ready_ms = (time.monotonic() - t0) * 1000.0
            except PwTimeout:
                ready_ms = None
                rec["ready_timeout"] = True
        extra = run_actions(page, entry.get("actions"), console_errors, entry.get("perf", "A"), budget)
        page.wait_for_timeout(5000)  # P-LTASK 采样窗（P-READY 后 5s）
        lt = longtask_total(page)
        metrics = {
            "P-TTFB": nav.get("ttfb"),
            "P-DCL": nav.get("dcl"),
            "P-LOAD": nav.get("load"),
            "P-READY": ready_ms,
            "P-LTASK": lt,
        }
        metrics.update(extra)
        shot_rel = f"shots/{entry['id']}-{vp_name}.png"
        page.screenshot(path=str(outdir / shot_rel), full_page=bool(entry.get("full_page", False)))
        perf_class = entry.get("perf", "A")
        mobile = vp_name == "mobile"
        v = {m: verdict(m, val, perf_class, budget, mobile) for m, val in metrics.items()}
        if metrics.get("P-CLICK") is not None:
            band_name = extra.get("_CLICK_BAND", "P-CLICK")
            v["P-CLICK"] = verdict(band_name, metrics.get("P-CLICK"), perf_class, budget, mobile)
        if console_errors:
            v["_console"] = "⚠"
        rec.update({"metrics": metrics, "verdicts": v, "shot": shot_rel,
                    "console_errors": console_errors[:50]})
    except Exception as exc:  # noqa: BLE001 - 走查记录失败本身
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        context.close()
        browser.close()
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description="FundLex fullsite walkthrough screenshot+perf skeleton")
    ap.add_argument("--base-url", default=os.environ.get("FUNDLEX_QA_BASE", "https://fundlex.club"))
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--budget", type=Path, default=DEFAULT_BUDGET)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--site", choices=["v1", "v2", "lc"], default=None,
                    help="按 manifest 的 site 字段过滤（V2 走查用本地 base-url 单独跑）")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--no-mobile", action="store_true")
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

    run_id = time.strftime("%Y%m%d-%H%M%S")
    outdir = args.out or Path("/tmp/opencode/qa/fullsite") / run_id
    (outdir / "shots").mkdir(parents=True, exist_ok=True)

    viewports = ["desktop"] + ([] if args.no_mobile else ["mobile"])
    all_samples: list[dict] = []
    with sync_playwright() as pw:
        for entry in entries:
            if entry.get("mode") == "staged":
                # 依赖种子/状态编排的条目：阶段二补齐编排脚本后转 direct；
                # 骨架期登记为 SKIP，保证三数相等校验可解释。
                all_samples.append({"id": entry["id"], "viewport": "-", "skipped": "staged(需种子/编排,阶段二执行)",
                                    "metrics": {}, "verdicts": {}})
                continue
            for sample_i in range(args.samples):
                for vp in viewports:
                    rec = shoot_one(pw, entry, args.base_url, vp, outdir, budget, args.headful)
                    rec["sample"] = sample_i
                    all_samples.append(rec)
                    print(json.dumps({"id": rec["id"], "vp": vp, "i": sample_i,
                                      "verdicts": rec.get("verdicts"), "err": rec.get("error")},
                                     ensure_ascii=False))

    # 聚合：同 id+viewport 取中位数
    agg: dict[str, dict] = {}
    for r in all_samples:
        key = f"{r['id']}|{r['viewport']}"
        slot = agg.setdefault(key, {"id": r["id"], "viewport": r["viewport"], "metrics": {}, "verdicts": {},
                                    "shots": [], "console_errors": set(), "errors": []})
        for m, val in (r.get("metrics") or {}).items():
            if val is not None:
                slot["metrics"].setdefault(m, []).append(val)
        slot["verdicts"] = r.get("verdicts") or slot["verdicts"]
        if r.get("shot"):
            slot["shots"].append(r["shot"])
        slot["console_errors"].update(r.get("console_errors") or [])
        if r.get("error"):
            slot["errors"].append(r["error"])
        if r.get("skipped"):
            slot["skipped"] = r["skipped"]

    results = []
    for slot in agg.values():
        med = {m: (statistics.median(vals) if vals else None) for m, vals in slot["metrics"].items()}
        results.append({"id": slot["id"], "viewport": slot["viewport"],
                        "metrics_median": med, "verdicts": slot["verdicts"],
                        "shots": slot["shots"], "console_errors": sorted(slot["console_errors"]),
                        "errors": slot["errors"], **({"skipped": slot["skipped"]} if slot.get("skipped") else {})})

    (outdir / "results.json").write_text(json.dumps({
        "run_id": run_id, "base_url": args.base_url, "samples": args.samples,
        "budget_version": budget["_meta"]["version"], "results": results,
        "counts": {"manifest_entries": len(manifest["entries"]), "selected": len(entries),
                   "result_rows": len(results)},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    with (outdir / "PERF.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "viewport", "P-TTFB", "P-DCL", "P-LOAD", "P-READY", "P-CLICK", "P-LTASK", "verdicts", "errors"])
        for r in results:
            m = r["metrics_median"]
            w.writerow([r["id"], r["viewport"], m.get("P-TTFB"), m.get("P-DCL"), m.get("P-LOAD"),
                        m.get("P-READY"), m.get("P-CLICK"), m.get("P-LTASK"),
                        json.dumps(r["verdicts"], ensure_ascii=False),
                        ";".join(r["errors"])])

    ce = {r["id"]: r["console_errors"] for r in results if r.get("console_errors")}
    (outdir / "console-errors.json").write_text(json.dumps(ce, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] out={outdir} counts: manifest={len(manifest['entries'])} selected={len(entries)} rows={len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
