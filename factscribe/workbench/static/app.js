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
    'hc.h': '体检', 'hc.facts': '{n} 条事实', 'hc.sections': '{m} 节正文',
    'hc.build': '最近编译：{t}', 'hc.nobuild': '尚无编译产物',
    'hc.note': '体检读数来自真闸（factscribe audit）：只读，不改盘。',
    'mv.h': '机器视图', 'mv.sub': '这一层是给工具看的，不是给稿子看的——按主题折叠，点开看细节。',
    'seg3': '检查报告 / 机器视图', 'seg3.note': '段三接入：检查报告、机器视图与体检判定在段三接入。',
    'seg3.note2': '段三接入：机器视图（账本完整性、证据链、原始产物）在段三接入。',
    'seg4': '段四接入：AI 对话（带上下文的提问、建议采纳）在段四接入。',
    /* ---- 段三：检查报告 / 机器视图 ---- */
    'rp.rerun': '重跑检查', 'rp.rerunning': '进行中…',
    'rp.rerunOk': '重跑完成：红 {r} · 黄 {y}（{ms} 毫秒）',
    'rp.rerunErr': '重跑失败：{code} {msg}',
    'rp.ry': '红 {r} · 黄 {y}', 'rp.n': '{n} 条',
    'rp.findings': '发现', 'rp.chain': '四步链',
    'rp.findingsT': '发现明细', 'rp.close': '关闭', 'rp.details': '查看明细 ▸',
    'rp.empty': '没有发现：这盘干净。',
    'rp.idle': '先打开一篇论文。',
    'rp.loading': '读取中…',
    'rp.loadErr': '读检查报告失败：{e}',
    'rp.loadErrM': '读机器视图失败：{e}',
    'rp.digest': '账本指纹', 'rp.numbers': '数字回账', 'rp.cites': '引用', 'rp.pdf': 'PDF',
    'rp.pdfOk': '已核对', 'rp.pdfStale': '已过期', 'rp.pdfNone': '未产出',
    'rp.generated': '体检时间：{t}',
    'rp.roOk': '只读：项目目录零写入',
    'rp.roChanged': '只读：有改动 {files}',
    'rp.stepOk': '就绪', 'rp.stepPartial': '未齐', 'rp.stepMissing': '缺',
    'rp.chainVal': '{v} / {t}',
    'rp.sevRed': '红', 'rp.sevYellow': '黄', 'rp.sevInfo': '提示',
    'mv.ledger': '账本表', 'mv.scan': '正文扫描',
    'mv.evidence': '文献与证据链', 'mv.export': '导出与命令',
    'mv.rows': '{n} 行', 'mv.cov': '覆盖 {n}%', 'mv.sections': '章节', 'mv.coverage': '覆盖率',
    'mv.num': '数字回账', 'mv.unbound': '未绑定', 'mv.unmatched': '未回账',
    'mv.skipped': '跳过注释', 'mv.files': '扫描文件', 'mv.bytes': '{n} 字节',
    'mv.cites': '引用', 'mv.bibEntries': '文献条目', 'mv.bibFiles': '文献文件',
    'mv.bibUnused': '未用条目', 'mv.frozen': '已冻结', 'mv.unfrozen': '未冻结',
    'mv.freezeState': '证据冻结', 'mv.evFp': '证据指纹',
    'mv.entries': '证据条目', 'mv.log': '证据日志', 'mv.cmds': '命令',
    'mv.cmdCount': '{n} 条命令',
    'mv.colId': 'id', 'mv.colClaim': '断言', 'mv.colValue': '值',
    'mv.colConf': '置信', 'mv.colFile': '出处文件', 'mv.colFp': '指纹',
    'mv.none': '（无）',
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
    'hc.note': 'Health figures come from the real gate (factscribe audit): read-only, nothing is written.',
    'mv.h': 'Machine view', 'mv.sub': 'This layer is for tools, not for the manuscript — collapsed by topic.',
    'seg3': 'Check report / machine view', 'seg3.note': 'Stage 3: check report, machine view and health verdicts arrive in stage 3.',
    'seg3.note2': 'Stage 3: machine view (ledger integrity, evidence chain, raw artefacts) arrives in stage 3.',
    'seg4': 'Stage 4: AI chat (questions with context, suggestion adoption) arrives in stage 4.',
    /* ---- stage 3: check report / machine view ---- */
    'rp.rerun': 'Re-run check', 'rp.rerunning': 'Running…',
    'rp.rerunOk': 'Re-run done: {r} red · {y} yellow ({ms} ms)',
    'rp.rerunErr': 'Re-run failed: {code} {msg}',
    'rp.ry': '{r} red · {y} yellow', 'rp.n': '{n}',
    'rp.findings': 'Findings', 'rp.chain': 'Four-step chain',
    'rp.findingsT': 'Finding details', 'rp.close': 'Close', 'rp.details': 'View details ▸',
    'rp.empty': 'No findings — this disk is clean.',
    'rp.idle': 'Open a paper first.',
    'rp.loading': 'Loading…',
    'rp.loadErr': 'Failed to load the check report: {e}',
    'rp.loadErrM': 'Failed to load the machine view: {e}',
    'rp.digest': 'Ledger fingerprint', 'rp.numbers': 'Numbers reconciled',
    'rp.cites': 'Citations', 'rp.pdf': 'PDF',
    'rp.pdfOk': 'verified', 'rp.pdfStale': 'stale', 'rp.pdfNone': 'not built',
    'rp.generated': 'Checked at: {t}',
    'rp.roOk': 'Read-only: zero writes to the project directory',
    'rp.roChanged': 'Read-only: changed {files}',
    'rp.stepOk': 'ready', 'rp.stepPartial': 'partial', 'rp.stepMissing': 'missing',
    'rp.chainVal': '{v} / {t}',
    'rp.sevRed': 'red', 'rp.sevYellow': 'yellow', 'rp.sevInfo': 'info',
    'mv.ledger': 'Ledger', 'mv.scan': 'Body scan',
    'mv.evidence': 'Citations & evidence', 'mv.export': 'Export & commands',
    'mv.rows': '{n} rows', 'mv.cov': '{n}% covered', 'mv.sections': 'Sections', 'mv.coverage': 'Coverage',
    'mv.num': 'Numbers reconciled', 'mv.unbound': 'Unbound', 'mv.unmatched': 'Unmatched',
    'mv.skipped': 'Skipped annotations', 'mv.files': 'Scanned files', 'mv.bytes': '{n} bytes',
    'mv.cites': 'Citations', 'mv.bibEntries': 'Bibliography entries',
    'mv.bibFiles': 'Bibliography files', 'mv.bibUnused': 'Unused keys',
    'mv.frozen': 'frozen', 'mv.unfrozen': 'not frozen',
    'mv.freezeState': 'Evidence freeze', 'mv.evFp': 'Evidence fingerprint',
    'mv.entries': 'Evidence entries', 'mv.log': 'Evidence log', 'mv.cmds': 'Commands',
    'mv.cmdCount': '{n} commands',
    'mv.colId': 'id', 'mv.colClaim': 'Claim', 'mv.colValue': 'Value',
    'mv.colConf': 'Confidence', 'mv.colFile': 'Source file', 'mv.colFp': 'Fingerprint',
    'mv.none': '(none)',
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
  report: null,       // 段三：检查报告数据（/report）
  machine: null,      // 段三：机器视图数据（/machine）
  reportError: '',
  machineError: '',
  reportLoading: false,
  rerun: null,        // 段三：最近一次重跑检查的结果
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
  // 标题分盘取：各盘自己的 main.tex \title（中文盘显示中文标题）。
  // 服务端 meta 是权威（meta.name 就是这个盘自己 main.tex 的 \title）；
  // 绝不退回项目级标题——那是另一盘（可能是另一种语言）的题。
  const diskTitle = (state.meta && state.meta.name) || disk.name || '';
  $('#coverTitle').textContent = diskTitle || disk.id;
  // 副标题＝这个盘自己 \title{…} 里 `\\` 之后那半句（各盘各的）。
  const diskSub = (state.meta && state.meta.subtitle) || '';
  $('#coverSub').textContent = diskSub || t('cover.sub', { disk: disk.id });
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
  const setText = (sel, text) => {
    const el = $(sel);
    if (el) el.textContent = text;
  };
  setText('#stFacts', t('hc.facts', { n: facts }));
  setText('#stSections', t('hc.sections', { m: sections }));
  setText('#stNote', t('hc.note'));
  setText('#seg4Note', t('seg4'));
  // 段三：体检 / 发现 / 四步链 / 机器视图。
  renderReport();
  renderMachine();
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
  // 段三：检查报告与机器视图跟着当前盘走（进哪篇管哪篇）。
  resetReportState();
  state.rerun = null;
  state.reportLoading = true;
  renderStatus();
  await loadReport();
  state.reportLoading = false;
  renderStatus();
}

/* ---------------------------------------------------------------- 段三：检查报告 / 机器视图 */

const CHAIN_KEYS = ['declare', 'bind', 'reconcile', 'certify'];
const CHAIN_STATE_KEY = { ok: 'rp.stepOk', partial: 'rp.stepPartial', missing: 'rp.stepMissing' };

/* 段三的三个接口都跟着当前盘走（进哪篇管哪篇）。 */
function diskApiPath(suffix) {
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return null;
  return `/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/${suffix}`;
}

function reportIdle() {
  return !(state.project && currentDisk());
}

/* 短指纹：正文只显 8 位，完整 sha256 只进 title 属性，绝不当文本渲染。 */
function fpShort(shortValue, fullValue) {
  const s = String(shortValue || '');
  if (s) return s.slice(0, 8);
  const f = String(fullValue || '');
  return f ? f.slice(0, 8) : '';
}

function listJoin(items) {
  const arr = (items || []).map((x) => String(x)).filter((x) => x !== '');
  if (!arr.length) return t('mv.none');
  return arr.join(state.lang === 'en' ? ', ' : '、');
}

function numPair(a, b) {
  return Number(a || 0) + ' / ' + Number(b || 0);
}

function kvRow(key, value, title, mono) {
  const cls = mono ? 'kv-v mono' : 'kv-v';
  const ttl = title ? ` title="${esc(title)}"` : '';
  return `<div class="kv-row"><span class="kv-k">${esc(key)}</span><span class="${cls}"${ttl}>${esc(value)}</span></div>`;
}

function sevClass(sev) {
  if (sev === 'red') return 'red';
  if (sev === 'yellow') return 'yellow';
  return 'info';
}

function sevLabel(sev) {
  if (sev === 'red') return t('rp.sevRed');
  if (sev === 'yellow') return t('rp.sevYellow');
  return t('rp.sevInfo');
}

function pdfStatusText(pdf) {
  if (!pdf || !pdf.checked) return t('rp.pdfNone');
  return pdf.stale ? t('rp.pdfStale') : t('rp.pdfOk');
}

function errorText(payload, fallbackCode) {
  if (!payload) return fallbackCode || '';
  const code = payload.code || fallbackCode || 'ERROR';
  const msg = payload.error || payload.message || '';
  return msg ? code + ' · ' + msg : code;
}

function reportHealth() {
  const report = state.report;
  if (!report || report.ok === false) return null;
  return report.health || {};
}

function reportFindings() {
  const report = state.report;
  if (!report || !Array.isArray(report.findings)) return [];
  return report.findings;
}

/* 换盘时先清干净：别让上一篇的体检数字挂在这一篇上。 */
function resetReportState() {
  state.report = null;
  state.machine = null;
  state.reportError = '';
  state.machineError = '';
}

/* 读检查报告与机器视图：两个 GET 并发，谁失败都不拖垮另一个。 */
async function loadReport() {
  const reportPath = diskApiPath('report');
  const machinePath = diskApiPath('machine');
  if (!reportPath || !machinePath) return;
  resetReportState();
  const [rep, mach] = await Promise.allSettled([getJSON(reportPath), getJSON(machinePath)]);
  if (rep.status === 'fulfilled') {
    state.report = rep.value || null;
    state.reportError = (state.report && state.report.ok === false)
      ? errorText(state.report, 'REPORT_FAILED') : '';
  } else {
    state.report = null;
    state.reportError = (rep.reason && rep.reason.message) || String(rep.reason);
  }
  if (mach.status === 'fulfilled') {
    state.machine = mach.value || null;
    state.machineError = (state.machine && state.machine.ok === false)
      ? errorText(state.machine, 'MACHINE_FAILED') : '';
  } else {
    state.machine = null;
    state.machineError = (mach.reason && mach.reason.message) || String(mach.reason);
  }
}

/* ---------------------------------------------------------------- 检查报告（pane-report） */

function findingRowHtml(f) {
  return `<div class="fp-item">
    <div class="fp-h"><span class="fp-sev ${sevClass(f.severity)}">${esc(sevLabel(f.severity))}</span><span class="fp-code">${esc(f.code || '')}</span></div>
    <div class="fp-msg">${esc(f.message || '')}</div>
    ${f.location ? `<div class="fp-loc">${esc(f.location)}</div>` : ''}
  </div>`;
}

function findingDetailHtml(f) {
  return `<div class="fd-item">
    <div class="fd-h"><span class="fp-sev ${sevClass(f.severity)}">${esc(sevLabel(f.severity))}</span><span class="fp-code">${esc(f.code || '')}</span></div>
    <div class="fd-msg">${esc(f.message || '')}</div>
    <div class="fd-kv"><span class="fd-k">location</span><span class="fd-v">${esc(f.location || '—')}</span></div>
    <div class="fd-kv"><span class="fd-k">token</span><span class="fd-v">${esc(f.token || '—')}</span></div>
    <div class="fd-kv"><span class="fd-k">context</span><span class="fd-v fd-pre">${esc(f.context || '—')}</span></div>
  </div>`;
}

function chainStepHtml(step, index) {
  const st = (step && step.state) || (step && step.ok ? 'ok' : 'partial');
  const cls = st === 'ok' ? 'done' : (st === 'partial' ? 'partial' : 'missing');
  const badgeCls = st === 'ok' ? 'done' : (st === 'partial' ? 'todo' : '');
  const label = (step && (step.label || step.key)) || '';
  const val = t('rp.chainVal', { v: Number((step && step.value) || 0), t: Number((step && step.total) || 0) });
  const detail = (step && step.detail) ? ' · ' + step.detail : '';
  return `<div class="rstep ${cls}">
    <div class="rstep-h"><span class="rstep-no">${index + 1}</span><span>${esc(label)}</span><span class="badge ${badgeCls}">${esc(t(CHAIN_STATE_KEY[st] || 'rp.stepPartial'))}</span></div>
    <div class="rstep-c">${esc(val)}${esc(detail)}</div>
  </div>`;
}

function renderReport() {
  const report = state.report;
  const health = reportHealth();
  const findings = reportFindings();
  const idle = reportIdle();

  /* —— 体检卡 —— */
  const badge = $('#badgeHealth');
  if (badge) {
    if (health) {
      const red = Number(health.red || 0);
      const yellow = Number(health.yellow || 0);
      badge.textContent = t('rp.ry', { r: red, y: yellow });
      badge.className = 'fold-badge ' + (red > 0 ? 'red' : (yellow > 0 ? 'warn' : 'ok'));
    } else {
      badge.textContent = '—';
      badge.className = 'fold-badge';
    }
  }
  const factsEl = $('#stFacts');
  if (factsEl) {
    const n = health ? Number(health.facts || 0) : Number((state.meta && state.meta.facts) || 0);
    factsEl.textContent = t('hc.facts', { n: n });
    factsEl.className = 'st ' + (n > 0 ? 'ok' : 'warn');
  }
  const secEl = $('#stSections');
  if (secEl) {
    const n = health ? Number(health.sections || 0) : Number((state.meta && state.meta.sections) || 0);
    secEl.textContent = t('hc.sections', { m: n });
    secEl.className = 'st ' + (n > 0 ? 'ok' : 'warn');
  }
  const kv = $('#stHealthKv');
  if (kv) {
    if (!health) {
      kv.innerHTML = '';
    } else {
      const nums = health.numbers || {};
      const cites = health.citations || {};
      const pdf = health.pdf || {};
      const rows = [];
      // 账本指纹：正文只显 8 位短码；完整 sha256 只在 title 里。
      rows.push(kvRow(t('rp.digest'), fpShort(health.digest_short, health.digest), health.digest, true));
      rows.push(kvRow(t('rp.numbers'), numPair(nums.numbers_matched, nums.numbers_total)));
      rows.push(kvRow(t('rp.cites'), numPair(cites.cites_unique, cites.bib_entries)));
      if (pdf && pdf.checked) rows.push(kvRow(t('rp.pdf'), pdfStatusText(pdf)));
      kv.innerHTML = rows.join('');
    }
  }
  const noteEl = $('#stNote');
  if (noteEl) {
    if (state.reportError) {
      noteEl.textContent = t('rp.loadErr', { e: state.reportError });
    } else {
      const gen = (report && report.generated_at) || '';
      noteEl.textContent = gen ? t('rp.generated', { t: gen }) + ' · ' + t('hc.note') : t('hc.note');
    }
  }
  const errEl = $('#stRerunErr');
  if (errEl) {
    const rr = state.rerun;
    if (rr && rr.ok === false) {
      errEl.hidden = false;
      errEl.textContent = t('rp.rerunErr', { code: rr.code || 'RERUN_FAILED', msg: rr.error || '' });
    } else {
      errEl.hidden = true;
      errEl.textContent = '';
    }
  }

  /* —— 发现卡 —— */
  const fbadge = $('#badgeFindings');
  if (fbadge) {
    fbadge.textContent = t('rp.n', { n: findings.length });
    const hasRed = findings.some((f) => f.severity === 'red');
    fbadge.className = 'fold-badge ' + (!findings.length ? 'ok' : (hasRed ? 'red' : 'warn'));
  }
  const fbody = $('#bodyFindings');
  if (fbody) {
    let html = '';
    if (idle) {
      html = `<div class="ff-empty">${esc(t('rp.idle'))}</div>`;
    } else if (state.reportLoading) {
      html = `<div class="ff-empty">${esc(t('rp.loading'))}</div>`;
    } else if (state.reportError) {
      html = `<div class="ff-empty">${esc(t('rp.loadErr', { e: state.reportError }))}</div>`;
    } else if (!findings.length) {
      html = `<div class="ff-empty">${esc(t('rp.empty'))}</div>`;
    } else {
      html = '<div class="fp-list">' + findings.map(findingRowHtml).join('') + '</div>';
    }
    if (report && report.ok !== false) {
      html += `<button type="button" class="rp-detail-btn" data-rp-details>${esc(t('rp.details'))}</button>`;
    }
    fbody.innerHTML = html;
    const more = fbody.querySelector('[data-rp-details]');
    if (more) more.addEventListener('click', openFindingsModal);
  }

  /* —— 四步链卡 —— */
  const chain = (report && Array.isArray(report.chain)) ? report.chain.slice() : [];
  chain.sort((a, b) => {
    const ia = CHAIN_KEYS.indexOf(a.key);
    const ib = CHAIN_KEYS.indexOf(b.key);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  const cbadge = $('#badgeChain');
  if (cbadge) {
    const okCount = chain.filter((s) => s.state === 'ok').length;
    cbadge.textContent = okCount + '/' + CHAIN_KEYS.length;
    cbadge.className = 'fold-badge ' + (chain.length && okCount === CHAIN_KEYS.length ? 'ok' : 'warn');
  }
  const cbody = $('#bodyChainSteps');
  if (cbody) {
    if (idle) {
      cbody.innerHTML = `<div class="ff-empty">${esc(t('rp.idle'))}</div>`;
    } else if (state.reportLoading) {
      cbody.innerHTML = `<div class="ff-empty">${esc(t('rp.loading'))}</div>`;
    } else if (!chain.length) {
      cbody.innerHTML = `<div class="ff-empty">${esc(state.reportError ? t('rp.loadErr', { e: state.reportError }) : t('rp.empty'))}</div>`;
    } else {
      cbody.innerHTML = chain.map(chainStepHtml).join('');
    }
  }
}

function openFindingsModal() {
  const findings = reportFindings();
  const body = $('#modalFindingsBody');
  if (body) {
    body.innerHTML = findings.length
      ? findings.map(findingDetailHtml).join('')
      : `<div class="ff-empty">${esc(t('rp.empty'))}</div>`;
  }
  const modal = $('#modalFindings');
  if (modal) modal.hidden = false;
}

/* ---------------------------------------------------------------- 机器视图（pane-machine） */

function machineGroups() {
  const machine = state.machine;
  if (!machine || machine.ok === false || !machine.groups) return null;
  return machine.groups;
}

function machineIdleText() {
  if (reportIdle()) return t('rp.idle');
  if (state.reportLoading) return t('rp.loading');
  if (state.machineError) return t('rp.loadErrM', { e: state.machineError });
  return t('rp.idle');
}

function renderMachine() {
  const groups = machineGroups();
  renderLedgerGroup(groups ? groups.ledger : null);
  renderScanGroup(groups ? groups.scan : null);
  renderEvidenceGroup(groups ? groups.chain : null);
  renderExportGroup(groups ? groups.export : null);
}

/* 账本表：指纹列只显 8 位短码，完整 sha256 只在 title；出处只显文件名，路径在 title。 */
function renderLedgerGroup(ledger) {
  const badge = $('#badgeLedger');
  const body = $('#bodyLedger');
  const rows = (ledger && Array.isArray(ledger.rows)) ? ledger.rows : [];
  const total = (ledger && ledger.total !== undefined) ? Number(ledger.total) : rows.length;
  if (badge) {
    badge.textContent = t('mv.rows', { n: total });
    badge.className = 'acc-badge ' + (total > 0 ? 'ok' : 'warn');
  }
  if (!body) return;
  if (!ledger) {
    body.innerHTML = `<div class="ff-empty">${esc(machineIdleText())}</div>`;
    return;
  }
  const digest = fpShort(ledger.digest_short, '');
  const head = `<div class="kv">${kvRow(t('rp.digest'), digest || '—', '', true)}</div>`;
  if (!rows.length) {
    body.innerHTML = head + `<div class="ff-empty">${esc(t('mv.none'))}</div>`;
    return;
  }
  const trs = rows.map((r) => `<tr>
      <td><code>${esc(r.id || '')}</code></td>
      <td>${esc(r.claim || '')}</td>
      <td><code>${esc(r.value || '')}</code></td>
      <td>${esc(r.confidence || '')}</td>
      <td title="${esc(r.source_path || r.source_file || '')}"><code>${esc(r.source_file || '')}</code></td>
      <td title="${esc(r.fp || '')}"><code>${esc(fpShort(r.fp_short, r.fp))}</code></td>
    </tr>`).join('');
  body.innerHTML = head + `<table class="mt mv-table">
      <thead><tr><th>${esc(t('mv.colId'))}</th><th>${esc(t('mv.colClaim'))}</th><th>${esc(t('mv.colValue'))}</th><th>${esc(t('mv.colConf'))}</th><th>${esc(t('mv.colFile'))}</th><th>${esc(t('mv.colFp'))}</th></tr></thead>
      <tbody>${trs}</tbody></table>`;
}

/* 正文扫描：章节数、数字回账、覆盖率、未绑定/未回账、扫描文件与字节数。 */
function renderScanGroup(scan) {
  const badge = $('#badgeScan');
  const body = $('#bodyScan');
  const pct = scan ? Number(scan.coverage_percent || 0) : 0;
  if (badge) {
    badge.textContent = t('mv.cov', { n: pct });
    badge.className = 'acc-badge ' + (pct >= 100 ? 'ok' : 'warn');
  }
  if (!body) return;
  if (!scan) {
    body.innerHTML = `<div class="ff-empty">${esc(machineIdleText())}</div>`;
    return;
  }
  const rows = [];
  rows.push(kvRow(t('mv.sections'), String(Number(scan.sections || 0))));
  rows.push(kvRow(t('mv.num'), numPair(scan.numbers_matched, scan.numbers_total)));
  rows.push(kvRow(t('mv.coverage'), pct + '%'));
  rows.push(kvRow(t('mv.unbound'), String(Number(scan.numbers_unbound || 0))));
  rows.push(kvRow(t('mv.unmatched'), String(Number(scan.numbers_unmatched || 0))));
  rows.push(kvRow(t('mv.skipped'), String(Number(scan.annotations_skipped || 0))));
  let html = `<div class="kv">${rows.join('')}</div>`;
  const files = Array.isArray(scan.rows) ? scan.rows : [];
  if (files.length) {
    const trs = files.map((f) => `<tr><td><code>${esc(f.name || f.file || '')}</code></td><td class="mv-num">${esc(t('mv.bytes', { n: Number(f.bytes || 0) }))}</td></tr>`).join('');
    html += `<div class="mv-sub-t">${esc(t('mv.files'))}</div><table class="mt mv-table"><tbody>${trs}</tbody></table>`;
  }
  body.innerHTML = html;
}

/* 文献与证据链：引用、文献条目/文件/未用键、证据冻结状态与指纹、证据日志、PDF 状态。 */
function renderEvidenceGroup(chain) {
  const badge = $('#badgeEvidence');
  const body = $('#bodyEvidence');
  const frozen = chain ? !!chain.frozen : false;
  if (badge) {
    badge.textContent = frozen ? t('mv.frozen') : t('mv.unfrozen');
    badge.className = 'acc-badge ' + (frozen ? 'ok' : 'warn');
  }
  if (!body) return;
  if (!chain) {
    body.innerHTML = `<div class="ff-empty">${esc(machineIdleText())}</div>`;
    return;
  }
  const pdf = chain.pdf || {};
  const rows = [];
  rows.push(kvRow(t('mv.cites'), numPair(chain.cites_unique, chain.cites_total)));
  rows.push(kvRow(t('mv.bibEntries'), String(Number(chain.bib_entries || 0))));
  rows.push(kvRow(t('mv.bibFiles'), listJoin(chain.bib_files)));
  rows.push(kvRow(t('mv.bibUnused'), listJoin(chain.bib_unused)));
  rows.push(kvRow(t('mv.freezeState'), frozen ? t('mv.frozen') : t('mv.unfrozen')));
  rows.push(kvRow(t('mv.entries'), String(Number(chain.evidence_entries || 0))));
  // 证据指纹：正文只显 8 位短码；完整 sha256 只在 title。
  rows.push(kvRow(t('mv.evFp'), fpShort(chain.evidence_sha256_short, chain.evidence_sha256), chain.evidence_sha256, true));
  if (pdf && pdf.checked) rows.push(kvRow(t('rp.pdf'), pdfStatusText(pdf)));
  let html = `<div class="kv">${rows.join('')}</div>`;
  const log = Array.isArray(chain.evidence_log) ? chain.evidence_log : [];
  if (log.length) {
    const trs = log.map((e) => `<tr><td>${esc(e.action || '')}</td><td><code>${esc(fpShort(e.hash, ''))}</code></td><td class="mv-num">${esc(String(Number(e.entries || 0)))}</td><td>${esc(e.reason || '')}</td></tr>`).join('');
    html += `<div class="mv-sub-t">${esc(t('mv.log'))}</div><table class="mt mv-table"><thead><tr><th>action</th><th>hash</th><th>entries</th><th>reason</th></tr></thead><tbody>${trs}</tbody></table>`;
  }
  body.innerHTML = html;
}

/* 导出与命令：只列命令与说明，不执行。 */
function renderExportGroup(ex) {
  const badge = $('#badgeExport');
  const body = $('#bodyExport');
  const commands = (ex && Array.isArray(ex.commands)) ? ex.commands : [];
  if (badge) {
    badge.textContent = t('mv.cmdCount', { n: commands.length });
    badge.className = 'acc-badge' + (commands.length ? ' ok' : '');
  }
  if (!body) return;
  if (!ex) {
    body.innerHTML = `<div class="ff-empty">${esc(machineIdleText())}</div>`;
    return;
  }
  let html = '';
  if (commands.length) {
    html = commands.map((c) => `<div class="cmd-row"><span class="cmd-l">${esc(c.label || '')}</span><code class="cmd-c">${esc(c.cmd || '')}</code></div>`).join('');
  } else {
    html = `<div class="ff-empty">${esc(t('mv.none'))}</div>`;
  }
  if (ex.note) html += `<div class="acc-note">${esc(ex.note)}</div>`;
  body.innerHTML = html;
}

/* ---------------------------------------------------------------- 段三：重跑检查（只读） */

function setRerunNote(text, kind) {
  const el = $('#rpRerunNote');
  if (!el) return;
  el.textContent = text || '';
  el.hidden = !text;
  el.className = 'rp-tools-note' + (kind === 'bad' ? ' bad' : (kind === 'ok' ? ' ok' : ''));
}

function readonlyText(ro) {
  if (!ro) return '';
  if (ro.identical) return t('rp.roOk');
  const files = [].concat(ro.changed || [], ro.touched || []);
  return t('rp.roChanged', { files: listJoin(files) });
}

async function rerunCheck() {
  const path = diskApiPath('report/rerun');
  if (!path) return;
  const btn = $('#rpRerun');
  if (btn) btn.disabled = true;
  setRerunNote(t('rp.rerunning'), 'busy');
  const cardErr = $('#stRerunErr');
  if (cardErr) { cardErr.hidden = true; cardErr.textContent = ''; }
  let data = null;
  try {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({}),
    });
    try { data = await res.json(); } catch (err) { data = null; }
    if (!data) data = { ok: false, code: 'HTTP_' + res.status, error: 'HTTP ' + res.status };
  } catch (err) {
    data = { ok: false, code: 'RERUN_FAILED', error: (err && err.message) || String(err) };
  }
  state.rerun = data;
  if (btn) btn.disabled = false;
  if (data.ok) {
    const summary = data.summary || {};
    const red = Number(summary.red || 0);
    const yellow = Number(summary.yellow || 0);
    toast(t('rp.rerunOk', { r: red, y: yellow, ms: Number(data.duration_ms || 0) }));
    setRerunNote(readonlyText(data.readonly), (data.readonly && data.readonly.identical) ? 'ok' : 'bad');
    // 重跑完刷新体检与机器视图（仍然只读）。
    await loadReport();
    renderStatus();
  } else {
    const code = data.code || 'RERUN_FAILED';
    const msg = data.error || data.message || '';
    toast(t('rp.rerunErr', { code: code, msg: msg }));
    setRerunNote(t('rp.rerunErr', { code: code, msg: msg }), 'bad');
    renderReport();
  }
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
  // 段三：切回面板时按当前数据重画（语言切换后也走这条路）。
  if (name === 'report') renderReport();
  if (name === 'machine') renderMachine();
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
  // 段三：检查报告折叠卡（默认全收起）与机器视图手风琴
  $$('.rc-fold-h').forEach((btn) => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.rcard.fold');
      if (card) card.classList.toggle('open');
    });
  });
  $$('.acc-h').forEach((btn) => {
    btn.addEventListener('click', () => {
      const card = btn.closest('.acc-card');
      if (card) card.classList.toggle('on');
    });
  });
  // 段三：重跑检查（只读）+ 发现明细模态框
  $('#rpRerun').addEventListener('click', rerunCheck);
  $('#modalFindingsClose').addEventListener('click', () => { $('#modalFindings').hidden = true; });
  $('#modalFindings').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalFindings') $('#modalFindings').hidden = true;
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Escape') return;
    const modal = $('#modalFindings');
    if (modal && !modal.hidden) modal.hidden = true;
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
