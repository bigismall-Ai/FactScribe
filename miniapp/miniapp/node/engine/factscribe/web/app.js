// 事实闸 · Client（网页与 MiniApp 共用）
// 呈现与交互；写操作按当前模式走后端（MiniApp 经 Node，网页直连 Python），
// 页面自己不落盘。判定一律来自 Python 原版，这里只显示。
//
// 呈现层的三条自律（2026-11 改版）：
//   1. 过期就说过期——内容改了、审计没重跑，旧结论不许继续冒充现状。
//   2. 状态不靠颜色单独承载——每个判定都带符号和文字（WCAG 1.4.1）。
//   3. 危险动作先问一句——删章节、冻结证据、导入事实，都是「先确认再执行」。

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// 同一份界面，两种启动方式：
//   宿主里打开（window.mcode.miniapp 存在）＝ MiniApp 面，带 AI 起草、项目启动；
//   浏览器直接打开（factscribe web）＝ 只操作真实论文项目。
// ?dev=1 或 --dev 启动时，网页也把宿主专属的按钮显示出来，方便对照调试。
const MODE = detectMode();

function detectMode() {
  const mini = Boolean(globalThis.window?.mcode?.miniapp);
  const dev = new URLSearchParams(location.search).get('dev') === '1';
  return { mini, dev, showHostUi: mini || dev };
}

/** 工作台接口：MiniApp 走 Node 代理，网页直连 Python。 */
function wb(suffix) {
  return (MODE.mini ? '/api/workbench' : '/api') + suffix;
}

/**
 * 论文里一张图的地址：MiniApp 走 Node 代理，网页直连 Python。
 *
 * 网页这一侧要把 token 带上——<img> 带不了请求头，只能走查询串。
 * MiniApp 的 token 在 Node 那头，页面不用也不该知道。
 */
function assetUrl(path) {
  const rel = String(path || '').trim().replace(/^\.?\//, '');
  let url = wb('/asset') + '?path=' + encodeURIComponent(rel);
  if (!MODE.mini && state.token) url += '&token=' + encodeURIComponent(state.token);
  return url;
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

const state = {
  tab: 'workbench',
  workbench: null,
  workbenchStatus: null,
  workbenchAudit: null,
  workbenchProject: null,
  projects: [],
  projectPath: '',
  // 项目页有两级：'list'（列表）、'new'（新建表单）、'add'（加入已有文件夹）。
  // 地址栏是 #/project、#/project/new、#/project/add。
  projectView: 'list',
  // 手风琴：同一时刻只展开一条（存路径）。projectEdit = 正在编辑的那一条。
  projectOpen: '',
  projectEdit: '',
  // 新建项目页顶部的错误（失败时留在表单里，不跳走）。
  npError: '',
  projectPython: '',
  projectPythonPath: '',
  run: null,
  ai: { requestId: null, streaming: false, sessionId: null, text: '', candidate: '', events: [] },
  hostView: 'unknown',
  hostKey: '',
  hostWorkspace: '',
  hostWorkspaceDefault: false,
  token: '',
  wbEvidence: null,
  wbReports: null,
  wbCitations: null,
  // 引用页当前的过滤：all | no-id | unused
  citeFilter: 'all',
  citeLoading: false,
  wbMode: 'source',
  wbPdfUrl: '',
  // 右栏两个面板互斥：'issues'（要处理的问题）| 'ai'（AI 聊天）。
  wbSide: 'issues',
  // AI 聊天的历史：[{role:'user'|'assistant', text}]，按项目存在本地。
  chat: [],
  // 聊天里等着的工具审批卡（宿主 agent 问要不要放行）。
  chatApprovals: [],
  // 当前聊天历史属于哪个项目（键＝factscribe.chat.<路径>）；换项目才换历史。
  chatKey: null,
  // 当前选中的章节（空＝还没选过）。引导条的第 ① 步就看它。
  currentSection: '',
  // 新手引导：示例论文的路径 + 本次打开后的两个进度标志。
  // edited = 保存过正文或追加过事实；auditedAfterEdit = 之后又重跑过审计。
  guide: { path: '', edited: false, auditedAfterEdit: false },
  // ~/.factscribe 目录（从项目列表接口拿）；示例论文就在它下面。
  factscribeDir: '',
  // 界面偏好：语言与主题。跟项目数据无关，存 localStorage，刷新还在。
  lang: 'zh',
  theme: '',
};

// ------------------------------------------------------------------ 界面语言与主题
// 语言与主题是「这台机器的偏好」，不是项目的一部分：存 localStorage。
// 默认语言中文；默认主题跟随系统（不写 data-theme，用户点过才写死）。
//
// 本步覆盖：导航与页标题、主要按钮、字段标签、表格表头、空状态提示、
// 报告页的状态词、侧栏项目按钮、两个切换按钮本身。
// 不翻译：Python 引擎产出的审计消息与违规码说明、论文正文与项目名；
// 长段说明文字保留中文（那是解释，不是标签）。
//
// 键名用短名（nav.* / page.* / btn.* / field.* / th.* / empty.* / report.* / state.* / prefs.*）。

const I18N = {
  zh: {
    'nav.sections': '章节目录',
    'nav.facts': '工作台事实账',
    'nav.reports': '实验报告',
    'page.workbench': '本地工作台',
    'page.project': '项目',
    'page.projectNew': '新建论文项目',
    'page.ai': 'AI 起草',
    'page.reports': '实验报告',
    'page.citations': '引用',
    'btn.check': '检查',
    'btn.lock': '封存',
    'btn.sign': '签收',
    'btn.import': '导入',
    'btn.saveSection': '保存本节',
    'btn.buildPdf': '编译 PDF',
    'btn.openPdf': '打开 PDF',
    'btn.loadProject': '载入工作台项目',
    'btn.addProject': '加入项目列表',
    'btn.removeProject': '从列表移除',
    'btn.useHostProject': '用当前对话项目',
    'btn.startConnect': '启动并连接',
    'btn.stopWorkbench': '停止工作台',
    'btn.genCandidate': '生成候选',
    'btn.stop': '停止',
    'btn.acceptWrite': '采纳并写入本节',
    'btn.appendFact': '追加事实',
    'btn.newReportTemplate': '新建报告模板',
    'btn.addCitation': '添加引用',
    'btn.delete': '删除',
    'btn.source': '源码',
    'btn.preview': '预览',
    'btn.buildPreview': '编译预览',
    'btn.wbAudit': '用工作台审计',
    'btn.sideIssues': '要处理的问题',
    'btn.sideAi': 'AI 聊天',
    'btn.chatSend': '发送',
    'btn.freeze': '冻结',
    'btn.unfreeze': '解冻',
    'btn.connect': '连接',
    'btn.disconnect': '断开',
    'btn.savePython': '保存解释器设置',
    'btn.cancel': '取消',
    'field.recentProjects': '最近项目',
    'field.projectFolder': '项目文件夹',
    'field.signer': '签收人',
    'field.pickSection': '选择一节',
    'field.report': '报告',
    'th.key': 'Key',
    'th.title': '标题',
    'th.identifier': 'DOI / arXiv',
    'th.citeCount': '引用次数',
    'th.status': '状态',
    'th.action': '操作',
    'cite.filterAll': '全部',
    'cite.filterNoId': '缺标识',
    'cite.filterUnused': '未引用',
    'cite.statusOk': '有标识',
    'cite.statusNoId': '缺 DOI/arXiv',
    'cite.statusBadId': '标识不合法',
    'cite.statusUnused': '未引用',
    'cite.duplicate': '重复 key',
    'cite.summary': '共 {total} 条 · 已用 {used} · 未用 {unused} · 缺标识 {noId} · 重复 {dup} · 文件 {files} 个',
    'cite.fileCount': '{n} 条',
    'cite.empty': '没有参考文献文件（配置 bib 或正文 \\bibliography{}）',
    'cite.needProject': '先载入工作台项目，再看引用。',
    'cite.error': '引用列表读不出来：',
    'cite.none': '没有符合条件的条目。',
    'cite.needKey': '引用 key 不能为空',
    'cite.added': '已添加引用',
    'cite.deleted': '已删除引用',
    'cite.confirmDelete': '删掉这条引用？{key}',
    'empty.noReports': '还没有报告。报告由实验脚本产出（experiments/<实验>/reports/*.report.toml），也可以点右上角「新建报告模板」先生成一份。',
    'empty.noFacts': '账里还没有事实。',
    'empty.noRedYellow': '没有红黄项。',
    'empty.noReportSelected': '先选一份报告。',
    'empty.noReviewCard': '还没有审阅卡：先检查并封存（把哈希钉住）才出卡。',
    'empty.needWorkbenchReports': '先载入工作台项目，再看实验报告。',
    'empty.needWorkbenchCard': '先载入工作台项目，再看审阅卡。',
    'report.final': 'final',
    'report.partial': 'partial',
    'report.superseded': 'superseded',
    'report.unknownStatus': '状态未知',
    'report.locked': '已封存',
    'report.lockStale': '封存已失效',
    'report.unlocked': '未封存',
    'report.signed': '已签收',
    'report.unsigned': '未签收',
    'report.readOnly': '只读',
    'report.newPrompt': '新报告的 id（默认 report-YYYYMMDD）',
    'report.newNeedId': '报告 id 不能为空',
    'report.templateCreated': '模板已建，填好 metrics 后检查/封存/签收',
    'state.actionDone': '{what}完成',
    'prefs.themeLight': '浅',
    'prefs.themeDark': '深',
    'prefs.langZh': '中文',
    'prefs.langEn': 'English',
    'prefs.groupLang': '语言',
    'prefs.groupTheme': '主题',
    'wb.sectionAdd': '新建章节',
    'wb.sectionRename': '改名（不动正文里的引用）',
    'wb.sectionDelete': '删除这一节',
    'wb.readOnly': '只读工作台：写操作需要 --allow-write',
    'ph.claimShort': '一句话说清这条事实',
    'ph.signer': '谁签的（签收必填，工具不替你猜）',
    'token.paste': '粘贴 token',
    'token.need': '需要 token',
    'sidebar.noProject': '未选择项目，点击项目管理选择或新建项目',
    'btn.projectManage': '项目管理',
    'guide.title': '新手引导',
    'guide.desc': '用一份示例论文走一遍：看问题 → 改一个数 → 变绿。不会动你的论文。',
    'guide.bar': '新手引导',
    'guide.step1': '选一节',
    'guide.step2': '看红牌',
    'guide.step3': '报告签收',
    'guide.step4': '导入事实',
    'guide.step5': '红牌清零',
    'guide.hint1': '左边点任意一节开始。',
    'guide.hint2': '看右边「要处理的问题」：47.3 账里没有、ghost2024 不存在。',
    'guide.hint3': '去「实验报告」：检查 → 封存 → 签收（签收人写你的名字）。',
    'guide.hint4': '签收后在报告页点「导入」，账里会多出 guide.guide-1.p95。',
    'guide.hint5': '把正文 47.3 改成 12.5 并写成 12.5\\fact{guide.guide-1.p95}，删掉 ghost2024，再重跑审计；红牌变 0 即完成（黄牌仍要人判断）。',
    'guide.readyMini': '示例已准备好：点「启动并连接」，然后回工作台看红牌。',
    'guide.opened': '已打开示例论文',
    'guide.resetDone': '示例已重置',
    'btn.guideOpen': '打开示例项目',
    'btn.guideOpenExists': '打开示例项目（已存在）',
    'btn.guideReset': '重置示例',
    'btn.guideClose': '关闭引导',
    'btn.newProject': '新建项目',
    'btn.npCreate': '创建',
    'btn.npTabNew': '新建项目',
    'btn.npTabAdd': '加入已有文件夹',
    'btn.npJoin': '加入',
    'page.projectAdd': '加入已有文件夹',
    'np.addDesc': '这个文件夹里要有 factscribe.toml。登记完就能在项目列表里选它。',
    'project.current': '当前',
    'project.listEmpty': '还没有论文项目。',
    'project.actionEdit': '编辑',
    'project.actionDelete': '删除',
    'project.actionLoad': '载入项目',
    'project.actionCopy': '复制路径',
    'project.editName': '名称',
    'project.editDesc': '详情',
    'project.editPath': '路径',
    'project.editSave': '保存',
    'project.editCancel': '取消',
    'project.removed': '已从列表移除（文件夹和正文都没动）',
    'project.copied': '路径已复制',
    'project.copyFailed': '复制不了：请手动选中路径复制',
    'np.creating': '创建中…',
    'np.created': '已创建：{name}',
  },
  en: {
    'nav.sections': 'Sections',
    'nav.facts': 'Workbench ledger',
    'nav.reports': 'Experiment reports',
    'page.workbench': 'Local workbench',
    'page.project': 'Project',
    'page.projectNew': 'New project',
    'page.ai': 'AI draft',
    'page.reports': 'Experiment reports',
    'page.citations': 'Citations',
    'btn.check': 'Check',
    'btn.lock': 'Lock',
    'btn.sign': 'Sign',
    'btn.import': 'Import',
    'btn.saveSection': 'Save section',
    'btn.buildPdf': 'Build PDF',
    'btn.openPdf': 'Open PDF',
    'btn.loadProject': 'Load workbench project',
    'btn.addProject': 'Add to project list',
    'btn.removeProject': 'Remove from list',
    'btn.useHostProject': 'Use current chat project',
    'btn.startConnect': 'Start and connect',
    'btn.stopWorkbench': 'Stop workbench',
    'btn.genCandidate': 'Generate draft',
    'btn.stop': 'Stop',
    'btn.acceptWrite': 'Accept and write to section',
    'btn.appendFact': 'Append fact',
    'btn.newReportTemplate': 'New report template',
    'btn.addCitation': 'Add citation',
    'btn.delete': 'Delete',
    'btn.source': 'Source',
    'btn.preview': 'Preview',
    'btn.buildPreview': 'Build preview',
    'btn.wbAudit': 'Audit with workbench',
    'btn.sideIssues': 'Issues to fix',
    'btn.sideAi': 'AI chat',
    'btn.chatSend': 'Send',
    'btn.freeze': 'Freeze',
    'btn.unfreeze': 'Unfreeze',
    'btn.connect': 'Connect',
    'btn.disconnect': 'Disconnect',
    'btn.savePython': 'Save interpreter settings',
    'btn.cancel': 'Cancel',
    'field.recentProjects': 'Recent projects',
    'field.projectFolder': 'Project folder',
    'field.signer': 'Signed by',
    'field.pickSection': 'Pick a section',
    'field.report': 'Report',
    'th.key': 'Key',
    'th.title': 'Title',
    'th.identifier': 'DOI / arXiv',
    'th.citeCount': 'Cites',
    'th.status': 'Status',
    'th.action': 'Action',
    'cite.filterAll': 'All',
    'cite.filterNoId': 'Missing id',
    'cite.filterUnused': 'Unused',
    'cite.statusOk': 'Has id',
    'cite.statusNoId': 'Missing DOI/arXiv',
    'cite.statusBadId': 'Invalid id',
    'cite.statusUnused': 'Unused',
    'cite.duplicate': 'duplicate key',
    'cite.summary': '{total} entries · {used} used · {unused} unused · {noId} missing id · {dup} duplicate · {files} files',
    'cite.fileCount': '{n} entries',
    'cite.empty': 'No reference file (config bib or \\bibliography{} in the text)',
    'cite.needProject': 'Load a workbench project first, then open citations.',
    'cite.error': 'Cannot read the citation list: ',
    'cite.none': 'No entry matches this filter.',
    'cite.needKey': 'Citation key is required',
    'cite.added': 'Citation added',
    'cite.deleted': 'Citation deleted',
    'cite.confirmDelete': 'Delete this citation? {key}',
    'empty.noReports': 'No reports yet. Reports come from experiment scripts (experiments/<experiment>/reports/*.report.toml), or click "New report template" at the top right to make one.',
    'empty.noFacts': 'No facts in the ledger yet.',
    'empty.noRedYellow': 'No red or yellow items.',
    'empty.noReportSelected': 'Pick a report first.',
    'empty.noReviewCard': 'No review card yet: run Check and Lock first.',
    'empty.needWorkbenchReports': 'Load a workbench project first, then open reports.',
    'empty.needWorkbenchCard': 'Load a workbench project first, then open the review card.',
    'report.final': 'Final',
    'report.partial': 'Partial',
    'report.superseded': 'Superseded',
    'report.unknownStatus': 'Unknown status',
    'report.locked': 'Locked',
    'report.lockStale': 'Lock expired',
    'report.unlocked': 'Not locked',
    'report.signed': 'Signed',
    'report.unsigned': 'Not signed',
    'report.readOnly': 'Read-only',
    'report.newPrompt': 'Id for the new report (default report-YYYYMMDD)',
    'report.newNeedId': 'Report id cannot be empty',
    'report.templateCreated': 'Template created — fill in the metrics, then check / lock / sign',
    'state.actionDone': '{what} done',
    'prefs.themeLight': 'Light',
    'prefs.themeDark': 'Dark',
    'prefs.langZh': 'Chinese',
    'prefs.langEn': 'English',
    'prefs.groupLang': 'Language',
    'prefs.groupTheme': 'Theme',
    'wb.sectionAdd': 'New section',
    'wb.sectionRename': 'Rename (leaves \\input references alone)',
    'wb.sectionDelete': 'Delete this section',
    'wb.readOnly': 'Read-only workbench: writes need --allow-write',
    'ph.claimShort': 'Say in one line what this fact claims',
    'ph.signer': 'Who signed it (required for sign-off)',
    'token.paste': 'Paste token',
    'token.need': 'Token required',
    'sidebar.noProject': 'No project selected — pick or create one in Project Management',
    'btn.projectManage': 'Project Management',
    'guide.title': 'Getting started',
    'guide.desc': 'Walk one sample paper end to end: see the issues → change one number → go green. Your own paper is untouched.',
    'guide.bar': 'Getting started',
    'guide.step1': 'Pick a section',
    'guide.step2': 'See the red flags',
    'guide.step3': 'Sign the report',
    'guide.step4': 'Import facts',
    'guide.step5': 'No red flags',
    'guide.hint1': 'Pick any section on the left to start.',
    'guide.hint2': 'Look at the issues on the right: 47.3 is not in the ledger and ghost2024 does not exist.',
    'guide.hint3': 'Open Experiment reports: check -> lock -> sign (type your name).',
    'guide.hint4': 'After signing, click Import; a new fact guide.guide-1.p95 appears.',
    'guide.hint5': 'Change 47.3 to 12.5 and bind it as 12.5\\fact{guide.guide-1.p95}, remove ghost2024, then re-run the audit; zero red flags finishes the guide (yellows still need a human).',
    'guide.readyMini': 'Sample is ready: click “Start and connect”, then open the workbench.',
    'guide.opened': 'Sample paper opened',
    'guide.resetDone': 'Sample reset',
    'btn.guideOpen': 'Open the sample project',
    'btn.guideOpenExists': 'Open the sample project (already there)',
    'btn.guideReset': 'Reset the sample',
    'btn.guideClose': 'Close the guide',
    'btn.newProject': 'New project',
    'btn.npCreate': 'Create',
    'btn.npTabNew': 'New project',
    'btn.npTabAdd': 'Add existing folder',
    'btn.npJoin': 'Add',
    'page.projectAdd': 'Add existing folder',
    'np.addDesc': 'The folder must contain factscribe.toml. Once registered you can pick it in the project list.',
    'project.current': 'Current',
    'project.listEmpty': 'No project yet.',
    'project.actionEdit': 'Edit',
    'project.actionDelete': 'Delete',
    'project.actionLoad': 'Load project',
    'project.actionCopy': 'Copy path',
    'project.editName': 'Name',
    'project.editDesc': 'Description',
    'project.editPath': 'Path',
    'project.editSave': 'Save',
    'project.editCancel': 'Cancel',
    'project.removed': 'Removed from the list (the folder and its files are untouched)',
    'project.copied': 'Path copied',
    'project.copyFailed': 'Could not copy: select the path and copy it by hand',
    'np.creating': 'Creating…',
    'np.created': 'Created: {name}',
  },
};

/** 中文原文 → 字典键。JS 生成的文案按中文原文查表，两套语言都对得上。 */
const I18N_KEYS = {
  '状态未知': 'report.unknownStatus',
  '已封存': 'report.locked',
  '封存已失效': 'report.lockStale',
  '未封存': 'report.unlocked',
  '已签收': 'report.signed',
  '未签收': 'report.unsigned',
  '只读': 'report.readOnly',
  '还没有报告。报告由实验脚本产出（experiments/<实验>/reports/*.report.toml），也可以点右上角「新建报告模板」先生成一份。': 'empty.noReports',
  '账里还没有事实。': 'empty.noFacts',
  '没有红黄项。': 'empty.noRedYellow',
  '先选一份报告。': 'empty.noReportSelected',
  '还没有审阅卡：先检查并封存（把哈希钉住）才出卡。': 'empty.noReviewCard',
  '先载入工作台项目，再看实验报告。': 'empty.needWorkbenchReports',
  '先载入工作台项目，再看审阅卡。': 'empty.needWorkbenchCard',
  '检查': 'btn.check',
  '封存': 'btn.lock',
  '签收': 'btn.sign',
  '导入': 'btn.import',
  '未选择': 'sidebar.noProject',
};

const has = (obj, key) => Object.prototype.hasOwnProperty.call(obj, key);

/** 取当前语言的文案：字典没有就退回中文，再没有就用调用方给的兜底。 */
function t(key, fallback) {
  if (!key) return fallback ?? '';
  const dict = I18N[state.lang] || I18N.zh;
  if (has(dict, key)) return dict[key];
  if (has(I18N.zh, key)) return I18N.zh[key];
  return fallback ?? key;
}

/** 按中文原文取文案：查不到映射就原样返回中文（总比空白强）。 */
function tz(zh) {
  const key = I18N_KEYS[zh];
  return key ? t(key, zh) : zh;
}

/** 带占位符的文案：{n} 这类换成实数。 */
function tf(key, vars) {
  return t(key).replace(/\{(\w+)\}/g, (m, k) => (vars && has(vars, k) ? String(vars[k]) : m));
}

// ------------------------------------------------- 语言 / 主题的开关（侧栏底部）

/** 扫一遍 DOM 里的静态标记：data-i18n / data-i18n-title / data-i18n-placeholder。 */
function applyLangDom() {
  for (const el of $$('[data-i18n]')) {
    const key = el.getAttribute('data-i18n');
    if (key) el.textContent = t(key, el.textContent);
  }
  for (const el of $$('[data-i18n-title]')) {
    const key = el.getAttribute('data-i18n-title');
    if (key) el.title = t(key, el.title);
  }
  for (const el of $$('[data-i18n-placeholder]')) {
    const key = el.getAttribute('data-i18n-placeholder');
    if (key) el.placeholder = t(key, el.getAttribute('placeholder') || '');
  }
  syncLangButtons();
}

/** 切语言：静态文案扫一遍，JS 生成的文案靠重渲染当前页跟上。 */
function applyLang() {
  document.documentElement.lang = state.lang === 'en' ? 'en' : 'zh-CN';
  applyLangDom();
  renderTab();
  updateTitle();
}

/** 换语言并记住：刷新后还在。 */
function setLang(lang) {
  const next = lang === 'en' ? 'en' : 'zh';
  if (state.lang === next) return;
  state.lang = next;
  try {
    localStorage.setItem('factscribe.lang', next);
  } catch {
    /* 隐私模式下写不进去就算了，界面照常用 */
  }
  applyLang();
}

/** 主题：写了 data-theme 就写死；不写就跟随系统（默认状态）。 */
function applyTheme(theme) {
  const next = theme === 'light' || theme === 'dark' ? theme : '';
  state.theme = next;
  if (next) document.documentElement.dataset.theme = next;
  else delete document.documentElement.dataset.theme;
  try {
    if (next) localStorage.setItem('factscribe.theme', next);
    else localStorage.removeItem('factscribe.theme');
  } catch {
    /* 写不进去就算了，主题仍然生效，只是刷新后不记得 */
  }
  syncThemeButtons();
}

/** 当前实际生效的主题：用户选过就用用户的，没选就跟系统。 */
function effectiveTheme() {
  if (state.theme) return state.theme;
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

function syncThemeButtons() {
  const eff = effectiveTheme();
  for (const [id, theme] of [['#btn-theme-light', 'light'], ['#btn-theme-dark', 'dark']]) {
    const btn = $(id);
    if (!btn) continue;
    const on = eff === theme;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-pressed', String(on));
  }
}

function syncLangButtons() {
  for (const [id, lang] of [['#btn-lang-zh', 'zh'], ['#btn-lang-en', 'en']]) {
    const btn = $(id);
    if (!btn) continue;
    const on = state.lang === lang;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-pressed', String(on));
  }
}

/** 读回上次的语言与主题：刷新后还在。 */
function initPrefs() {
  let lang = '';
  let theme = '';
  try {
    lang = localStorage.getItem('factscribe.lang') || '';
    theme = localStorage.getItem('factscribe.theme') || '';
  } catch {
    /* 读不到就用默认值 */
  }
  state.lang = lang === 'en' ? 'en' : 'zh';
  applyTheme(theme === 'light' || theme === 'dark' ? theme : '');
  document.documentElement.lang = state.lang === 'en' ? 'en' : 'zh-CN';
  applyLangDom();
  // 跟随系统时，系统配色变了高亮的那一格也要跟着换。
  try {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => { if (!state.theme) syncThemeButtons(); };
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else if (mq.addListener) mq.addListener(onChange);
  } catch {
    /* 老浏览器没有 matchMedia：不影响使用 */
  }
}


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
  REPORT_MISSING: '报告找不到',
  REPORT_METRIC_MISSING: '报告里没有这个指标',
  REPORT_NOT_SIGNED: '报告没签收',
  REPORT_METRIC_MISMATCH: '值与报告对不上',
  REPORT_SOURCE_MISMATCH: '来源不是报告里的那份',
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

async function api(path, opts = {}) {
  const headers = { 'content-type': 'application/json', ...(opts.headers || {}) };
  if (!MODE.mini && state.token) headers.Authorization = 'Bearer ' + state.token;
  const res = await fetch(path, { ...opts, headers });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (res.status === 401) {
    showTokenPanel();
    throw new Error('token 不对或缺失');
  }
  if (!res.ok || data.ok === false) {
    const message = data?.error?.message || data?.error || 'HTTP ' + res.status;
    throw new Error(typeof message === 'string' ? message : JSON.stringify(message));
  }
  return data;
}

function showTokenPanel() {
  const panel = $('#token-panel');
  if (panel) panel.hidden = false;
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

// ------------------------------------------------------------------ 页面路由
// 同一份 HTML 切成多个页面，靠地址栏的 hash 认页（#/workbench、#/reports、#/project）。
// 前进/后退能用，是因为切页时写的是 location.hash（会压一条历史），不是 replaceState。
// 递归防护：自己写 hash 会触发 hashchange，用 suppressHash 标一下，别又切回去。

// 页名 → 字典键（文案在 I18N 里，中英各一套）。
const PAGE_LABEL = {
  workbench: 'page.workbench',
  facts: 'nav.facts',
  reports: 'page.reports',
  citations: 'page.citations',
  project: 'page.project',
  ai: 'page.ai',
};

const ALL_PAGES = Object.keys(PAGE_LABEL);

// 允许的页就这六个：工作台、工作台事实账、实验报告、引用、项目、AI 起草。
// 工作台本身没有导航项——章节才是入口；项目视图只由侧栏顶部按钮进入。
// AI 起草是宿主专属：网页里没有宿主 agent，页面会自己说清为什么不能起草。

/** 启动落在哪一页：项目管理——一个文件夹就是一个项目，先选项目再干活。 */
function defaultPage() {
  return 'project';
}

/** 地址栏里的 hash → 页名；不认识就是空。 */
function pageFromHash() {
  const raw = String(location.hash || '').replace(/^#\/?/, '');
  if (raw === 'project/new' || raw === 'project/add') {
    return raw;
  }
  // 项目的其它子路由不认：回项目列表页（非法子路由不许停在空白面板上）。
  if (raw.startsWith('project/')) {
    return 'project';
  }
  return ALL_PAGES.includes(raw) ? raw : '';
}

/** 面板 id：新建与「加入已有文件夹」共用新建页那个面板（里面是两个页签）。 */
function panelIdFor(tab) {
  return (tab === 'project/new' || tab === 'project/add')
    ? 'panel-project-new'
    : 'panel-' + tab;
}

let suppressHash = false;

/** 切页后同步地址栏：写 hash 而不是 replaceState，这样浏览器前进/后退才有得退。 */
function writeHash(tab, replace) {
  const next = '#/' + tab;
  if (location.hash === next) return;
  if (replace) {
    history.replaceState(null, '', next);
    return;
  }
  suppressHash = true;
  location.hash = next;
}

/** 标题跟着当前页与项目走：工作台 · 论文名 */
function updateTitle() {
  const pageKey = state.tab === 'project' && state.projectView === 'new'
    ? 'page.projectNew'
    : state.tab === 'project' && state.projectView === 'add'
      ? 'page.projectAdd'
      : PAGE_LABEL[state.tab];
  const label = pageKey ? t(pageKey, 'FactScribe') : 'FactScribe';
  const wbName = String(state.workbenchProject?.project || state.workbenchStatus?.project || '').trim();
  document.title = wbName ? label + ' · ' + wbName : label;
}

function switchTab(tab, opts = {}) {
  // 项目页有三态：'project'（列表）、'project/new'（新建）、'project/add'（加入已有文件夹）。
  const [base, sub] = String(tab || '').split('/');
  state.tab = base;
  state.projectView = base === 'project' ? (sub || 'list') : 'list';
  for (const btn of $$('.nav-item')) {
    const on = btn.dataset.tab === base;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', String(on));
  }
  for (const panel of $$('.panel')) {
    const on = panel.id === panelIdFor(tab);
    panel.classList.toggle('is-active', on);
    panel.hidden = !on;
  }
  if (tab === 'project/new') openNewProjectForm();
  renderWorkbenchSections();
  renderTab();
  updateTitle();
  if (!opts.fromHash) writeHash(tab, opts.replace);
}

/** 地址栏变了：回到那一页（前进/后退就是走这里）。 */
function onHashChange() {
  if (suppressHash) {
    suppressHash = false;
    return;
  }
  const raw = String(location.hash || '').replace(/^#\/?/, '');
  const tab = pageFromHash();
  if (!tab) {
    // 不认识的 hash（或本模式没有的页）：回默认页，地址也改回合法值
    const fallback = defaultPage();
    switchTab(fallback, { fromHash: true });
    history.replaceState(null, '', '#/' + fallback);
    return;
  }
  const view = tab.startsWith('project/') ? tab.slice('project/'.length) : 'list';
  const same = state.tab === (tab.startsWith('project/') ? 'project' : tab)
    && state.projectView === view;
  if (!same) {
    switchTab(tab, { fromHash: true });
  } else if (raw !== tab) {
    // 非法子路由（例如 #/project/xxx）：地址改回合法值，人停在项目列表。
    history.replaceState(null, '', '#/' + tab);
  }
}

function renderTab() {
  if (state.tab === 'workbench') renderWorkbench();
  else if (state.tab === 'facts') renderWorkbenchFacts();
  else if (state.tab === 'reports') {
    // 按需加载：只有真的切到「实验报告」页才请求；其他视图不预拉
    renderWorkbenchReports();
    if (state.workbenchProject) loadWorkbenchReports().catch(() => {});
  }
  else if (state.tab === 'citations') {
    // 引用页同理：进页面才请求 /api/citations
    renderCitations();
    if (state.workbenchProject) loadCitations().catch(() => {});
  }
  else if (state.tab === 'project') renderProjects();
  else if (state.tab === 'ai') renderAi();
}

// ------------------------------------------------------------------ KPI
// 工作台的问题统计也要用这排数字，所以它留着。

function kpi(value, label, cls, hint) {
  return (
    '<div class="kpi"><div class="kpi-value"' + (cls ? ' style="color:var(--mcode-' + cls + ')"' : '') + '>' + esc(String(value)) +
    '</div><div class="kpi-label">' + esc(label) + '</div>' +
    (hint ? '<div class="kpi-hint">' + esc(hint) + '</div>' : '') + '</div>'
  );
}

// ------------------------------------------------------------------ 本地工作台
// 只显示工作台项目的结果；页面里没有别的项目副本，不混用。


// ------------------------------------------------------------------ AI 起草
// 页面发起的 agent session 会绑定当前项目目录；Node 发起不会。
// 输出只进候选区，采纳后写工作台项目，再跑闸门。

function applyMode() {
  const name = $('#app-name');
  if (name) name.textContent = MODE.mini ? 'MiniFactScribe' : 'FactScribe';
  const sub = $('#app-sub');
  if (sub) {
    sub.textContent = MODE.mini
      ? 'FactScribe · 数字与引用的机械闸门'
      : '本地工作台 · 真实论文项目';
  }
  // 网页里服务已经起好，MiniApp 的「启动并连接」整块不需要。
  const wbProject = $('#wb-project');
  if (wbProject) wbProject.hidden = !MODE.mini;
  // 「在浏览器打开」只有 MiniApp 需要：网页本来就在浏览器里。
  const openBrowser = $('#btn-wb-open-browser');
  if (openBrowser) openBrowser.hidden = !MODE.mini;
  // 只有「AI 起草」是宿主专属页签：网页里没有宿主 agent。
  const hostTabs = ['ai'];
  for (const tab of hostTabs) {
    const btn = document.querySelector('.nav-item[data-tab="' + tab + '"]');
    if (btn) btn.hidden = !MODE.showHostUi;
  }
  // 项目管理两种模式都要：网页也要选论文项目
  for (const sel of ['#workbench-host-path', '.manual-connect']) {
    const el = $(sel);
    if (el) el.hidden = !MODE.showHostUi;
  }
  // 宿主专属的启动控件：普通网页藏起来；开发模式留着看，但下面的禁用逻辑照旧
  if (!MODE.showHostUi) {
    for (const sel of ['#btn-workbench-start', '#btn-workbench-stop', '#btn-project-host',
      '#workbench-allow-write', '#workbench-allow-build', '#project-python',
      '#project-pythonpath', '#btn-project-python']) {
      const el = $(sel);
      if (!el) continue;
      const label = el.closest('label');
      if (label && el.type === 'checkbox') { label.hidden = true; continue; }
      const field = el.closest('label') || el;
      if (el.type === 'text' || el.type === 'password') field.hidden = true;
      else el.hidden = true;
    }
  }
  if (!MODE.mini) {
    // 网页里没有 Node：启动/项目登记只做界面预览，不给误点
    for (const sel of ['#btn-workbench-start', '#btn-workbench-stop', '#btn-workbench-connect',
      '#btn-workbench-disconnect', '#btn-project-host', '#btn-project-python']) {
      const el = $(sel);
      if (!el) continue;
      el.disabled = true;
      el.title = '这是 MiniApp 专属按钮；网页里由命令行启动的服务已经就绪';
    }
    // AI 聊天：网页里没有宿主 agent，输入禁用并说清原因；历史仍可看。
    setChatNotice('网页模式不能起草：需要 MiniApp 宿主');
    for (const sel of ['#wb-chat-input', '#wb-chat-send']) {
      const el = $(sel);
      if (!el) continue;
      el.disabled = true;
      el.title = '需要 MiniApp 宿主';
    }
    const banner = $('#session-banner');
    if (banner) {
      banner.hidden = !MODE.dev;
      if (MODE.dev) {
        banner.textContent = '开发模式：宿主专属的按钮和输入都显示出来了，但启动工作台和 AI 起草需要 MiniApp 宿主；网页里请直接用下面已经连上的服务。';
      }
    }
  }
}

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

/** 拼提示：当前节 + 事实账 + 硬约束。AI 起草页与右栏的 AI 聊天共用这一套。 */
function buildSectionPrompt(request) {
  const file = aiSectionFile();
  const row = (state.workbenchProject?.sections || []).find((s) => s.file === file);
  const facts = (state.workbenchProject?.facts || []).map((f) =>
    '- ' + f.id + ' | ' + (f.claim || '') + ' | ' + (f.value || '') + ' | ' + (f.source || ''));
  return [
    '你是论文写作助手，正在帮作者起草或改写一节 LaTeX 正文。',
    '硬约束：正文里的每个数字都必须来自下面的事实账；不得编造数字、引用或实验；',
    '不确定的地方写 TODO，不要猜。只输出完整替换本节的 LaTeX，不要解释。',
    '',
    '当前节：' + file,
    '',
    '用户要求：' + (request || '按事实账起草/改写本节。'),
    '',
    '当前正文：',
    row ? row.text : '（空）',
    '',
    '事实账（id | 主张 | 值 | 来源）：',
    facts.length ? facts.join('\n') : '（账里没有事实——不要写任何数字，先提示作者记账）',
  ].join('\n');
}

function aiPrompt() {
  const instruction = $('#ai-instruction')?.value.trim() || '';
  return buildSectionPrompt(instruction || '按事实账起草/改写本节。');
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
  await api(wb('/sections'), {
    method: 'PUT',
    body: JSON.stringify({ file, text: state.ai.candidate }),
  });
  $('#ai-accept-state').textContent = '已写入 ' + file + '，正在重跑审计…';
  toast('已写入 ' + file);
  // 采纳 AI 候选＝改了正文：引导条第 ③ 步也算数。
  state.guide.edited = true;
  await loadWorkbenchProject();
  await runWorkbenchAudit();
  $('#ai-accept-state').textContent = '已写入 ' + file + '；审计已重跑';
  state.ai.candidate = '';
  state.ai.text = '';
  renderAi();
}


// ------------------------------------------------------ 论文项目（文件夹＝项目）
// 一个文件夹就是一个论文项目：换项目＝换文件夹。登记册在 ~/.factscribe/projects.json，
// 不在 dataDir——重装插件后还要认得这些文件夹。

let workbenchBusy = false;

function projectBusy(flag) {
  if (flag !== undefined) workbenchBusy = Boolean(flag);
  const start = $('#btn-workbench-start');
  const stop = $('#btn-workbench-stop');
  if (start) start.disabled = workbenchBusy || !state.projectPath;
  if (stop) stop.disabled = workbenchBusy || !state.run;
}

function renderProjects() {
  if (state.projectView === 'new' || state.projectView === 'add') {
    renderNewProject();
    return;
  }
  renderSidebarProject();
  const w = state.workbench || { configured: false };
  // 项目页自己的几处状态：当前对话路径、当前项目、运行状态、手动连接。
  const hostPath = $('#workbench-host-path');
  if (hostPath) {
    hostPath.textContent = state.hostWorkspace
      ? '当前对话项目：' + state.hostWorkspace
      : '当前对话没有项目文件夹（或尚未读取）；可以直接填论文项目文件夹。';
  }
  const projectSummary = $('#wb-project-summary');
  if (projectSummary) {
    projectSummary.textContent = state.workbenchProject
      ? '论文项目：' + (state.workbenchProject.project || state.workbenchProject.root || '已载入') + '（点开切换）'
      : '论文项目（点开选择）';
  }
  const runState = $('#workbench-run-state');
  if (runState) {
    if (state.run) {
      const mode = state.run.mode
        ? (state.run.mode.write ? '可写' : t('report.readOnly')) + (state.run.mode.build ? ' · 可编译' : '')
        : '';
      runState.textContent = '运行中 · PID ' + state.run.pid + ' · ' + mode + ' · ' + state.run.project;
    } else {
      runState.textContent = '';
    }
  }
  const url = $('#workbench-url');
  if (url) url.value = w.url || '';
  const token = $('#workbench-token');
  if (token) {
    token.placeholder = w.tokenSet
      ? '已保存（留空不改）'
      : '启动 serve 时打印的 token';
  }
  const disconnect = $('#btn-workbench-disconnect');
  if (disconnect) disconnect.disabled = MODE.mini ? !w.configured : true;
  renderProjectList();
  const input = $('#project-path');
  if (input && document.activeElement !== input && input.value !== state.projectPath) {
    input.value = state.projectPath;
  }
  const python = $('#project-python');
  if (python && document.activeElement !== python && python.value !== state.projectPython) {
    python.value = state.projectPython;
  }
  const pythonPath = $('#project-pythonpath');
  if (pythonPath && document.activeElement !== pythonPath && pythonPath.value !== state.projectPythonPath) {
    pythonPath.value = state.projectPythonPath;
  }
  projectBusy();
  renderGuide();
}

/** 当前正在用的项目文件夹（列表里给它加「当前」徽标）。 */
function currentProjectPath() {
  return String(state.workbenchProject?.root || state.projectPath || '');
}

/** 路径太长时只留尾巴：…/家目录/论文。 */
function shortPath(path, keep = 3) {
  const text = String(path || '');
  const parts = text.split('/').filter(Boolean);
  if (parts.length <= keep) return text;
  return '…/' + parts.slice(-keep).join('/');
}

/** 左栏的项目列表：手风琴。点一行展开那一条，里面是四个动作。

    同一时刻只展开一条（state.projectOpen 记着路径）；再点一次收起。
    新手引导的示例论文不在列表里（服务端标了 guide:true）——它是示例，
    不是人自己的论文。
*/
function renderProjectList() {
  const list = $('#project-list');
  if (!list) return;
  const rows = state.projects.filter((p) => !p.guide);
  const empty = $('#project-list-empty');
  if (!rows.length) {
    list.innerHTML = '';
    if (empty) {
      empty.hidden = false;
      empty.textContent = t('project.listEmpty');
    }
    return;
  }
  if (empty) empty.hidden = true;
  const current = currentProjectPath();
  list.innerHTML = rows.map((p) => {
    const path = String(p.path || '');
    const isCurrent = path === current;
    const name = p.name || path.split('/').filter(Boolean).pop() || path;
    const desc = String(p.description || '').trim();
    const open = state.projectOpen === path;
    const editing = state.projectEdit === path;
    return '<li class="project-item' + (isCurrent ? ' is-current' : '') +
      (open ? ' is-open' : '') + '">' +
      '<button class="project-item-main" type="button" data-path="' + esc(path) +
      '" aria-expanded="' + String(open) + '">' +
      '<span class="project-item-name">' + esc(name) +
      (isCurrent ? '<span class="project-badge">' + esc(t('project.current')) + '</span>' : '') +
      '</span>' +
      '<span class="project-item-path" title="' + esc(path) + '">' + esc(shortPath(path)) + '</span>' +
      (desc ? '<span class="project-item-desc">' + esc(desc) + '</span>' : '') +
      '</button>' +
      (open ? projectItemActions(path, name, desc, editing) : '') +
      '</li>';
  }).join('');
}

/** 展开后的那一块：编辑 / 删除 / 载入项目 / 复制路径（编辑时多一个小表单）。 */
function projectItemActions(path, name, desc, editing) {
  const actions = [
    ['edit', t('project.actionEdit')],
    ['delete', t('project.actionDelete')],
    ['load', t('project.actionLoad')],
    ['copy', t('project.actionCopy')],
  ].map(([action, label]) =>
    '<button class="btn project-item-act" type="button" data-action="' + action +
    '" data-path="' + esc(path) + '">' + esc(label) + '</button>').join('');
  const form = editing
    ? '<div class="project-edit" data-path="' + esc(path) + '">' +
      '<label class="field"><span>' + esc(t('project.editName')) + '</span>' +
      '<input class="project-edit-name" type="text" autocomplete="off" value="' + esc(name) + '" /></label>' +
      '<label class="field"><span>' + esc(t('project.editDesc')) + '</span>' +
      '<input class="project-edit-desc" type="text" autocomplete="off" value="' + esc(desc) + '" /></label>' +
      '<label class="field"><span>' + esc(t('project.editPath')) + '</span>' +
      '<input type="text" value="' + esc(path) + '" readonly /></label>' +
      '<div class="panel-actions">' +
      '<button class="btn btn-primary" type="button" data-action="save-edit" data-path="' + esc(path) + '">' +
      esc(t('project.editSave')) + '</button>' +
      '<button class="btn" type="button" data-action="cancel-edit" data-path="' + esc(path) + '">' +
      esc(t('project.editCancel')) + '</button>' +
      '</div></div>'
    : '';
  return '<div class="project-item-actions">' + actions + form + '</div>';
}

/** 展开条里的动作：编辑 / 删除 / 载入项目 / 复制路径。 */
async function projectItemAction(action, path) {
  if (action === 'edit') {
    state.projectEdit = path;
    renderProjects();
    return;
  }
  if (action === 'cancel-edit') {
    state.projectEdit = '';
    renderProjects();
    return;
  }
  if (action === 'copy') {
    await copyProjectPath(path);
    return;
  }
  if (action === 'delete') {
    await removeProjectFromList(path);
    return;
  }
  if (action === 'load') {
    await loadProjectFromList(path);
  }
}

/** 载入项目：网页让服务切到那个文件夹；MiniApp 把路径填进输入框（等人点启动）。 */
async function loadProjectFromList(path) {
  if (!path) return;
  if (MODE.mini) {
    state.projectPath = path;
    const input = $('#project-path');
    if (input) input.value = path;
    renderProjects();
    toast('已选中：' + path);
    return;
  }
  await chooseProject(path);
}

/** 从列表移除一个项目：只动登记册，文件夹和正文一个字都不改。危险动作：先问一次。 */
async function removeProjectFromList(path) {
  if (!path) return;
  if (!confirm('从列表移除这个项目？\n（文件夹和正文都不会动）')) return;
  const data = await api('/api/projects?path=' + encodeURIComponent(path), { method: 'DELETE' });
  state.projects = Array.isArray(data.projects) ? data.projects : [];
  state.projectPath = data.lastPath || '';
  if (state.projectOpen === path) {
    state.projectOpen = '';
    state.projectEdit = '';
  }
  if (state.run && state.run.project === path) {
    $('#workbench-status').textContent = '这个项目还在运行；先点「停止工作台」再移除。';
  } else {
    $('#workbench-status').textContent = t('project.removed');
  }
  renderProjects();
  renderWorkbench();
}

/** 复制路径到剪贴板。剪贴板不可用就说清楚，不假装复制过了。 */
async function copyProjectPath(path) {
  try {
    if (!navigator.clipboard || !navigator.clipboard.writeText) throw new Error('no clipboard');
    await navigator.clipboard.writeText(String(path || ''));
    toast(t('project.copied'));
  } catch {
    toast(t('project.copyFailed'));
  }
}

/** 保存编辑：改登记册的 name/description，并写进项目自己的 factscribe.toml。 */
async function saveProjectEdit(path) {
  const box = $$('.project-edit').find((el) => el.dataset.path === path);
  if (!box) return;
  const name = String(box.querySelector('.project-edit-name')?.value ?? '').trim();
  const desc = String(box.querySelector('.project-edit-desc')?.value ?? '').trim();
  if (!name) throw new Error('项目名称不能为空');
  const data = await api(wb('/projects/update'), {
    method: 'POST',
    body: JSON.stringify({ path, name, description: desc }),
  });
  state.projects = Array.isArray(data.projects) ? data.projects : state.projects;
  state.projectEdit = '';
  renderProjects();
  toast('已更新：' + String(data?.project?.name || name));
}

// ------------------------------------------------------------ 新建项目页
// #/project/new：填几项 → 生成骨架 → 切到工作台。失败留在表单里，不跳走。

/** 表单默认值。文件夹名不转拼音：中文名自己写，默认给 paper-YYYYMMDD。 */
function newProjectDefaults() {
  const now = new Date();
  const stamp = now.getFullYear()
    + String(now.getMonth() + 1).padStart(2, '0')
    + String(now.getDate()).padStart(2, '0');
  return {
    parent: '~',
    slug: 'paper-' + stamp,
    lang: 'zh',
    sections: 'sections/*.tex',
    facts: 'facts/*.toml',
    bib: 'refs.bib',
    root_tex: 'main.tex',
    build: 'tectonic -X compile main.tex',
    output: 'main.pdf',
  };
}

/** 进新建页：把默认值填进去（只在这里填，别把人填一半的表单冲掉）。 */
function openNewProjectForm() {
  const d = newProjectDefaults();
  const set = (sel, value) => { const el = $(sel); if (el) el.value = value; };
  set('#np-title', '');
  set('#np-parent', d.parent);
  set('#np-slug', d.slug);
  set('#np-authors', '');
  set('#np-description', '');
  set('#np-lang', d.lang);
  set('#np-sections', d.sections);
  set('#np-facts', d.facts);
  set('#np-bib', d.bib);
  set('#np-root-tex', d.root_tex);
  set('#np-build', d.build);
  set('#np-source-root', '');
  set('#np-output', d.output);
  state.npError = '';
  renderNewProject();
}

/** 新建页只管错误提示与两个页签的显隐；字段值由 openNewProjectForm 填、人自己改。 */
function renderNewProject() {
  const err = $('#np-error');
  if (err) {
    err.textContent = state.npError || '';
    err.hidden = !state.npError;
  }
  const isAdd = state.projectView === 'add';
  const newSection = $('#np-new-section');
  const addSection = $('#np-add-section');
  if (newSection) newSection.hidden = isAdd;
  if (addSection) addSection.hidden = !isAdd;
  for (const btn of $$('.np-tab')) {
    const on = btn.dataset.view === (isAdd ? 'add' : 'new');
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-selected', String(on));
  }
}

function showNpError(message) {
  state.npError = String(message || '');
  renderNewProject();
}

/** 创建项目：调 POST /api/projects/create，成功后切到工作台并载入新项目。 */
async function createProjectFromForm() {
  const btn = $('#btn-np-create');
  const value = (sel) => String($(sel)?.value ?? '').trim();
  const title = value('#np-title');
  const parent = value('#np-parent');
  const slug = value('#np-slug');
  if (!title) { showNpError('请填项目名称'); return; }
  if (!parent) { showNpError('请填父目录（放新文件夹的地方）'); return; }
  if (!slug) { showNpError('请填文件夹名'); return; }
  const authors = value('#np-authors').split(/[,，]/)
    .map((s) => s.trim()).filter(Boolean);
  const body = {
    title,
    parent,
    slug,
    authors,
    description: value('#np-description'),
    lang: value('#np-lang') || 'zh',
    sections: value('#np-sections'),
    facts: value('#np-facts'),
    bib: value('#np-bib'),
    root_tex: value('#np-root-tex'),
    build: value('#np-build'),
    source_root: value('#np-source-root'),
    output: value('#np-output'),
  };
  if (btn) btn.disabled = true;
  const label = btn ? btn.textContent : '';
  if (btn) btn.textContent = t('np.creating');
  try {
    const data = await api(wb('/projects/create'), {
      method: 'POST',
      body: JSON.stringify(body),
    });
    const path = String(data?.project?.path || '');
    if (path) {
      state.projectPath = path;
      const input = $('#project-path');
      if (input) input.value = path;
    }
    state.npError = '';
    try { await loadProjects(); } catch { /* 列表刷新失败不挡新建 */ }
    switchTab('workbench');
    if (!MODE.mini) {
      await loadWorkbenchStatus().catch(() => {});
      await loadWorkbenchProject().catch(() => {});
    }
    toast(tf('np.created', { name: String(data?.project?.name || slug) }));
  } catch (err) {
    showNpError(err.message);
    toast('创建失败：' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = label || t('btn.npCreate');
    }
  }
}

async function loadProjects() {
  const data = await api('/api/projects');
  state.projects = Array.isArray(data.projects) ? data.projects : [];
  state.projectPython = data.python || '';
  state.projectPythonPath = data.pythonpath || '';
  state.factscribeDir = data.dir || '';
  // 没选过项目：优先上次用的，其次当前对话的项目，最后列表里的第一个
  if (!state.projectPath) {
    state.projectPath = data.lastPath
      || state.hostWorkspace
      || (state.projects[0] && state.projects[0].path)
      || '';
  }
  renderProjects();
}

async function chooseProject(path) {
  const project = await addProject(path);
  if (!MODE.mini) {
    // 网页里「选项目」就是让服务切到这个文件夹
    await loadWorkbenchStatus();
    await loadWorkbenchProject();
    await runWorkbenchAudit();
  }
  return project;
}

async function addProject(rawPath) {
  const path = String(rawPath ?? state.projectPath ?? '').trim();
  if (!path) throw new Error('先填论文项目文件夹');
  const data = await api('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
  state.projectPath = data.project.path;
  state.projects = Array.isArray(data.projects) ? data.projects : state.projects;
  renderProjects();
  $('#workbench-status').textContent =
    '已加入：' + data.project.name + '（' + data.project.path + '）';
  return data.project;
}

/** 「加入已有文件夹」：只登记进册子，不改那个文件夹里的任何东西。 */
async function addExistingProject() {
  const path = String($('#np-existing-path')?.value ?? '').trim();
  const note = $('#np-add-note');
  if (!path) {
    if (note) note.textContent = '先填论文项目文件夹';
    throw new Error('先填论文项目文件夹');
  }
  const project = await addProject(path);
  if (note) note.textContent = '已加入：' + project.name;
  toast('已加入：' + project.name);
  switchTab('project');
}

async function useHostProject() {
  if (!state.hostWorkspace) throw new Error('当前对话没有项目文件夹；请从论文项目的对话里打开');
  state.projectPath = state.hostWorkspace;
  $('#project-path').value = state.hostWorkspace;
  renderProjects();
  return addProject(state.hostWorkspace);
}

async function saveProjectPython() {
  const python = $('#project-python').value.trim();
  const pythonpath = $('#project-pythonpath').value.trim();
  const data = await api('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ python, pythonpath }),
  });
  state.projectPython = data.python || '';
  state.projectPythonPath = data.pythonpath || '';
  $('#workbench-status').textContent = '已保存：解释器 ' + (python || '（默认 python3）') +
    (pythonpath ? ' · 包路径 ' + pythonpath : '');
}

async function startWorkbench() {
  const path = String($('#project-path').value ?? '').trim();
  if (!path) throw new Error('先填论文项目文件夹');
  projectBusy(true);
  $('#workbench-run-state').textContent = '启动中…';
  $('#workbench-status').textContent = '启动中…（固定命令 python3 -m factscribe serve）';
  try {
    const data = await api('/api/workbench/start', {
      method: 'POST',
      body: JSON.stringify({
        path,
        allowWrite: Boolean($('#workbench-allow-write').checked),
        allowBuild: Boolean($('#workbench-allow-build').checked),
      }),
    });
    state.projectPath = data.project;
    state.workbench = { configured: true, url: data.url, tokenSet: true };
    state.run = {
      project: data.project, pid: data.pid,
      mode: { write: Boolean(data.allowWrite), build: Boolean(data.allowBuild) },
    };
    state.workbenchAudit = null;
    $('#workbench-status').textContent =
      (data.reused ? '已在运行：' : '已启动：') + data.url + '（PID ' + data.pid + '，' +
      (data.allowWrite ? '可写' : t('report.readOnly')) + (data.allowBuild ? ' · 可编译' : '') + '）';
    state.projectPython = state.projectPython || '';
    await loadProjects();
    await loadWorkbenchStatus();
    await loadWorkbenchProject();
    toast('工作台已启动');
  } finally {
    projectBusy(false);
    renderWorkbench();
  }
}

async function stopWorkbench() {
  projectBusy(true);
  try {
    await api('/api/workbench/stop', { method: 'POST' });
    state.run = null;
    state.workbench = { configured: false };
    state.workbenchStatus = null;
    state.workbenchProject = null;
    state.workbenchAudit = null;
    $('#workbench-status').textContent = '已停止工作台';
    renderWorkbench();
    toast('工作台已停止');
  } finally {
    projectBusy(false);
    renderWorkbench();
  }
}

/** 侧栏顶部：项目按钮 + 当前项目名；没有项目就写那句默认提示。 */
function renderSidebarProject() {
  const el = $('#sidebar-project-name');
  if (!el) return;
  const project = state.workbenchProject;
  let name = String(project?.project || '').trim();
  if (!name && state.projectPath) {
    // 服务端还没载入项目时，登记册里的名字先用着。
    const row = state.projects.find((p) => p.path === state.projectPath);
    name = String(row?.name || '').trim();
  }
  const has = Boolean(name);
  const root = $('#sidebar-project-root');
  const empty = $('#sidebar-project-empty');
  const sections = $('#sidebar-sections');
  if (root) root.hidden = !has;
  if (empty) empty.hidden = has;
  if (sections) sections.hidden = !has;
  if (has) {
    el.textContent = name;
    root.title = name;
  }
  const btn = $('#btn-sidebar-project');
  if (btn) {
    btn.title = has
      ? '当前项目：' + name + '（点它去项目页换项目）'
      : '还没选论文项目（点它去项目页选一个或新建一个）';
  }
}

// ------------------------------------------------------------ 新手引导（示例论文）
// 一份随包发布的示例论文：看问题 → 改一个数 → 变绿。示例只装到
// ~/.factscribe/samples/guide，用户的论文一个字都不动。
// 引导条上的五个勾全部由当前状态推导——不许假勾：没做的事就是没勾。

const GUIDE_KEY = 'factscribe.guide';
const GUIDE_STEP_KEYS = ['guide.step1', 'guide.step2', 'guide.step3', 'guide.step4', 'guide.step5'];
const GUIDE_MARKS = ['①', '②', '③', '④', '⑤'];

/** localStorage 里记的示例路径（空＝没开过或已关闭）。 */
function guideStoredPath() {
  try {
    return localStorage.getItem(GUIDE_KEY) || '';
  } catch {
    return '';
  }
}

/** 记住引导开着（路径）还是关了（空串）。 */
function guideStorePath(path) {
  try {
    localStorage.setItem(GUIDE_KEY, String(path || ''));
  } catch {
    /* 写不进去就算了：这一轮仍然能用 */
  }
}

/** 这个路径是不是那份示例：尾段固定，比全路径稳（HOME 可能有软链）。 */
function isGuideSample(path) {
  const text = String(path || '').replace(/\\/g, '/').replace(/\/+$/, '');
  return text.endsWith('/samples/guide');
}

/** 示例论文该在哪：~/.factscribe/samples/guide。 */
function guideSamplePath() {
  const dir = String(state.factscribeDir || '').replace(/\/+$/, '');
  return dir ? dir + '/samples/guide' : '';
}

/** 这台机器上是不是已经有示例了（开过、或者当前正开着它）。 */
function guideSampleExists() {
  if (state.guide.path && isGuideSample(state.guide.path)) return true;
  const root = String(state.workbenchProject?.root || '');
  if (root && isGuideSample(root)) return true;
  return state.projects.some((p) => isGuideSample(p.path));
}

/** 引导条该不该出现：开了引导，且当前工作台项目就是那份示例。 */
function guideActive() {
  const path = state.guide.path || guideStoredPath();
  if (!path || !isGuideSample(path)) return false;
  const root = String(state.workbenchProject?.root || '');
  return Boolean(root) && isGuideSample(root);
}

/** 五步的进度：每一条都从当前状态推出来。 */
function guideProgress() {
  const audit = state.workbenchAudit;
  const findings = Array.isArray(audit?.findings) ? audit.findings : [];
  const reports = state.wbReports?.reports || [];
  const facts = state.workbenchProject?.facts || [];
  return [
    Boolean(state.currentSection),            // ① 选过任意一节
    findings.length > 0,                     // ② 看到红黄
    reports.some((r) => r.signed),            // ③ 报告已签收
    facts.some((f) => String(f.report || '')),// ④ 报告事实已导入
    Boolean(audit) && findings.every((f) => f.severity !== 'red'),  // ⑤ 红牌清零
  ];
}

/** 画引导条：项目页的按钮文案 + 工作台页的引导条。 */
function renderGuide() {
  const openBtn = $('#btn-guide-open');
  if (openBtn) {
    openBtn.textContent = guideSampleExists() ? t('btn.guideOpenExists') : t('btn.guideOpen');
  }
  const bar = $('#guide-bar');
  if (!bar) return;
  const active = guideActive();
  bar.hidden = !active;
  bar.setAttribute('aria-label', t('guide.bar'));
  if (!active) return;
  const done = guideProgress();
  const host = $('#guide-steps');
  if (host) {
    host.innerHTML = done.map((ok, i) =>
      '<span class="guide-step' + (ok ? ' is-done' : '') + '" data-step="' + (i + 1) + '">' +
      '<span class="guide-step-mark">' + (ok ? '✓' : '○') + '</span> ' +
      GUIDE_MARKS[i] + ' ' + esc(t(GUIDE_STEP_KEYS[i])) + '</span>').join('');
  }
  const hint = $('#guide-hint');
  if (hint) {
    const missing = done.findIndex((ok) => !ok);
    hint.hidden = missing < 0;
    hint.textContent = missing < 0 ? '' : t('guide.hint' + (missing + 1));
  }
}

/** 打开示例论文：装一份，再把服务切到它（网页）/ 把路径填进输入框（MiniApp）。 */
async function openGuideSample() {
  const btn = $('#btn-guide-open');
  const note = $('#guide-card-note');
  if (btn) btn.disabled = true;
  try {
    const data = await api(wb('/samples/guide'), {
      method: 'POST',
      body: JSON.stringify({ reset: false }),
    });
    const path = String(data?.path || guideSamplePath());
    if (!path) throw new Error('服务端没给出示例路径');
    state.guide.path = path;
    guideStorePath(path);
    if (MODE.mini) {
      // MiniApp：路径填进项目输入框，等人点「启动并连接」。
      await addProject(path);
      const input = $('#project-path');
      if (input) input.value = path;
      state.projectPath = path;
      renderProjects();
      if (note) note.textContent = t('guide.readyMini');
      toast(t('guide.readyMini'));
      return;
    }
    // 网页：本机服务直接切到示例，再载入并审计。
    await chooseProject(path);
    switchTab('workbench');
    if (note) note.textContent = t('guide.opened');
    toast(t('guide.opened'));
  } catch (err) {
    if (note) note.textContent = '打开示例失败：' + err.message;
    toast('打开示例失败：' + err.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/** 重置示例：删掉重装一份，再刷新项目与审计。 */
async function resetGuideSample() {
  const buttons = [$('#btn-guide-reset'), $('#btn-guide-reset-bar')].filter(Boolean);
  for (const b of buttons) b.disabled = true;
  try {
    const data = await api(wb('/samples/guide'), {
      method: 'POST',
      body: JSON.stringify({ reset: true }),
    });
    const path = String(data?.path || state.guide.path || guideSamplePath());
    if (path) {
      state.guide.path = path;
      guideStorePath(path);
    }
    state.guide.edited = false;
    state.guide.auditedAfterEdit = false;
    state.workbenchAudit = null;
    await loadWorkbenchProject();
    await runWorkbenchAudit();
    toast(t('guide.resetDone'));
  } catch (err) {
    toast('重置示例失败：' + err.message);
  } finally {
    for (const b of buttons) b.disabled = false;
  }
}

/** 关闭引导：藏起来，并把这个决定记进 localStorage（刷新后不再冒出来）。 */
function closeGuide() {
  state.guide.path = '';
  guideStorePath('');
  renderGuide();
  toast(t('btn.guideClose'));
}

function renderWorkbench() {
  const w = state.workbench || { configured: false };
  const badge = $('#workbench-badge');
  if (!badge) return;
  renderSidebarProject();
  renderWorkbenchSections();
  badge.textContent = MODE.mini
    ? (state.run ? '运行中' : (w.configured ? '已配置' : '未连接'))
    : '本机服务';
  renderProjects();
  $('#btn-workbench-audit').disabled = !w.configured;
  renderWbMeta();
  // 右栏两面板互斥；聊天记录跟着当前项目走。
  renderWbSide();
  loadChat();

  if (!w.configured) {
    $('#workbench-audit').innerHTML = '';
    $('#btn-workbench-save').disabled = true;
    renderWorkbenchSections();
    renderWbMode();
    return;
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
    // 当前选中的是哪一节：引导条第 ① 步就看它。
    state.currentSection = select.value || '';
    const row = project.sections.find((s) => s.file === select.value);
    $('#workbench-section-text').value = row ? row.text : '';
    updateHighlight();
    $('#workbench-save-state').textContent = project.read_only
      ? '工作台是只读模式（启动时没加 --allow-write）'
      : '可写';
    $('#btn-workbench-save').disabled = Boolean(project.read_only);
    $('#workbench-section-text').readOnly = project.read_only;
  } else {
    $('#workbench-save-state').textContent = '';
    $('#btn-workbench-save').disabled = true;
  }
  const emptyBox = $('#wb-section-empty');
  if (emptyBox) emptyBox.hidden = Boolean(project);
  const currentLabel = $('#wb-current-section');
  if (currentLabel) currentLabel.textContent = project ? (select.value || '') : '';
  renderWorkbenchSections();
  renderWbMode();

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
  const auditMeta = $('#wb-audit-meta');
  if (auditMeta) {
    auditMeta.textContent = findings.length
      ? red.length + ' 红 / ' + yellow.length + ' 黄'
      : '';
  }
  const note = verdict === 'green'
    ? '账有据、据未改、文有绑。它不说明结论为真。'
    : verdict === 'yellow'
      ? '跑完了，但有未核验或未绑定的项——不判死，但必须逐条看过。'
      : '有事实层矛盾：这些数或引用回不到账，必须改。';
  const rows = findings.slice(0, 12).map((f) => {
    const isRed = f.severity === 'red';
    const sev = isRed ? '红牌' : '黄牌';
    const cls = isRed ? 'chip-red' : 'chip-yellow';
    const jump = jumpTargetFor(f.location);
    const jumpBtn = jump
      ? '<button type="button" class="link-btn wb-jump" data-jump-file="' + esc(jump.file) +
        '" data-jump-line="' + jump.line + '">跳到那一行</button>'
      : '';
    return '<div class="issue">' +
      '<div class="issue-head"><span class="chip ' + cls + '">' + sev + '</span>' +
      '<span class="issue-label">' + esc(ISSUE_LABEL[f.code] || f.code) + '</span>' +
      '<span class="code">' + esc(f.code || '') + '</span>' +
      '<span class="loc">' + esc(f.location || '') + '</span>' + jumpBtn + '</div>' +
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
    (rows || '<div class="line-empty">' + t('empty.noRedYellow') + '</div>') +
    (findings.length > 12 ? '<div class="muted-note">只显示前 12 条；完整结果看 serve 的 --json 输出。</div>' : '');
}

// ------------------------------------------------------ 工作台两栏
// 左：源码 / 预览；右：要处理的问题 + AI 入口。章节目录在左侧栏里。
// 这里只管「看和改」，事实账、证据、报告各自成块放在别处。

/** 章节标题：正文里的 \\section{...} 优先，没有就用文件名。 */
function sectionTitle(section) {
  const text = String(section?.text || '');
  const m = /\\(?:sub)?section\*?\{([^}]*)\}/.exec(text);
  if (m && m[1].trim()) return m[1].trim();
  const file = String(section?.file || '');
  const base = file.split('/').pop() || file;
  return base.replace(/\.tex$/i, '') || file || '（未命名）';
}

/** 某一节上的问题条数：红牌与黄牌分开数，符号之外还有数字。 */
function sectionIssueCounts(file) {
  const findings = (state.workbenchAudit?.findings) || [];
  let red = 0;
  let yellow = 0;
  for (const f of findings) {
    const loc = String(f.location || '');
    if (!loc.startsWith(file + ':')) continue;
    if (f.severity === 'red') red += 1;
    else yellow += 1;
  }
  return { red, yellow };
}

/** 左栏目录：由 state.workbenchProject.sections 生成，当前节高亮。 */
function renderWorkbenchSections() {
  const list = $('#wb-section-list');
  const count = $('#wb-section-count');
  const project = state.workbenchProject;
  const sections = project?.sections || [];
  const current = $('#workbench-section-select')?.value || '';
  if (count) count.textContent = sections.length ? sections.length + ' 节' : '';
  const locked = workbenchReadOnly();
  const addBtn = $('#btn-wb-section-add');
  if (addBtn) {
    addBtn.disabled = locked;
    addBtn.title = locked ? t('wb.readOnly') : t('wb.sectionAdd');
  }
  if (!list) return;
  if (!sections.length) {
    list.innerHTML = '<div class="line-empty">还没有章节：先载入工作台项目。</div>';
    return;
  }
  list.innerHTML = sections.map((s, index) => {
    // 只有停在工作台页签时，当前节才高亮；切到事实账/引用时不能还亮着。
    const active = s.file === current && state.tab === 'workbench';
    const c = sectionIssueCounts(s.file);
    const badge = !state.workbenchAudit
      ? '<span class="wb-badge wb-badge-none" title="还没审计，这一节的问题未知">·</span>'
      : c.red
        ? '<span class="wb-badge wb-badge-red" title="这一节有 ' + c.red + ' 条红牌问题">✕ ' + c.red + '</span>'
        : c.yellow
          ? '<span class="wb-badge wb-badge-yellow" title="这一节有 ' + c.yellow + ' 条黄牌问题">! ' + c.yellow + '</span>'
          : '<span class="wb-badge wb-badge-ok" title="这一节没有红黄项">✓</span>';
    const lockTitle = locked ? t('wb.readOnly') : '';
    // 一行三个键：主按钮切节，右侧两个小按钮改名 / 删除。
    // id 按约定固定（脚本要认这三个 id），具体是哪一节靠 data-file。
    return '<div class="wb-section-row' + (active ? ' is-active' : '') + '">' +
      '<button type="button" class="wb-section-item' + (active ? ' is-active' : '') +
      '" data-section="' + esc(s.file) + '" aria-current="' + (active ? 'true' : 'false') +
      '" title="' + esc(s.file) + '">' +
      '<span class="wb-section-num">' + (index + 1) + '</span>' +
      '<span class="wb-section-name">' + esc(sectionTitle(s)) + '</span>' + badge +
      '</button>' +
      '<button type="button" class="wb-section-act" id="wb-section-rename" data-action="rename"' +
      ' data-file="' + esc(s.file) + '" title="' + esc(lockTitle || t('wb.sectionRename')) + '"' +
      (locked ? ' disabled' : '') + ' aria-label="' + esc(t('wb.sectionRename')) + '">✎</button>' +
      '<button type="button" class="wb-section-act" id="wb-section-delete" data-action="delete"' +
      ' data-file="' + esc(s.file) + '" title="' + esc(lockTitle || t('wb.sectionDelete')) + '"' +
      (locked ? ' disabled' : '') + ' aria-label="' + esc(t('wb.sectionDelete')) + '">🗑</button>' +
      '</div>';
  }).join('');
}

/** 工作台是不是只读：没连上、或者服务端没开 --allow-write，都写不了。 */
function workbenchReadOnly() {
  const project = state.workbenchProject;
  if (project) return Boolean(project.read_only);
  const status = state.workbenchStatus;
  if (status) return Boolean(status.read_only);
  return true;
}

/** 右栏那行紧凑信息：项目名 · N 条事实 · M 节 · 可写/只读（根路径进 title，不占屏）。 */
function renderWbMeta() {
  const el = $('#wb-meta');
  if (!el) return;
  const s = state.workbenchStatus;
  const p = state.workbenchProject;
  if (!s && !p) {
    el.textContent = '';
    el.title = el.dataset.note || '';
    return;
  }
  const count = (v) => (Array.isArray(v) ? v.length : Number(v || 0));
  const name = (s && s.project) || (p && p.project) || '（未命名项目）';
  const facts = count(s && s.facts !== undefined ? s.facts : (p && p.facts));
  const sections = count(s && s.sections !== undefined ? s.sections : (p && p.sections));
  const readOnly = s ? Boolean(s.read_only) : Boolean(p && p.read_only);
  el.textContent = name + ' · ' + facts + ' 条事实 · ' + sections + ' 节 · '
    + (readOnly ? '只读' : '可写');
  // 根路径与那句提醒都进 title：不占屏，但鼠标悬停能看到。
  const root = (s && s.root) || (p && p.root) || '';
  const note = el.dataset.note || '';
  el.title = root ? root + '｜' + note : note;
}

// ------------------------------------------------------- 章节增删改（目录级）

/** 章节写操作：走工作台接口（MiniApp 经 Node 代理，网页直连 Python）。 */
async function wbSectionRequest(url, body) {
  const headers = { 'content-type': 'application/json' };
  if (!MODE.mini && state.token) headers.Authorization = 'Bearer ' + state.token;
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body || {}),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    data = {};
  }
  if (res.status === 401) {
    showTokenPanel();
    throw new Error('token 不对或缺失');
  }
  return { status: res.status, data };
}

/** 失败信息：先给人话，再退回机器码。 */
function wbErrorText(data, status) {
  const err = (data && data.error) || null;
  if (err) return err.message || err.code || ('HTTP ' + status);
  return 'HTTP ' + status;
}

async function createWorkbenchSection() {
  if (workbenchReadOnly()) {
    toast(t('wb.readOnly'));
    return;
  }
  const name = (prompt('新章节文件名（例 sections/07-method.tex）', 'sections/') || '').trim();
  if (!name) return;
  try {
    const { status, data } = await wbSectionRequest(wb('/sections/create'), { file: name });
    if (status !== 200) {
      toast('新建失败：' + wbErrorText(data, status));
      return;
    }
    await loadWorkbenchProject();
    selectWorkbenchSection(data.file || name);
    renderWorkbenchSections();
    toast('已新建 ' + (data.file || name));
  } catch (err) {
    toast('新建失败：' + err.message);
  }
}

async function renameWorkbenchSection(file) {
  if (workbenchReadOnly()) {
    toast(t('wb.readOnly'));
    return;
  }
  const next = (prompt('新文件名', file) || '').trim();
  if (!next || next === file) return;
  try {
    const { status, data } = await wbSectionRequest(wb('/sections/rename'), { from: file, to: next });
    if (status !== 200) {
      toast('改名失败：' + wbErrorText(data, status));
      return;
    }
    await loadWorkbenchProject();
    selectWorkbenchSection(data.file || next);
    renderWorkbenchSections();
    toast('已改名：只改文件名，正文里的引用没动');
  } catch (err) {
    toast('改名失败：' + err.message);
  }
}

async function deleteWorkbenchSection(file) {
  if (workbenchReadOnly()) {
    toast(t('wb.readOnly'));
    return;
  }
  if (!confirm('删除 ' + file + '？正文里的引用不会自动改。')) return;
  try {
    let { status, data } = await wbSectionRequest(wb('/sections/delete'), { file });
    if (status === 409) {
      // 还被引用着：先说清楚在哪儿被引用，人确认了才 force 删。
      const refs = (data && data.error && data.error.references) || [];
      const where = refs.map((r) => r.file + ':' + r.line).join('、');
      const again = confirm('正文还在引用它：' + (where || '（位置未知）') + '\n仍然删除？');
      if (!again) return;
      ({ status, data } = await wbSectionRequest(wb('/sections/delete'), { file, force: true }));
    }
    if (status !== 200) {
      toast('删除失败：' + wbErrorText(data, status));
      return;
    }
    await loadWorkbenchProject();
    renderWorkbenchSections();
    toast('已删除 ' + file);
  } catch (err) {
    toast('删除失败：' + err.message);
  }
}

/** 目录里的操作按钮：改名 / 删除。 */
function handleSectionAction(action, file) {
  if (!file) return;
  if (action === 'rename') renameWorkbenchSection(file);
  else if (action === 'delete') deleteWorkbenchSection(file);
}

/** 切到某一节：隐藏下拉是唯一事实来源，目录与源码都跟着它走。 */
function selectWorkbenchSection(file) {
  const select = $('#workbench-section-select');
  if (!select || !file) return;
  if (select.value === file) return;
  select.value = file;
  select.dispatchEvent(new Event('change'));
}

/** 源码 / 预览 两个视图的显隐与按钮状态。 */
function renderWbMode() {
  const preview = state.wbMode === 'preview';
  const sourcePane = $('#wb-source-pane');
  const previewPane = $('#wb-preview-pane');
  if (sourcePane) sourcePane.hidden = preview;
  if (previewPane) previewPane.hidden = !preview;
  const srcBtn = $('#btn-wb-mode-source');
  const pdfBtn = $('#btn-wb-mode-preview');
  if (srcBtn) srcBtn.classList.toggle('is-active', !preview);
  if (pdfBtn) pdfBtn.classList.toggle('is-active', preview);
  if (preview) renderWbPreviewHtml();
}

/** 切到预览：网页渲染当前节（不编译、不依赖 PDF）。 */
function setWbMode(mode) {
  state.wbMode = mode === 'preview' ? 'preview' : 'source';
  renderWbMode();
}

/** 去掉未转义的 % 注释。 */
function stripTexComment(line) {
  let out = '';
  for (let i = 0; i < line.length; i += 1) {
    if (line[i] === '%' && line[i - 1] !== '\\') break;
    out += line[i];
  }
  return out;
}

// ------------------------------------------- MathML：LaTeX 数学子集 → MathML
//
// 只认一小撮：分组、上下标、\frac、\sqrt、希腊字母、常用符号、
// \text/\mathrm/\mathbf、\left( \right)。认不出的命令原样显示（\foo），
// 不崩也不吞——论文里的公式什么写法都有，崩了就没法预览。

const TEX_GREEK = {
  alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε',
  zeta: 'ζ', eta: 'η', theta: 'θ', iota: 'ι', kappa: 'κ',
  lambda: 'λ', mu: 'μ', nu: 'ν', xi: 'ξ', pi: 'π', rho: 'ρ',
  sigma: 'σ', tau: 'τ', upsilon: 'υ', phi: 'φ', chi: 'χ',
  psi: 'ψ', omega: 'ω',
  Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ',
  Pi: 'Π', Sigma: 'Σ', Upsilon: 'Υ', Phi: 'Φ', Psi: 'Ψ',
  Omega: 'Ω', varphi: 'φ', varepsilon: 'ε', vartheta: 'θ',
};

const TEX_OPS = {
  cdot: '⋅', times: '×', pm: '±', mp: '∓', div: '÷',
  le: '≤', leq: '≤', ge: '≥', geq: '≥',
  ne: '≠', neq: '≠', equiv: '≡', approx: '≈', sim: '∼',
  propto: '∝', infty: '∞', partial: '∂', nabla: '∇',
  sum: '∑', prod: '∏', int: '∫', oint: '∮',
  in: '∈', ni: '∋', subset: '⊂', supset: '⊃', subseteq: '⊆',
  supseteq: '⊇', cup: '∪', cap: '∩',
  to: '→', rightarrow: '→', leftarrow: '←', Rightarrow: '⇒',
  Leftarrow: '⇐', leftrightarrow: '↔', mapsto: '↦',
  forall: '∀', exists: '∃', neg: '¬', lnot: '¬',
  land: '∧', lor: '∨', wedge: '∧', vee: '∨',
  ll: '≪', gg: '≫', angle: '∠', therefore: '∴', because: '∵',
  dots: '…', ldots: '…', cdots: '⋯',
};

const TEX_ESCAPED = {
  '%': '%', '&': '&', '#': '#', '$': '$', '_': '_',
  '{': '{', '}': '}', ' ': ' ',
};

/**
 * 一段 LaTeX 数学 → MathML。
 *
 * display=true 出 <math display="block">（独立成行），否则是行内公式。
 * 纯函数：同样的输入永远给同样的输出，不碰 DOM。
 */
function texMathToMathML(src, display) {
  const body = texMathParse(String(src == null ? '' : src));
  return '<math xmlns="http://www.w3.org/1998/Math/MathML" class="tex-math"'
    + (display ? ' display="block"' : '') + '>' + body + '</math>';
}

/** LaTeX 数学 → MathML 片段（没有 <math> 外壳）。 */
function texMathParse(src) {
  const s = String(src == null ? '' : src);
  let i = 0;

  /** 读一个命令：\name 或 \X。 */
  function readCommand() {
    const start = i;
    i += 1;
    if (i >= s.length) return { name: '', raw: '\\' };
    let name = '';
    if (/[a-zA-Z]/.test(s[i])) {
      while (i < s.length && /[a-zA-Z]/.test(s[i])) { name += s[i]; i += 1; }
    } else {
      name = s[i];
      i += 1;
    }
    return { name, raw: s.slice(start, i) };
  }

  /** 读一段花括号里的原文（不解析）：给 \text 用。 */
  function readRawGroup() {
    while (i < s.length && /\s/.test(s[i])) i += 1;
    if (i >= s.length) return '';
    if (s[i] !== '{') { const one = s[i]; i += 1; return one; }
    let depth = 0;
    let j = i;
    for (; j < s.length; j += 1) {
      if (s[j] === '\\') { j += 1; continue; }
      if (s[j] === '{') depth += 1;
      else if (s[j] === '}') { depth -= 1; if (depth === 0) { j += 1; break; } }
    }
    const inner = s.slice(i + 1, Math.max(i + 1, j - 1));
    i = j;
    return inner;
  }

  /** 读一个参数：{…} 解析成 mrow，单个字符就一个原子。 */
  function readArg() {
    while (i < s.length && /\s/.test(s[i])) i += 1;
    if (i >= s.length) return '<mrow></mrow>';
    if (s[i] === '{') { i += 1; return '<mrow>' + readSeq(true) + '</mrow>'; }
    return readAtom();
  }

  /** 一个原子：分组、命令、或者单个字符。 */
  function readAtom() {
    const ch = s[i];
    if (ch === undefined) return '';
    if (ch === '{') { i += 1; return '<mrow>' + readSeq(true) + '</mrow>'; }
    if (ch === '\\') return readCommandNode();
    if (/\s/.test(ch)) { i += 1; return ''; }
    if (/[0-9]/.test(ch)) {
      let n = '';
      while (i < s.length && /[0-9]/.test(s[i])) { n += s[i]; i += 1; }
      if (s[i] === '.') {
        n += '.';
        i += 1;
        while (i < s.length && /[0-9]/.test(s[i])) { n += s[i]; i += 1; }
      }
      return '<mn>' + esc(n) + '</mn>';
    }
    if (/[a-zA-Z]/.test(ch)) { i += 1; return '<mi>' + esc(ch) + '</mi>'; }
    i += 1;
    return '<mo>' + esc(ch) + '</mo>';
  }

  /** 一个命令：能认的转 MathML，认不出的原样显示。 */
  function readCommandNode() {
    const cmd = readCommand();
    const name = cmd.name;
    if (name === 'frac') {
      return '<mfrac>' + readArg() + readArg() + '</mfrac>';
    }
    if (name === 'sqrt') {
      while (i < s.length && /\s/.test(s[i])) i += 1;
      if (s[i] === '[') {          // 根指数：先不做，跳过它
        let depth = 0;
        while (i < s.length) {
          if (s[i] === '[') depth += 1;
          else if (s[i] === ']') { depth -= 1; if (depth === 0) { i += 1; break; } }
          i += 1;
        }
      }
      return '<msqrt>' + readArg() + '</msqrt>';
    }
    if (name === 'text' || name === 'textrm') {
      return '<mtext>' + esc(readRawGroup()) + '</mtext>';
    }
    if (name === 'mathrm' || name === 'operatorname') {
      return textVariant(readRawGroup(), 'normal');
    }
    if (name === 'mathbf' || name === 'bm' || name === 'boldsymbol') {
      return textVariant(readRawGroup(), 'bold');
    }
    if (name === 'mathit' || name === 'textit') {
      return textVariant(readRawGroup(), 'italic');
    }
    if (name === 'fact' || name === 'sys') {
      return '<mtext>' + esc(readRawGroup()) + '</mtext>';
    }
    if (name === 'fsignore') {
      return texMathToMathML(readRawGroup(), false);
    }
    if (name === 'toprule' || name === 'midrule' || name === 'bottomrule'
        || name === 'hline') {
      return '';
    }
    if (name === 'left' || name === 'right') {
      // \left( \right)：当普通括号处理
      while (i < s.length && /\s/.test(s[i])) i += 1;
      const ch = s[i];
      if (ch === undefined) return '';
      i += 1;
      if ('()[]|./'.indexOf(ch) < 0) return '<mo></mo>';
      return '<mo>' + esc(ch) + '</mo>';
    }
    if (name === '\\') return '';            // 行末换行：行内公式里当空白
    if (has(TEX_GREEK, name)) return '<mi>' + TEX_GREEK[name] + '</mi>';
    if (has(TEX_OPS, name)) return '<mo>' + TEX_OPS[name] + '</mo>';
    if (has(TEX_ESCAPED, name)) return '<mo>' + esc(TEX_ESCAPED[name]) + '</mo>';
    // 认不出的命令：原样显示，别吞、也别崩。
    return '<mtext class="tex-math-raw">' + esc(cmd.raw) + '</mtext>';
  }

  /** \mathrm / \mathbf：单个字母用 mi，长的用 mtext。 */
  function textVariant(raw, variant) {
    const body = String(raw == null ? '' : raw);
    if (body.length === 1 && /[a-zA-Z]/.test(body)) {
      return '<mi mathvariant="' + variant + '">' + esc(body) + '</mi>';
    }
    return '<mtext mathvariant="' + variant + '">' + esc(body) + '</mtext>';
  }

  /** 一串原子；^ 与 _ 取前一个原子做底（两个都有就合成 msubsup）。 */
  function readSeq(inGroup) {
    const out = [];
    let base = null;
    let sub = null;
    let sup = null;
    const flush = () => {
      if (base === null) return;
      if (sub !== null && sup !== null) {
        out.push('<msubsup>' + base + sub + sup + '</msubsup>');
      } else if (sub !== null) {
        out.push('<msub>' + base + sub + '</msub>');
      } else if (sup !== null) {
        out.push('<msup>' + base + sup + '</msup>');
      } else {
        out.push(base);
      }
      base = null;
      sub = null;
      sup = null;
    };
    while (i < s.length) {
      const ch = s[i];
      if (inGroup && ch === '}') { i += 1; break; }
      if (ch === '^' || ch === '_') {
        i += 1;
        const script = readAtom();
        if (base === null) base = '<mrow></mrow>';
        if (ch === '^') sup = script;
        else sub = script;
        continue;
      }
      const atom = readAtom();
      if (atom !== '') {
        flush();
        base = atom;
      }
    }
    flush();
    return out.join('');
  }

  return readSeq(false);
}

/** 行内 LaTeX 的最小子集：只做排版，不执行任何命令。 */
function latexInline(text) {
  const raw = String(text == null ? '' : text);
  // 数学先摘出来：转义之后再找 $…$ 就认不出里面的命令了。
  const maths = [];
  let s = raw.replace(/\$([^$]+)\$/g, (m, body) => {
    maths.push(texMathToMathML(body, false));
    return '\u0001' + maths.length + '\u0001';
  });
  s = esc(s);
  s = s.replace(/\\textbf\{([^{}]*)\}/g, '<strong>$1</strong>');
  s = s.replace(/\\emph\{([^{}]*)\}/g, '<em>$1</em>');
  s = s.replace(/\\textit\{([^{}]*)\}/g, '<em>$1</em>');
  s = s.replace(/\\texttt\{([^{}]*)\}/g, '<code>$1</code>');
  s = s.replace(/\\underline\{([^{}]*)\}/g, '<u>$1</u>');
  s = s.replace(/\\footnote\{([^{}]*)\}/g, '<span class="tex-fn">（$1）</span>');
  s = s.replace(/\\(?:cite|citep|citet|parencite|textcite|Cite|citeauthor)\{([^{}]*)\}/g,
    '<span class="tex-cite">[$1]</span>');
  s = s.replace(/\\(?:ref|autoref|cref|Cref|eqref|pageref)\{([^{}]*)\}/g,
    '<span class="tex-ref">($1)</span>');
  s = s.replace(/\\sys\{([^{}]*)\}/g, '<span class="tex-sys">sys($1)</span>');
  s = s.replace(/\\checkmark\b/g, '✓');
  s = s.replace(/\\(toprule|midrule|bottomrule|hline)\b/g, '');
  s = s.replace(/\\(begin|end)\{[^{}]*\}/g, '');
  s = s.replace(/\\fsignore\{([^{}]*)\}/g, '$1');
  s = s.replace(/\\input\{([^{}]*)\}/g, '<span class="tex-input">（含 $1）</span>');
  s = s.replace(/\\href\{[^{}]*\}\{([^{}]*)\}/g, '$1');
  s = s.replace(/\\url\{([^{}]*)\}/g, '<span class="tex-url">$1</span>');
  s = s.replace(/\\verb\|([^|]*)\|/g, '<code>$1</code>');
  s = s.replace(/\\(?:noindent|centering|footnotesize|small|large|Large|normalsize|par|medskip|smallskip|bigskip|newpage|clearpage|maketitle|tableofcontents)\b/g, '');
  s = s.replace(/\\(?:vspace|hspace|setlength|thispagestyle|pagestyle|bibliography|bibliographystyle)\*?\{[^{}]*\}(?:\{[^{}]*\})?/g, '');
  s = s.replace(/\\fact\{([^{}]*)\}/g, '<span class="tex-fact">$1</span>');
  s = s.replace(/\\label\{[^{}]*\}/g, '');
  s = s.replace(/\\([%&_#{}])/g, '$1');
  s = s.replace(/~/g, ' ');
  s = s.replace(/\\\\/g, '<br>');
  // 数学换回 MathML（放最后：里面的尖括号不该再被当成命令处理）。
  s = s.replace(/\u0001(\d+)\u0001/g, (m, n) => maths[Number(n) - 1] || '');
  return s;
}

/** 块级公式：align 用 \\ 分行，每行各出一个 <math display="block">。 */
function texMathBlockHtml(text) {
  const rows = String(text == null ? '' : text).split(/\\\\/);
  return rows
    .map((row) => row.trim())
    .filter((row) => row !== '')
    .map((row) => texMathToMathML(row, true))
    .join('');
}

function texBlockStart(line) {
  return /^\\(section|subsection|subsubsection|begin\{(itemize|enumerate|table|figure|equation|align)\}|\[)/.test(line)
    || line.startsWith('$$');
}

/** 把一节 LaTeX 渲染成网页预览（安全：先转义，再只做白名单替换）。 */
function latexToHtml(source) {
  const lines = String(source || '').replace(/\r/g, '').split('\n').map(stripTexComment);
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) { i += 1; continue; }
    let m;
    if ((m = /^\\section\*?\{(.+)\}/.exec(line))) {
      out.push('<h2>' + latexInline(m[1]) + '</h2>'); i += 1; continue;
    }
    if ((m = /^\\subsection\*?\{(.+)\}/.exec(line))) {
      out.push('<h3>' + latexInline(m[1]) + '</h3>'); i += 1; continue;
    }
    if ((m = /^\\subsubsection\*?\{(.+)\}/.exec(line))) {
      out.push('<h4>' + latexInline(m[1]) + '</h4>'); i += 1; continue;
    }
    if ((m = /^\\paragraph\*?\{(.+)\}/.exec(line))) {
      out.push('<h5>' + latexInline(m[1]) + '</h5>'); i += 1; continue;
    }
    if (/^\\begin\{itemize\}/.test(line) || /^\\begin\{enumerate\}/.test(line)) {
      const ordered = /^\\begin\{enumerate\}/.test(line);
      const items = [];
      i += 1;
      while (i < lines.length && !/^\\end\{(itemize|enumerate)\}/.test(lines[i].trim())) {
        const row = lines[i].trim();
        if (row.startsWith('\\item')) items.push(row.replace(/^\\item\s*/, ''));
        else if (row && items.length) items[items.length - 1] += ' ' + row;
        i += 1;
      }
      i += 1;
      out.push('<' + (ordered ? 'ol' : 'ul') + '>' +
        items.map((x) => '<li>' + latexInline(x) + '</li>').join('') +
        '</' + (ordered ? 'ol' : 'ul') + '>');
      continue;
    }
    if (/^\\begin\{(equation|align)\*?\}/.test(line) || line === '\\[') {
      const starred = /\*\}/.test(line);
      const close = line === '\\[' ? '\\]'
        : (/equation/.test(line) ? '\\end{equation}' : '\\end{align}').replace('}', starred ? '*}' : '}');
      const body = [];
      i += 1;
      while (i < lines.length && lines[i].trim() !== close) { body.push(lines[i]); i += 1; }
      i += 1;
      out.push('<div class="tex-math-block">' + texMathBlockHtml(body.join(' ')) + '</div>');
      continue;
    }
    if (line.startsWith('$$')) {
      // $$…$$：同行写完，或者跨行到下一个以 $$ 结尾的行。
      const body = [];
      const rest = line.slice(2);
      if (rest.length > 2 && rest.endsWith('$$')) {
        body.push(rest.slice(0, -2));
        i += 1;
      } else {
        if (rest.trim()) body.push(rest);
        i += 1;
        while (i < lines.length && !lines[i].trim().endsWith('$$')) { body.push(lines[i]); i += 1; }
        if (i < lines.length) {
          body.push(lines[i].trim().slice(0, -2));
          i += 1;
        }
      }
      out.push('<div class="tex-math-block">' + texMathBlockHtml(body.join(' ')) + '</div>');
      continue;
    }
    if (/^\\begin\{tabular\}/.test(line)) {
      const rows = [];
      i += 1;
      while (i < lines.length && !/^\\end\{tabular\}/.test(lines[i].trim())) { rows.push(lines[i]); i += 1; }
      i += 1;
      const cells = rows.join(' ').split(/\\\\/)
        .map((r) => r.replace(/\\(toprule|midrule|bottomrule|hline)/g, '').trim())
        .filter(Boolean)
        .map((r) => r.split('&').map((c) => c.trim()));
      if (cells.length) {
        out.push('<table class="tex-table"><thead><tr>' +
          cells[0].map((c) => '<th>' + latexInline(c) + '</th>').join('') +
          '</tr></thead><tbody>' +
          cells.slice(1).map((r) => '<tr>' + r.map((c) => '<td>' + latexInline(c) + '</td>').join('') + '</tr>').join('') +
          '</tbody></table>');
      }
      continue;
    }
    if (/^\\begin\{figure\*?\}/.test(line)) {
      let graphic = '';
      let caption = '';
      i += 1;
      while (i < lines.length && !/^\\end\{figure\*?\}/.test(lines[i].trim())) {
        const row = lines[i].trim();
        const g = /\\includegraphics(?:\[[^\]]*\])?\{([^{}]*)\}/.exec(row);
        if (g) graphic = g[1];
        const c = /\\caption\{([^{}]*)\}/.exec(row);
        if (c) caption = c[1];
        i += 1;
      }
      i += 1;
      out.push('<figure class="tex-figure">' + texFigureBody(graphic) +
        (caption ? '<figcaption>' + latexInline(caption) + '</figcaption>' : '') + '</figure>');
      continue;
    }
    if (/^\\begin\{table\*?\}/.test(line)) {
      let caption = '';
      let tableHtml = '';
      i += 1;
      while (i < lines.length && !/^\\end\{table\*?\}/.test(lines[i].trim())) {
        const row = lines[i].trim();
        const c = /\\caption\{([^{}]*)\}/.exec(row);
        if (c) caption = c[1];
        if (/^\\begin\{tabular\}/.test(row)) {
          const rows = [];
          i += 1;
          while (i < lines.length && !/^\\end\{tabular\}/.test(lines[i].trim())) { rows.push(lines[i]); i += 1; }
          const cells = rows.map((r) => r.replace(/\\(toprule|midrule|bottomrule|hline)/g, '')).join(' ')
            .split(/\\\\/).map((r) => r.trim()).filter(Boolean)
            .map((r) => r.split('&').map((cell) => cell.trim()));
          if (cells.length) {
            tableHtml = '<table class="tex-table">' +
              (caption ? '<caption>' + latexInline(caption) + '</caption>' : '') +
              '<thead><tr>' + cells[0].map((cell) => '<th>' + latexInline(cell) + '</th>').join('') +
              '</tr></thead><tbody>' +
              cells.slice(1).map((r) => '<tr>' + r.map((cell) => '<td>' + latexInline(cell) + '</td>').join('') + '</tr>').join('') +
              '</tbody></table>';
            caption = '';
          }
        }
        i += 1;
      }
      i += 1;
      if (tableHtml) out.push(tableHtml);
      else if (caption) out.push('<p class="tex-caption">' + latexInline(caption) + '</p>');
      continue;
    }
    if (/^\\end\{table\*?\}/.test(line)) { i += 1; continue; }

    if (/^\\begin\{(abstract|quote|quotation)\}/.test(line)) {
      const env = /^\\begin\{(abstract|quote|quotation)\}/.exec(line)[1];
      const close = '\\end{' + env + '}';
      const body = [];
      i += 1;
      while (i < lines.length && lines[i].trim() !== close) { body.push(lines[i]); i += 1; }
      i += 1;
      const inner = latexToHtml(body.join('\n'));
      out.push(env === 'abstract'
        ? '<div class="tex-abstract"><h3>摘要</h3>' + inner + '</div>'
        : '<blockquote>' + inner + '</blockquote>');
      continue;
    }

    if (/^\\begin\{description\}/.test(line)) {
      const items = [];
      i += 1;
      while (i < lines.length && !/^\\end\{description\}/.test(lines[i].trim())) {
        const row = lines[i].trim();
        const mm = /^\\item\[([^\]]*)\]\s*(.*)$/.exec(row);
        if (mm) items.push('<dt>' + latexInline(mm[1]) + '</dt><dd>' + latexInline(mm[2]) + '</dd>');
        else if (row && items.length) items[items.length - 1] += latexInline(row);
        i += 1;
      }
      i += 1;
      out.push('<dl class="tex-desc">' + items.join('') + '</dl>');
      continue;
    }
    if (/^\\(begin|end)\{/.test(line)) { i += 1; continue; }
    // 普通段落：一直收，直到空行或下一个块
    const para = [line];
    i += 1;
    while (i < lines.length) {
      const row = lines[i].trim();
      if (!row || texBlockStart(row)) break;
      para.push(row); i += 1;
    }
    out.push('<p>' + latexInline(para.join(' ')) + '</p>');
  }
  return out.join('\n');
}

/**
 * figure 里的图：走 /api/asset 读项目里的图片（PDF 由服务端转成 PNG）。
 *
 * 读不出来（文件不在、路径越界、服务端没装 poppler）时显示文件名占位，
 * 不留一个破图。
 */
function texFigureBody(graphic) {
  const name = String(graphic == null ? '' : graphic).trim();
  if (!name) return '<div class="tex-figure-box">图</div>';
  const onerr = "this.outerHTML='<span class=&quot;tex-img-missing&quot;>'"
    + "+(this.dataset.missing||'')+'</span>'";
  return '<div class="tex-figure-box">'
    + '<img class="tex-img" src="' + esc(assetUrl(name)) + '" alt="' + esc(name) + '"'
    + ' data-missing="' + esc(name) + '" onerror="' + onerr + '">'
    + '</div>';
}

/** 把当前节渲染进预览框。 */
function renderWbPreviewHtml() {
  const box = $('#wb-preview-html');
  if (!box) return;
  const file = $('#workbench-section-select')?.value || '';
  if (!file) {
    box.innerHTML = '<div class="line-empty">先选一节。</div>';
    return;
  }
  const text = $('#workbench-section-text')?.value || '';
  box.innerHTML = latexToHtml(text) || '<div class="line-empty">这一节没有内容。</div>';
}

// ------------------------------------- 源码高亮：pre 叠在 textarea 底下
//
// textarea 的文字是透明的（只留光标），底下那层 pre 显示带颜色的同一份文本。
// 两层的字体、行高、内边距必须完全一致，否则光标会跟字错行。
//
// 高亮是自己写的，不引第三方：LaTeX 的高亮规则就那么几条，
// 一条正则 + 一点优先级就够，犯不着为一屏高亮拉一个依赖进来。

// 超过这个大小就不高亮了：每敲一个字都重画一遍大文件，输入会卡。
const HIGHLIGHT_MAX_CHARS = 200 * 1024;

/**
 * 一段 LaTeX → 带 span 的 HTML。
 *
 * 先转义，再按优先级包 span：注释 > 环境 > 命令 > 转义符 > 数学 > 花括号 > 数字。
 * 注释优先级最高（% 后面的都是注释），环境先于命令（\begin{…} 不是命令）。
 */
function highlightTex(text) {
  const src = String(text == null ? '' : text);
  const re = /(%[^\n]*)|(\\(?:begin|end)\{[^{}]*\})|(\\[a-zA-Z]+)|(\\[^a-zA-Z\s])|(\$[^$\n]*\$)|([{}])|(\d+(?:\.\d+)?)/g;
  let out = '';
  let last = 0;
  let m;
  while ((m = re.exec(src)) !== null) {
    out += esc(src.slice(last, m.index));
    const cls = m[1] ? 'tx-comment'
      : m[2] ? 'tx-env'
      : (m[3] || m[4]) ? 'tx-cmd'
      : m[5] ? 'tx-math'
      : m[6] ? 'tx-brace'
      : 'tx-num';
    out += '<span class="' + cls + '">' + esc(m[0]) + '</span>';
    last = m.index + m[0].length;
  }
  out += esc(src.slice(last));
  return out;
}

/** 高亮层跟着源码走：输入、切节、插入片段之后都调它。 */
function updateHighlight() {
  const ta = $('#workbench-section-text');
  const pre = $('#wb-highlight');
  if (!ta || !pre) return;
  const code = pre.querySelector('code');
  const note = $('#wb-highlight-note');
  const text = ta.value || '';
  if (text.length > HIGHLIGHT_MAX_CHARS) {
    // 太大的文件不高亮：说清楚为什么关了，别让人以为是坏了。
    if (code) code.textContent = '';
    if (note) {
      note.textContent = '这一节超过 200 KB，已关闭语法高亮（输入更流畅）。';
      note.hidden = false;
    }
    return;
  }
  if (note) {
    note.textContent = '';
    note.hidden = true;
  }
  // 末尾补一个换行：textarea 永远多出最后一行，高亮层也得有，两层才等高。
  if (code) code.innerHTML = highlightTex(text) + '\n';
  syncHighlightMetrics();
  syncHighlightScroll();
}

/** 滚动同步：输入框滚到哪，高亮层跟到哪（不然两层的字会错行）。 */
function syncHighlightScroll() {
  const ta = $('#workbench-section-text');
  const pre = $('#wb-highlight');
  if (!ta || !pre) return;
  pre.scrollTop = ta.scrollTop;
  pre.scrollLeft = ta.scrollLeft;
}

/** 输入框有滚动条时，把它占掉的宽度补回高亮层：两层的字才对得上。 */
function syncHighlightMetrics() {
  const ta = $('#workbench-section-text');
  const pre = $('#wb-highlight');
  if (!ta || !pre) return;
  const style = window.getComputedStyle(ta);
  const border = (parseFloat(style.borderLeftWidth) || 0)
    + (parseFloat(style.borderRightWidth) || 0);
  const bar = Math.max(0, (ta.offsetWidth - ta.clientWidth) - border);
  if (pre.dataset.basePad === undefined) {
    pre.dataset.basePad = String(parseFloat(style.paddingRight) || 0);
  }
  pre.style.paddingRight = (parseFloat(pre.dataset.basePad) + bar) + 'px';
}

/** 问题的位置能不能跳：正文:N 跳当前节；<节文件>:<行> 跳那一节那一行。 */
function jumpTargetFor(location) {
  const loc = String(location || '');
  let m = /^正文:(\d+)$/.exec(loc);
  if (m) {
    return { file: $('#workbench-section-select')?.value || '', line: Number(m[1]) };
  }
  m = /^([^:]+):(\d+)(?::\d+)?$/.exec(loc);
  if (!m) return null;
  const file = m[1];
  const known = (state.workbenchProject?.sections || []).some((s) => s.file === file);
  if (!known) return null;
  return { file, line: Number(m[2]) };
}

/** 跳到源码的某一行：滚动过去并选中那一行。 */
function jumpToLine(file, line) {
  const ta = $('#workbench-section-text');
  if (!ta) return;
  if (file) selectWorkbenchSection(file);
  const lines = (ta.value || '').split('\n');
  const target = Math.max(1, Math.min(Number(line) || 1, lines.length));
  let start = 0;
  for (let i = 0; i < target - 1; i += 1) start += lines[i].length + 1;
  const end = start + lines[target - 1].length;
  state.wbMode = 'source';
  renderWbMode();
  ta.focus();
  ta.setSelectionRange(start, end);
  const style = window.getComputedStyle(ta);
  const lineHeight = parseFloat(style.lineHeight) || 23;
  ta.scrollTop = Math.max(0, (target - 3) * lineHeight);
}

// ------------------------------------- 工作台：快捷插入 / 右栏互斥 / AI 聊天
//
// 快捷插入：在光标处插入模板，槽位（{} 里）自动落到光标上。
// 右栏：问题与 AI 聊天互斥，同时只显示一个。
// 聊天：历史按项目存在本地（factscribe.chat.<项目路径>），刷新后还在。

/** 模板里的槽位：第一个空的 {}；没有就找第一个不是环境参数的 {…}。 */
function snippetSlot(template) {
  const empty = template.indexOf('{}');
  if (empty >= 0) return { start: empty + 1, end: empty + 1 };
  for (let i = 0; i < template.length; i += 1) {
    if (template[i] !== '{') continue;
    const close = template.indexOf('}', i);
    if (close < 0) break;
    // \begin{...} / \end{...} 是环境名，不是让人填的槽位。
    if (/\\(begin|end)$/.test(template.slice(Math.max(0, i - 6), i))) {
      i = close;
      continue;
    }
    return { start: close, end: close };
  }
  return null;
}

/** 插入后光标停在哪：槽位 > data-caret（mid 或锚点子串）> 文末。 */
function snippetCaret(template, spec) {
  const slot = snippetSlot(template);
  if (slot) return slot;
  if (spec === 'mid') {
    const at = Math.floor(template.length / 2);
    return { start: at, end: at };
  }
  if (spec && spec !== 'end') {
    const at = template.indexOf(spec);
    if (at >= 0) return { start: at + spec.length, end: at + spec.length };
  }
  return { start: template.length, end: template.length };
}

/** 在光标处插入一段模板；槽位落在花括号里，直接接着写。 */
function insertSnippet(template, spec) {
  const ta = $('#workbench-section-text');
  if (!ta) return;
  if (ta.readOnly) {
    toast('只读工作台：写操作需要 --allow-write');
    return;
  }
  const value = ta.value;
  const start = typeof ta.selectionStart === 'number' ? ta.selectionStart : value.length;
  const end = typeof ta.selectionEnd === 'number' ? ta.selectionEnd : start;
  const caret = snippetCaret(template, spec);
  ta.value = value.slice(0, start) + template + value.slice(end);
  const at = start + caret.start;
  ta.focus();
  ta.setSelectionRange(at, start + caret.end);
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  updateHighlight();
}

/** 右栏：问题与 AI 聊天互斥，同时只显示一个。 */
function renderWbSide() {
  const side = state.wbSide === 'ai' ? 'ai' : 'issues';
  const issues = $('#wb-side-issues');
  const ai = $('#wb-side-ai');
  if (issues) issues.hidden = side !== 'issues';
  if (ai) ai.hidden = side !== 'ai';
  const issuesBtn = $('#btn-wb-side-issues');
  const aiBtn = $('#btn-wb-side-ai');
  if (issuesBtn) issuesBtn.classList.toggle('is-active', side === 'issues');
  if (aiBtn) aiBtn.classList.toggle('is-active', side === 'ai');
}

/** 聊天历史存在本地：键是 factscribe.chat.<项目路径>，刷新后还在。 */
const CHAT_KEY_PREFIX = 'factscribe.chat.';

function chatStorageKey() {
  const root = String(state.workbenchProject?.root || state.projectPath || '');
  return root ? CHAT_KEY_PREFIX + root : '';
}

/** 换项目才换历史：同一个项目时内存里那份已经是最新的。 */
function loadChat() {
  const key = chatStorageKey();
  if (key === state.chatKey) return;
  state.chatKey = key;
  state.chat = [];
  state.chatApprovals = [];
  if (key) {
    try {
      const raw = localStorage.getItem(key);
      const list = raw ? JSON.parse(raw) : [];
      if (Array.isArray(list)) {
        state.chat = list.filter((m) => m && typeof m.text === 'string' &&
          (m.role === 'user' || m.role === 'assistant'));
      }
    } catch {
      state.chat = [];
    }
  }
  renderChat();
}

function saveChat() {
  const key = chatStorageKey();
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(state.chat));
  } catch {
    // 存不下就算了：聊天照常显示，只是不留历史。
  }
}

/** 聊天区那行说明（网页模式下说清为什么发不了）。 */
function setChatNotice(text) {
  const el = $('#wb-chat-notice');
  if (el) el.textContent = String(text || '');
}

/** 聊天记录：用户靠右、助手靠左；有新消息就滚到底部。 */
function renderChat() {
  const log = $('#wb-chat-log');
  if (!log) return;
  const msgs = state.chat.map((m) =>
    '<div class="wb-msg wb-msg-' + (m.role === 'user' ? 'user' : 'ai') + '">' +
    '<div class="wb-msg-role">' + (m.role === 'user' ? '我' : 'AI') + '</div>' +
    '<div class="wb-msg-text">' + esc(m.text) + '</div></div>').join('');
  const approvals = state.chatApprovals.map((a) =>
    '<div class="approval-card"><b>工具等待批准：' + esc(a.toolName || '') + '</b>' +
    (a.reason ? '<div class="muted-note">' + esc(a.reason) + '</div>' : '') +
    (a.toolInput ? '<code>' + esc(String(a.toolInput).slice(0, 500)) + '</code>' : '') +
    '<div class="approval-actions">' +
    '<button class="btn btn-primary" data-chat-approval="' + esc(a.id) + '" data-decision="allowOnce">允许一次</button>' +
    '<button class="btn" data-chat-approval="' + esc(a.id) + '" data-decision="deny">拒绝</button>' +
    '</div></div>').join('');
  log.innerHTML = msgs || '<div class="line-empty">还没有对话。问一句，或让 AI 按事实账改这一节。</div>';
  if (approvals) log.insertAdjacentHTML('beforeend', approvals);
  log.scrollTop = log.scrollHeight;
}

/** 发一条：提示里带上当前节与事实账（复用 AI 起草那套拼提示）。 */
async function sendChat() {
  const input = $('#wb-chat-input');
  const text = String(input?.value || '').trim();
  if (!text) return;
  if (!MODE.mini) {
    setChatNotice('网页模式不能起草：需要 MiniApp 宿主');
    return;
  }
  const agent = aiAgent();
  if (!agent?.run) {
    setChatNotice('当前页面没有宿主 agent；请从论文项目的对话里打开本页');
    return;
  }
  state.chat.push({ role: 'user', text });
  input.value = '';
  const reply = { role: 'assistant', text: '' };
  state.chat.push(reply);
  renderChat();
  const requestId = (globalThis.crypto?.randomUUID?.() || ('chat-' + Date.now() + '-' + Math.random()));
  try {
    const result = await agent.run({ text: buildSectionPrompt(text), requestId },
      { onEvent: (e) => handleChatEvent(e, reply) });
    if (result?.text) reply.text = result.text;
    if (result?.error) reply.text += (reply.text ? '\n' : '') + 'Agent 错误：' + result.error;
    if (result?.pendingQuestion) reply.text += (reply.text ? '\n' : '') + 'Agent 在等问卷；请到聊天侧面板回答。';
  } catch (err) {
    reply.text = '发送失败：' + (err?.message || err);
  }
  renderChat();
  saveChat();
}

/** 聊天里的流式事件：文字直接追加到当前那条助手消息。 */
function handleChatEvent(event, reply) {
  if (!event || typeof event !== 'object') return;
  if (event.type === 'text.delta') {
    reply.text += event.text || '';
  } else if (event.type === 'message.committed') {
    if (event.text) reply.text = event.text;
  } else if (event.type === 'permission.requested') {
    state.chatApprovals.push({ id: event.requestId, sessionId: event.sessionId,
      toolName: event.toolName, reason: event.reason, toolInput: event.toolInput });
  } else if (event.type === 'error') {
    reply.text += (reply.text ? '\n' : '') + '错误：' + (event.message || event.text || '');
  }
  renderChat();
}

/** 审批卡：允许一次 / 拒绝。 */
async function replyChatApproval(id, decision) {
  const agent = aiAgent();
  const item = state.chatApprovals.find((a) => String(a.id) === String(id));
  if (!agent?.reply || !item) return;
  await agent.reply({ sessionId: item.sessionId, requestId: item.id, decision });
  state.chatApprovals = state.chatApprovals.filter((a) => a !== item);
  renderChat();
}


// ------------------------------------------------ 工作台：事实账 / 证据 / 编译
// 这三块原来只在本地面板里；统一界面后 MiniApp 和网页共用，走同一套 Python 判据。

function renderWorkbenchFacts() {
  const project = state.workbenchProject;
  const facts = project?.facts || [];
  const sources = project?.sources || [];
  const count = $('#wb-facts-count');
  if (count) count.textContent = facts.length ? '（' + facts.length + ' 条）' : '（还没有事实）';
  const sourcesBox = $('#wb-fact-sources');
  if (sourcesBox) {
    sourcesBox.innerHTML = sources.map((s) => '<option value="' + esc(s.id) + '"></option>').join('');
  }
  const form = $('#wb-fact-form');
  if (form) form.hidden = Boolean(project?.read_only);
  // 只读工作台：追加事实要写盘，右上角的入口一并灰掉并说清原因。
  const addBtn = $('#btn-wb-fact-add');
  if (addBtn) {
    addBtn.disabled = Boolean(project?.read_only);
    addBtn.title = project?.read_only ? t('wb.readOnly') : '';
  }
  const box = $('#wb-facts');
  if (!box) return;
  if (!facts.length) {
    box.innerHTML = '<div class="line-empty">' + t('empty.noFacts') + '</div>';
    return;
  }
  box.innerHTML = '<table class="facts-table"><thead><tr><th>ID</th><th>主张</th><th>值</th><th>来源</th></tr></thead><tbody>' +
    facts.map((f) => '<tr><td>' + esc(f.id) + '</td><td>' + esc(f.claim) +
      '</td><td class="code">' + esc(f.value) + '</td><td class="code">' + esc(f.source) +
      '</td></tr>').join('') + '</tbody></table>';
}

/** 事实账右上角：展开追加事实的表单，滚过去并把焦点放到 ID 栏。 */
function openFactForm() {
  const card = $('#wb-fact-card');
  if (card) {
    card.open = true;
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  const id = $('#wb-fact-id');
  if (id) id.focus();
}

async function addWorkbenchFact(event) {
  event.preventDefault();
  const body = {
    id: $('#wb-fact-id').value.trim(),
    claim: $('#wb-fact-claim').value.trim(),
    value: $('#wb-fact-value').value.trim(),
    source: $('#wb-fact-source').value.trim(),
    locator: $('#wb-fact-locator').value.trim(),
    confidence: $('#wb-fact-confidence').value,
    derived_from: $('#wb-fact-derived').value.trim(),
    expr: $('#wb-fact-expr').value.trim(),
    note: $('#wb-fact-note').value.trim(),
  };
  if (!body.id || !body.claim || !body.value || !body.source) throw new Error('ID、主张、值、来源都要填');
  if (body.derived_from && !body.expr) throw new Error('填了推算父项就要填算式');
  if (body.expr && !body.derived_from) throw new Error('填了算式就要填推算父项');
  const data = await api(wb('/facts'), { method: 'POST', body: JSON.stringify(body) });
  $('#wb-fact-result').textContent = '已追加 ' + data.id + '。该抄进清单：' +
    (data.manifest_line || '（看服务输出）');
  $('#wb-fact-form').reset();
  toast('已追加 ' + data.id);
  // 引导条第 ③ 步：往事实账里补过一条也算「改了一处」。
  state.guide.edited = true;
  await loadWorkbenchProject();
  await runWorkbenchAudit();
}

function renderWorkbenchEvidence() {
  const e = state.wbEvidence || {};
  const meta = $('#wb-evidence-meta');
  if (meta) meta.textContent = e.lock ? '已冻结' : '未冻结';
  const bits = [];
  if (e.defined === false) bits.push('未声明 [evidence]');
  if (e.lock) {
    bits.push('lock ' + String(e.lock.sha256 || '').slice(0, 12) + ' · ' +
      esc(e.lock.entries) + ' 条');
  }
  if (e.mismatch) bits.push('<span class="chip chip-red">清单与冻结件不一致</span>');
  if (e.unfrozen) bits.push('<span class="chip chip-yellow">已解冻：' + esc(e.unfrozen.reason || '') + '</span>');
  if (e.log?.action) bits.push('最后动作 ' + esc(e.log.action));
  const box = $('#wb-evidence');
  if (!box) return;
  box.innerHTML = bits.length
    ? bits.map((b) => '<div class="muted-note">' + b + '</div>').join('')
    : '<div class="line-empty">没有冻结记录。</div>';
}

async function loadWorkbenchEvidence() {
  if (!state.workbenchProject) return;
  state.wbEvidence = await api(wb('/evidence'));
  renderWorkbenchEvidence();
}

// --------------------------------------------------------- 实验报告（工作台）

/** 下拉里的一项：实验 / 报告文件 · 状态。 */
function reportOptionLabel(r) {
  const exp = r.experiment || '（未标实验）';
  const name = String(r.path || '').split('/').pop();
  return exp + ' / ' + name + ' · ' + reportStatusWord(r.status);
}

// 报告状态词：引擎给的是 final / partial / superseded，翻译成人话。
const REPORT_STATUS_WORD = {
  final: 'report.final',
  partial: 'report.partial',
  superseded: 'report.superseded',
};

function reportStatusWord(status) {
  const key = REPORT_STATUS_WORD[status];
  return key ? t(key) : (status || t('report.unknownStatus'));
}

function selectedReport() {
  const list = (state.wbReports?.reports) || [];
  const path = $('#wb-report-select')?.value || '';
  return list.find((r) => r.path === path) || null;
}

function renderWorkbenchReports() {
  const data = state.wbReports || {};
  const list = data.reports || [];
  const meta = $('#wb-reports-meta');
  if (meta) {
    meta.textContent = list.length ? list.length + ' 份报告' : '';
  }
  const select = $('#wb-report-select');
  if (select) {
    const previous = select.value;
    select.innerHTML = list.length
      ? list.map((r) => '<option value="' + esc(r.path) + '">' +
          esc(reportOptionLabel(r)) + '</option>').join('')
      : '<option value="">（没有报告）</option>';
    if (previous && list.some((r) => r.path === previous)) select.value = previous;
  }
  const box = $('#wb-reports');
  if (box) {
    const notes = [];
    if (!state.workbenchProject) {
      notes.push(t('empty.needWorkbenchReports'));
    }
    if (state.workbenchProject?.read_only) {
      notes.push('只读工作台：启动时没加 --allow-write，封存/签收/导入用不了。');
    }
    if (data.error) notes.push('报告列表读不出来：' + data.error);
    if (!list.length && !notes.length) {
      notes.push(t('empty.noReports'));
    }
    box.innerHTML = notes
      .map((n) => '<div class="muted-note">' + esc(n) + '</div>').join('');
  }
  // 没有报告时按钮必须禁用：让用户点了再报错是最差的选择
  const hasReport = Boolean(selectedReport());
  const readOnly = Boolean(state.workbenchProject?.read_only);
  for (const [id, needsWrite] of [['check', false], ['lock', true],
    ['sign', true], ['import', true]]) {
    const btn = $('#btn-wb-report-' + id);
    if (!btn) continue;
    const blocked = !hasReport || (needsWrite && readOnly);
    btn.disabled = blocked;
    btn.title = !hasReport ? '先让实验产出一份 report.toml（experiments/*/reports/）'
      : (needsWrite && readOnly ? '启动时没加 --allow-write' : '');
  }
  // 新建模板要写盘：只读工作台不许点。
  const newBtn = $('#btn-report-new');
  if (newBtn) {
    newBtn.disabled = readOnly;
    newBtn.title = readOnly ? '启动时没加 --allow-write' : '';
  }
  renderReportState(selectedReport());
  renderReportCard(selectedReport(), list.length);
}

/** 状态行：状态 · 封存 · 签收（不行就说原因）。 */
function renderReportState(item) {
  const el = $('#wb-report-state');
  if (!el) return;
  if (!item) {
    el.textContent = '';
    return;
  }
  const bits = [reportStatusWord(item.status)];
  bits.push(item.lock_ok ? t('report.locked') : (item.locked ? t('report.lockStale') : t('report.unlocked')));
  bits.push(item.signed ? t('report.signed') : t('report.unsigned'));
  let text = bits.join(' · ');
  if (item.reason) text += '（' + item.reason + '）';
  el.textContent = text;
}

/** 审阅卡：逐行显示，不截断——截掉的那行等于人没看见却签了字。 */
function renderReportCard(item, count) {
  const box = $('#wb-report-card');
  if (!box) return;
  if (!state.workbenchProject) {
    box.innerHTML = '<div class="line-empty">' + t('empty.needWorkbenchCard') + '</div>';
    return;
  }
  if (!item) {
    box.innerHTML = count
      ? '<div class="line-empty">' + t('empty.noReportSelected') + '</div>'
      : '<div class="line-empty">' + t('empty.noReports') + '</div>';
    return;
  }
  const lines = item.card || [];
  if (!lines.length) {
    box.innerHTML = '<div class="line-empty">' + t('empty.noReviewCard') + '</div>';
    return;
  }
  box.innerHTML = '<div class="wb-report-card-title">审阅卡</div>' +
    lines.map((line) => '<div class="wb-report-line">' + esc(line) + '</div>').join('');
}

async function loadWorkbenchReports() {
  if (!state.workbenchProject || state.wbReportsLoading) return;
  state.wbReportsLoading = true;
  try {
    state.wbReports = await api(wb('/reports'));
  } catch (err) {
    state.wbReports = { workspace: '', reports: [], error: err.message };
  } finally {
    state.wbReportsLoading = false;
  }
  renderWorkbenchReports();
}

/** 今天的日期串：report-YYYYMMDD。 */
function reportIdStamp() {
  const now = new Date();
  const ymd = String(now.getFullYear())
    + String(now.getMonth() + 1).padStart(2, '0')
    + String(now.getDate()).padStart(2, '0');
  return 'report-' + ymd;
}

/**
 * 报告页右上角：新建一份报告模板。
 *
 * 报告下拉空着是因为报告由实验脚本产出；这里给一个起点——
 * 在工作区的 reports/ 下写一份带注释的 toml，人填完 metrics 就能走
 * 「检查 → 封存 → 签收 → 导入」。
 */
async function newReportTemplate() {
  const raw = prompt(t('report.newPrompt'), reportIdStamp());
  if (raw === null) return;
  const id = String(raw).trim();
  if (!id) {
    toast(t('report.newNeedId'));
    return;
  }
  const data = await api(wb('/reports/template'), {
    method: 'POST',
    body: JSON.stringify({ id }),
  });
  await loadWorkbenchReports();
  // 选中新报告：一眼看到自己刚建的那份。
  const select = $('#wb-report-select');
  if (select && data.path) select.value = data.path;
  renderReportState(selectedReport());
  renderReportCard(selectedReport(), (state.wbReports?.reports || []).length);
  const el = $('#wb-report-state');
  if (el) el.textContent = t('report.templateCreated');
  toast(t('report.templateCreated'));
}

// ------------------------------------------------------------------ 引用页
//
// 多个 bib 汇总 + 每条的状态。只读：这里不编辑 bib，也不联网核对
// （联网核对仍然走 audit）。状态短名：ok 有标识 / no_id 缺 DOI/arXiv /
// bad_id 标识不合法 / unused 未引用。

const CITE_STATUS = {
  ok: { label: 'cite.statusOk', chip: 'ok' },
  no_id: { label: 'cite.statusNoId', chip: 'warn' },
  bad_id: { label: 'cite.statusBadId', chip: 'bad' },
  duplicate: { label: 'cite.duplicate', chip: 'bad' },
  unused: { label: 'cite.statusUnused', chip: 'mute' },
};

/** 状态短名：中文标签 + 颜色（颜色之外还有字，色盲也读得出）。 */
function citeStatusChip(status) {
  const item = CITE_STATUS[status] || CITE_STATUS.ok;
  return '<span class="num-chip ' + item.chip + '">' + esc(t(item.label)) + '</span>';
}

/** 当前过滤下的条目：all / no-id（缺标识）/ unused（正文没引到）。 */
function citeFiltered(data) {
  const rows = data.entries || [];
  const filter = state.citeFilter;
  if (filter === 'no-id') return rows.filter((r) => r.status === 'no_id');
  if (filter === 'unused') return rows.filter((r) => Number(r.used || 0) <= 0);
  return rows;
}

function renderCitations() {
  const data = state.wbCitations || {};
  const rows = data.entries || [];
  const files = data.files || [];
  const readOnly = Boolean(state.workbenchProject?.read_only);
  // 只读工作台：改 bib 要写盘，添加与删除都灰掉并说清原因。
  const addBtn = $('#btn-cite-add');
  if (addBtn) {
    addBtn.disabled = readOnly;
    addBtn.title = readOnly ? t('wb.readOnly') : '';
  }
  for (const btn of $$('.cite-filter')) {
    const on = (btn.dataset.filter || 'all') === state.citeFilter;
    btn.classList.toggle('is-active', on);
    btn.setAttribute('aria-pressed', String(on));
  }
  const summary = $('#cite-summary');
  if (summary) {
    summary.textContent = rows.length
      ? tf('cite.summary', {
        total: data.total ?? rows.length,
        used: data.used ?? 0,
        unused: data.unused ?? 0,
        noId: data.no_id ?? 0,
        dup: data.duplicate ?? 0,
        files: files.length,
      })
      : '';
  }
  const filesBox = $('#cite-files');
  if (filesBox) {
    filesBox.innerHTML = files.length
      ? files.map((f) => '<span class="cite-file"><span class="cite-file-path">' +
        esc(f.path) + '</span><span class="cite-file-count">' +
        esc(tf('cite.fileCount', { n: f.entries ?? 0 })) + '</span></span>').join('')
      : '';
  }
  const tbody = $('#cite-tbody');
  if (!tbody) return;
  if (!state.workbenchProject) {
    tbody.innerHTML = '<tr class="table-empty-row"><td colspan="6">' +
      esc(t('cite.needProject')) + '</td></tr>';
    return;
  }
  if (data.error) {
    tbody.innerHTML = '<tr class="table-empty-row"><td colspan="6">' +
      esc(t('cite.error') + data.error) + '</td></tr>';
    return;
  }
  if (!files.length) {
    tbody.innerHTML = '<tr class="table-empty-row"><td colspan="6">' +
      esc(t('cite.empty')) + '</td></tr>';
    return;
  }
  const shown = citeFiltered(data);
  if (!shown.length) {
    tbody.innerHTML = '<tr class="table-empty-row"><td colspan="6">' +
      esc(t('cite.none')) + '</td></tr>';
    return;
  }
  tbody.innerHTML = shown.map((r) => {
    const id = r.doi || r.arxiv || r.url || '';
    const dup = r.duplicate
      ? '<span class="cite-dup">' + esc(t('cite.duplicate')) + '</span>' : '';
    const where = (r.files || []).length > 1
      ? '<div class="cite-row-files">' + esc((r.files || []).join(' · ')) + '</div>' : '';
    return '<tr>'
      + '<td class="mono" title="' + esc((r.file || '') + ':' + (r.line || 0)) + '">'
      + esc(r.key) + dup + where + '</td>'
      + '<td>' + esc(r.title || '—') + '</td>'
      + '<td class="mono">' + esc(id || '—') + '</td>'
      + '<td class="cell-num">' + esc(String(r.used ?? 0)) + '</td>'
      + '<td>' + citeStatusChip(r.status) + '</td>'
      + '<td class="cite-act">'
      + '<button class="btn btn-danger cite-del" type="button" data-cite-delete="'
      + esc(r.key) + '"' + (readOnly ? ' disabled' : '') + '>'
      + esc(t('btn.delete')) + '</button></td>'
      + '</tr>';
  }).join('');
}

async function loadCitations() {
  if (!state.workbenchProject || state.citeLoading) return;
  state.citeLoading = true;
  try {
    state.wbCitations = await api(wb('/citations'));
  } catch (err) {
    state.wbCitations = {
      total: 0, used: 0, unused: 0, no_id: 0, bad_id: 0,
      files: [], entries: [], error: err.message,
    };
  } finally {
    state.citeLoading = false;
  }
  renderCitations();
}

/** 引用页右上角：展开添加引用的内联表单。 */
function openCiteForm() {
  const form = $('#cite-form');
  if (form) form.hidden = false;
  const key = $('#cite-key');
  if (key) key.focus();
}

/** 收起添加引用的表单（取消 / 提交完都走这里）。 */
function closeCiteForm() {
  const form = $('#cite-form');
  if (form) form.hidden = true;
}

/** 提交：把这一条追加到项目的 cfg.bib（后端原子写），然后刷新列表。 */
async function addCitation(event) {
  event.preventDefault();
  const body = {
    key: ($('#cite-key')?.value || '').trim(),
    title: ($('#cite-title')?.value || '').trim(),
    author: ($('#cite-author')?.value || '').trim(),
    year: ($('#cite-year')?.value || '').trim(),
    doi: ($('#cite-doi')?.value || '').trim(),
    arxiv: ($('#cite-arxiv')?.value || '').trim(),
  };
  if (!body.key) throw new Error(t('cite.needKey'));
  await api(wb('/citations/add'), {
    method: 'POST',
    body: JSON.stringify(body),
  });
  const form = $('#cite-form');
  if (form) form.reset();
  closeCiteForm();
  await loadCitations();
  toast(t('cite.added'));
}

/** 删一条：先问人，确认了才调接口（删 bib 里的东西不是能顺手做的事）。 */
async function deleteCitation(key) {
  if (!key) return;
  if (!confirm(tf('cite.confirmDelete', { key }))) return;
  await api(wb('/citations/delete'), {
    method: 'POST',
    body: JSON.stringify({ key }),
  });
  await loadCitations();
  toast(t('cite.deleted'));
}

const REPORT_ACTION_LABEL = {
  check: '检查', lock: '封存', sign: '签收', import: '导入',
};

/** 四个动作走同一个接口：检查 / 封存 / 签收 / 导入。 */
async function reportAction(action) {
  const select = $('#wb-report-select');
  const path = select?.value || '';
  if (!path) throw new Error(t('empty.noReportSelected'));
  const by = ($('#wb-report-by')?.value || '').trim();
  if (action === 'sign' && !by) {
    const el = $('#wb-report-state');
    if (el) el.textContent = '签收要写签收人：工具不替你签字。';
    toast('签收必须填签收人');
    return;
  }
  const data = await api(wb('/reports'), {
    method: 'POST',
    body: JSON.stringify({ action, report: path, by }),
  });
  await loadWorkbenchReports();
  const result = data.result || {};
  if (action === 'check' && result.ok === false) {
    const first = (result.errors || [])[0];
    throw new Error(first ? first.message : '检查没过');
  }
  if (action === 'import') {
    toast(result.written ? '已写进事实账：' + (result.facts_file || '')
      : (result.unchanged ? '账上已是最新，没改动' : '演练：没有写盘'));
    await loadWorkbenchProject();
    await runWorkbenchAudit();
    renderGuide();
    return;
  }
  toast(tf('state.actionDone', { what: tz(REPORT_ACTION_LABEL[action] || action) }));
}

async function freezeWorkbenchEvidence() {
  const reason = prompt('冻结理由（可留空）', '') ?? null;
  if (reason === null) return;
  const data = await api(wb('/evidence/freeze'), {
    method: 'POST', body: JSON.stringify({ reason }),
  });
  toast('已冻结：' + String(data.sha256 || '').slice(0, 12));
  await loadWorkbenchEvidence();
  await runWorkbenchAudit();
}

async function unfreezeWorkbenchEvidence() {
  const reason = prompt('为什么改证据清单（必填）', '');
  if (!reason || !reason.trim()) throw new Error('解冻必须写理由');
  await api(wb('/evidence/unfreeze'), {
    method: 'POST', body: JSON.stringify({ reason: reason.trim() }),
  });
  toast('已解冻；改完记得重新冻结');
  await loadWorkbenchEvidence();
  await runWorkbenchAudit();
}

async function buildWorkbenchPdf() {
  const el = $('#wb-build-state');
  el.textContent = '编译中…';
  const data = await api(wb('/build'), { method: 'POST' });
  if (buildSucceeded(data)) {
    el.textContent = '编译成功 · ' + data.pdf_bytes + ' 字节';
    $('#btn-wb-pdf').hidden = false;
    toast('PDF 编译完成');
  } else {
    el.textContent = '编译失败 · 退出码 ' + data.exit;
    el.title = String(data.output_text || '').slice(0, 2000);
    toast('编译失败，悬停看输出');
  }
}

async function openWorkbenchPdf() {
  const headers = {};
  if (!MODE.mini && state.token) headers.Authorization = 'Bearer ' + state.token;
  const res = await fetch(wb('/pdf'), { headers });
  if (!res.ok) throw new Error('PDF 还没生成或不可读（HTTP ' + res.status + '）');
  const blob = await res.blob();
  const win = window.open('', '_blank');
  if (!win) throw new Error('浏览器拦了新窗口');
  win.location.href = URL.createObjectURL(blob);
}

async function loadWorkbenchProject() {
  try {
    state.workbenchProject = await api(wb('/project'));
  } catch (err) {
    if (!MODE.mini && /还没有选论文项目/.test(err.message)) {
      state.workbenchProject = null;
      state.wbEvidence = null;
      state.wbReports = null;
      loadChat();
      renderWorkbench();
      return;
    }
    throw err;
  }
  // 换了项目就换聊天历史；同一个项目时内存里那份已经是最新的。
  loadChat();
  renderWorkbench();
  renderWorkbenchFacts();
  const project = state.workbenchProject;
  const build = $('#btn-wb-build');
  if (build) {
    build.disabled = !project?.build_allowed;
    build.title = project?.build_allowed
      ? '执行 project.build 或自动编译 main.tex'
      : '启动时没加 --allow-build';
  }
  const freeze = $('#btn-wb-freeze');
  const unfreeze = $('#btn-wb-unfreeze');
  if (freeze) freeze.disabled = Boolean(project?.read_only);
  if (unfreeze) unfreeze.disabled = Boolean(project?.read_only);
  // 只读工作台：封存/签收/导入写不了盘，按钮灰掉并说清原因。
  for (const [sel, needsWrite] of [['#btn-wb-report-check', false],
    ['#btn-wb-report-lock', true], ['#btn-wb-report-sign', true],
    ['#btn-wb-report-import', true]]) {
    const btn = $(sel);
    if (!btn) continue;
    const blocked = !selectedReport() || (needsWrite && Boolean(project?.read_only));
    btn.disabled = blocked;
    btn.title = !selectedReport()
      ? '先让实验产出一份 report.toml'
      : (needsWrite && project?.read_only ? '启动时没加 --allow-write' : '');
  }
  await loadWorkbenchEvidence();
  // 当前就在报告页：项目刚载入完，补一次渲染与按需拉取
  if (state.tab === 'reports') {
    renderWorkbenchReports();
    loadWorkbenchReports().catch(() => {});
  }
  // 引用页同理
  if (state.tab === 'citations') {
    renderCitations();
    loadCitations().catch(() => {});
  }
}

async function saveWorkbenchSection() {
  const project = state.workbenchProject;
  if (!project) throw new Error('先载入工作台项目');
  const file = $('#workbench-section-select').value;
  const text = $('#workbench-section-text').value;
  $('#workbench-save-state').textContent = '保存中…';
  await api(wb('/sections'), {
    method: 'PUT',
    body: JSON.stringify({ file, text }),
  });
  $('#workbench-save-state').textContent = '已保存 ' + file;
  // 引导条第 ③ 步：这次打开之后动过正文。
  state.guide.edited = true;
  await loadWorkbenchProject();
  toast('工作台章节已保存');
}

async function loadWorkbench() {
  if (!MODE.mini) {
    // 网页就是 Python 服务本身：没有 Node 代理，也没有一键启动
    state.workbench = { configured: true, url: location.origin, tokenSet: Boolean(state.token) };
    state.run = null;
    renderWorkbench();
    return;
  }
  try {
    const data = await api('/api/workbench');
    state.workbench = { configured: Boolean(data.configured), url: data.url || '', tokenSet: Boolean(data.tokenSet) };
    state.run = data.running
      ? { project: data.project || '', pid: data.pid || 0, mode: data.mode || null }
      : null;
  } catch {
    state.workbench = { configured: false };
    state.run = null;
  }
  renderWorkbench();
}

async function loadWorkbenchStatus() {
  try {
    state.workbenchStatus = await api(wb('/status'));
  } catch (err) {
    if (!MODE.mini && /还没有选论文项目/.test(err.message)) {
      state.workbenchStatus = null;
      renderWorkbench();
      return;
    }
    throw err;
  }
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
  state.run = null;
  state.workbenchAudit = null;
  $('#workbench-status').textContent = '已连接：' + data.url + '（手动连接；一键启动的进程已停）';
  await loadWorkbenchStatus();
  await loadWorkbenchProject();
  toast('已连接本地工作台');
}

async function disconnectWorkbench() {
  await api('/api/workbench', { method: 'DELETE' });
  state.workbench = { configured: false };
  state.run = null;
  state.workbenchStatus = null;
  state.workbenchAudit = null;
  state.workbenchProject = null;
  $('#workbench-status').textContent = '';
  renderWorkbench();
}

async function runWorkbenchAudit() {
  $('#workbench-status').textContent = '工作台审计中…';
  state.workbenchAudit = await api(wb('/audit'), { method: 'POST' });
  // 引导条第 ④ 步：改过之后又重跑了审计。
  if (state.guide.edited) state.guide.auditedAfterEdit = true;
  // 审计跑完是常态，不是动作结果：状态行回到空闲（空），只留错误与明确动作。
  $('#workbench-status').textContent = '';
  renderWorkbench();
  renderGuide();
}

function wire() {
  for (const btn of $$('.nav-item')) btn.addEventListener('click', () => switchTab(btn.dataset.tab));

  // 源码编辑器：输入时重画高亮层，滚动时两层一起动。
  const sectionText = $('#workbench-section-text');
  if (sectionText) {
    sectionText.addEventListener('input', () => updateHighlight());
    sectionText.addEventListener('scroll', () => syncHighlightScroll());
  }
  window.addEventListener('resize', () => {
    syncHighlightMetrics();
    syncHighlightScroll();
  });

  // 引用页：按状态过滤（全部 / 缺标识 / 未引用）
  for (const btn of $$('.cite-filter')) {
    btn.addEventListener('click', () => {
      state.citeFilter = btn.dataset.filter || 'all';
      renderCitations();
    });
  }
  // 引用页右上角：展开添加引用的内联表单。
  $('#btn-cite-add').addEventListener('click', openCiteForm);
  $('#btn-cite-cancel').addEventListener('click', closeCiteForm);
  $('#cite-form').addEventListener('submit', (e) => {
    addCitation(e).catch((err) => {
      const note = $('#cite-result');
      if (note) note.textContent = t('cite.error') + err.message;
      toast(t('cite.error') + err.message);
    });
  });
  // 引用页每行的删除按钮：确认后才真删。
  $('#cite-tbody').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-cite-delete]');
    if (!btn) return;
    deleteCitation(btn.dataset.citeDelete).catch((err) => {
      toast(t('cite.error') + err.message);
    });
  });
  // 事实账右上角：展开追加事实的表单。
  $('#btn-wb-fact-add').addEventListener('click', openFactForm);
  // 报告页右上角：新建一份报告模板。
  $('#btn-report-new').addEventListener('click', () => {
    newReportTemplate().catch((e) => toast('新建报告模板失败：' + e.message));
  });

  // 侧栏底部：语言 / 主题。点一下就换，并且记住（刷新后还在）。
  $('#btn-lang-zh').addEventListener('click', () => setLang('zh'));
  $('#btn-lang-en').addEventListener('click', () => setLang('en'));
  $('#btn-theme-light').addEventListener('click', () => applyTheme('light'));
  $('#btn-theme-dark').addEventListener('click', () => applyTheme('dark'));

  window.addEventListener('hashchange', onHashChange);
  // 动作消息只有一份（#workbench-status），项目页也要看得见：抄一份过去。
  const status = $('#workbench-status');
  const mirror = $('#project-status');
  if (status && mirror && typeof MutationObserver !== 'undefined') {
    const copy = () => { mirror.textContent = status.textContent; };
    new MutationObserver(copy).observe(status, { childList: true, characterData: true, subtree: true });
  }
  // 项目列表：点一行展开那一条（手风琴，同一时刻只展开一条）；
  // 展开后的四个动作：编辑 / 删除 / 载入项目 / 复制路径。
  $('#project-list').addEventListener('click', (e) => {
    const act = e.target.closest('[data-action]');
    if (act) {
      e.stopPropagation();
      projectItemAction(act.dataset.action, act.dataset.path || '').catch((err) => {
        $('#workbench-status').textContent = '操作失败：' + err.message;
        toast('操作失败：' + err.message);
      });
      return;
    }
    const row = e.target.closest('.project-item-main');
    if (!row) return;
    const path = row.dataset.path || '';
    if (!path) return;
    state.projectOpen = state.projectOpen === path ? '' : path;
    if (!state.projectOpen) state.projectEdit = '';
    renderProjects();
  });
  // 新建项目：右栏那个大按钮 → #/project/new
  $('#btn-new-project').addEventListener('click', () => {
    switchTab('project/new');
  });
  $('#new-project-form').addEventListener('submit', (e) => {
    e.preventDefault();
    createProjectFromForm();
  });
  $('#btn-np-cancel').addEventListener('click', () => {
    switchTab('project');
  });
  // 新建页的两个页签：新建 / 加入已有文件夹（各自一个 hash）。
  $('#btn-np-tab-new').addEventListener('click', () => switchTab('project/new'));
  $('#btn-np-tab-add').addEventListener('click', () => switchTab('project/add'));
  $('#btn-np-add-cancel').addEventListener('click', () => switchTab('project'));
  $('#btn-np-existing-add').addEventListener('click', () => {
    addExistingProject().catch((e) => {
      const note = $('#np-add-note');
      if (note) note.textContent = '加入失败：' + e.message;
      toast('加入失败：' + e.message);
    });
  });
  $('#btn-project-host').addEventListener('click', () => {
    useHostProject().catch((e) => { $('#workbench-status').textContent = '用当前对话项目失败：' + e.message; });
  });
  $('#btn-project-python').addEventListener('click', () => {
    saveProjectPython().catch((e) => { $('#workbench-status').textContent = '保存解释器失败：' + e.message; });
  });
  $('#btn-workbench-start').addEventListener('click', () => {
    startWorkbench().catch((e) => {
      $('#workbench-status').textContent = '启动失败：' + e.message;
      toast('启动失败：' + e.message);
    });
  });
  $('#btn-workbench-stop').addEventListener('click', () => {
    stopWorkbench().catch((e) => { $('#workbench-status').textContent = '停止失败：' + e.message; });
  });
  $('#btn-workbench-connect').addEventListener('click', () => {
    connectWorkbench().catch((e) => { $('#workbench-status').textContent = '连接失败：' + e.message; toast('连接失败：' + e.message); });
  });
  $('#btn-workbench-disconnect').addEventListener('click', () => {
    disconnectWorkbench().catch((e) => toast('断开失败：' + e.message));
  });
  $('#btn-wb-open-browser').addEventListener('click', () => {
    api(wb('/browser'), { method: 'POST' })
      .then(() => toast('已在本机浏览器打开（同一个服务）'))
      .catch((e) => toast('打开浏览器失败：' + e.message));
  });
  $('#btn-workbench-audit').addEventListener('click', () => {
    runWorkbenchAudit().catch((e) => { $('#workbench-status').textContent = '审计失败：' + e.message; toast('审计失败：' + e.message); });
  });
  // 新手引导：装示例、切过去、跟着五步走。
  $('#btn-guide-open').addEventListener('click', () => {
    openGuideSample();
  });
  // 「重置示例」有两个入口：项目页右栏与工作台引导条。
  $('#btn-guide-reset').addEventListener('click', () => {
    resetGuideSample();
  });
  $('#btn-guide-reset-bar').addEventListener('click', () => {
    resetGuideSample();
  });
  $('#btn-guide-close').addEventListener('click', () => {
    closeGuide();
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
    updateHighlight();
    state.currentSection = $('#workbench-section-select').value || '';
    renderWorkbenchSections();
    const label = $('#wb-current-section');
    if (label) label.textContent = $('#workbench-section-select').value;
    renderAi();
    renderGuide();
    if (state.wbMode === 'preview') renderWbPreviewHtml();
  });

  // 侧栏目录：点一下就切到那一节，并把工作台打开（章节本身就是入口）
  $('#wb-section-list').addEventListener('click', (e) => {
    const act = e.target.closest('[data-action]');
    if (act) {
      e.stopPropagation();
      handleSectionAction(act.dataset.action, act.dataset.file);
      return;
    }
    const btn = e.target.closest('[data-section]');
    if (!btn) return;
    selectWorkbenchSection(btn.dataset.section);
    renderWorkbenchSections();
    if (state.tab !== 'workbench') switchTab('workbench');
  });

  // 侧栏目录：新建一节
  $('#btn-wb-section-add').addEventListener('click', () => {
    createWorkbenchSection();
  });

  // 侧栏顶部：项目按钮进项目页（导航里没有「项目」项了）
  $('#btn-sidebar-project').addEventListener('click', () => switchTab('project'));

  // 工作台：源码 / 预览
  $('#btn-wb-mode-source').addEventListener('click', () => setWbMode('source'));
  $('#btn-wb-mode-preview').addEventListener('click', () => setWbMode('preview'));

  // 工作台：问题列表里「跳到那一行」
  $('#workbench-audit').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-jump-line]');
    if (!btn) return;
    jumpToLine(btn.dataset.jumpFile, Number(btn.dataset.jumpLine));
  });

  // 工作台：快捷插入——点一下在光标处插入模板，槽位落到花括号里
  $('#wb-snippets').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-insert]');
    if (!btn) return;
    // 预览态下源码是藏着的：先切回源码，插入才有地方落。
    if (state.wbMode !== 'source') {
      state.wbMode = 'source';
      renderWbMode();
    }
    insertSnippet(btn.dataset.insert || '', btn.dataset.caret || '');
  });

  // 工作台：右栏两个面板互斥（要处理的问题 / AI 聊天）
  $('#btn-wb-side-issues').addEventListener('click', () => {
    state.wbSide = 'issues';
    renderWbSide();
  });
  $('#btn-wb-side-ai').addEventListener('click', () => {
    state.wbSide = 'ai';
    renderWbSide();
  });

  // 工作台：AI 聊天（发送 + 工具审批卡）
  $('#wb-chat-send').addEventListener('click', () => {
    sendChat().catch((e) => toast('发送失败：' + e.message));
  });
  $('#wb-chat-log').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-chat-approval]');
    if (!btn) return;
    replyChatApproval(btn.dataset.chatApproval, btn.dataset.decision).catch((err) => {
      toast('审批失败：' + err.message);
    });
  });

  // 工作台：事实、证据、编译、token
  $('#wb-fact-form').addEventListener('submit', (e) => {
    addWorkbenchFact(e).catch((err) => {
      $('#wb-fact-result').textContent = '追加失败：' + err.message;
      toast('追加失败：' + err.message);
    });
  });
  $('#btn-wb-freeze').addEventListener('click', () => {
    freezeWorkbenchEvidence().catch((e) => toast('冻结失败：' + e.message));
  });
  $('#btn-wb-unfreeze').addEventListener('click', () => {
    unfreezeWorkbenchEvidence().catch((e) => toast('解冻失败：' + e.message));
  });
  // 实验报告：四个动作走同一个接口，动作完刷新列表与审阅卡。
  for (const [id, action] of [['#btn-wb-report-check', 'check'],
    ['#btn-wb-report-lock', 'lock'],
    ['#btn-wb-report-sign', 'sign'],
    ['#btn-wb-report-import', 'import']]) {
    $(id).addEventListener('click', () => {
      reportAction(action).catch((e) => toast('报告操作失败：' + e.message));
    });
  }
  $('#wb-report-select').addEventListener('change', () => {
    renderReportState(selectedReport());
    renderReportCard(selectedReport(), (state.wbReports?.reports || []).length);
  });
  $('#btn-wb-build').addEventListener('click', () => {
    buildWorkbenchPdf().catch((e) => { $('#wb-build-state').textContent = '编译失败：' + e.message; });
  });
  $('#btn-wb-pdf').addEventListener('click', () => {
    openWorkbenchPdf().catch((e) => toast(e.message));
  });
  $('#btn-token').addEventListener('click', () => {
    const token = $('#token-input').value.trim();
    if (!token) return toast('先填 token');
    state.token = token;
    sessionStorage.setItem('factscribe.token', token);
    $('#token-panel').hidden = true;
    loadWorkbenchStatus()
      .then(() => loadWorkbenchProject())
      .then(() => runWorkbenchAudit())
      .catch((e) => toast('连接失败：' + e.message));
  });
}

async function init() {
  // 界面偏好先读回来：语言与主题要在第一屏就生效，别等用户点一下。
  initPrefs();
  // 引导开着没：路径记在 localStorage，空＝上次被关掉了。
  state.guide.path = guideStoredPath();
  applyMode();
  // 地址栏说了算：有合法 hash 就去那一页，没有就按模式取默认页。
  const hashPage = pageFromHash();
  if (MODE.mini) {
    // 先问宿主：这是不是从论文对话打开的（fail-closed 的前提）
    await detectHostContext();
  } else {
    state.token = tokenFromUrl();
    if (!state.token) showTokenPanel();
  }
  wire();
  // 首屏用 replaceState 写 hash：不该给浏览器塞一条空的历史。

  if (MODE.mini) {
    const urlProject = new URLSearchParams(location.search).get('project') || '';
    if (urlProject) state.projectPath = urlProject;
    // 聊天历史只跟项目路径有关：先读回来，别等后端应答。
    loadChat();
    try {
      await loadProjects();
      // ?project=<文件夹>：AI 或用户从对话里带过来的路径，直接登记
      if (urlProject && !state.projects.some((p) => p.path === state.projectPath)) {
        await addProject(urlProject);
      }
    } catch (err) {
      $('#workbench-status').textContent = '项目列表读取失败：' + err.message;
    }
    await loadWorkbench();
    switchTab(hashPage || defaultPage(), { replace: true });
  } else {
    // 网页：服务已经由命令行启动，页面只操作真实论文项目
    await loadWorkbench();
    switchTab(hashPage || defaultPage(), { replace: true });
    try {
      await loadProjects();
    } catch (err) {
      $('#workbench-status').textContent = '项目列表读取失败：' + err.message;
    }
    // 网页里项目路径来自服务端；聊天历史按这个路径读回来。
    loadChat();
    if (state.token) {
      try {
        await loadWorkbenchStatus();
        await loadWorkbenchProject();
        if (state.workbenchProject) await runWorkbenchAudit();
      } catch (err) {
        toast('加载失败：' + err.message);
      }
    }
  }

  // 服务自己挂了要能看见：只在「正在跑」且停在工作台页签时轻量轮询
  if (MODE.mini) {
    setInterval(() => {
      if (state.tab !== 'workbench' || !state.run) return;
      api('/api/workbench')
        .then((data) => {
          if (data.running) return;
          state.run = null;
          state.workbench = { configured: Boolean(data.configured), url: data.url || '', tokenSet: Boolean(data.tokenSet) };
          $('#workbench-status').textContent = '工作台已不在运行（自己退出或被杀）；要接着用就再点「启动并连接」。';
          renderWorkbench();
        })
        .catch(() => {});
    }, 5000);
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      try {
        localStorage.setItem('minifactscribe.tab', state.tab);
      } catch {
        /* 视图偏好写不进去就算了，不影响数据 */
      }
    }
  });
}

init();
