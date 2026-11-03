/* FL-D1015：Slim Select（MIT 2.13.1 vendor 单文件）全站装配层。
 *
 * 兼容面（既有代码零改动）：
 * - 原生 <select> 由 Slim Select 自带保留并隐藏同步，.value/patchHTML/aria-label 语义不变；
 * - ss.afterChange → 原生 select 派发 'change'（bubbles），既有监听/过滤链照常；
 * - 原版代码静默置值 / patchHTML 重渲 options → MutationObserver 触发 destroy+重建；
 * - Playwright page.select_option 直驱原生 select 时，原生 'change' 监听反向同步 ss。
 */
(function () {
  'use strict';
  if (!window.SlimSelect) return;
  var instances = new Map();
  var syncing = false;
  // 程序态窗口：feed/setData 期间由 kit 标记，SS afterChange debounce（100ms）+余量
  var PROGRAMMATIC = new Map(); // select -> expiresAt(ms)
  function markProgrammatic(select, ms) {
    PROGRAMMATIC.set(select, Date.now() + (ms || 400));
    setTimeout(function () { PROGRAMMATIC.delete(select); }, (ms || 400) + 10);
  }
  function programmaticEvicted(select) {
    var at = PROGRAMMATIC.get(select);
    return at !== undefined && at > Date.now();
  }

  function showSearch(select) {
    // 长清单开搜索（任务选择/指引对比/指引筛选类）；短筛选器维持纯列表不打扰。
    return select.options.length >= 8 || /task-select|guide/.test(select.id);
  }

  function build(select) {
    if (!select.isConnected) return;
    if (select.dataset.flSelectvend === '1') return;
    var ss = new window.SlimSelect({
      select: select,
      settings: {
        placeholderText: ' ',
        showSearch: showSearch(select),
        searchPlaceholder: '搜索…',
        searchText: '无匹配项',
        searchHighlight: true,
        openPosition: 'auto',
      },
      events: {
        afterChange: function () {
          // 程序态（feed/setData 重灌 ids 重生 → SS afterChange 判定选择抵触）——不转发
          if (syncing || programmaticEvicted(select)) return;
          syncing = true;
          try { select.dispatchEvent(new Event('change', { bubbles: true })); }
          finally { syncing = false; }
        },
      },
    });
    // FL-D1015 双边闸：SS 2.x 的 select 端观察器/change 回灌会在宿主反复重填时
    // 以空 store 写实原生 options（实测 #task-select 清空）。数据同步全走
    // FundLexSelectKit.feed/interval → ss.setData；用户交互自然在 SS 内闭环。
    if (ss.select && ss.select.changeListen) ss.select.changeListen(false);
    instances.set(select, ss);
    select.dataset.flSelectvend = '1';
    // SS 以 display:none 隐藏原生 select——Playwright select_option/无障碍测试需真节点：
    // 恢复布局盒为 1px 透明可见（视觉仍不可见，aria-hidden 保持由 SS 管制）。
    select.style.display = 'block';
    select.style.position = 'absolute';
    select.style.width = '1px';
    select.style.height = '1px';
    select.style.opacity = '0.001';
    select.style.pointerEvents = 'none';
    select.tabIndex = -1;
  }

  function enhance(select) {
    // 以包装标记为准而非实例表：patchHTML/node 复用会剥光套件属性，
    // instances 表保留使后续扫描误判已增强（R2 驳回的 task-page-size 漏回根因）。
    if (select.dataset.flSelectvend === '1') return;
    if (!select.isConnected) return;
    var stale = instances.get(select);
    if (stale) {
      try { stale.destroy(); } catch (e) {}
      instances.delete(select);
      try { feed.signature.delete(select); } catch (e) {}
    }
    build(select);
    // options 重渲（patchHTML / app 重填）：SS 2.x 把自身 data 当权威源——选项外来注入
    // 会被其内部观察器夹空（#task-select 实测 options.length=0）。唯一可靠契约=应用
    // 侧同步调用 FundLexSelectKit.feed(select)（app.js patchHTML refreshGuideDiffCard 等
    // 打枣点已挂），不经任何异步观察路径。
    if (!instances.get(select)) { /* never */ }
    // 原生源驱动（Playwright select_option / 代码 set+dispatch）→ 回写 ss
    select.addEventListener('change', function () {
      if (syncing) return;
      var ss = instances.get(select);
      if (!ss) return;
      syncing = true;
      try { ss.setSelected(select.value); } finally { syncing = false; }
    });
    // disabled、选项与静默赋值拖底：DOM 与 SS data 签名不一致且 DOM 非空即重灌（自愈排序竞态）。
    var lastFeedSig = '';
    var keepAlive = setInterval(function () {
      // detached→停止 interval 并销毁 ss（否则 windowResize 监听/闭包漏，FL-D1015-R2 残留承压测试实锤）
      if (!select.isConnected) {
        clearInterval(keepAlive);
        try {
          var stale_ = instances.get(select);
          instances.delete(select);
          try { feed.signature.delete(select); } catch (e) {}
          stale_ && stale_.destroy();
        } catch (e) {}
        return;
      }
      if (!instances.has(select)) return;
      var ss = instances.get(select);
      var cur = ss.getSelected ? ss.getSelected() : null;
      var want = select.value;
      // SS 空数据时 getSelected 返回 []：cur[0]===undefined 与 DOM value='' 同为“未选”，不算分歧。
      var curV = Array.isArray(cur) ? (cur.length ? cur[0] : '') : (cur == null ? '' : cur);
      if (curV !== want) {
        syncing = true;
        try { ss.setSelected(want); } catch (e) {} finally { syncing = false; }
      }
      var data = Array.from(select.options).map(function (o) {
        var d = { text: o.textContent, value: o.value };
        if (o.disabled) d.disabled = true;
        d.selected = o.selected;
        return d;
      });
      var sig = JSON.stringify(data.map(function (d) { return [d.value, d.text]; }));
      var curSig = '';
      try {
        curSig = JSON.stringify((ss.getData() || []).map(function (d) { return [d.value, d.text]; }));
      } catch (e) {}
      if (data.length && sig !== curSig && sig !== lastFeedSig) {
        lastFeedSig = sig;
        syncing = true;
        markProgrammatic(select, 500);
        try { ss.setData(data); } catch (e) {} finally { syncing = false; }
      }
      // disabled 状态同步（SS observer 已关，由拖底负责）：
      try {
        if (select.disabled) { if (!ss.settings || !ss.settings.disabled) ss.disable(); }
        else if (ss.settings && ss.settings.disabled) ss.enable();
      } catch (e) {}
    }, 300);

  }

  function enhanceAll(root) {
    (root || document).querySelectorAll('select:not([data-fl-selectvend])')
      .forEach(function (select) { enhance(select); });
  }

  // 应用侧打枣点：选项内容变化（patchHTML/innerHTML 重填）后同步调用
  // FundLexSelectKit.feed(select)，我们用 ss.setData 重新灌入（SS 契约唯一通路）。
  function feed(el) {
    if (!el || el.tagName !== 'SELECT') return;
    var ss = instances.get(el);
    if (!ss) return;
    var data = Array.from(el.options).map(function (o) {
      var d = { text: o.textContent, value: o.value };
      if (o.disabled) d.disabled = true;
      d.selected = o.selected;
      return d;
    });
    // 内容未变提早返回（F3：500ms 程序态窗吞用户点击的风险面要压到最小）
    var sig = JSON.stringify(data.map(function (d) { return [d.value, d.text, !!d.selected]; }));
    if (data.length && !data.some(function (d) { return d.selected; }) && el.value) {
      var pick = data.find(function (d) { return d.value === el.value; });
      if (pick) pick.selected = true;
    }
    if (sig === (feed.signature.get(el) || '')) return;
    feed.signature.set(el, sig);
    // 标记程序态：setData 重生成 option ids，SS afterChange 会误判选择改变；
    // 窗口内不转发 afterChange（用户真实操作仍会过：click 在窗口外）。
    markProgrammatic(el, 500);
    ss.setData(data);
    // 与 DOM 选择状态对齐（SS 对 selected 属性有自己的初始化语义）
    ss.setSelected(el.value);
  }
  feed.signature = new WeakMap();

  window.FundLexSelectKit = { enhanceAll: enhanceAll, feed: feed };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', enhanceAll);
  } else {
    enhanceAll();
  }
  // 动态注入 select（分页、模型表单等）增量装配（debounce）；
  // 即时回收被移除的已增强 select（SS resize 监听至窗口级，过期实例销毁不能等 300ms 轮询）。
  var timer = null;
  new MutationObserver(function (mutations) {
    for (var mi = 0; mi < mutations.length; mi++) {
      var m = mutations[mi];
      if (m.type !== 'childList' || !m.removedNodes.length) continue;
      for (var ni = 0; ni < m.removedNodes.length; ni++) {
        var node = m.removedNodes[ni];
        if (node.nodeType !== 1) continue;
        var selects = [];
        if (node.tagName === 'SELECT') selects.push(node);
        if (node.querySelectorAll) {
          node.querySelectorAll('select[data-fl-selectvend="1"]').forEach(function (s) { selects.push(s); });
        }
        selects.forEach(function (s) {
          var stale = instances.get(s);
          if (!stale) return;
          instances.delete(s);
          try { feed.signature.delete(s); } catch (e) {}
          try { stale.destroy(); } catch (e) {}
          delete s.dataset.flSelectvend;
        });
      }
    }
    if (timer) return;
    timer = setTimeout(function () { timer = null; enhanceAll(); }, 60);
  }).observe(document.body || document.documentElement, { childList: true, subtree: true });
})();
