/* FactScribe 工作台 · 段二（写回与章节管理）
   交互结构移植自 workbench-redesign/prototype-v4.html；
   段一做只读骨架，段二接上写回（正文就地编辑）与章节管理（调序/删除/新建）。 */
'use strict';

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];

const TOKEN_RE = /\ue000P\d+\ue001/;

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
    'toc.manage': '章节管理', 'toc.new': '＋ 新建章节', 'toc.newT': '新建章节',
    'toc.newTitle': '章节标题', 'toc.newTitlePh': '例如：实验设置',
    'toc.newSlug': '文件名（可空）', 'toc.newSlugPh': 'setup',
    'toc.create': '创建', 'toc.up': '上移', 'toc.down': '下移',
    'toc.del': '删除', 'toc.delAsk': '把这一节挪到 sections/attic/（可恢复）？',
    'toc.done': '目录已更新',
    'edit.hint': '点段落进入编辑；Esc 或点外面保存。',
    'edit.saved': '已保存（原稿留在 .bak）',
    'edit.prot': '锁',
    'pf.title': '论文标题', 'pf.titlePh': '例如：多臂实验台的调度策略',
    'pf.lang': '写作语言', 'pf.langEn': '英文盘', 'pf.langZh': '中文盘',
    'pf.langBoth': '英文盘 + 中文盘',
    'pf.langHint': '建几个盘是创建时定下的重操作，建好后不可改。',
    'pf.slug': '文件夹名', 'pf.slugPh': 'my-new-paper',
    'pf.dir': '项目目录', 'pf.dirPh': 'papers/my-new-paper',
    'pf.dirHint': '项目目录是身份锚：事实账与引用都按路径绑定，改它等于断链，所以只读。',
    'pf.reports': '实验报告目录', 'pf.reportsCustom': '自定义实验报告目录',
    'pf.reportsDefault': '恢复默认',
    'pf.reportsHint': '默认是「〈项目目录〉/reports」，点「自定义」才解锁。',
    'pf.journal': '目标期刊 / 会议', 'pf.template': '参考模板',
    'pf.question': '一句话研究问题',
    'pf.save': '保存', 'pf.cancel': '取消',
    'pf.newTitle': '新建论文项目', 'pf.editTitle': '编辑项目',
    'pf.newSub': '建好之后，这个项目会出现在项目列表里。',
    'pf.editSub': '项目目录与语言盘集合已锁死（条目 24 裁定）；其余字段可改。',
    'pf.created': '已建：{n}',
    'prog.facts': '{b}/{t} 事实已绑',
    'prog.none': '暂无定量事实',
    'time.never': '还没打开过',
    'card.edit': '编辑',
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
    'toc.manage': 'Sections', 'toc.new': '＋ New section', 'toc.newT': 'New section',
    'toc.newTitle': 'Section title', 'toc.newTitlePh': 'e.g. Experimental setup',
    'toc.newSlug': 'File name (optional)', 'toc.newSlugPh': 'setup',
    'toc.create': 'Create', 'toc.up': 'Move up', 'toc.down': 'Move down',
    'toc.del': 'Delete', 'toc.delAsk': 'Move this section to sections/attic/ (reversible)?',
    'toc.done': 'Contents updated',
    'edit.hint': 'Click a paragraph to edit; Esc or click outside to save.',
    'edit.saved': 'Saved (original kept as .bak)',
    'edit.prot': 'locked',
    'pf.title': 'Paper title', 'pf.titlePh': 'e.g. Scheduling policies for multi-arm testbeds',
    'pf.lang': 'Writing language', 'pf.langEn': 'English disk',
    'pf.langZh': 'Chinese disk', 'pf.langBoth': 'English disk + Chinese disk',
    'pf.langHint': 'How many disks exist is fixed at creation time.',
    'pf.slug': 'Folder name', 'pf.slugPh': 'my-new-paper',
    'pf.dir': 'Project directory', 'pf.dirPh': 'papers/my-new-paper',
    'pf.dirHint': 'The project directory is the identity anchor: facts and citations bind to it, so it is read-only.',
    'pf.reports': 'Experiment report directory',
    'pf.reportsCustom': 'Customise report directory',
    'pf.reportsDefault': 'Restore default',
    'pf.reportsHint': 'Defaults to "<project dir>/reports"; unlock to change it.',
    'pf.journal': 'Target journal / conference', 'pf.template': 'Reference template',
    'pf.question': 'Research question in one line',
    'pf.save': 'Save', 'pf.cancel': 'Cancel',
    'pf.newTitle': 'New paper project',
    'pf.editSub': 'Project directory and disk set are locked (item 24); other fields are editable.',
    'pf.newSub': 'Once created, the project shows up in the project list.',
    'pf.created': 'Created: {n}',
    'prog.facts': '{b}/{t} facts bound',
    'prog.none': 'No quantitative facts yet',
    'time.never': 'never opened',
    'card.edit': 'Edit',
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
  editing: null,      // 正在编辑的块 {id, file, host}
  assembly: [],       // main.tex 的装配清单
  form: null,         // 新建/编辑项目表单 {mode, project, disk}
};

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  let data = null;
  try { data = await res.json(); } catch (err) { data = null; }
  if (!res.ok || !data || data.ok === false) {
    const msg = (data && data.error) || ('HTTP ' + res.status);
    throw new Error(msg);
  }
  return data;
}

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
    const disk = project.disks[0] || {};
    const progress = disk.progress || { bound: 0, total: 0, percent: 0 };
    const progText = progress.total
      ? t('prog.facts', { b: progress.bound, t: progress.total })
      : t('prog.none');
    const last = disk.last_opened ? formatTime(disk.last_opened) : t('time.never');
    const row = document.createElement('div');
    row.className = 'pj-row-item';
    row.innerHTML = `
      <span class="pj-r-name">${esc(project.name)}</span>
      <span class="pj-r-disks">${esc(diskSummary(project))}</span>
      <span class="pj-r-prog"><span class="pj-bar"><span class="pj-bar-in" style="width:${progress.percent || 0}%"></span></span><span class="pj-r-time">${esc(progText)}</span></span>
      <span class="pj-r-status"><span class="pj-chip pj-draft">${esc(progText)}</span></span>
      <span class="pj-r-time">${esc(last)}</span>
      <span class="pj-r-actions">
        <button type="button" class="btn-ghost pj-edit" data-edit="${esc(project.id)}">${esc(t('card.edit'))}</button>
        <button type="button" class="btn-primary pj-open" data-open="${esc(project.id)}">${esc(t('card.open'))}</button>
      </span>`;
    list.appendChild(row);
  });
  $$('#pjList [data-open]').forEach((btn) => {
    btn.addEventListener('click', () => openProject(btn.dataset.open));
  });
  $$('#pjList [data-edit]').forEach((btn) => {
    btn.addEventListener('click', () => openForm('edit', btn.dataset.edit));
  });
}

function formatTime(stamp) {
  const date = new Date(stamp);
  if (isNaN(date.getTime())) return stamp;
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
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
        node.dataset.file = block.file || '';
        node.classList.add('editable-para');
        node.addEventListener('click', (ev) => {
          ev.stopPropagation();
          enterEdit(block.id, block.file || '');
        });
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
  // 标题分盘取：各盘自己的 main.tex \title（中文盘显示中文标题）
  $('#coverTitle').textContent = disk.name || state.project.name || disk.id;
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
  await loadAssembly();
  // 记「最近打开」（写进项目配置的 [workbench].last_opened）
  try {
    await postJSON('/api/project/opened', { project: project.id, disk: disk.id });
    const fresh = await getJSON('/api/projects');
    state.projects = fresh.projects || [];
  } catch (err) { /* 记不上不影响使用 */ }
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

/* ---------------------------------------------------------------- 就地编辑 */

function collectPlain(host) {
  /* 把编辑区里的内容还原成「散文 + 占位符」的串（占位符＝保护面芯片）。 */
  let out = '';
  host.childNodes.forEach((node) => {
    if (node.nodeType === 3) { out += node.nodeValue; return; }
    if (node.nodeType !== 1) return;
    if (node.dataset && node.dataset.token) { out += node.dataset.token; return; }
    out += collectPlain(node);
  });
  return out;
}

function buildEditor(model) {
  const host = document.createElement('div');
  host.className = 'editing';
  host.setAttribute('contenteditable', 'true');
  host.setAttribute('spellcheck', 'false');
  const parts = String(model.plain || '').split(/(\ue000P\d+\ue001)/);
  parts.forEach((part) => {
    if (!part) return;
    if (TOKEN_RE.test(part)) {
      const index = part.replace(/\D/g, '');
      const chip = (model.chips || []).find((c) => String(c.i) === index);
      const span = document.createElement('span');
      span.className = 'prot-chip';
      span.setAttribute('contenteditable', 'false');
      span.dataset.token = part;
      span.title = (chip && chip.raw) || '';
      span.textContent = (chip && chip.display) || part;
      host.appendChild(span);
      return;
    }
    host.appendChild(document.createTextNode(part));
  });
  return host;
}

async function enterEdit(blockId, file) {
  if (state.editing) await saveEdit();
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return;
  let model = null;
  try {
    model = await getJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/block/${encodeURIComponent(blockId)}`);
  } catch (err) {
    toast('打不开这一段：' + err.message);
    return;
  }
  if (!model || model.ok === false) {
    toast((model && model.error) || '打不开这一段');
    return;
  }
  const target = document.getElementById(blockId);
  if (!target) return;
  const editor = buildEditor(model);
  target.replaceWith(editor);
  editor.id = blockId;
  state.editing = { id: blockId, file: file || model.file, host: editor };
  editor.focus();
  const range = document.createRange();
  range.selectNodeContents(editor);
  range.collapse(false);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

async function saveEdit() {
  const editing = state.editing;
  if (!editing) return;
  state.editing = null;
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return;
  const text = collectPlain(editing.host);
  try {
    const result = await postJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/edit`, {
      file: editing.file,
      block: editing.id,
      text: text,
    });
    (result.warnings || []).forEach((text) => toast(text));
    toast(t('edit.saved'));
    await loadDisk();
  } catch (err) {
    toast('没保存上：' + err.message);
    await loadDisk();
  }
}

async function cancelEdit() {
  if (!state.editing) return;
  state.editing = null;
  await loadDisk();
}

/* ---------------------------------------------------------------- 章节管理 */

async function loadAssembly() {
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) { state.assembly = []; return; }
  try {
    const data = await getJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/assembly`);
    state.assembly = data.entries || [];
  } catch (err) {
    state.assembly = [];
  }
  renderManageList();
}

function renderManageList() {
  const list = $('#tocManageList');
  if (!list) return;
  list.innerHTML = '';
  state.assembly.forEach((entry, index) => {
    const li = document.createElement('li');
    li.className = 'tm-item';
    li.innerHTML = `
      <span class="tm-t">${esc(entry.title || entry.rel)}</span>
      <span class="tm-f">${esc(entry.rel)}</span>
      <span class="tm-ops">
        <button type="button" class="tm-btn" data-move="up" data-rel="${esc(entry.rel)}" title="${esc(t('toc.up'))}" ${index === 0 ? 'disabled' : ''}>↑</button>
        <button type="button" class="tm-btn" data-move="down" data-rel="${esc(entry.rel)}" title="${esc(t('toc.down'))}" ${index === state.assembly.length - 1 ? 'disabled' : ''}>↓</button>
        <button type="button" class="tm-btn tm-del" data-del="${esc(entry.rel)}" title="${esc(t('toc.del'))}">🗑</button>
      </span>`;
    list.appendChild(li);
  });
  $$('#tocManageList [data-move]').forEach((btn) => {
    btn.addEventListener('click', () => moveSection(btn.dataset.rel, btn.dataset.move));
  });
  $$('#tocManageList [data-del]').forEach((btn) => {
    btn.addEventListener('click', () => deleteSection(btn.dataset.del));
  });
}

async function tocAction(path, body) {
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return null;
  try {
    const result = await postJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/${path}`, body);
    toast(t('toc.done'));
    await loadAssembly();
    await loadDisk();
    return result;
  } catch (err) {
    toast('目录操作失败：' + err.message);
    return null;
  }
}

function moveSection(rel, direction) {
  return tocAction('toc/move', { file: rel, direction: direction });
}

function deleteSection(rel) {
  if (!window.confirm(t('toc.delAsk'))) return;
  return tocAction('toc/delete', { file: rel });
}

function openNewSection() {
  $('#newSecTitle').value = '';
  $('#newSecSlug').value = '';
  $('#modalNew').hidden = false;
  $('#newSecTitle').focus();
}

async function createSection() {
  const title = $('#newSecTitle').value.trim();
  if (!title) { toast(t('toc.newTitle')); return; }
  const slug = $('#newSecSlug').value.trim();
  $('#modalNew').hidden = true;
  await tocAction('toc/create', { title: title, slug: slug });
}

/* ---------------------------------------------------------------- 项目表单 */

function openForm(mode, projectId) {
  const form = { mode: mode, project: projectId || '', disk: '' };
  state.form = form;
  $('#fvTitle').textContent = mode === 'edit' ? t('pf.editTitle') : t('pf.newTitle');
  $('#fvSub').textContent = mode === 'edit' ? t('pf.editSub') : t('pf.newSub');
  $('#pfTitle').value = '';
  $('#pfSlug').value = '';
  $('#pfJournal').value = '';
  $('#pfTemplate').value = '';
  $('#pfQuestion').value = '';
  $('#pfMsg').textContent = '';
  if (mode === 'edit') {
    const project = state.projects.find((p) => p.id === projectId);
    const disk = project && project.disks[0];
    if (!project || !disk) { toast(t('lang.none')); return; }
    form.disk = disk.id;
    $('#pfTitle').value = project.name || '';
    $('#pfSlug').value = disk.id;
    $('#pfSlug').disabled = true;
    $('#pfLang').value = disk.lang === 'zh' ? 'zh' : 'en';
    $('#pfLang').disabled = true;
    $('#pfDir').value = disk.project_dir || disk.id;
    $('#pfDir').readOnly = true;
    $('#pfDirHint').hidden = false;
    const reports = disk.reports_dir || ((disk.project_dir || disk.id) + '/reports');
    $('#pfReports').value = reports;
    $('#pfReports').readOnly = true;
    $('#pfReportsUnlock').hidden = false;
    $('#pfReportsReset').hidden = true;
  } else {
    $('#pfSlug').disabled = false;
    $('#pfLang').disabled = false;
    $('#pfLang').value = 'en';
    $('#pfDir').value = '';
    $('#pfDir').readOnly = false;
    $('#pfReports').value = '';
    $('#pfReports').readOnly = true;
    $('#pfReportsUnlock').hidden = false;
    $('#pfReportsReset').hidden = true;
  }
  setView('form');
}

function syncReportsDefault() {
  const dir = $('#pfDir').value.trim() || $('#pfSlug').value.trim();
  $('#pfReports').value = dir ? dir + '/reports' : '';
}

async function submitForm(event) {
  event.preventDefault();
  const title = $('#pfTitle').value.trim();
  const msg = $('#pfMsg');
  if (!title) { msg.textContent = t('pf.title'); return; }
  const body = {
    title: title,
    langs: [$('#pfLang').value === 'zh' ? 'zh' : 'en'],
    slug: $('#pfSlug').value.trim(),
    project_dir: $('#pfDir').value.trim(),
    reports_dir: $('#pfReports').value.trim(),
    journal: $('#pfJournal').value.trim(),
    template: $('#pfTemplate').value.trim(),
    question: $('#pfQuestion').value.trim(),
  };
  if ($('#pfLang').value === 'both') body.langs = ['en', 'zh'];
  try {
    if (state.form && state.form.mode === 'edit') {
      await postJSON('/api/project/update', {
        project: state.form.project,
        disk: state.form.disk,
        title: title,
        journal: body.journal,
        template: body.template,
        question: body.question,
        reports_dir: body.reports_dir,
      });
    } else {
      await postJSON('/api/project/new', body);
    }
    await loadProjects();
    setView('projects');
    toast(t('pf.created', { n: title }));
  } catch (err) {
    msg.textContent = err.message;
  }
}

/* ---------------------------------------------------------------- 交互 */

function setView(view) {
  document.body.setAttribute('data-view', view);
  if (view === 'projects') {
    $('#tocList').innerHTML = '';
    $('#bodyBlocks').innerHTML = '';
    $('#tocManageList').innerHTML = '';
    state.assembly = [];
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
  // 段二：新建/编辑项目
  $('#goNew').addEventListener('click', () => openForm('new'));
  $('#projectForm').addEventListener('submit', submitForm);
  $('#pfCancel').addEventListener('click', () => setView('projects'));
  $('#pfDir').addEventListener('input', syncReportsDefault);
  $('#pfSlug').addEventListener('input', syncReportsDefault);
  $('#pfReportsUnlock').addEventListener('click', () => {
    $('#pfReports').readOnly = false;
    $('#pfReportsUnlock').hidden = true;
    $('#pfReportsReset').hidden = false;
  });
  $('#pfReportsReset').addEventListener('click', () => {
    syncReportsDefault();
    $('#pfReports').readOnly = true;
    $('#pfReportsUnlock').hidden = false;
    $('#pfReportsReset').hidden = true;
  });
  // 段二：章节管理
  $('#tocNew').addEventListener('click', openNewSection);
  $('#newSecOk').addEventListener('click', createSection);
  $('#newSecCancel').addEventListener('click', () => { $('#modalNew').hidden = true; });
  $('#modalNew').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalNew') $('#modalNew').hidden = true;
  });
  // 段二：编辑态的提交键（Esc / 点外面）
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && state.editing) {
      ev.preventDefault();
      saveEdit();
    }
  });
  document.addEventListener('click', (ev) => {
    if (!state.editing) return;
    if (state.editing.host.contains(ev.target)) return;
    if (ev.target.closest('#tocFloat') || ev.target.closest('.modal')) return;
    saveEdit();
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
