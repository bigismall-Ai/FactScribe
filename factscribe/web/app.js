// FactScribe 本地工作台：只调用本服务 /api/*，不依赖框架。
const $ = (s) => document.querySelector(s);
const state = { project: null, current: null, audit: null, evidence: null, token: '' };

const LABELS = {
  UNMATCHED_NUMBER: '数字回不到账',
  BOUND_MISMATCH: '数字与绑定冲突',
  UNBOUND_NUMBER: '回得到账但没钉住',
  MISSING_CITE: '引用缺 bib 条目',
  BIB_NO_STABLE_ID: '引用缺稳定标识',
  MISSING_SOURCE: '事实缺来源',
  MISSING_SOURCE_FIELD: '事实未填来源字段',
  SOURCE_SHA256_MISMATCH: '来源材料被改过',
  MANIFEST_UNSIGNED: '清单没签字',
  SOURCE_NOT_SIGNED: '来源没进清单',
  UNUSED_BIB: '文献没被引用',
  UNUSED_FACT: '事实没被使用',
  DUPLICATE_VALUE: '同值待判断',
  LOW_BINDING_RATE: '绑定率偏低',
  FIGURE_UNVERIFIED: '图里的数字未核验',
  EVIDENCE_UNFROZEN: '证据清单已解冻',
  EVIDENCE_SET_CHANGED: '证据清单改过没重冻',
};

function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function toast(text) {
  const el = $('#toast');
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 2600);
}

function tokenFromUrl() {
  const url = new URL(location.href);
  const token = url.searchParams.get('token') || '';
  if (token) {
    url.searchParams.delete('token');
    history.replaceState(null, '', url.toString());
  }
  return token || sessionStorage.getItem('factscribe.token') || '';
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.token) headers.Authorization = 'Bearer ' + state.token;
  if (options.body) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { ...options, headers });
  let data = {};
  try { data = await res.json(); } catch { data = {}; }
  if (res.status === 401) {
    $('#token-panel').hidden = false;
    throw new Error('token 不对或缺失');
  }
  if (!res.ok || data.ok === false) {
    const msg = data?.error?.message || data?.error || 'HTTP ' + res.status;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return data;
}

// ------------------------------------------------------------------ 加载

async function load() {
  if (!state.token) {
    $('#token-panel').hidden = false;
    return;
  }
  sessionStorage.setItem('factscribe.token', state.token);
  const project = await api('/api/project');
  state.project = project;
  $('#project').textContent = (project.project || '未命名') + ' · ' +
    project.sections.length + ' 节 · ' + project.facts.length + ' 条事实' +
    (project.read_only ? ' · 只读' : ' · 可写');
  $('#readonly-note').textContent = project.read_only
    ? '只读模式（启动时没加 --allow-write）'
    : '';
  $('#btn-save').disabled = project.read_only;
  $('#section-text').readOnly = project.read_only;
  $('#btn-freeze').disabled = project.read_only;
  $('#btn-unfreeze').disabled = project.read_only;
  renderSections();
  renderFacts();
  const saved = localStorage.getItem('factscribe.section');
  const first = project.sections.find((s) => s.file === saved) || project.sections[0];
  if (first) selectSection(first.file);
  await loadEvidence();
  await runAudit();
}

function renderSections() {
  const list = $('#section-list');
  const sections = state.project?.sections || [];
  $('#section-count').textContent = sections.length + ' 节';
  list.innerHTML = sections.map((s) => {
    const firstLine = (s.text || '').split('\n').find((l) => l.trim()) || '';
    const title = firstLine.replace(/^\\[a-zA-Z]+\*?\{?|\}?$/g, '').slice(0, 40) || s.file;
    return '<button class="section-item" data-file="' + esc(s.file) + '">' +
      esc(s.file) + '<small>' + esc(title) + '</small></button>';
  }).join('');
  for (const btn of list.querySelectorAll('.section-item')) {
    btn.addEventListener('click', () => selectSection(btn.dataset.file));
  }
}

function selectSection(file) {
  const row = (state.project?.sections || []).find((s) => s.file === file);
  if (!row) return;
  state.current = file;
  localStorage.setItem('factscribe.section', file);
  $('#section-title').textContent = file;
  $('#section-text').value = row.text || '';
  for (const btn of document.querySelectorAll('.section-item')) {
    btn.classList.toggle('active', btn.dataset.file === file);
  }
}

// ------------------------------------------------------------------ 保存

async function saveSection() {
  if (!state.current) return;
  const text = $('#section-text').value;
  $('#save-state').textContent = '保存中…';
  const data = await api('/api/sections', {
    method: 'PUT',
    body: JSON.stringify({ file: state.current, text }),
  });
  const row = state.project.sections.find((s) => s.file === state.current);
  if (row) row.text = text;
  $('#save-state').textContent = '已保存 ' + data.file;
  toast('已保存 ' + data.file);
}

// ------------------------------------------------------------------ 审计

function verdictOf(exit) {
  return exit === 0 ? 'green' : exit === 3 ? 'yellow' : 'red';
}

async function runAudit() {
  const audit = await api('/api/audit', { method: 'POST' });
  state.audit = audit;
  const verdict = verdictOf(audit.exit);
  const el = $('#verdict');
  el.className = 'verdict ' + verdict;
  const word = { green: '绿牌', yellow: '黄牌', red: '红牌' }[verdict];
  const red = (audit.findings || []).filter((f) => f.severity === 'red').length;
  const yellow = (audit.findings || []).filter((f) => f.severity === 'yellow').length;
  el.textContent = word + ' · 退出码 ' + audit.exit;
  $('#audit-meta').textContent = red + ' 红 / ' + yellow + ' 黄';
  renderFindings();
}

function renderFindings() {
  const findings = state.audit?.findings || [];
  const box = $('#findings');
  if (!findings.length) {
    box.innerHTML = '<div class="empty">没有红黄项。</div>';
    return;
  }
  box.innerHTML = findings.slice(0, 40).map((f) => {
    const cls = f.severity === 'red' ? 'red' : 'yellow';
    return '<div class="finding"><div class="head">' +
      '<span class="tag ' + cls + '">' + (cls === 'red' ? '红牌' : '黄牌') + '</span>' +
      '<b>' + esc(LABELS[f.code] || f.code) + '</b>' +
      '<span class="code">' + esc(f.code || '') + '</span>' +
      '<span class="code">' + esc(f.location || '') + '</span>' +
      '</div><div class="msg">' + esc(f.message || '') + '</div></div>';
  }).join('') + (findings.length > 40
    ? '<div class="empty">只显示前 40 条。</div>' : '');
}

// ------------------------------------------------------------------ 事实账

function renderFacts() {
  const facts = state.project?.facts || [];
  $('#facts-count').textContent = facts.length + ' 条';
  if (!facts.length) {
    $('#facts-body').innerHTML = '<div class="empty">账里还没有事实。</div>';
    return;
  }
  $('#facts-body').innerHTML = '<table><thead><tr><th>ID</th><th>主张</th><th>值</th><th>来源</th></tr></thead><tbody>' +
    facts.map((f) => '<tr><td>' + esc(f.id) + '</td><td>' + esc(f.claim) +
      '</td><td class="code">' + esc(f.value) + '</td><td class="code">' +
      esc(f.source) + '</td></tr>').join('') + '</tbody></table>';
}

// ------------------------------------------------------------------ 证据

async function loadEvidence() {
  state.evidence = await api('/api/evidence');
  renderEvidence();
}

function renderEvidence() {
  const e = state.evidence || {};
  $('#evidence-meta').textContent = e.lock ? '已冻结' : '未冻结';
  const bits = [];
  if (!e.defined) bits.push('未声明 [evidence]');
  if (e.lock) bits.push('lock ' + esc(String(e.lock.sha256 || '').slice(0, 12)) +
    ' · ' + esc(e.lock.entries) + ' 条');
  if (e.mismatch) bits.push('<span style="color:var(--bad)">清单与冻结件不一致</span>');
  if (e.unfrozen) bits.push('<span style="color:var(--warn)">已解冻：' +
    esc(e.unfrozen.reason || '') + '</span>');
  if (e.log?.action) bits.push('最后动作 ' + esc(e.log.action));
  $('#evidence-body').innerHTML = bits.length
    ? bits.map((b) => '<div class="muted">' + b + '</div>').join('')
    : '<div class="empty">没有冻结记录。</div>';
}

async function freezeEvidence() {
  const reason = prompt('冻结理由（可留空）', '') ?? null;
  if (reason === null) return;
  const data = await api('/api/evidence/freeze', {
    method: 'POST', body: JSON.stringify({ reason }),
  });
  toast('已冻结：' + String(data.sha256 || '').slice(0, 12));
  await loadEvidence();
  await runAudit();
}

async function unfreezeEvidence() {
  const reason = prompt('为什么改证据清单（必填）', '');
  if (!reason || !reason.trim()) {
    toast('解冻必须写理由');
    return;
  }
  await api('/api/evidence/unfreeze', {
    method: 'POST', body: JSON.stringify({ reason: reason.trim() }),
  });
  toast('已解冻；改完记得重新冻结');
  await loadEvidence();
  await runAudit();
}

// ------------------------------------------------------------------ 启动

function wire() {
  $('#btn-audit').addEventListener('click', () => {
    runAudit().catch((e) => toast('审计失败：' + e.message));
  });
  $('#btn-save').addEventListener('click', () => {
    saveSection().catch((e) => { $('#save-state').textContent = '保存失败：' + e.message; toast(e.message); });
  });
  $('#btn-freeze').addEventListener('click', () => {
    freezeEvidence().catch((e) => toast('冻结失败：' + e.message));
  });
  $('#btn-unfreeze').addEventListener('click', () => {
    unfreezeEvidence().catch((e) => toast('解冻失败：' + e.message));
  });
  $('#btn-token').addEventListener('click', () => {
    const token = $('#token-input').value.trim();
    if (!token) return toast('先填 token');
    state.token = token;
    $('#token-panel').hidden = true;
    load().catch((e) => toast('加载失败：' + e.message));
  });
}

state.token = tokenFromUrl();
wire();
load().catch((e) => toast('加载失败：' + e.message));
