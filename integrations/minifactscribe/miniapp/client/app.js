// 事实闸 · Client
// 呈现与交互；所有写操作走 Node 领域服务，页面不直接落盘。
//
// 呈现层的三条自律（2026-11 改版）：
//   1. 过期就说过期——内容改了、审计没重跑，旧结论不许继续冒充现状。
//   2. 状态不靠颜色单独承载——每个判定都带符号和文字（WCAG 1.4.1）。
//   3. 危险动作先问一句——覆盖项目、删事实、改哈希，都是「先确认再执行」。

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const state = {
  project: null,
  audit: null,
  verify: null,
  tab: 'manuscript',
  editingFactId: null,
  auditSig: null,
  stale: false,
  saveFailed: false,
  workbench: null,
  workbenchStatus: null,
  workbenchAudit: null,
  workbenchProject: null,
  ai: { requestId: null, streaming: false, sessionId: null, text: '', candidate: '', events: [] },
  hostView: 'unknown',
  hostKey: '',
  hostWorkspace: '',
  hostWorkspaceDefault: false,
};

// ------------------------------------------------------------------ 词汇表
// 内部违规码是给机器看的；给人看的必须是中文短名。
const ISSUE_LABEL = {
  UNMATCHED_NUMBER: '数字回不到账',
  BOUND_MISMATCH: '数字与绑定冲突',
  UNBOUND_NUMBER: '回得到账但没钉住',
  MISSING_CITE: '引用缺 bib 条目',
  BIB_NO_STABLE_ID: '引用缺稳定标识',
  UNKNOWN_CITE_COMMAND: '未知引用命令',
  DUPLICATE_BIB_KEY: 'bib 键重复',
  UNUSED_BIB: '文献没被引用',
  UNUSED_FACT: '事实没被使用',
  DUPLICATE_VALUE: '同值待判断',
  MISSING_SOURCE: '事实缺来源',
  MISSING_SOURCE_FIELD: '事实未填来源字段',
  MISSING_SOURCE_SHA256: '事实缺来源哈希',
  SOURCE_SHA256_MISMATCH: '来源材料被改过',
  DUPLICATE_ID: '事实 ID 重复',
  EXPR_MISMATCH: '推算值对不上',
  EXPR_INVALID: '算式无法求值',
  DERIVED_CYCLE: '推算链成环',
  NUMBER_AS_CROSSREF: '结构编号当成了数据',
  LOW_BINDING_RATE: '绑定率偏低',
  CITE_FAKE: '文献查无此文',
  CITE_SUSPECT: '文献元数据对不上',
  CITE_UNVERIFIED: '文献本轮没核验成',
  RESOLVE_DEGRADED: '联网核验大面积失败',
  UNKNOWN_FACT_MARKER: '正文指向不存在的事实',
  BAD_ID_FORMAT: '事实 ID 格式不对',
  BAD_SOURCE_PATH: '来源指向不存在的材料',
  CONFIG: '项目没配好',
  PROTECT_NUMBER: '改写动了数字',
  PROTECT_CITE: '改写动了引用',
  PROTECT_FACT: '改写动了事实标记',
  PROTECT_FORMULA: '改写动了公式',
  PROTECT_TABLE: '改写动了表格',
  PROTECT_XREF: '改写动了交叉引用',
};

function labelOf(code) {
  return ISSUE_LABEL[code] || '未归类的问题';
}

// 数字判定的符号：颜色之外还要有形状，色弱与单色打印才读得出。
const CHIP = {
  ok: { sym: '✓', label: '已绑定且对得上' },
  warn: { sym: '!', label: '回得到账但没钉住' },
  bad: { sym: '✕', label: '回不到账或与绑定冲突' },
  mute: { sym: '·', label: '结构编号，不作数据' },
};

// 事实账与覆盖矩阵共用一套状态词，别一个叫「已内联绑定」一个叫「已绑定」。
const USED_IN_LABEL = {
  '已内联绑定': '已绑定',
  '只命中值域（未绑定）': '未绑定',
  '未被引用': '未被引用',
};

/** 位置串翻译成人话。 */
function formatLocation(loc) {
  if (!loc) return '';
  let m = /^正文:(\d+)$/.exec(loc);
  if (m) return '正文 第 ' + m[1] + ' 行';
  m = /^事实账:(.+)$/.exec(loc);
  if (m) return '事实 ' + m[1];
  m = /^来源:(.+)$/.exec(loc);
  if (m) return '来源材料 ' + m[1];
  m = /^refs\.bib:(.+)$/.exec(loc);
  if (m) return 'bib 条目 ' + m[1];
  if (loc === '事实账') return '事实账';
  if (loc === '正文') return '正文';
  if (loc === '引用核验') return '引用核验';
  return loc;
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'content-type': 'application/json' }, ...opts });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok || data.ok === false) {
    const message = data?.error?.message || data?.error || 'HTTP ' + res.status;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

async function sha256Hex(text) {
  if (!globalThis.crypto || !globalThis.crypto.subtle) throw new Error('当前环境不支持现算哈希');
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(String(text ?? '')));
  return Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

let toastTimer = null;
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    el.hidden = true;
  }, 2600);
}

// ------------------------------------------------------------------ 过期检测
// 审计结论只在「正文 + 引用 + 事实账 + 来源材料」这套内容上成立。
// 内容一改，旧结论就是过期结论——必须说出来，不能让旧红黄牌继续冒充现状。
function sigOf(project) {
  const p = project || {};
  const parts = [p.manuscript ?? '', p.bib ?? ''];
  for (const s of p.sources || []) parts.push(s.id + '\u0000' + (s.text ?? ''));
  for (const f of p.facts || []) {
    parts.push(
      [f.id, f.claim, f.value, f.source, f.sourceSha256, f.locator, f.confidence, f.expr, f.dupOk ? 1 : 0, f.notes]
        .join('\u0001'),
    );
  }
  const str = parts.join('\u0002');
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < str.length; i += 1) {
    const c = str.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
    h2 = Math.imul(h2 ^ c, 0x85ebca6b) >>> 0;
  }
  return h1.toString(16) + '-' + h2.toString(16);
}

function refreshStale() {
  state.stale = Boolean(state.audit && state.auditSig && sigOf(state.project) !== state.auditSig);
  const banner = $('#stale-banner');
  banner.hidden = !state.stale;
  if (state.stale) {
    $('#stale-text').textContent =
      '你在上次审计之后改过正文 / 事实账 / 引用。下面显示的还是改动前的结果——点「重新审计」刷新。';
  }
  renderVerdict();
}

// ------------------------------------------------------------------ 保存状态

let saveTimer = null;
function scheduleSave() {
  setSaveState('未保存', false);
  refreshStale();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 600);
}

function setSaveState(text, failed) {
  const el = $('#save-state');
  el.textContent = text;
  state.saveFailed = Boolean(failed);
  el.classList.toggle('is-failed', Boolean(failed));
  el.title = failed
    ? '保存失败，点这里重试'
    : text === '无改动'
      ? '当前内容与上次保存一致'
      : '改动会自动保存到本地数据目录';
}

async function saveNow() {
  setSaveState('保存中…', false);
  try {
    await api('/api/project', { method: 'PUT', body: JSON.stringify({ project: state.project }) });
    setSaveState('已保存', false);
    return true;
  } catch (err) {
    setSaveState('保存失败 · 点此重试', true);
    toast('保存失败：' + err.message);
    return false;
  }
}

function switchTab(tab) {
  state.tab = tab;
  for (const btn of $$('.nav-item')) {
    const on = btn.dataset.tab === tab;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', String(on));
  }
  for (const panel of $$('.panel')) {
    const on = panel.id === 'panel-' + tab;
    panel.classList.toggle('is-active', on);
    panel.hidden = !on;
  }
  renderTab();
}

function renderTab() {
  if (state.tab === 'manuscript') renderManuscript();
  else if (state.tab === 'ledger') renderLedger();
  else if (state.tab === 'refs') renderRefs();
  else if (state.tab === 'protect') renderProtect();
  else if (state.tab === 'audit') renderAudit();
  else if (state.tab === 'workbench') renderWorkbench();
  else if (state.tab === 'ai') renderAi();
}

// ------------------------------------------------------------------ 顶栏

function verdictSentence(a) {
  const shown = a.verdict === 'red' ? (a.redShown || a.red).length : a.verdict === 'yellow' ? (a.yellowShown || a.yellow).length : 0;
  const base = {
    green: '绿牌：账有据、据未改、文有绑。',
    red: '红牌 ' + shown + ' 处，必须改。',
    yellow: '黄牌 ' + shown + ' 处，待人判断。',
  }[a.verdict];
  return base + '（退出码 ' + a.exitCode + '）';
}

function renderVerdict() {
  const el = $('#verdict');
  if (!state.audit) {
    el.className = 'verdict verdict-idle';
    el.textContent = '未审计';
    el.title = '还没跑过审计——点右上角「运行审计」';
    return;
  }
  if (state.stale) {
    el.className = 'verdict verdict-stale';
    el.textContent = '结果已过期';
    el.title = '内容改过但没重跑审计。上次结论：' + verdictSentence(state.audit);
    return;
  }
  const a = state.audit;
  const word = { green: '绿牌', red: '红牌', yellow: '黄牌' }[a.verdict];
  const n = a.verdict === 'red' ? (a.redShown || a.red).length : a.verdict === 'yellow' ? (a.yellowShown || a.yellow).length : 0;
  el.className = 'verdict verdict-' + a.verdict;
  el.textContent = word + (n ? ' ' + n + ' 处' : '');
  el.title = verdictSentence(a);
}

// ------------------------------------------------------------------ 正文

function issuesByLine() {
  const map = new Map();
  for (const issue of state.audit?.issues || []) {
    const m = /^正文:(\d+)$/.exec(issue.location || '');
    if (!m) continue;
    const line = Number(m[1]);
    if (!map.has(line)) map.set(line, []);
    map.get(line).push(issue);
  }
  return map;
}

function renderManuscript() {
  $('#manuscript-input').value = state.project.manuscript ?? '';
  const lines = state.audit?.lines || [];
  const byLine = issuesByLine();
  const report = $('#line-report');

  if (!state.audit) {
    report.innerHTML = '<div class="line-empty">先运行一次审计，这里会逐行显示每个数字的判定。</div>';
    $('#manuscript-stats').textContent = '';
    return;
  }

  const rows = [];
  for (const line of lines) {
    if (!line.numbers.length && !line.bound.length) continue;
    const chips = [];
    for (const num of line.numbers) {
      const hits = (byLine.get(line.line) || []).filter((i) => i.token === num.token);
      let cls = 'ok';
      let title = CHIP.ok.label;
      if (num.crossref) {
        cls = 'mute';
        title = CHIP.mute.label;
      } else if (hits.some((h) => h.severity === 'red')) {
        cls = 'bad';
        title = hits.find((h) => h.severity === 'red').message;
      } else if (hits.some((h) => h.severity === 'yellow')) {
        cls = 'warn';
        title = hits.find((h) => h.severity === 'yellow').message;
      } else if (!line.bound.length) {
        cls = 'warn';
        title = CHIP.warn.label;
      }
      const sym = CHIP[cls].sym;
      chips.push(
        '<span class="num-chip ' + cls + '" title="' + esc(title) + '"><span class="chip-sym" aria-hidden="true">' + sym + '</span>' +
          '<span class="sr-only">' + esc(CHIP[cls].label) + '：</span>' + esc(num.token) + '</span>',
      );
    }
    const bound = line.bound.length
      ? line.bound.map((id) => '<span class="fact-chip">绑 ' + esc(id) + '</span>').join('')
      : '<span class="fact-chip none">这行没绑定</span>';
    rows.push(
      '<div class="line-row">' +
        '<div class="line-no">第 ' + line.line + ' 行</div>' +
        '<div class="line-main">' +
          '<div class="line-text">' + esc(line.text.trim() || '（空行）') + '</div>' +
          '<div class="line-meta">' + bound + chips.join('') + '</div>' +
        '</div>' +
      '</div>',
    );
  }
  report.innerHTML = rows.length ? rows.join('') : '<div class="line-empty">正文里没有可审计的数字。</div>';

  const s = state.audit.stats;
  $('#manuscript-stats').textContent = s
    ? s.denom
      ? s.denom + ' 个数据数字：' + s.bound + ' 已绑定 · ' + s.unboundYellow + ' 有账没钉住 · ' + s.unmatched + ' 回不到账'
      : '正文里没有数据数字'
    : '';
}

// ------------------------------------------------------------------ 事实账

function factStatus(id) {
  const issues = state.audit?.issues || [];
  const fact = (state.project.facts || []).find((f) => f.id === id);
  const sourceId = fact ? fact.source : '';
  // 精确匹配，别用前缀——A2 会误吃 A26 的黄牌
  const mine = issues.filter(
    (i) => i.location === '事实账:' + id || (sourceId && i.location === '来源:' + sourceId),
  );
  if (mine.some((i) => i.severity === 'red')) return { cls: 'bad', text: '红牌' };
  if (mine.some((i) => i.severity === 'yellow')) return { cls: 'warn', text: '黄牌' };
  const row = (state.audit?.matrix?.facts || []).find((r) => r.id === id);
  if (row?.usedIn === '已内联绑定') return { cls: 'ok', text: '已绑定' };
  if (row && row.usedIn.startsWith('只命中')) return { cls: 'warn', text: '未绑定' };
  return { cls: 'mute', text: '未被引用' };
}

/** 账本里钉住的来源哈希（可能多条事实钉了同一个来源）。 */
function pinnedHashOf(sourceId) {
  const pinned = (state.project.facts || [])
    .filter((f) => f.source === sourceId)
    .map((f) => String(f.sourceSha256 || ''))
    .filter(Boolean);
  return pinned[0] || '';
}

function renderLedger() {
  const facts = state.project.facts || [];
  const tbody = $('#facts-tbody');
  $('#facts-count').textContent = facts.length ? '共 ' + facts.length + ' 条事实' : '账上还没有事实';

  if (!facts.length) {
    tbody.innerHTML =
      '<tr class="table-empty-row"><td colspan="6">账上还没有事实。点右上角「新增事实」，先记一条有来源的数。</td></tr>';
  } else {
    tbody.innerHTML = facts
      .map((f) => {
        const st = factStatus(f.id);
        return (
          '<tr class="clickable" data-fact="' + esc(f.id) + '" title="点击编辑这条事实">' +
            '<td class="mono">' + esc(f.id) + '</td>' +
            '<td>' + esc(f.claim) + '</td>' +
            '<td class="mono">' + esc(f.value) + '</td>' +
            '<td>' + esc(f.source || '—') + '</td>' +
            '<td><span class="status-dot"><span class="dot dot-' + st.cls + '"></span>' + st.text + '</span></td>' +
            '<td><button class="link-btn edit-btn" type="button" data-edit-fact="' + esc(f.id) + '">编辑</button></td>' +
          '</tr>'
        );
      })
      .join('');
  }

  const sourceSel = $('#f-source');
  const current = sourceSel.value;
  sourceSel.innerHTML =
    '<option value="">（无来源）</option>' +
    (state.project.sources || []).map((s) => '<option value="' + esc(s.id) + '">' + esc(s.id) + '</option>').join('');
  sourceSel.value = current;

  const sources = $('#sources-list');
  sources.innerHTML = (state.project.sources || [])
    .map((s) => {
      const usedBy = facts.filter((f) => f.source === s.id).length;
      const pinned = pinnedHashOf(s.id);
      return (
        '<div class="source-card" data-source="' + esc(s.id) + '">' +
          '<div class="source-head">' +
            '<span class="source-id">' + esc(s.name || s.id) +
              ' <span class="muted-note">（' + esc(s.id) + '，' + usedBy + ' 条事实引用）</span></span>' +
            '<span class="source-actions">' +
              '<button class="btn" type="button" data-rehash="' + esc(s.id) + '">更新哈希</button>' +
            '</span>' +
          '</div>' +
          '<div class="source-hashes">' +
            '<span class="hash-note">账内钉住 <b data-pinned-sha="' + esc(s.id) + '">' +
              (pinned ? esc(pinned.slice(0, 16)) + '…' : '（没有）') + '</b></span>' +
            '<span class="hash-note">材料现算 <b data-live-sha="' + esc(s.id) + '">计算中…</b></span>' +
            '<span class="sha-cmp mute" data-sha-cmp="' + esc(s.id) + '">比对中…</span>' +
          '</div>' +
          '<textarea class="editor editor-bib" data-source-text="' + esc(s.id) + '" spellcheck="false" aria-label="' + esc(s.id) + ' 内容">'
            + esc(s.text) + '</textarea>' +
          '<div class="confirm-box" data-rehash-confirm="' + esc(s.id) + '" hidden>' +
            '<span>更新哈希＝承认现在这份材料就是正确版本，并把账本钉住的值改成它。这会洗掉「来源材料被改过」的红牌。</span>' +
            '<div class="confirm-actions">' +
              '<button class="btn btn-danger" type="button" data-rehash-ok="' + esc(s.id) + '">确认更新</button>' +
              '<button class="btn" type="button" data-rehash-cancel="' + esc(s.id) + '">取消</button>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
    })
    .join('') || '<div class="line-empty">还没有来源材料。每条事实都要指到一份来源。</div>';

  refreshLiveHashes();
  loadFactForm(state.editingFactId);
}

/** 现算每份材料的 sha256，和账本钉住的值摆在一起对照。 */
function refreshLiveHashes() {
  for (const s of state.project.sources || []) {
    const id = String(s.id);
    sha256Hex(s.text ?? '')
      .then((h) => {
        const liveEl = document.querySelector('[data-live-sha="' + CSS.escape(id) + '"]');
        if (liveEl) liveEl.textContent = h.slice(0, 16) + '…';
        const cmpEl = document.querySelector('[data-sha-cmp="' + CSS.escape(id) + '"]');
        if (!cmpEl) return;
        const pinned = pinnedHashOf(id);
        const same = Boolean(pinned) && pinned === h;
        cmpEl.className = 'sha-cmp ' + (!pinned ? 'mute' : same ? 'ok' : 'bad');
        cmpEl.textContent = !pinned
          ? '账内没钉住哈希 → 会判红'
          : same
            ? '与账内钉住的一致'
            : '与账内钉住的不一致 → 会判红';
      })
      .catch(() => {
        const liveEl = document.querySelector('[data-live-sha="' + CSS.escape(id) + '"]');
        if (liveEl) liveEl.textContent = '此环境无法现算';
        const cmpEl = document.querySelector('[data-sha-cmp="' + CSS.escape(id) + '"]');
        if (cmpEl) {
          cmpEl.className = 'sha-cmp mute';
          cmpEl.textContent = '无法比对';
        }
      });
  }
}

function loadFactForm(id) {
  const facts = state.project.facts || [];
  const f = id ? facts.find((x) => x.id === id) : null;
  $('#fact-form-title').textContent = f ? '编辑事实 ' + f.id : '新增事实';
  $('#f-id').value = f ? f.id : '';
  $('#f-claim').value = f ? f.claim : '';
  $('#f-value').value = f ? f.value : '';
  $('#f-source').value = f ? f.source : (state.project.sources || [])[0]?.id || '';
  $('#f-locator').value = f ? f.locator : '';
  $('#f-confidence').value = f ? f.confidence || 'high' : 'high';
  $('#f-expr').value = f ? f.expr : '';
  $('#f-notes').value = f ? f.notes : '';
  $('#f-dup').checked = f ? Boolean(f.dupOk) : false;
  $('#btn-delete-fact').hidden = !f;
  $('#fact-delete-confirm').hidden = true;
  $('#fact-delete-id').textContent = f ? f.id : '';
  showFormErrors([]);
}

// ------------------------------------------------------------------ 引用

function renderRefs() {
  $('#bib-input').value = state.project.bib ?? '';
  const rows = state.audit?.matrix?.citations || [];
  const verifyMap = new Map((state.verify?.results || []).map((r) => [r.key, r]));
  const statusText = {
    verified: ['ok', '已核验'],
    suspect: ['warn', '标题对不上'],
    not_found: ['bad', '查无此文'],
    unverified: ['warn', '未核验成'],
    no_id: ['bad', '无稳定标识'],
  };
  $('#refs-count').textContent = rows.length ? '共 ' + rows.length + ' 条 bib 条目' : 'bib 里还没有条目';

  if (!rows.length) {
    $('#bib-tbody').innerHTML =
      '<tr class="table-empty-row"><td colspan="5">bib 里还没有条目。上面贴一段 .bib 原文，这里会列出每条文献。</td></tr>';
  } else {
    $('#bib-tbody').innerHTML = rows
      .map((r) => {
        const v = verifyMap.get(r.key);
        const st = v ? statusText[v.status] || ['mute', v.status] : ['mute', '未核验'];
        const sid = r.stableId ? r.stableId.kind + ':' + r.stableId.value : '无';
        return (
          '<tr>' +
            '<td class="mono">' + esc(r.key) + '</td>' +
            '<td>' + esc(r.title) + '</td>' +
            '<td class="mono">' + esc(sid) + '</td>' +
            '<td class="cell-num">' + r.cited + ' 次</td>' +
            '<td><span class="status-dot" title="' + esc(v?.detail || '') + '"><span class="dot dot-' + st[0] + '"></span>' + st[1] + '</span></td>' +
          '</tr>'
        );
      })
      .join('');
  }
  const note = $('#verify-note');
  if (state.verify) {
    note.textContent =
      '本轮联网核验 ' + state.verify.results.length + ' 条，其中 ' + state.verify.failures +
      ' 条没核验成（网络/限流），没核验成不等于核验失败。' +
      (state.stale ? '　注意：正文或引用改过了，这轮结论只适用于改之前的内容。' : '');
  } else {
    note.textContent = '点「联网核验存在性」去 Crossref / arXiv 查这条引用到底存不存在。';
  }
}

// ------------------------------------------------------------------ 改写保护

function renderProtect() {
  $('#protect-before').value = state.project.protect?.before ?? '';
  $('#protect-after').value = state.project.protect?.after ?? '';
  const box = $('#protect-result');
  if (!box.innerHTML.trim()) {
    box.innerHTML = '<div class="line-empty">还没比对过。左边贴改前、右边贴改后，点「比对保护面」。</div>';
  }
}

// ------------------------------------------------------------------ 审计

function renderAudit() {
  const a = state.audit;
  const summary = $('#audit-summary');
  if (!a) {
    summary.innerHTML = '<div class="line-empty">还没有跑过审计。</div>';
    $('#issues-list').innerHTML = '';
    $('#matrix-tables').innerHTML = '';
    return;
  }
  const word = { green: '绿', red: '红', yellow: '黄' }[a.verdict];
  const note =
    a.verdict === 'green'
      ? '账有据、据未改、文有绑。它不说明结论为真。'
      : a.verdict === 'yellow'
        ? '跑完了，但有未核验或未绑定的项——不判死，但必须逐条看过。'
        : '有事实层矛盾：这些数或引用回不到账，必须改。';
  const s = a.stats || {};
  const redShown = (a.redShown || a.red).length;
  const yellowShown = (a.yellowShown || a.yellow).length;
  const redTotal = a.redCount ?? a.red.length;
  const yellowTotal = a.yellowCount ?? a.yellow.length;
  summary.innerHTML =
    '<div class="verdict-card ' + a.verdict + '">' +
      '<div><div class="verdict-word">' + word + '</div><div class="verdict-note">退出码 ' + a.exitCode + '</div></div>' +
      '<div class="verdict-note" style="flex:1">' + esc(note) + '</div>' +
    '</div>' +
    (state.stale
      ? '<div class="stale-strip">这是改动前的审计结果——正文 / 事实账 / 引用改过了，点右上角「重新审计」刷新。</div>'
      : '') +
    '<div class="kpi-row">' +
      kpi(redShown, '红牌 · 必须改', 'bad', redShown === redTotal ? null : '共 ' + redTotal + ' 条，折叠成 ' + redShown + ' 类') +
      kpi(yellowShown, '黄牌 · 待人判断', 'warn', yellowShown === yellowTotal ? null : '共 ' + yellowTotal + ' 条，折叠成 ' + yellowShown + ' 类') +
      kpi((state.project.facts || []).length, '账上事实', null, null) +
      kpi(s.denom ? Math.round((s.bound / s.denom) * 100) + '%' : '—', '正文数字已绑定', null,
        s.denom ? s.bound + '/' + s.denom + ' 个数据数字用 \\fact{} 钉住' : null) +
    '</div>';

  const list = $('#issues-list');
  // 呈现用折叠视图（同一来源的失配合并成一条）；判定数仍是 redCount/yellowCount。
  const all = [...(a.redShown || a.red), ...(a.yellowShown || a.yellow)];
  if (!all.length) {
    list.innerHTML = '<div class="protect-ok">没有红牌也没有黄牌。绿只说明账、据、文三者自洽。</div>';
  } else {
    list.innerHTML = all
      .map((i) => {
        const p = a.prescriptions[i.code];
        const sev = i.severity === 'red' ? 'chip-red' : 'chip-yellow';
        const sevText = i.severity === 'red' ? '红牌' : '黄牌';
        return (
          '<article class="issue">' +
            '<div class="issue-head">' +
              '<span class="chip ' + sev + '">' + sevText + '</span>' +
              '<span class="issue-label">' + esc(labelOf(i.code)) + '</span>' +
              '<span class="code" title="内部违规码">' + esc(i.code) + '</span>' +
              (i.location ? '<span class="loc">' + esc(formatLocation(i.location)) + '</span>' : '') +
              (i.folded ? '<span class="loc">（折叠了 ' + i.folded + ' 条）</span>' : '') +
            '</div>' +
            '<p class="issue-msg">' + esc(i.message) + '</p>' +
            (i.context ? '<p class="issue-ctx">' + esc(i.context) + '</p>' : '') +
            (p
              ? '<button class="link-btn" type="button" data-pres="' + esc(i.code) + '">怎么修</button>' +
                '<div class="prescription" hidden data-pres-body="' + esc(i.code) + '">' +
                  '<h4>' + esc(p.title) + '</h4><ol>' + p.steps.map((s) => '<li>' + esc(s) + '</li>').join('') + '</ol>' +
                  (p.note ? '<p class="pres-note">' + esc(p.note) + '</p>' : '') +
                '</div>'
              : '') +
          '</article>'
        );
      })
      .join('');
  }

  const m = a.matrix || { facts: [], citations: [] };
  $('#matrix-count').textContent = m.facts.length ? '共 ' + m.facts.length + ' 条事实' : '';
  $('#matrix-tables').innerHTML =
    '<div class="ledger-table-wrap"><table class="data-table">' +
      '<caption class="sr-only">事实覆盖矩阵</caption><thead><tr><th scope="col">事实</th><th scope="col">主张</th><th scope="col">值</th><th scope="col">正文位置</th><th scope="col">状态</th></tr></thead><tbody>' +
      (m.facts.length
        ? m.facts
            .map(
              (r) =>
                '<tr><td class="mono">' + esc(r.id) + '</td><td>' + esc(r.claim) + '</td><td class="mono">' + esc(r.value) +
                '</td><td class="mono">' + esc(r.boundLines.length ? r.boundLines.map((l) => '第 ' + l + ' 行').join('、') : '—') +
                '</td><td>' + esc(USED_IN_LABEL[r.usedIn] || r.usedIn) + '</td></tr>',
            )
            .join('')
        : '<tr class="table-empty-row"><td colspan="5">账上还没有事实，矩阵是空的。</td></tr>') +
      '</tbody></table></div>';
}

function kpi(value, label, cls, hint) {
  return (
    '<div class="kpi"><div class="kpi-value"' + (cls ? ' style="color:var(--mcode-' + cls + ')"' : '') + '>' + esc(String(value)) +
    '</div><div class="kpi-label">' + esc(label) + '</div>' +
    (hint ? '<div class="kpi-hint">' + esc(hint) + '</div>' : '') + '</div>'
  );
}

// ------------------------------------------------------------------ 表单校验

function validateFact() {
  const errs = [];
  const id = $('#f-id').value.trim();
  const claim = $('#f-claim').value.trim();
  const value = $('#f-value').value.trim();
  const sourceId = $('#f-source').value;
  if (!id) {
    errs.push({ field: 'f-id', msg: '给这条事实一个 ID，正文里要用 \fact{ID} 指它' });
  } else if (/\s/.test(id)) {
    errs.push({ field: 'f-id', msg: 'ID 里不能有空格' });
  } else {
    const dup = (state.project.facts || []).find(
      (f) => String(f.id).toLowerCase() === id.toLowerCase() && f.id !== state.editingFactId,
    );
    if (dup) errs.push({ field: 'f-id', msg: '已经有一条 ID 为 ' + dup.id + ' 的事实了' });
  }
  if (!claim) errs.push({ field: 'f-claim', msg: '写一句主张——这条事实到底在讲什么' });
  if (!value) errs.push({ field: 'f-value', msg: '填这个数（支持 10/16、56.25%、90431）' });
  if (!sourceId) errs.push({ field: 'f-source', msg: '指一份来源材料；没有来源的事实会被判红' });
  return errs;
}

function showFormErrors(errs) {
  const box = $('#form-errors');
  const list = $('#form-errors-list');
  list.innerHTML = errs
    .map((e) => '<li><button type="button" class="link-btn" data-goto="' + e.field + '">' + esc(e.msg) + '</button></li>')
    .join('');
  box.hidden = errs.length === 0;
  for (const f of ['f-id', 'f-claim', 'f-value', 'f-source']) {
    const el = $('#' + f + '-error');
    const e = errs.find((x) => x.field === f);
    if (el) {
      el.textContent = e ? e.msg : '';
      el.hidden = !e;
    }
    const input = $('#' + f);
    input.classList.toggle('has-error', Boolean(e));
    input.setAttribute('aria-invalid', e ? 'true' : 'false');
  }
}

// ------------------------------------------------------------------ 动作

async function runAudit(opts = {}) {
  const btn = $('#btn-audit');
  btn.disabled = true;
  btn.textContent = '审计中…';
  try {
    // 先落盘再审计：服务端审的是它持久化的项目，不是屏幕上的草稿。
    // 不先保存，会把「旧稿的结论」按「新稿的指纹」记成新鲜——正好砸掉过期检测。
    const saved = await saveNow();
    if (!saved) {
      toast('保存失败，未审计（先重试保存）');
      return;
    }
    const data = await api('/api/audit', { method: 'POST' });
    state.audit = data.audit;
    state.auditSig = sigOf(state.project);
    refreshStale();
    renderTab();
    // 首屏自动审计不抢页签；手动点「运行审计」才跳到审计页
    if (opts.focus !== false && state.tab !== 'audit') switchTab('audit');
  } catch (err) {
    toast('审计失败：' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '运行审计';
  }
}

async function loadDemo() {
  const data = await api('/api/demo', { method: 'POST' });
  state.project = data.project;
  state.audit = null;
  state.verify = null;
  state.editingFactId = null;
  state.auditSig = null;
  state.stale = false;
  $('#project-name').value = state.project.name;
  setSaveState('无改动', false);
  $('#demo-confirm').hidden = true;
  $('#btn-demo').hidden = false;
  renderVerdict();
  switchTab('manuscript');
  await runAudit();
  toast('已载入演示数据');
}


// ------------------------------------------------------------------ 本地工作台
// 只显示工作台项目的结果；左侧正文/事实账仍是本地草稿，不混用。


// ------------------------------------------------------------------ AI 起草
// 页面发起的 agent session 会绑定当前项目目录；Node 发起不会。
// 输出只进候选区，采纳后写工作台项目，再跑闸门。

function renderSessionBanner() {
  const banner = $('#session-banner');
  if (!banner) return;
  if (state.hostView === 'conversation') {
    banner.hidden = true;
    return;
  }
  banner.hidden = false;
  if (state.hostView === 'unknown') {
    banner.textContent = '无法确认当前是否从论文对话打开；AI 起草已禁用。请从论文项目的对话里重新打开 MiniFactScribe。';
  } else if (state.hostView !== 'conversation') {
    banner.textContent = '当前不是从论文对话打开的（位置：' + state.hostView + '）。AI 起草会失败；请从论文项目的对话里重新打开 MiniFactScribe。';
  } else if (!state.hostWorkspace) {
    banner.textContent = '当前对话没有项目文件夹。请在该论文项目的对话里打开 MiniFactScribe；工作台也可以手动填 URL + token。';
  } else {
    banner.hidden = true;
  }
}

async function detectHostContext() {
  const host = globalThis.window?.mcode?.miniapp?.host;
  try {
    if (!host?.navigation?.getState) {
      state.hostView = 'unknown';
    } else {
      const info = await host.navigation.getState();
      state.hostView = String(info?.view || 'unknown');
      state.hostKey = String(info?.key || '');
    }
  } catch {
    state.hostView = 'unknown';
    state.hostKey = '';
  }
  try {
    const agent = globalThis.window?.mcode?.miniapp?.agent;
    if (agent?.session && state.hostView === 'conversation') {
      const info = await agent.session();
      state.hostWorkspaceDefault = Boolean(info?.isDefaultWorkspace);
      state.hostWorkspace = state.hostWorkspaceDefault
        ? ''
        : String(info?.workspaceDir || '');
    }
  } catch {
    state.hostWorkspace = '';
    state.hostWorkspaceDefault = false;
  }
  renderSessionBanner();
}

function aiAgent() {
  return globalThis.window?.mcode?.miniapp?.agent || null;
}

function aiReady() {
  return Boolean(aiAgent()?.run && state.workbenchProject &&
    state.hostView === 'conversation');
}

function aiSectionFile() {
  return $('#workbench-section-select')?.value || '';
}

function aiPrompt() {
  const file = aiSectionFile();
  const row = (state.workbenchProject?.sections || []).find((s) => s.file === file);
  const facts = (state.workbenchProject?.facts || []).map((f) =>
    '- ' + f.id + ' | ' + (f.claim || '') + ' | ' + (f.value || '') + ' | ' + (f.source || ''));
  const instruction = $('#ai-instruction').value.trim();
  return [
    '你是论文写作助手，正在帮作者起草或改写一节 LaTeX 正文。',
    '硬约束：正文里的每个数字都必须来自下面的事实账；不得编造数字、引用或实验；',
    '不确定的地方写 TODO，不要猜。只输出完整替换本节的 LaTeX，不要解释。',
    '',
    '当前节：' + file,
    '',
    '用户要求：' + (instruction || '按事实账起草/改写本节。'),
    '',
    '当前正文：',
    row ? row.text : '（空）',
    '',
    '事实账（id | 主张 | 值 | 来源）：',
    facts.length ? facts.join('\n') : '（账里没有事实——不要写任何数字，先提示作者记账）',
  ].join('\n');
}

function aiEvent(kind, text, extra = {}) {
  state.ai.events.push({ kind, text, ...extra });
  if (state.ai.events.length > 80) state.ai.events.shift();
}

function renderAi() {
  const ready = aiReady();
  const hostOk = Boolean(aiAgent()?.run);
  $('#ai-host-status').textContent = !hostOk
    ? '没有宿主 agent'
    : (state.hostView === 'conversation'
      ? '项目对话 · agent 可用'
      : '不是项目对话 · agent 已禁用');
  if (!ready) {
    $('#ai-unavailable').hidden = false;
    $('#ai-unavailable').textContent = !hostOk
      ? '当前页面没有宿主 agent。请从论文项目的对话里打开 MiniFactScribe。'
      : (state.hostView !== 'conversation'
        ? 'AI 起草要求从论文项目的对话里打开本页（当前位置：' + state.hostView + '）。'
        : '先在工作台页签连接本地服务并载入项目。');
  } else {
    $('#ai-unavailable').hidden = true;
  }
  $('#ai-controls').hidden = !ready;
  $('#ai-section-name').textContent = state.workbenchProject
    ? (aiSectionFile() || '（未选节）')
    : '（未载入）';
  $('#btn-ai-run').disabled = !ready || state.ai.streaming;
  $('#btn-ai-stop').disabled = !state.ai.streaming;
  $('#btn-ai-accept').disabled = !state.ai.candidate || state.ai.streaming || Boolean(state.workbenchProject?.read_only);
  $('#ai-state').textContent = state.ai.streaming
    ? '生成中…'
    : (state.ai.candidate ? '候选已生成，等人采纳' : '就绪');
  const box = $('#ai-events');
  box.innerHTML = state.ai.events.map((e) => {
    if (e.kind === 'approval') {
      return '<div class="approval-card"><b>工具等待批准：' + esc(e.toolName || '') + '</b>' +
        (e.reason ? '<div class="muted-note">' + esc(e.reason) + '</div>' : '') +
        (e.toolInput ? '<code>' + esc(String(e.toolInput).slice(0, 500)) + '</code>' : '') +
        '<div class="approval-actions">' +
        '<button class="btn btn-primary" data-ai-approval="' + esc(e.id) + '" data-decision="allowOnce">允许一次</button>' +
        '<button class="btn" data-ai-approval="' + esc(e.id) + '" data-decision="deny">拒绝</button>' +
        '</div></div>';
    }
    const cls = e.kind === 'error' ? 'agent-event error' : e.kind === 'tool' ? 'agent-event tool' : 'agent-event';
    return '<div class="' + cls + '">' + esc(e.text) + '</div>';
  }).join('');
  const candidate = $('#ai-candidate');
  if (candidate.value !== state.ai.candidate) candidate.value = state.ai.candidate;
}

function handleAiEvent(event) {
  if (!event || typeof event !== 'object') return;
  if (event.type === 'text.delta') {
    state.ai.text += event.text || '';
    state.ai.candidate = state.ai.text;
  } else if (event.type === 'message.committed') {
    if (event.text) state.ai.candidate = event.text;
  } else if (event.type === 'tool.started') {
    aiEvent('tool', '调用工具：' + (event.name || ''));
  } else if (event.type === 'tool.finished') {
    aiEvent(event.ok === false ? 'error' : 'tool',
      '工具' + (event.ok === false ? '失败' : '完成') + '：' + (event.name || ''));
  } else if (event.type === 'permission.requested') {
    aiEvent('approval', '', { id: event.requestId, sessionId: event.sessionId,
      toolName: event.toolName, reason: event.reason, toolInput: event.toolInput });
  } else if (event.type === 'question.requested') {
    aiEvent('error', 'Agent 在等问卷；当前页面暂不支持问卷，请改用聊天侧面板回答。');
  } else if (event.type === 'turn.finished') {
    state.ai.streaming = false;
  }
  renderAi();
}

async function runAi() {
  const agent = aiAgent();
  if (!agent?.run) throw new Error('当前页面没有宿主 agent；请从论文项目的对话里打开本页');
  if (!state.workbenchProject) throw new Error('先在工作台页签载入项目');
  const requestId = (globalThis.crypto?.randomUUID?.() || ('ai-' + Date.now() + '-' + Math.random()));
  state.ai = { requestId, streaming: true, sessionId: null, text: '', candidate: '', events: [] };
  renderAi();
  try {
    const result = await agent.run({ text: aiPrompt(), requestId }, { onEvent: handleAiEvent });
    state.ai.streaming = false;
    state.ai.sessionId = result?.sessionId || null;
    if (result?.text) state.ai.candidate = result.text;
    if (result?.error) aiEvent('error', 'Agent 错误：' + result.error);
    if (result?.pendingQuestion) aiEvent('error', 'Agent 在等问卷；请到聊天侧面板回答。');
    renderAi();
  } catch (err) {
    state.ai.streaming = false;
    aiEvent('error', '生成失败：' + (err?.message || err));
    renderAi();
    throw err;
  }
}

function stopAi() {
  const agent = aiAgent();
  if (agent?.cancel && state.ai.requestId) {
    try { agent.cancel(state.ai.requestId); } catch { /* 已结束 */ }
  }
  state.ai.streaming = false;
  aiEvent('error', '已停止');
  renderAi();
}

async function replyAi(event, decision) {
  const agent = aiAgent();
  if (!agent?.reply) throw new Error('当前 agent 不支持审批');
  await agent.reply({ sessionId: event.sessionId, requestId: event.id, decision });
  state.ai.events = state.ai.events.filter((e) => e !== event);
  renderAi();
}

async function acceptAi() {
  if (!state.ai.candidate) throw new Error('还没有候选正文');
  const file = aiSectionFile();
  if (!file) throw new Error('先在工作台页签选一节');
  await api('/api/workbench/sections', {
    method: 'PUT',
    body: JSON.stringify({ file, text: state.ai.candidate }),
  });
  $('#ai-accept-state').textContent = '已写入 ' + file + '，正在重跑审计…';
  toast('已写入 ' + file);
  await loadWorkbenchProject();
  await runWorkbenchAudit();
  $('#ai-accept-state').textContent = '已写入 ' + file + '；审计已重跑';
  state.ai.candidate = '';
  state.ai.text = '';
  renderAi();
}

function renderWorkbench() {
  const w = state.workbench || { configured: false };
  const hostPath = $('#workbench-host-path');
  if (hostPath) {
    hostPath.textContent = state.hostWorkspace
      ? '当前对话项目：' + state.hostWorkspace
      : '当前对话没有项目文件夹（或尚未读取）；可在下面手动填工作台 URL + token。';
  }
  const badge = $('#workbench-badge');
  const summary = $('#workbench-summary');
  if (!badge) return;
  badge.textContent = w.configured ? '已配置' : '未连接';
  $('#workbench-url').value = w.url || '';
  $('#workbench-token').placeholder = w.tokenSet
    ? '已保存（留空不改）'
    : '启动 serve 时打印的 token';
  $('#btn-workbench-disconnect').disabled = !w.configured;
  $('#btn-workbench-audit').disabled = !w.configured;

  if (!w.configured) {
    summary.innerHTML = '<div class="line-empty">未连接。先在本机启动 <code>python3 -m factscribe serve &lt;项目&gt;</code>，把打印的 URL 和 token 填进来。</div>';
    $('#workbench-audit').innerHTML = '';
    return;
  }
  const s = state.workbenchStatus;
  if (!s) {
    summary.innerHTML = '<div class="line-empty">已配置，正在读取工作台状态…</div>';
  } else {
    summary.innerHTML =
      '<div class="verdict-card green">' +
        '<div><div class="verdict-word">工作台</div><div class="verdict-note">Python 引擎</div></div>' +
        '<div class="verdict-note" style="flex:1">' + esc(s.project || '（未命名）') +
          ' · ' + esc(s.facts) + ' 条事实 · ' + esc(s.sections) + ' 个节' +
          '<br><span class="muted-note">' + esc(s.root || '') + '</span></div>' +
      '</div>';
  }

  const project = state.workbenchProject;
  const editor = $('#workbench-editor');
  const select = $('#workbench-section-select');
  editor.hidden = !project;
  if (project) {
    const current = select.value || (project.sections[0] && project.sections[0].file) || '';
    select.innerHTML = project.sections.map((s) =>
      '<option value="' + esc(s.file) + '">' + esc(s.file) + '</option>').join('');
    select.value = project.sections.some((s) => s.file === current)
      ? current
      : (project.sections[0] && project.sections[0].file) || '';
    const row = project.sections.find((s) => s.file === select.value);
    $('#workbench-section-text').value = row ? row.text : '';
    $('#workbench-save-state').textContent = project.read_only
      ? '工作台是只读模式（启动时没加 --allow-write）'
      : '可写';
    $('#btn-workbench-save').disabled = project.read_only;
    $('#workbench-section-text').readOnly = project.read_only;
  } else {
    $('#workbench-save-state').textContent = '';
  }

  const a = state.workbenchAudit;
  if (!a) {
    $('#workbench-audit').innerHTML = '<div class="line-empty">还没有用工作台审计。上面的结果只来自 Python 原版。</div>';
    return;
  }
  const findings = Array.isArray(a.findings) ? a.findings : [];
  const red = findings.filter((f) => f.severity === 'red');
  const yellow = findings.filter((f) => f.severity === 'yellow');
  const verdict = a.exit === 0 ? 'green' : a.exit === 3 ? 'yellow' : 'red';
  const word = { green: '绿', yellow: '黄', red: '红' }[verdict];
  const note = verdict === 'green'
    ? '账有据、据未改、文有绑。它不说明结论为真。'
    : verdict === 'yellow'
      ? '跑完了，但有未核验或未绑定的项——不判死，但必须逐条看过。'
      : '有事实层矛盾：这些数或引用回不到账，必须改。';
  const rows = findings.slice(0, 12).map((f) => {
    const isRed = f.severity === 'red';
    const sev = isRed ? '红牌' : '黄牌';
    const cls = isRed ? 'chip-red' : 'chip-yellow';
    return '<div class="issue">' +
      '<div class="issue-head"><span class="chip ' + cls + '">' + sev + '</span>' +
      '<span class="issue-label">' + esc(ISSUE_LABEL[f.code] || f.code) + '</span>' +
      '<span class="code">' + esc(f.code || '') + '</span>' +
      '<span class="loc">' + esc(f.location || '') + '</span></div>' +
      '<div class="issue-msg">' + esc(f.message || '') + '</div>' +
      '</div>';
  }).join('');
  $('#workbench-audit').innerHTML =
    '<div class="verdict-card ' + verdict + '">' +
      '<div><div class="verdict-word">' + word + '</div><div class="verdict-note">退出码 ' + esc(a.exit) + '</div></div>' +
      '<div class="verdict-note" style="flex:1">' + esc(note) + '</div>' +
    '</div>' +
    '<div class="kpi-row">' +
      kpi(red.length, '红牌 · 必须改', 'bad', null) +
      kpi(yellow.length, '黄牌 · 待人判断', 'warn', null) +
    '</div>' +
    (rows || '<div class="line-empty">没有红黄项。</div>') +
    (findings.length > 12 ? '<div class="muted-note">只显示前 12 条；完整结果看 serve 的 --json 输出。</div>' : '');
}

async function loadWorkbenchProject() {
  state.workbenchProject = await api('/api/workbench/project');
  renderWorkbench();
}

async function saveWorkbenchSection() {
  const project = state.workbenchProject;
  if (!project) throw new Error('先载入工作台项目');
  const file = $('#workbench-section-select').value;
  const text = $('#workbench-section-text').value;
  $('#workbench-save-state').textContent = '保存中…';
  await api('/api/workbench/sections', {
    method: 'PUT',
    body: JSON.stringify({ file, text }),
  });
  $('#workbench-save-state').textContent = '已保存 ' + file;
  await loadWorkbenchProject();
  toast('工作台章节已保存');
}

async function loadWorkbench() {
  try {
    state.workbench = await api('/api/workbench');
  } catch {
    state.workbench = { configured: false };
  }
  renderWorkbench();
}

async function loadWorkbenchStatus() {
  state.workbenchStatus = await api('/api/workbench/status');
  renderWorkbench();
}

async function connectWorkbench() {
  const url = $('#workbench-url').value.trim();
  const token = $('#workbench-token').value.trim();
  $('#workbench-status').textContent = '连接中…';
  const data = await api('/api/workbench', {
    method: 'PUT',
    body: JSON.stringify({ url, token }),
  });
  state.workbench = { configured: true, url: data.url, tokenSet: true };
  state.workbenchAudit = null;
  $('#workbench-status').textContent = '已连接：' + data.url;
  await loadWorkbenchStatus();
  await loadWorkbenchProject();
  toast('已连接本地工作台');
}

async function disconnectWorkbench() {
  await api('/api/workbench', { method: 'DELETE' });
  state.workbench = { configured: false };
  state.workbenchStatus = null;
  state.workbenchAudit = null;
  state.workbenchProject = null;
  $('#workbench-status').textContent = '';
  renderWorkbench();
}

async function runWorkbenchAudit() {
  $('#workbench-status').textContent = '工作台审计中…';
  state.workbenchAudit = await api('/api/workbench/audit', { method: 'POST' });
  $('#workbench-status').textContent = '工作台审计完成';
  renderWorkbench();
}

function wire() {
  for (const btn of $$('.nav-item')) btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  $('#btn-audit').addEventListener('click', () => runAudit());
  $('#btn-rerun').addEventListener('click', () => runAudit());
  $('#btn-workbench-connect').addEventListener('click', () => {
    connectWorkbench().catch((e) => { $('#workbench-status').textContent = '连接失败：' + e.message; toast('连接失败：' + e.message); });
  });
  $('#btn-workbench-disconnect').addEventListener('click', () => {
    disconnectWorkbench().catch((e) => toast('断开失败：' + e.message));
  });
  $('#btn-workbench-audit').addEventListener('click', () => {
    runWorkbenchAudit().catch((e) => { $('#workbench-status').textContent = '审计失败：' + e.message; toast('审计失败：' + e.message); });
  });
  $('#btn-workbench-load').addEventListener('click', () => {
    loadWorkbenchProject().catch((e) => { $('#workbench-status').textContent = '载入失败：' + e.message; });
  });
  $('#btn-workbench-save').addEventListener('click', () => {
    saveWorkbenchSection().catch((e) => { $('#workbench-save-state').textContent = '保存失败：' + e.message; toast('保存失败：' + e.message); });
  });
  $('#btn-ai-run').addEventListener('click', () => {
    runAi().catch((e) => { $('#ai-state').textContent = '失败：' + e.message; toast('AI 起草失败：' + e.message); });
  });
  $('#btn-ai-stop').addEventListener('click', () => stopAi());
  $('#btn-ai-accept').addEventListener('click', () => {
    acceptAi().catch((e) => { $('#ai-accept-state').textContent = '失败：' + e.message; toast('写入失败：' + e.message); });
  });
  $('#ai-events').addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-ai-approval]');
    if (!btn) return;
    const id = btn.dataset.aiApproval;
    const decision = btn.dataset.decision;
    const event = state.ai.events.find((e) => e.kind === 'approval' && e.id === id);
    if (!event) return;
    replyAi(event, decision).catch((e) => toast('审批失败：' + e.message));
  });
  $('#workbench-section-select').addEventListener('change', () => {
    const project = state.workbenchProject;
    const row = project && project.sections.find((s) => s.file === $('#workbench-section-select').value);
    $('#workbench-section-text').value = row ? row.text : '';
    renderAi();
  });

  $('#save-state').addEventListener('click', () => {
    if (state.saveFailed) saveNow();
  });

  // 载入演示数据 = 覆盖当前项目，先确认再执行。
  $('#btn-demo').addEventListener('click', () => {
    const p = state.project || {};
    const hasContent = (p.manuscript || '').trim() || (p.bib || '').trim() || (p.facts || []).length;
    if (!hasContent) {
      loadDemo().catch((e) => toast(e.message));
      return;
    }
    $('#demo-confirm').hidden = false;
    $('#btn-demo').hidden = true;
  });
  $('#btn-demo-cancel').addEventListener('click', () => {
    $('#demo-confirm').hidden = true;
    $('#btn-demo').hidden = false;
  });
  $('#btn-demo-ok').addEventListener('click', () => {
    loadDemo().catch((e) => toast(e.message));
  });

  $('#project-name').addEventListener('input', (e) => {
    state.project.name = e.target.value;
    scheduleSave();
  });

  $('#manuscript-input').addEventListener('input', (e) => {
    state.project.manuscript = e.target.value;
    scheduleSave();
  });

  $('#bib-input').addEventListener('input', (e) => {
    state.project.bib = e.target.value;
    scheduleSave();
  });

  for (const id of ['protect-before', 'protect-after']) {
    $('#' + id).addEventListener('input', (e) => {
      state.project.protect = state.project.protect || { before: '', after: '' };
      state.project.protect[id === 'protect-before' ? 'before' : 'after'] = e.target.value;
      scheduleSave();
    });
  }

  // 事实账：点行或点「编辑」都能编辑
  $('#facts-tbody').addEventListener('click', (e) => {
    const editBtn = e.target.closest('button[data-edit-fact]');
    if (editBtn) {
      state.editingFactId = editBtn.dataset.editFact;
      loadFactForm(state.editingFactId);
      return;
    }
    const tr = e.target.closest('tr[data-fact]');
    if (!tr) return;
    state.editingFactId = tr.dataset.fact;
    loadFactForm(state.editingFactId);
  });

  $('#btn-add-fact').addEventListener('click', () => {
    state.editingFactId = null;
    loadFactForm(null);
    $('#f-id').focus();
  });

  $('#f-source').addEventListener('change', () => loadFactForm(state.editingFactId));

  $('#fact-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const errs = validateFact();
    showFormErrors(errs);
    if (errs.length) {
      const first = $('#' + errs[0].field);
      if (first) first.focus();
      return;
    }
    const id = $('#f-id').value.trim();
    const sourceId = $('#f-source').value;
    const src = (state.project.sources || []).find((s) => s.id === sourceId);
    const facts = state.project.facts || [];
    const existing = facts.find((f) => f.id === id);
    const next = {
      id,
      claim: $('#f-claim').value.trim(),
      value: $('#f-value').value.trim(),
      source: sourceId,
      sourceSha256: src ? src.sha256 : '',
      locator: $('#f-locator').value,
      confidence: $('#f-confidence').value,
      derivedFrom: existing ? existing.derivedFrom : [],
      expr: $('#f-expr').value,
      dupOk: $('#f-dup').checked,
      notes: $('#f-notes').value,
    };
    if (existing) Object.assign(existing, next);
    else facts.push(next);
    state.project.facts = facts;
    state.editingFactId = id;
    scheduleSave();
    renderLedger();
    toast('已保存事实 ' + id);
  });

  // 表单错误摘要：点一条就跳到出问题的字段
  $('#form-errors-list').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-goto]');
    if (!btn) return;
    const input = $('#' + btn.dataset.goto);
    if (input) input.focus();
  });

  // 删除事实：先确认，不弹「Are you sure?」
  $('#btn-delete-fact').addEventListener('click', () => {
    const id = state.editingFactId;
    if (!id) return;
    $('#fact-delete-id').textContent = id;
    $('#fact-delete-confirm').hidden = false;
    $('#btn-delete-fact').hidden = true;
  });
  $('#btn-delete-cancel').addEventListener('click', () => {
    $('#fact-delete-confirm').hidden = true;
    $('#btn-delete-fact').hidden = Boolean(state.editingFactId);
  });
  $('#btn-delete-ok').addEventListener('click', () => {
    const id = state.editingFactId;
    if (!id) return;
    state.project.facts = (state.project.facts || []).filter((f) => f.id !== id);
    state.editingFactId = null;
    scheduleSave();
    renderLedger();
    toast('已删除事实 ' + id);
  });

  // 来源材料
  $('#sources-list').addEventListener('click', async (e) => {
    const cancel = e.target.closest('[data-rehash-cancel]');
    if (cancel) {
      const card = cancel.closest('.source-card');
      const box = card && card.querySelector('[data-rehash-confirm]');
      if (box) box.hidden = true;
      const btn = card && card.querySelector('button[data-rehash]');
      if (btn) btn.hidden = false;
      return;
    }
    const ok = e.target.closest('[data-rehash-ok]');
    if (ok) {
      const src = (state.project.sources || []).find((s) => s.id === ok.dataset.rehashOk);
      if (!src) return;
      const textEl = $('textarea[data-source-text="' + CSS.escape(src.id) + '"]');
      if (textEl) src.text = textEl.value;
      try {
        src.sha256 = await sha256Hex(src.text);
      } catch (err) {
        toast('无法现算哈希：' + err.message);
        return;
      }
      // 账本里引用了这个来源的事实，同步更新它们记录的哈希
      for (const f of state.project.facts || []) {
        if (f.source === src.id) f.sourceSha256 = src.sha256;
      }
      scheduleSave();
      renderLedger();
      toast('来源哈希已更新（账本内引用同步）');
      return;
    }
    const btn = e.target.closest('button[data-rehash]');
    if (btn) {
      const card = btn.closest('.source-card');
      const box = card && card.querySelector('[data-rehash-confirm]');
      if (box) box.hidden = false;
      btn.hidden = true;
    }
  });

  $('#sources-list').addEventListener('input', (e) => {
    const ta = e.target.closest('textarea[data-source-text]');
    if (!ta) return;
    const src = (state.project.sources || []).find((s) => s.id === ta.dataset.sourceText);
    if (!src) return;
    src.text = ta.value;
    scheduleSave();
  });

  // 联网核验
  $('#btn-verify').addEventListener('click', async () => {
    const btn = $('#btn-verify');
    btn.disabled = true;
    btn.textContent = '核验中…';
    try {
      const data = await api('/api/verify', { method: 'POST' });
      state.verify = data.verify;
      if (data.audit) {
        state.audit = data.audit;
        state.auditSig = sigOf(state.project);
      }
      refreshStale();
      renderRefs();
      renderTab();
      toast('核验完成：' + data.verify.results.length + ' 条');
    } catch (err) {
      toast('核验失败：' + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '联网核验存在性';
    }
  });

  // 改写保护
  $('#btn-protect').addEventListener('click', async () => {
    try {
      const data = await api('/api/protect', {
        method: 'POST',
        body: JSON.stringify({ before: state.project.protect?.before || '', after: state.project.protect?.after || '' }),
      });
      const r = data.result;
      const box = $('#protect-result');
      box.innerHTML = r.issues.length
        ? r.issues
            .map(
              (i) =>
                '<div class="protect-row"><b>' + esc(labelOf(i.code)) + '</b> ' + esc(i.message) +
                ' <span class="code">' + esc(i.code) + '</span></div>',
            )
            .join('')
        : '<div class="protect-ok">保护面全绿：六类内容都没变。</div>';
    } catch (err) {
      toast('比对失败：' + err.message);
    }
  });

  // 处方展开
  $('#issues-list').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-pres]');
    if (!btn) return;
    const body = $('[data-pres-body="' + CSS.escape(btn.dataset.pres) + '"]');
    if (body) body.hidden = !body.hidden;
  });

  // 导出
  for (const btn of $$('[data-export]')) {
    btn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/export/' + btn.dataset.export);
        const text = await res.text();
        $('#export-title').textContent = btn.dataset.export;
        $('#export-body').textContent = text;
        $('#export-out').hidden = false;
      } catch (err) {
        toast('导出失败：' + err.message);
      }
    });
  }
  $('#btn-export-close').addEventListener('click', () => {
    $('#export-out').hidden = true;
  });
}

async function init() {
  try {
    const data = await api('/api/state');
    state.project = data.project;
    // 上轮的联网核验结论（服务端已落盘）——刷新后红牌不该静默消失
    state.verify = data.verify || null;
  } catch (err) {
    toast('加载失败：' + err.message);
    return;
  }
  $('#project-name').value = state.project.name;
  setSaveState('无改动', false);
  wire();
  await loadWorkbench();
  renderVerdict();
  switchTab('manuscript');
  await runAudit({ focus: false });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      try {
        localStorage.setItem('minifactscribe.tab', state.tab);
      } catch {
        /* 视图偏好写不进去就算了，不影响数据 */
      }
    }
  });
  try {
    const saved = localStorage.getItem('minifactscribe.tab')
      ?? localStorage.getItem('factgate.tab');
    if (saved) switchTab(saved);
  } catch {
    /* 忽略 */
  }
}

init();
