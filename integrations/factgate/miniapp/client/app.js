// 事实闸 · Client
// 呈现与交互；所有写操作走 Node 领域服务，页面不直接落盘。

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const state = { project: null, audit: null, verify: null, tab: 'manuscript', editingFactId: null };

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { 'content-type': 'application/json' }, ...opts });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (!res.ok || data.ok === false) throw new Error(data.error || 'HTTP ' + res.status);
  return data;
}

async function sha256Hex(text) {
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

let saveTimer = null;
function scheduleSave() {
  $('#save-state').textContent = '未保存';
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 600);
}

async function saveNow() {
  $('#save-state').textContent = '保存中…';
  try {
    await api('/api/project', { method: 'PUT', body: JSON.stringify({ project: state.project }) });
    $('#save-state').textContent = '已保存';
  } catch (err) {
    $('#save-state').textContent = '保存失败';
    toast('保存失败：' + err.message);
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
}

// ------------------------------------------------------------------ 顶栏

function renderVerdict() {
  const el = $('#verdict');
  if (!state.audit) {
    el.className = 'verdict verdict-idle';
    el.textContent = '未审计';
    return;
  }
  const a = state.audit;
  const word = { green: '绿', red: '红', yellow: '黄' }[a.verdict];
  el.className = 'verdict verdict-' + a.verdict;
  el.textContent = word + ' · exit ' + a.exitCode;
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
      let title = '已绑定且对得上';
      if (num.crossref) {
        cls = 'mute';
        title = '结构编号，不作数据';
      } else if (hits.some((h) => h.severity === 'red')) {
        cls = 'bad';
        title = hits.find((h) => h.severity === 'red').message;
      } else if (hits.some((h) => h.severity === 'yellow')) {
        cls = 'warn';
        title = hits.find((h) => h.severity === 'yellow').message;
      } else if (!line.bound.length) {
        cls = 'warn';
        title = '没绑定';
      }
      chips.push('<span class="num-chip ' + cls + '" title="' + esc(title) + '">' + esc(num.token) + '</span>');
    }
    const bound = line.bound.length
      ? line.bound.map((id) => '<span class="fact-chip">' + esc(id) + '</span>').join('')
      : '<span class="fact-chip none">未绑定</span>';
    rows.push(
      '<div class="line-row">' +
        '<div class="line-no">L' + line.line + '</div>' +
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
    ? '内联绑定 ' + s.bound + '/' + s.denom + '（' + (s.denom ? Math.round((s.bound / s.denom) * 100) : 0) + '%）'
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

function renderLedger() {
  const facts = state.project.facts || [];
  const tbody = $('#facts-tbody');
  tbody.innerHTML = facts
    .map((f) => {
      const st = factStatus(f.id);
      return (
        '<tr class="clickable" data-fact="' + esc(f.id) + '">' +
          '<td class="mono">' + esc(f.id) + '</td>' +
          '<td>' + esc(f.claim) + '</td>' +
          '<td class="mono">' + esc(f.value) + '</td>' +
          '<td>' + esc(f.source || '—') + '</td>' +
          '<td><span class="status-dot"><span class="dot dot-' + st.cls + '"></span>' + st.text + '</span></td>' +
        '</tr>'
      );
    })
    .join('');

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
      return (
        '<div class="source-card" data-source="' + esc(s.id) + '">' +
          '<div class="source-head">' +
            '<span class="source-id">' + esc(s.name || s.id) + ' <span class="muted-note">（' + esc(s.id) + '，' + usedBy + ' 条事实引用）</span></span>' +
            '<span class="source-actions">' +
              '<span class="hash-note">sha256 ' + esc(String(s.sha256 || '').slice(0, 16)) + '…</span>' +
              '<button class="btn" type="button" data-rehash="' + esc(s.id) + '">更新哈希</button>' +
            '</span>' +
          '</div>' +
          '<textarea class="editor editor-bib" data-source-text="' + esc(s.id) + '" spellcheck="false" aria-label="' + esc(s.id) + ' 内容">' + esc(s.text) + '</textarea>' +
        '</div>'
      );
    })
    .join('') || '<div class="line-empty">还没有来源材料。每条事实都要指到一份来源。</div>';

  loadFactForm(state.editingFactId);
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
  $('#f-dup').checked = f ? Boolean(f.dupOk) : false;
  const src = (state.project.sources || []).find((s) => s.id === (f ? f.source : $('#f-source').value));
  $('#f-hash').textContent = src ? '来源哈希现算：' + String(src.sha256 || '').slice(0, 24) + '…' : '';
  $('#btn-delete-fact').disabled = !f;
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
          '<td>' + r.cited + '</td>' +
          '<td><span class="status-dot" title="' + esc(v?.detail || '') + '"><span class="dot dot-' + st[0] + '"></span>' + st[1] + '</span></td>' +
        '</tr>'
      );
    })
    .join('');
  const note = $('#verify-note');
  if (state.verify) {
    note.textContent =
      '本轮联网核验 ' + state.verify.results.length + ' 条，其中 ' + state.verify.failures + ' 条没核验成（网络/限流），没核验成不等于核验失败。';
  } else {
    note.textContent = '点「联网核验存在性」去 Crossref / arXiv 查这条引用到底存不存在。';
  }
}

// ------------------------------------------------------------------ 改写保护

function renderProtect() {
  $('#protect-before').value = state.project.protect?.before ?? '';
  $('#protect-after').value = state.project.protect?.after ?? '';
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
    '<div class="kpi-row">' +
      kpi(redShown, redShown === redTotal ? '红牌（必须改）' : '红牌 ' + redShown + ' 类 / ' + redTotal + ' 条', 'bad') +
      kpi(yellowShown, yellowShown === yellowTotal ? '黄牌（待人判断）' : '黄牌 ' + yellowShown + ' 类 / ' + yellowTotal + ' 条', 'warn') +
      kpi((state.project.facts || []).length, '账上事实', '') +
      kpi(s.denom ? Math.round((s.bound / s.denom) * 100) + '%' : '—', '内联绑定率', '') +
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
        const sevText = i.severity === 'red' ? '红' : '黄';
        return (
          '<article class="issue">' +
            '<div class="issue-head">' +
              '<span class="chip ' + sev + '">' + sevText + '</span>' +
              '<span class="code">' + esc(i.code) + '</span>' +
              (i.location ? '<span class="loc">' + esc(i.location) + '</span>' : '') +
            '</div>' +
            '<p class="issue-msg">' + esc(i.message) + '</p>' +
            (i.context ? '<p class="issue-ctx">' + esc(i.context) + '</p>' : '') +
            (p
              ? '<button class="link-btn" type="button" data-pres="' + esc(i.code) + '">怎么办？</button>' +
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
  $('#matrix-tables').innerHTML =
    '<div class="ledger-table-wrap"><table class="data-table">' +
      '<caption class="sr-only">事实覆盖矩阵</caption><thead><tr><th scope="col">事实</th><th scope="col">主张</th><th scope="col">值</th><th scope="col">正文位置</th><th scope="col">状态</th></tr></thead><tbody>' +
      m.facts
        .map(
          (r) =>
            '<tr><td class="mono">' + esc(r.id) + '</td><td>' + esc(r.claim) + '</td><td class="mono">' + esc(r.value) +
            '</td><td class="mono">' + esc(r.boundLines.length ? r.boundLines.map((l) => 'L' + l).join(', ') : '—') +
            '</td><td>' + esc(r.usedIn) + '</td></tr>',
        )
        .join('') +
      '</tbody></table></div>';
}

function kpi(value, label, cls) {
  return '<div class="kpi"><div class="kpi-value"' + (cls ? ' style="color:var(--mcode-' + cls + ')"' : '') + '>' + esc(String(value)) + '</div><div class="kpi-label">' + esc(label) + '</div></div>';
}

// ------------------------------------------------------------------ 动作

async function runAudit(opts = {}) {
  const btn = $('#btn-audit');
  btn.disabled = true;
  btn.textContent = '审计中…';
  try {
    const data = await api('/api/audit', { method: 'POST' });
    state.audit = data.audit;
    renderVerdict();
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
  $('#project-name').value = state.project.name;
  renderVerdict();
  switchTab('manuscript');
  await runAudit();
  toast('已载入演示数据');
}

function wire() {
  for (const btn of $$('.nav-item')) btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  $('#btn-audit').addEventListener('click', () => runAudit());
  $('#btn-demo').addEventListener('click', () => loadDemo().catch((e) => toast(e.message)));

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

  // 事实账：点行编辑
  $('#facts-tbody').addEventListener('click', (e) => {
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
    const id = $('#f-id').value.trim();
    if (!id) {
      toast('事实必须有 id');
      return;
    }
    const sourceId = $('#f-source').value;
    const src = (state.project.sources || []).find((s) => s.id === sourceId);
    const facts = state.project.facts || [];
    const existing = facts.find((f) => f.id === id);
    const next = {
      id,
      claim: $('#f-claim').value,
      value: $('#f-value').value,
      source: sourceId,
      sourceSha256: src ? src.sha256 : '',
      locator: $('#f-locator').value,
      confidence: $('#f-confidence').value,
      derivedFrom: existing ? existing.derivedFrom : [],
      expr: $('#f-expr').value,
      dupOk: $('#f-dup').checked,
      notes: existing ? existing.notes : '',
    };
    if (existing) Object.assign(existing, next);
    else facts.push(next);
    state.project.facts = facts;
    state.editingFactId = id;
    scheduleSave();
    renderLedger();
    toast('已保存事实 ' + id);
  });

  $('#btn-delete-fact').addEventListener('click', () => {
    const id = state.editingFactId;
    if (!id) return;
    state.project.facts = (state.project.facts || []).filter((f) => f.id !== id);
    state.editingFactId = null;
    scheduleSave();
    renderLedger();
  });

  // 来源材料
  $('#sources-list').addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-rehash]');
    if (!btn) return;
    const src = (state.project.sources || []).find((s) => s.id === btn.dataset.rehash);
    if (!src) return;
    const textEl = $('textarea[data-source-text="' + CSS.escape(src.id) + '"]');
    if (textEl) src.text = textEl.value;
    src.sha256 = await sha256Hex(src.text);
    // 账本里引用了这个来源的事实，同步更新它们记录的哈希
    for (const f of state.project.facts || []) {
      if (f.source === src.id) f.sourceSha256 = src.sha256;
    }
    scheduleSave();
    renderLedger();
    toast('来源哈希已更新（账本内引用同步）');
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
      if (data.audit) state.audit = data.audit;
      renderVerdict();
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
        ? r.issues.map((i) => '<div class="protect-row"><b>' + esc(i.code) + '</b> ' + esc(i.message) + '</div>').join('')
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
  wire();
  renderVerdict();
  switchTab('manuscript');
  await runAudit({ focus: false });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      try {
        localStorage.setItem('factgate.tab', state.tab);
      } catch {
        /* 视图偏好写不进去就算了，不影响数据 */
      }
    }
  });
  try {
    const saved = localStorage.getItem('factgate.tab');
    if (saved) switchTab(saved);
  } catch {
    /* 忽略 */
  }
}

init();
