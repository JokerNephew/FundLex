/* FL-D1046：章节导航组件（修订审查视图 + 合同比对视图共用）。
 *
 * 交互（贴 Word 章节导航语言，用 FundLex 令牌）：
 * - 章节项点击进入：目标元素平滑滚到视窗中部；当前节随滚动端高亮；
 * - ≤760px 折叠为抽屉（底部小把手），桌面侧栏静态；
 * - 数据源两级：①已渲染结构里的 .doc-heading（样式优先）；
 *   ②`第X条`/`第X章`/`第X节`/`第X部` 正则锚定块级段落。
 */
(function () {
  'use strict';

  /* FL-D1053（用户实测刺「识别太少」）：基金合同显题惯用多级书写——
   * 一级=第X部分/篇/编 或 styled .doc-heading 或「一、二、三、」直缀；二级=第X条 或 （一）（二）…；三级=1. 2. …
   * 各级只允许原生段落/块级，trim ≤120 字；表格 td/global selector 不用（绝对粘身。
   */
  const HEADING_L1_RE = /^(第[一二三四五六七八九十百千万0-9〇零]+(部分|篇|编|章)|[一二三四五六七八九十]{1,4}、)/;
  const HEADING_L2_RE = /^(第[一二三四五六七八九十百千万0-9〇零]+(节|条|款)|（[一二三四五六七八九十]{1,4}）)/;
  const HEADING_L3_RE = /^\d+[\./、]/;
  const HEADING_RE = new RegExp(`^(?:${HEADING_L1_RE.source}|${HEADING_L2_RE.source}|${HEADING_L3_RE.source})`);

  /* FL-D1053（追加令，用户实测刺「目录里的章节标题也被识别了」）后跳阶段检皮：
   * 目录区典型标记规则：
   *  - 单独锚段（全文恰为"目录"，允许跨多空格预=>；
   *  - 点线领导符尾页码（「……. 1」「……. １」）；
   *  - 尾部页码（与空白京类的 1~4 位数字，含全角数字）；
   * 区域起：首个独立锚段处、至正文首个一级标题者止——期间不纳入任何条目；
   * 跨页目录同样适用（对改进目录字符并无窗口绑定）；
   * 正文里含「目录」字样的真条款（如「不得以……广告目录」）不误伤：仅单独位锚段触发。
   */
  const TOC_ANCHOR_RE = /^目\s*录$/;
  const TOC_LEADER_RE = /^\.{2,}\s*[\d０-９]{1,4}$/;
  const TOC_TAIL_RE = /[\s\t…‥︙·.]+[\d０-９]{1,4}\s*$/;
  const TOC_MIN = 3;   // 少于 3 个标题就不渲染侧栏


  /* FL-D1077（用户实测返刺「目录里的章节还在」）：样式/正则/虚拟三路共用目录闸——
   * 目录行与正文章名文本完全一样（「第一部分  前言」出现两次），单行无 distinguishing，
   * 靠区域记名：锚段「目 录」开区后，区域内标题一律记名不入；同一文本第二次出现必为正文首章，收区放行。 */
  function makeTocGate() {
    let inRegion = false;
    const tocSet = new Set();
    return function gate(text, level) {
      if (TOC_ANCHOR_RE.test(text)) { inRegion = true; return false; }
      if (inRegion) {
        // 目录行带页码、正文章名不带——剥页码记名，否则正文首章永不与目录相认（区域不收，全章被吞）。
        const base = text.replace(TOC_TAIL_RE, '').trim();
        if (level > 0 && tocSet.has(base)) { inRegion = false; return true; }
        if (level > 0) tocSet.add(base);
        return false;
      }
      if (TOC_LEADER_RE.test(text) || TOC_TAIL_RE.test(text)) return false;
      return true;
    };
  }
  function levelOfText(text, fallback) {
    if (!text) return fallback;
    if (HEADING_L1_RE.test(text)) return 1;
    if (HEADING_L2_RE.test(text)) return 2;
    if (HEADING_L3_RE.test(text)) return 3;
    return fallback;
  }

  function shortLabel(text) {
    return (text || '').trim().replace(/\s+/g, ' ').slice(0, 40);
  }

  /** 样式优先（后端 pipeline 的 doc-heading 类）；尾部页码/领导符同样入剔除（偶发封面·页面试。） */
  function fromStyledHeadings(root) {
    if (!root) return [];
    const gate = makeTocGate();
    return Array.from(root.querySelectorAll('.doc-heading')).filter(el => {
      const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
      if (!text) return false;
      return gate(text, levelOfText(text, 1));
    }).map((el, i) => {
      const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
      return {
        key: `h${i}`,
        text: shortLabel(text) || `节 ${i + 1}`,
        level: levelOfText(text, 1),
        anchor: () => el,
      };
    });
  }

  /** 正则分级兜底（FL-D1053 + 目录区剔除）：块级修剪 ≤120 字、同层去重、伪命中剔除。 */
  function fromClauseRegex(root, selector) {
    if (!root) return [];
    const nodes = root.matches && root.matches(selector) ? [root, ...root.querySelectorAll(selector)]
      : Array.from(root.querySelectorAll(selector));
    const items = [];
    const seen = new Set();
    const gate = makeTocGate();
    const accept = (el, text) => gate(text, levelOfText(text, 0));
    for (const el of nodes) {
      if (el.closest('table')) continue;
      const text = (el.textContent || '').trim().replace(/\s+/g, ' ');
      // 锚段由 makeTocGate 内部开区（FL-D1077 统一闸）——这里交给 accept 判定。
      if (!text || text.length > 120) continue;
      let level = 0;
      if (HEADING_L1_RE.test(text)) level = 1;
      else if (HEADING_L2_RE.test(text)) level = 2;
      else if (HEADING_L3_RE.test(text)) level = 3;
      if (!level) { gate(text, 0); continue; }   // 锚段（level0）也须过闸开区
      if (!accept(el, text)) continue;
      const key = `${level}|${text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({ key: `c${items.length}`, text: shortLabel(text), level, anchor: () => el });
    }
    return items;
  }

  /** 虚拟文档级段落扫：读整个虚拟 blocks（含未挂载分块）文本并剥 html — 抽头地在用
   * `root._virtualDoc.blocks`。解决虚拟化大文档在 DOM 肉眼只见末屏上下文。 */
  function sectionTextFromBlock(blockHtml, template) {
    template.innerHTML = blockHtml || '';
    return (template.content.textContent || '');
  }

  function fromVirtualBlocks(root) {
    const vd = root._virtualDoc;
    if (!vd || !Array.isArray(vd.blocks) || !vd.blocks.length) return null;
    const template = document.createElement('template');
    const items = [];
    const seen = new Set();
    const gate = makeTocGate();
    for (const block of vd.blocks) {
      const opt = { text: sectionTextFromBlock(block.html, template).trim().replace(/\s+/g, ' ') };
      const blockId = block.blockId;
      if (!opt.text || opt.text.length > 120) continue;
      // 表格内的 capture 通过 html 上下文查生（compare-table-paragraph / table 的 extension
      const htmlTemplate = template;
      htmlTemplate.innerHTML = block.html || '';
      if (htmlTemplate.content.querySelector(':scope > table') || htmlTemplate.content.querySelector(':scope > p.compare-table-paragraph')) continue;
      let level = 0;
      if (HEADING_L1_RE.test(opt.text)) level = 1;
      else if (HEADING_L2_RE.test(opt.text)) level = 2;
      else if (HEADING_L3_RE.test(opt.text)) level = 3;
      if (!level) { gate(opt.text, 0); continue; }   // 锚段（level0）也须过闸开区
      if (!gate(opt.text, level)) continue;
      const key = `${level}|${opt.text}`;
      if (seen.has(key)) continue;
      seen.add(key);
      items.push({
        key: `vb${items.length}`,
        text: shortLabel(opt.text),
        level,
        virtualBlockId: blockId,
        anchor: () => {
          const el = root.querySelector(`[data-block-id="${CSS.escape(blockId)}"]`);
          return el || null;
        },
      });
    }
    return items;
  }

  function collect(root, options = {}) {
    // FL-D1077：章+节都出（节深度缩进），目录区三路共用闸剔除。
    const levels = (Array.isArray(options.levels) && options.levels.length ? options.levels : [1, 2]).map(Number);
    // FL-D1078：上下文归级——文书用「第X部分/章」为章时，「一、二、」实为节级（降级 2，与章分阶缩进）；
    // 无部分/章的文书保持旧语义（一、二、=章级）。
    const PART_HEAD_RE = /^第[一二三四五六七八九十百千万0-9〇零]+(部分|篇|编|章)/;
    const ENUM_HEAD_RE = /^[一二三四五六七八九十]{1,4}、/;
    const reLevelByContext = (items) => {
      if (!items.some(item => PART_HEAD_RE.test(item.text || ''))) return items;
      return items.map(item => ENUM_HEAD_RE.test(item.text || '') && Number(item.level) === 1
        ? { ...item, level: 2 } : item);
    };
    const keepLevelFilter = (items) => reLevelByContext(items).filter(item => levels.includes(Number(item.level ?? 1)));

    // 虚拟文档（虚拟化窗格）优先以全量 blocks 为数据源——DOM 可见部分仅是子集
    if (root && root._virtualDoc) {
      const virtualItems = fromVirtualBlocks(root);
      if (virtualItems && virtualItems.length) return keepLevelFilter(virtualItems);
    }
    const styled = fromStyledHeadings(root);
    if (styled.length >= (options.tocMin ?? TOC_MIN)) return keepLevelFilter(styled);
    const selector = options.selector || 'p,li,div,[data-block-id]';
    const clo = fromClauseRegex(root, selector).filter(item => !styled.some(s => s.text === item.text));
    return keepLevelFilter([...styled, ...clo]);
  }

  /** 用户点某项时调视点定位：默认 scrollIntoView；可被调用方 override（带 anchor 元素上下文）。 */
  function jumpTo(section, customScrollPane) {
    const target = section && typeof section.anchor === 'function' ? section.anchor() : null;
    if (!target) return;
    const pane = (customScrollPane && customScrollPane()) || target.scrollParent || target.closest('.review-doc,.compare-pane,.compare-merged-doc,.compare-view-body') || document.documentElement;
    const t = target.getBoundingClientRect();
    const p = pane.getBoundingClientRect();
    const delta = t.top + t.height / 2 - p.top - p.height / 2;
    pane.scrollBy({ top: delta, behavior: 'smooth' });
  }

  function mount({ host, root, title, pane, onSelect, collapse }) {
    if (!host || !root) return null;
    let sections = [];
    let activeIdx = -1;
    let raf = null;

    function render(items) {
      sections = Array.isArray(items) ? items : [];
      // FL-D1055：replaceChildren 会带着拖手柄一起清——先于清挂接（若有）并在重建后归位，
      // 否则每个换组/视模式切换都牢牢丢拉手（实测 per-render）。
      const keepSplitter = host.querySelector('.section-nav-splitter');
      host.replaceChildren();
      if (!sections.length) {
        if (keepSplitter) host.append(keepSplitter);
        return;
      }
      const nav = document.createElement('aside');
      nav.className = 'section-nav';
      nav.setAttribute('role', 'navigation');
      nav.setAttribute('aria-label', title || '章节');
        const head = document.createElement('div');
      head.className = 'section-nav-head';
      const strong = document.createElement('strong');
      strong.textContent = title || '章节';
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'section-nav-toggle';
      toggle.setAttribute('aria-label', '切换章节导航');
      toggle.setAttribute('aria-expanded', 'false');
      toggle.textContent = '章节';
      head.append(strong, toggle);
      // FL-D1059（用户原话）：章节栏折叠钮——收=细条只留把手，态位 localStorage 记忆。
      if (collapse) {
        const cbtn = document.createElement('button');
        cbtn.type = 'button';
        cbtn.className = 'section-collapse-toggle';
        cbtn.dataset.titleExpand = '展开章节栏';
        cbtn.dataset.titleCollapse = '折叠章节栏';
        cbtn.dataset.textExpand = '»';
        cbtn.dataset.textCollapse = '«';
        cbtn.textContent = '«';
        cbtn.setAttribute('aria-expanded', 'true');
        cbtn.setAttribute('aria-label', '折叠或展开章节栏');
        head.appendChild(cbtn);
        window.FundLexSectionNav.attachCollapse(cbtn, collapse.gridContainer, collapse.stateClass, collapse.key,
                                                false, collapse.onToggle || null);
      }
      const list = document.createElement('ol');
      list.className = 'section-nav-list';
      sections.forEach((section, i) => {
        const li = document.createElement('li');
        li.dataset.idx = String(i);
        li.dataset.level = String(section.level || 1);
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'section-nav-item';
        btn.textContent = section.text;
        btn.title = section.text;
        btn.dataset.jump = String(i);
        btn.addEventListener('click', () => {
          if (onSelect) onSelect(section, jumpTo);
          else jumpTo(section, pane);
          setActive(i);
          tickHli();
          if (window.matchMedia('(max-width: 760px)').matches) {
            nav.classList.remove('is-open');
            toggle.setAttribute('aria-expanded', 'false');
          }
        });
        li.append(btn);
        list.append(li);
      });
      toggle.addEventListener('click', (e) => {
        e.preventDefault();
        const open = nav.classList.toggle('is-open');
        toggle.setAttribute('aria-expanded', String(open));
      });
      nav.append(head, list);
      host.append(nav);
      if (keepSplitter) host.append(keepSplitter);
      computeActive();
    }

    function setActive(i) {
      activeIdx = i;
      host.querySelectorAll('.section-nav-item').forEach((btn, idx) => {
        btn.classList.toggle('is-active', idx === i);
      });
    }

    function currentPane() {
      return (pane && pane()) || root.scrollParent || root;
    }

    function computeActive() {
      if (!sections.length) return;
      const pane = currentPane();
      if (!pane || typeof pane.getBoundingClientRect !== 'function') return;
      const paneTop = pane.getBoundingClientRect().top;
      let candidate = 0;
      sections.forEach((section, i) => {
        const target = section.anchor && section.anchor();
        if (!target) return;
        if (target.getBoundingClientRect().top <= paneTop + 56) candidate = i;
      });
      if (candidate !== activeIdx) setActive(candidate);
    }

    function tickHli() {
      if (!raf) raf = requestAnimationFrame(() => { raf = null; computeActive(); });
    }

    let detachScroll = [];
    function bindScroll() {
      detachScroll.forEach(fn => fn());
      detachScroll = [];
      const pane = currentPane();
      const targets = Array.isArray(pane) ? pane : [pane];
      targets.forEach(p => {
        if (!p || typeof p.addEventListener !== 'function') return;
        const handler = () => tickHli();
        p.addEventListener('scroll', handler, { passive: true });
        detachScroll.push(() => p.removeEventListener('scroll', handler));
      });
    }

    function destroy() {
      detachScroll.forEach(fn => fn());
      detachScroll = [];
      host.replaceChildren();
    }

    return { render, destroy, refresh: () => { bindScroll(); computeActive(); } };
  }

  /* FL-D1055：章节栏宽可拖（用户原话）——AIIA separator 拖动手柄挂 nav 右缘，
   * 复用 FundLexColumnSplitter（原 FundLexColumnSplitter/review-splitter 交互语言，
   * 只拿交互不拿样式色）；拖完持久化到由本调用方提供的 localStorage 键（两视图独立键）。
   * 用法：你已经 mount() 了一处 nav → 再 attachSplitter(nav 的容器 host, 拖手参数)，其他宽度
   * 与布局线按原方式由【调用方 CSS 读取的变量】跟换。窄屏(≤760px)进入抽屉模式自动关禁用。
   */
  function attachSplitter(nav, container, getTarget, opts = {}) {
    if (!window.FundLexColumnSplitter || !nav || !container) return null;
    const existing = nav.querySelector('.section-nav-splitter');
    if (existing) { try { existing.remove(); } catch {} }
    const sp = document.createElement('div');
    sp.className = 'section-nav-splitter';
    // FL-D1055：审阅侧 wrapper 带 pointer-events:none 压壳——splitter 自身必须恢复交互，
    // 否则拖拽/键盘都不可达（与上一波层次挡击型防的太迟吸附，证底领目间距的两条范本该做）
    sp.style.pointerEvents = 'auto';
    sp.id = opts.id || '';
    sp.setAttribute('role', 'separator');
    sp.setAttribute('aria-label', opts.ariaLabel || '调整章节导航宽度');
    sp.setAttribute('aria-orientation', 'vertical');
    sp.setAttribute('aria-valuemin', String(opts.min ?? 200));
    sp.setAttribute('aria-valuemax', String(opts.max ?? 420));
    sp.setAttribute('aria-valuetext', `${opts.fallback ?? 200} 像素`);
    sp.tabIndex = 0;
    nav.appendChild(sp);
    const instance = window.FundLexColumnSplitter(sp, container, getTarget, {
      key: opts.key || `fundlex-sectionnav-${container.id || 'x'}-width`,
      variable: opts.variable || '--section-nav-column-width',
      min: opts.min ?? 200,
      max: opts.max ?? 420,
      minOther: opts.minOther ?? 280,
      fallback: opts.fallback ?? 200,
      side: opts.side ?? 'left',
      disabled: opts.disabled ?? (() => matchMedia('(max-width: 760px)').matches),
      onEnd: opts.onEnd,
    });
    return { handle: sp, instance };
  }


  /* FL-D1059：折叠通用钮——调用方先提供 DOM 的钮 `role=button` / class section-collapse，
   * 调 helper 接其上（hind 支持不更改 DOM 位置内容的方式更冷我享面试官吧）：
   * attachCollapse(btn, gridContainer, stateClass, key_persistence, onToggle)
   * 每次 toggle：gridContainer.classList.toggle(stateClass, next)、btn aria-expanded 同步、
   * localStorage key 记住（视图独立键）。
   * FL-D1092：onToggle(collapsed) 可选回调——折叠切宽后由调用方触发宿主重排
   *（比对视图=refreshVirtualLayouts+drawLines，防止大文档虚拟块沿旧宽错位）。 */
  function attachCollapse(btn, gridContainer, stateClass, key, defaultCollapsed = false, onToggle = null) {
    if (!btn || !gridContainer || !stateClass) return null;
    let collapsed = defaultCollapsed;
    try {
      const saved = localStorage.getItem(key);
      if (saved !== null) collapsed = saved === '1';
    } catch {}
    let fromUser = false;
    const apply = (next, user = false) => {
      fromUser = !!user;
      collapsed = !!next;
      gridContainer.classList.toggle(stateClass, collapsed);
      btn.classList.toggle('is-active', collapsed);
      btn.setAttribute('aria-expanded', String(!collapsed));
      const titleExpand = btn.dataset.titleExpand || '展开';
      const titleCollapse = btn.dataset.titleCollapse || '折叠';
      btn.title = collapsed ? titleExpand : titleCollapse;
      if (btn.dataset.textExpand !== undefined || btn.dataset.textCollapse !== undefined) {
        btn.textContent = collapsed ? (btn.dataset.textExpand || '»') : (btn.dataset.textCollapse || '«');
      }
      try { localStorage.setItem(key, collapsed ? '1' : '0'); } catch {}
      // FL-D1092：切宽后重排通知（初始化 apply 不触发——避免首帧双排版）。
      if (onToggle && fromUser) requestAnimationFrame(() => onToggle(collapsed));
    };
    btn.addEventListener('click', e => { e.preventDefault(); apply(!collapsed, true); });
    btn.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); apply(!collapsed, true); }
    });
    apply(collapsed);
    return { apply, get collapsed() { return collapsed; } };
  }

  window.FundLexSectionNav = { mount, collect, jumpTo, attachSplitter, attachCollapse, HEADING_RE, TOC_MIN };
})();
