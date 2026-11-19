/* FactScribe 工作台 · 段一（骨架 + 真数据只读面）
   交互结构移植自 workbench-redesign/prototype-v4.html；
   本段只实现只读部分，写操作与 AI/检查报告接入留给后续段。 */
'use strict';

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];

const I18N = {
  zh: {
    'nav.projects': '项目管理', 'tb.new': '新建',
    'pg.title': '论文项目', 'pg.sub': '打开一篇论文继续写，或新建一个项目。',
    'pg.searchPh': '搜索项目名…', 'pg.empty': '这个根目录下没有找到论文项目（含 factscribe.toml 的目录）。',
    'card.open': '打开', 'card.status': '状态', 'card.last': '最近打开',
    'card.disks': '盘', 'card.sections': '节', 'card.facts': '事实',
    'status.placeholder': '段二接入', 'time.placeholder': '段二接入',
    'prog.placeholder': '进度占位',
    'toc.h': '目录', 'toc.collapse': '收起目录', 'toc.toggle': '显示/隐藏目录',
    'tab.report': '检查报告', 'tab.machine': '机器视图', 'tab.ai': 'AI 对话',
    'side.reports': '实验报告', 'side.collapse': '收起右栏', 'side.expand': '展开右栏',
    'rp.sideT': '打开实验报告管理',
    'hc.h': '体检', 'hc.facts': '{n} 条事实', 'hc.sections': '{n} 节正文',
    'hc.build': '最近编译：{t}', 'hc.nobuild': '尚无编译产物',
    'hc.note': '段一：状态行只读真实计数；判定与修复动作在段三接入。',
    'mv.h': '机器视图', 'mv.sub': '这一层是给工具看的，不是给稿子看的——按主题折叠，点开看细节。',
    'seg3': '检查报告 / 机器视图', 'seg3.note': '段三接入：检查报告、机器视图与体检判定在段三接入。',
    'seg3.note2': '段三接入：机器视图（账本完整性、证据链、原始产物）在段三接入。',
    'seg4': '段四接入：AI 对话（带上下文的提问、建议采纳）在段四接入。',
    'cover.sub': '盘：{disk}',
    'cover.st': '{n} 条事实 · {m} 节正文',
    'lang.none': '这个项目没有别的语言盘',
    'toast.opened': '已打开：{name}',
    'lang.zh': '中文盘', 'lang.en': '英文盘',
    'disc.zh': '中文盘', 'disc.en': '英文盘',
  },
  en: {
    'nav.projects': 'Projects', 'tb.new': 'New',
    'pg.title': 'Paper projects', 'pg.sub': 'Open a paper to keep writing, or create a new project.',
    'pg.searchPh': 'Search projects…', 'pg.empty': 'No paper project found under this root (a directory with factscribe.toml).',
    'card.open': 'Open', 'card.status': 'Status', 'card.last': 'Last opened',
    'card.disks': 'Disks', 'card.sections': 'sections', 'card.facts': 'facts',
    'status.placeholder': 'stage 2', 'time.placeholder': 'stage 2',
    'prog.placeholder': 'progress placeholder',
    'toc.h': 'Contents', 'toc.collapse': 'Collapse contents', 'toc.toggle': 'Show/hide contents',
    'tab.report': 'Check report', 'tab.machine': 'Machine view', 'tab.ai': 'AI chat',
    'side.reports': 'Reports', 'side.collapse': 'Hide panel', 'side.expand': 'Show panel',
    'rp.sideT': 'Open experiment report manager',
    'hc.h': 'Health', 'hc.facts': '{n} facts', 'hc.sections': '{m} sections',
    'hc.build': 'Last build: {t}', 'hc.nobuild': 'No build artefact yet',
    'hc.note': 'Stage 1: the status line reads real counts; verdicts and repair actions arrive in stage 3.',
    'mv.h': 'Machine view', 'mv.sub': 'This layer is for tools, not for the manuscript — collapsed by topic.',
    'seg3': 'Check report / machine view', 'seg3.note': 'Stage 3: check report, machine view and health verdicts arrive in stage 3.',
    'seg3.note2': 'Stage 3: machine view (ledger integrity, evidence chain, raw artefacts) arrives in stage 3.',
    'seg4': 'Stage 4: AI chat (questions with context, suggestion adoption) arrives in stage 4.',
    'cover.sub': 'Disk: {disk}',
    'cover.st': '{n} facts · {m} sections',
    'lang.none': 'This project has no other language disk',
    'toast.opened': 'Opened: {name}',
    'lang.zh': 'Chinese disk', 'lang.en': 'English disk',
    'disc.zh': 'Chinese disk', 'disc.en': 'English disk',
  },
};

const state = {
  lang: 'zh',
  projects: [],
  project: null,
  disk: null,
  blocks: [],
  meta: null,
  rtab: 'report',
  filter: '',
};

function t(key, vars) {
  const dict = I18N[state.lang] || I18N.zh;
  let text = dict[key] !== undefined ? dict[key] : (I18N.zh[key] !== undefined ? I18N.zh[key] : key);
  if (vars) {
    Object.keys(vars).forEach((name) => {
      text = text.split('{' + name + '}').join(vars[name]);
    });
  }
  return text;
}

function esc(s) {
  return String(s === null || s === undefined ? '' : s)
    .replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function toast(text) {
  const el = $('#toast');
  if (!el) return;
  el.textContent = text;
  el.classList.add('on');
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove('on'), 1900);
}

function applyI18n() {
  document.documentElement.lang = state.lang === 'en' ? 'en' : 'zh-CN';
  $$('[data-i18n]').forEach((el) => { el.textContent = t(el.getAttribute('data-i18n')); });
  $$('[data-i18n-ph]').forEach((el) => { el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph'))); });
  $$('[data-i18n-title]').forEach((el) => { el.setAttribute('title', t(el.getAttribute('data-i18n-title'))); });
  $('#langSeg').querySelectorAll('button').forEach((btn) => {
    btn.classList.toggle('on', btn.dataset.lang === state.lang);
  });
  document.body.classList.toggle('panel-en', state.lang === 'en');
}

async function getJSON(url) {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return res.json();
}

/* ---------------------------------------------------------------- 项目列表 */

function diskSummary(project) {
  return project.disks.map((disk) => {
    const label = disk.lang === 'zh' ? t('disc.zh') : t('disc.en');
    return `${disk.id}（${label}·${disk.sections}${t('card.sections')}·${disk.facts}${t('card.facts')}）`;
  }).join('　');
}

function renderProjects() {
  const list = $('#pjList');
  const empty = $('#pjEmpty');
  const filter = state.filter.trim().toLowerCase();
  const rows = state.projects.filter((project) => {
    if (!filter) return true;
    return (project.name + ' ' + project.id + ' ' + project.disks.map((d) => d.id).join(' '))
      .toLowerCase().includes(filter);
  });
  list.innerHTML = '';
  empty.hidden = rows.length > 0;
  rows.forEach((project) => {
    const row = document.createElement('div');
    row.className = 'pj-row-item';
    row.innerHTML = `
      <span class="pj-r-name">${esc(project.name)}</span>
      <span class="pj-r-disks">${esc(diskSummary(project))}</span>
      <span class="pj-r-prog"><span class="pj-r-time">${esc(t('prog.placeholder'))}</span></span>
      <span class="pj-r-status"><span class="pj-chip pj-draft">${esc(t('status.placeholder'))}</span></span>
      <span class="pj-r-time">${esc(t('time.placeholder'))}</span>
      <span class="pj-r-actions">
        <button type="button" class="btn-primary pj-open" data-open="${esc(project.id)}">${esc(t('card.open'))}</button>
      </span>`;
    list.appendChild(row);
  });
  $$('#pjList [data-open]').forEach((btn) => {
    btn.addEventListener('click', () => openProject(btn.dataset.open));
  });
}

async function loadProjects() {
  try {
    const data = await getJSON('/api/projects');
    state.projects = data.projects || [];
  } catch (err) {
    state.projects = [];
    toast('读取项目失败：' + err.message);
  }
  renderProjects();
}

/* ---------------------------------------------------------------- 工作台 */

function currentDisk() {
  if (!state.project) return null;
  return state.project.disks.find((d) => d.id === state.disk) || state.project.disks[0] || null;
}

function diskLabel(disk) {
  return disk.lang === 'zh' ? t('disc.zh') : t('disc.en');
}

function renderBlocks() {
  const host = $('#bodyBlocks');
  const toc = $('#tocList');
  host.innerHTML = '';
  toc.innerHTML = '';
  const stack = [];
  state.blocks.forEach((block) => {
    if (block.kind === 'section') {
      const section = document.createElement('section');
      section.setAttribute('data-sec', block.id);
      const heading = document.createElement('h2');
      heading.className = 'sec-h';
      heading.id = block.id;
      const cn = document.createElement('span');
      cn.className = 'sec-cn';
      cn.textContent = block.title;
      heading.appendChild(cn);
      if (block.title_en) {
        const en = document.createElement('span');
        en.className = 'sec-en';
        en.textContent = block.title_en;
        heading.appendChild(en);
      }
      section.appendChild(heading);
      host.appendChild(section);
      stack.push({ id: block.id, title: block.title, title_en: block.title_en, level: 1 });
      const li = document.createElement('li');
      li.innerHTML = `<a href="#${esc(block.id)}"><span class="cn">${esc(block.title)}</span>` +
        (block.title_en ? `<span class="en">${esc(block.title_en)}</span>` : '') + '</a>';
      toc.appendChild(li);
    } else if (block.kind === 'subsection') {
      const heading = document.createElement('h3');
      heading.className = 'sub-h';
      heading.id = block.id;
      heading.textContent = block.title;
      host.appendChild(heading);
      const li = document.createElement('li');
      li.innerHTML = `<a href="#${esc(block.id)}"><span class="cn">${esc(block.title)}</span></a>`;
      toc.appendChild(li);
    } else if (block.kind === 'abstract') {
      const box = document.createElement('section');
      box.className = 'abstract';
      box.id = block.id;
      box.innerHTML = `<div class="ab-label">${esc(state.lang === 'en' ? 'Abstract' : '摘要')}</div>`;
      host.appendChild(box);
      const holder = box;
      const para = document.createElement('div');
      para.innerHTML = block.html || '';
      holder.appendChild(para.firstElementChild || document.createTextNode(''));
    } else {
      const holder = document.createElement('div');
      holder.innerHTML = block.html || '';
      const node = holder.firstElementChild;
      if (node) {
        node.id = block.id;
        host.appendChild(node);
      }
    }
  });
  $$('#tocList a').forEach((a) => {
    a.addEventListener('click', (ev) => {
      ev.preventDefault();
      const target = document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)));
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
}

function renderCover() {
  const disk = currentDisk();
  if (!disk) return;
  $('#coverTitle').textContent = state.project.name || disk.name || disk.id;
  $('#coverSub').textContent = t('cover.sub', { disk: disk.id });
  $('#coverSt').textContent = t('cover.st', {
    n: state.meta ? state.meta.facts : disk.facts,
    m: state.meta ? state.meta.sections : disk.sections,
  });
  const langLine = disk.lang === 'zh' ? t('disc.zh') : t('disc.en');
  $('#coverMeta').innerHTML = `${esc(t('card.disks'))}: <b>${esc(disk.id)}</b> · ${esc(langLine)} · ${esc(disk.path)}`;
}

function renderStatus() {
  const facts = state.meta ? state.meta.facts : 0;
  const sections = state.meta ? state.meta.sections : 0;
  $('#stFacts').textContent = t('hc.facts', { n: facts });
  $('#stSections').textContent = t('hc.sections', { m: sections });
  const built = state.meta && state.meta.last_build;
  $('#stBuild').textContent = built ? t('hc.build', { t: built }) : t('hc.nobuild');
  $('#stNote').textContent = t('hc.note');
  $('#seg3Note').textContent = t('seg3.note');
  $('#seg3Note2').textContent = t('seg3.note2');
  $('#seg4Note').textContent = t('seg4');
}

async function openProject(projectId, diskId) {
  const project = state.projects.find((p) => p.id === projectId);
  if (!project) return;
  state.project = project;
  const disk = diskId
    ? project.disks.find((d) => d.id === diskId)
    : (project.disks.find((d) => d.lang === 'en') || project.disks[0]);
  if (!disk) return;
  state.disk = disk.id;
  state.lang = disk.lang === 'zh' ? 'zh' : 'en';
  document.body.setAttribute('data-view', 'workbench');
  applyI18n();
  await loadDisk();
  toast(t('toast.opened', { name: project.name }));
}

async function loadDisk() {
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return;
  try {
    const data = await getJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/sections`);
    state.blocks = data.blocks || [];
  } catch (err) {
    state.blocks = [];
    toast('读取章节失败：' + err.message);
  }
  try {
    state.meta = await getJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/meta`);
  } catch (err) {
    state.meta = null;
  }
  renderCover();
  renderBlocks();
  renderStatus();
}

/* ---------------------------------------------------------------- 交互 */

function setView(view) {
  document.body.setAttribute('data-view', view);
  if (view === 'projects') {
    $('#tocList').innerHTML = '';
    $('#bodyBlocks').innerHTML = '';
  }
}

function switchRtab(name) {
  state.rtab = name;
  $$('.rtab').forEach((btn) => btn.classList.toggle('on', btn.dataset.rtab === name));
  $('#pane-report').classList.toggle('on', name === 'report');
  $('#pane-machine').classList.toggle('on', name === 'machine');
  $('#pane-ai').classList.toggle('on', name === 'ai');
  document.body.classList.toggle('ai-full', name === 'ai');
}

function bind() {
  $('#goProjects').addEventListener('click', () => { setView('projects'); loadProjects(); });
  $('#pjSearch').addEventListener('input', (ev) => {
    state.filter = ev.target.value || '';
    renderProjects();
  });
  $('#langSeg').addEventListener('click', (ev) => {
    const btn = ev.target.closest('button[data-lang]');
    if (!btn) return;
    const lang = btn.dataset.lang;
    if (state.project && document.body.getAttribute('data-view') === 'workbench') {
      const disk = state.project.disks.find((d) => d.lang === lang);
      if (!disk) { toast(t('lang.none')); return; }
      state.lang = lang;
      applyI18n();
      openProject(state.project.id, disk.id);
      return;
    }
    state.lang = lang;
    applyI18n();
    renderProjects();
  });
  $$('.rtab').forEach((btn) => {
    btn.addEventListener('click', () => switchRtab(btn.dataset.rtab));
  });
  $('#tocToggle').addEventListener('click', () => {
    document.body.classList.toggle('toc-hidden');
  });
  $('#tocCollapse').addEventListener('click', () => {
    document.body.classList.add('toc-hidden');
  });
  $('#rcCollapse').addEventListener('click', () => {
    document.body.classList.add('rc-collapsed');
  });
  $('#rcOpen').addEventListener('click', () => {
    document.body.classList.remove('rc-collapsed');
  });
  $('#aiEntry').addEventListener('click', () => switchRtab('ai'));
  $('#aiFab').addEventListener('click', () => switchRtab('ai'));
  $('#rpSideBtn').addEventListener('click', () => {
    toast(t('seg3.note2'));
  });
  window.addEventListener('scroll', () => {
    const doc = document.documentElement;
    const total = doc.scrollHeight - doc.clientHeight;
    const pct = total > 0 ? (doc.scrollTop / total) * 100 : 0;
    const bar = $('#prog');
    if (bar) bar.style.width = Math.min(100, pct) + '%';
  });
}

async function main() {
  bind();
  applyI18n();
  switchRtab('report');
  await loadProjects();
  setView('projects');
}

document.addEventListener('DOMContentLoaded', main);
