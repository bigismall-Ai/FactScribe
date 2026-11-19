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
    'status.draft': '未建账', 'status.checking': '在写', 'status.released': '已绑完',
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
    /* ---- 段四：AI 对话（真后端）+ 实验报告导入（真文件） ---- */
    'ai.ask': '问 AI', 'ai.askPara': '这一段有什么可改的？',
    'ai.reportQ': '用大白话解读这份检查报告',
    'ai.back': '返回', 'ai.clear': '清空',
    'ai.note': 'AI 对话接的是真后端（/api/chat）。模型没接上时，回复会明确标成「模拟」，不会假装是模型答的。',
    'ai.you': '你', 'ai.ph': '问一句…', 'ai.send': '发送', 'ai.sending': '发送中…',
    'ai.waiting': '模型正在想…', 'ai.err': '提问失败：{e}', 'ai.empty': '（没有返回内容）',
    'ai.ctxHead': '当前段落 · {sec}', 'ai.ctxHeadNone': '当前段落',
    'ai.fbChip': '模拟', 'ai.fbNote': '未接模型{d}',
    'ai.q1': '① 总结这篇论文的状态', 'ai.q2': '② 这一段有什么可改的？', 'ai.q3': '③ 这段为什么被标了缺作者',
    'ai.q1.text': '总结这篇论文的状态', 'ai.q2.text': '这一段有什么可改的？', 'ai.q3.text': '这段为什么被标了缺作者',
    'ai.noProject': '先打开一篇论文。',
    'rp.title.paper': '实验报告 · {p}',
    'rp.sub': '当前项目的实验报告：导入、字段映射、数字绑定与签收状态。',
    'rp.backWs': '返回工作台', 'rp.back': '返回列表',
    'rp.card.time': '导入时间', 'rp.card.bound': '绑定 {n} 个数字', 'rp.card.from': '来源', 'rp.card.file': '文件',
    'rp.st.pending_check': '待核对', 'rp.st.signed': '已签收', 'rp.st.confirmed': '已确认',
    'rp.from.import': '来自导入', 'rp.from.unknown': '未知来源',
    'rp.empty': '该项目还没有报告，点右上角「导入实验报告」。',
    'rp.loading': '读取中…', 'rp.loadErr': '读实验报告失败：{e}',
    'rp.read': '让 AI 解读这份报告', 'rp.readT': 'AI 用大白话总评当前检查结果',
    'rp.d.bound': '数字绑定清单', 'rp.d.file': '原始文件', 'rp.d.draft': '导入草稿',
    'rp.d.nobound': '这份报告还没有绑定数字。',
    'rp.d.rowsNote': '本版接口只返回绑定条数，逐条明细待后端补齐。',
    'rp.noProject': '先打开一篇论文，再看实验报告。',
    'wz.open': '导入实验报告', 'wz.title': '导入实验报告',
    'wz.s1': '选文件', 'wz.s2': '字段映射', 'wz.s3': '确认绑定',
    'wz.s1.h': '下面是本项目 reports 目录里的真实文件；也可以直接上传一份。',
    'wz.s1.empty': 'reports 目录里还没有文件，先上传一份。',
    'wz.s1.meta': '{size} 字节 · {mtime}',
    'wz.s1.upload': '上传文件', 'wz.s1.uploading': '上传中…', 'wz.s1.upErr': '上传失败：{e}',
    'wz.s2.h': '把报告里的指标对到论文事实账的字段；对不上的可以先跳过。',
    'wz.s2.empty': '这份文件没解析出可绑定的行。',
    'wz.s2.loading': '解析中…', 'wz.s2.err': '解析失败：{e}',
    'wz.col.id': '报告 id', 'wz.col.claim': '断言', 'wz.col.val': '报告值', 'wz.col.field': '事实账字段',
    'wz.skip': '— 跳过 —',
    'wz.failed': '以下行解析失败，已跳过',
    'wz.s3.h': '确认后写入草稿，交人核对后才进正式事实账。',
    'wz.sum.file': '文件', 'wz.sum.sha': '指纹', 'wz.sum.mapped': '将绑定的行',
    'wz.sum.skip': '跳过', 'wz.sum.disk': '目标盘', 'wz.sum.project': '目标项目',
    'wz.draftNote': '导入只写草稿 {path}；正式事实账 facts/*.toml 不会被改动。',
    'wz.next': '下一步', 'wz.back': '上一步', 'wz.confirm': '确认导入',
    'wz.done': '已导入 {n} 行，草稿在 {path}',
    'wz.fail': '导入失败：{e}',
    'wz.nofile': '先选一份文件。', 'wz.norows': '先解析出行。',
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
    'np.pdf': '渲染PDF', 'np.check': '全检一次', 'np.bundle': '导出投稿包',
    'np.openDir': '打开目录', 'np.collapse': '收起导航', 'np.toc': '目录',
    'np.ai': '智能助手', 'np.reports': '实验报告', 'np.import': '从外部导入',
    'nav.open': '展开导航', 'np.tocEmpty': '这个盘还没有章节。',
    'act.pdfTitle': '渲染 PDF', 'act.bundleTitle': '导出投稿包',
    'act.openTitle': '打开项目目录', 'act.close': '关闭',
    'act.pdfOk': '编译完成', 'act.pdfFail': '编译没成功',
    'act.pdfPages': '{n} 页 · {b} 字节', 'act.pdfPreview': '预览',
    'act.pdfDownload': '下载 PDF', 'act.pdfPath': '产物路径',
    'act.bundleOk': '投稿包已导出', 'act.bundleFail': '清单门没过',
    'act.bundlePath': '包目录', 'act.bundleFiles': '包内 {n} 件',
    'act.bundleGate': '清单门：{p} 过 / {f} 不过 / {w} 豁免',
    'act.openOk': '已在访达里打开', 'act.openUnsupported': '本机不是 macOS：路径如下。',
    'rp.delAsk': '删掉这条导入记录？\n（只删草稿记录；报告源文件不动）',
    'rp.deleted': '已删掉这条导入记录（源文件没动）',
    'rp.noDelete': '这条记录删不掉：{e}',
    'ab.label': '摘要', 'ab.edit': '点击编辑摘要', 'ab.saved': '摘要已保存',
    'ab.missing': '这个盘的主文件里没有 abstract 环境。',
    'fc.title': '证据', 'fc.nofact': '账本里没有这条事实。',
    'fc.claim': '断言', 'fc.value': '值', 'fc.source': '出处',
    'fc.locator': '定位', 'fc.fp': '指纹', 'fc.conf': '置信',
    'check.title': '全检结果', 'check.tabReport': '检查报告',
    'check.tabMachine': '机器底账', 'rp.card.del': '删除',
    'np.aiNote': '对话层是半透明悬浮层，浮在正文上方；这里放上下文与入口。',
    'np.aiOpen': '打开对话层', 'np.aiClose': '收起对话层',
  },
  en: {
    'nav.projects': 'Projects', 'tb.new': 'New',
    'pg.title': 'Paper projects', 'pg.sub': 'Open a paper to keep writing, or create a new project.',
    'pg.searchPh': 'Search projects…', 'pg.empty': 'No paper project found under this root (a directory with factscribe.toml).',
    'card.open': 'Open', 'card.status': 'Status', 'card.last': 'Last opened',
    'card.disks': 'Disks', 'card.sections': 'sections', 'card.facts': 'facts',
    'status.placeholder': 'stage 2', 'time.placeholder': 'stage 2',
    'status.draft': 'No ledger yet', 'status.checking': 'In progress',
    'status.released': 'Fully bound',
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
    /* ---- stage 4: AI chat (real backend) + experiment report import (real files) ---- */
    'ai.ask': 'Ask AI', 'ai.askPara': 'What could be improved in this paragraph?',
    'ai.reportQ': 'Explain this check report in plain words',
    'ai.back': 'Back', 'ai.clear': 'Clear',
    'ai.note': 'AI chat talks to the real backend (/api/chat). When no model is reachable the reply is clearly marked as a mock — it is never passed off as the model.',
    'ai.you': 'You', 'ai.ph': 'Ask something…', 'ai.send': 'Send', 'ai.sending': 'Sending…',
    'ai.waiting': 'The model is thinking…', 'ai.err': 'Request failed: {e}', 'ai.empty': '(no content returned)',
    'ai.ctxHead': 'Current paragraph · {sec}', 'ai.ctxHeadNone': 'Current paragraph',
    'ai.fbChip': 'Mock', 'ai.fbNote': 'model not connected{d}',
    'ai.q1': '① Summarize this paper\'s state', 'ai.q2': '② What could be improved in this paragraph?', 'ai.q3': '③ Why is this flagged missing-author',
    'ai.q1.text': 'Summarize this paper\'s state', 'ai.q2.text': 'What could be improved in this paragraph?', 'ai.q3.text': 'Why is this flagged missing-author',
    'ai.noProject': 'Open a paper first.',
    'rp.title.paper': 'Experiment reports · {p}',
    'rp.sub': 'Experiment reports of the current project: import, field mapping, bound numbers and sign-off status.',
    'rp.backWs': 'Back to workspace', 'rp.back': 'Back to list',
    'rp.card.time': 'Imported', 'rp.card.bound': '{n} numbers bound', 'rp.card.from': 'Source', 'rp.card.file': 'File',
    'rp.st.pending_check': 'To check', 'rp.st.signed': 'Signed off', 'rp.st.confirmed': 'Confirmed',
    'rp.from.import': 'From import', 'rp.from.unknown': 'Unknown source',
    'rp.empty': 'No reports for this project yet — import one from the top-right button.',
    'rp.loading': 'Loading…', 'rp.loadErr': 'Failed to load the experiment reports: {e}',
    'rp.read': 'Let AI explain this report', 'rp.readT': 'AI summarizes the current check results in plain words',
    'rp.d.bound': 'Bound numbers', 'rp.d.file': 'Original file', 'rp.d.draft': 'Import draft',
    'rp.d.nobound': 'This report has no bound numbers yet.',
    'rp.d.rowsNote': 'This API returns only the bound count; per-row details are not available yet.',
    'rp.noProject': 'Open a paper first to see its experiment reports.',
    'wz.open': 'Import experiment report', 'wz.title': 'Import experiment report',
    'wz.s1': 'Choose file', 'wz.s2': 'Map fields', 'wz.s3': 'Confirm binding',
    'wz.s1.h': 'These are the real files in this project\'s reports directory; you can also upload one.',
    'wz.s1.empty': 'No files in the reports directory yet — upload one first.',
    'wz.s1.meta': '{size} B · {mtime}',
    'wz.s1.upload': 'Upload a file', 'wz.s1.uploading': 'Uploading…', 'wz.s1.upErr': 'Upload failed: {e}',
    'wz.s2.h': 'Map report metrics to fact-ledger fields; skip the ones that don\'t fit.',
    'wz.s2.empty': 'No rows could be parsed from this file.',
    'wz.s2.loading': 'Parsing…', 'wz.s2.err': 'Parse failed: {e}',
    'wz.col.id': 'Report id', 'wz.col.claim': 'Claim', 'wz.col.val': 'Report value', 'wz.col.field': 'Ledger field',
    'wz.skip': '— Skip —',
    'wz.failed': 'These rows failed to parse and were skipped',
    'wz.s3.h': 'Once confirmed it is written as a draft and only enters the live ledger after human sign-off.',
    'wz.sum.file': 'File', 'wz.sum.sha': 'Fingerprint', 'wz.sum.mapped': 'Rows to bind',
    'wz.sum.skip': 'Skipped', 'wz.sum.disk': 'Target disk', 'wz.sum.project': 'Target project',
    'wz.draftNote': 'The import only writes the draft {path}; the live ledger facts/*.toml is not touched.',
    'wz.next': 'Next', 'wz.back': 'Back', 'wz.confirm': 'Confirm import',
    'wz.done': 'Imported {n} rows; draft at {path}',
    'wz.fail': 'Import failed: {e}',
    'wz.nofile': 'Pick a file first.', 'wz.norows': 'Parse the rows first.',
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
    'pf.newTitle': 'New paper project', 'pf.editTitle': 'Edit project',
    'pf.editSub': 'Project directory and disk set are locked (item 24); other fields are editable.',
    'pf.newSub': 'Once created, the project shows up in the project list.',
    'pf.created': 'Created: {n}',
    'prog.facts': '{b}/{t} facts bound',
    'prog.none': 'No quantitative facts yet',
    'time.never': 'never opened',
    'card.edit': 'Edit',
    'np.pdf': '渲染PDF', 'np.check': '全检一次', 'np.bundle': '导出投稿包',
    'np.openDir': '打开目录', 'np.collapse': '收起导航', 'np.toc': '目录',
    'np.ai': '智能助手', 'np.reports': '实验报告', 'np.import': '从外部导入',
    'nav.open': '展开导航', 'np.tocEmpty': '这个盘还没有章节。',
    'act.pdfTitle': '渲染 PDF', 'act.bundleTitle': '导出投稿包',
    'act.openTitle': '打开项目目录', 'act.close': '关闭',
    'act.pdfOk': '编译完成', 'act.pdfFail': '编译没成功',
    'act.pdfPages': '{n} 页 · {b} 字节', 'act.pdfPreview': '预览',
    'act.pdfDownload': '下载 PDF', 'act.pdfPath': '产物路径',
    'act.bundleOk': '投稿包已导出', 'act.bundleFail': '清单门没过',
    'act.bundlePath': '包目录', 'act.bundleFiles': '包内 {n} 件',
    'act.bundleGate': '清单门：{p} 过 / {f} 不过 / {w} 豁免',
    'act.openOk': '已在访达里打开', 'act.openUnsupported': '本机不是 macOS：路径如下。',
    'rp.delAsk': '删掉这条导入记录？\n（只删草稿记录；报告源文件不动）',
    'rp.deleted': '已删掉这条导入记录（源文件没动）',
    'rp.noDelete': '这条记录删不掉：{e}',
    'ab.label': '摘要', 'ab.edit': '点击编辑摘要', 'ab.saved': '摘要已保存',
    'ab.missing': '这个盘的主文件里没有 abstract 环境。',
    'fc.title': '证据', 'fc.nofact': '账本里没有这条事实。',
    'fc.claim': '断言', 'fc.value': '值', 'fc.source': '出处',
    'fc.locator': '定位', 'fc.fp': '指纹', 'fc.conf': '置信',
    'check.title': '全检结果', 'check.tabReport': '检查报告',
    'check.tabMachine': '机器底账', 'rp.card.del': 'Delete',
    'np.aiNote': 'The chat layer is a translucent overlay floating above the body; context and entry live here.',
    'np.aiOpen': 'Open chat layer', 'np.aiClose': 'Hide chat layer',
  },
};

const state = {
  lang: 'zh',
  projects: [],
  project: null,
  disk: null,
  blocks: [],
  meta: null,
  nav: { pane: 'toc', aiOpen: false },   // 段五：导航面板（目录/报告 ＋ 助手浮层）
  filter: '',
  editing: null,      // 正在编辑的块 {id, file, host}
  assembly: [],       // main.tex 的装配清单
  form: null,         // 新建/编辑项目表单 {mode, project, disk}
  abstract: null,     // 段五：封面摘要块模型（cover-abstract）
  report: null,       // 段三：检查报告数据（/report）
  machine: null,      // 段三：机器视图数据（/machine）
  reportError: '',
  machineError: '',
  reportLoading: false,
  rerun: null,        // 段三：最近一次重跑检查的结果
  ai: { messages: [], quote: null, waiting: false, seq: 0 },   // 段四：AI 对话（真后端）
  reports: { list: [], loading: false, error: '', detail: null }, // 段四：实验报告
  wz: { step: 1, file: '', fileSize: 0, files: [], rows: [], failed: [], suggested: [], sha: '', busy: false, parseError: '' }, // 段四：导入向导
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
  // 段五：报告列表在导航面板里，跟着语言重画。
  renderReports();
  applyLangToggle();
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
    const disks = diskSummary(project);
    // 状态：由真实进度派生（跟原型三态一致），不另造字段。
    const status = !progress.total ? 'draft'
      : (progress.bound >= progress.total ? 'released' : 'checking');
    const row = document.createElement('div');
    row.className = 'pj-row-item';
    row.innerHTML = `
      <div class="pj-r-title"><span class="pj-r-name">${esc(project.name)}</span></div>
      <div class="pj-r-line">
        <span class="pj-r-disks" title="${esc(disks)}">${esc(disks)}</span>
        <span class="pj-r-status"><span class="pj-chip pj-${status}">${esc(t('status.' + status))}</span></span>
        <span class="pj-r-last" title="${esc(last)}">${esc(last)}</span>
        <span class="pj-r-prog"><span class="pj-bar"><span class="pj-bar-in" style="width:${progress.percent || 0}%"></span></span><span class="pj-r-time">${esc(progText)}</span></span>
        <span class="pj-r-actions">
          <button type="button" class="btn-ghost pj-edit" data-edit="${esc(project.id)}">${esc(t('card.edit'))}</button>
          <button type="button" class="btn-primary pj-open" data-open="${esc(project.id)}">${esc(t('card.open'))}</button>
        </span>
      </div>`;
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
  host.innerHTML = '';
  let curSec = '';
  state.blocks.forEach((block) => {
    if (block.kind === 'section') {
      curSec = block.title || '';
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
    } else if (block.kind === 'subsection') {
      curSec = block.title || '';
      const heading = document.createElement('h3');
      heading.className = 'sub-h';
      heading.id = block.id;
      heading.textContent = block.title;
      host.appendChild(heading);
    } else if (block.kind === 'abstract') {
      // 段五：摘要归封面（封面摘要区可编辑），正文里不重复渲染。
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
        bindParaTools(node, (node.textContent || '').replace(/\s+/g, ' ').trim(), curSec, block.id);
        host.appendChild(node);
      }
    }
  });
  bindFactChips(host);
  renderTocList();
}

/* 段五：目录住进导航面板；章节管理并入目录——
   目录条目行内直接带 ↑↓/删除，末尾一行是「＋新建章节」。
   条目顺序＝装配顺序（main.tex 的 \input 链），调序后目录跟着走。 */
function renderTocList() {
  const toc = $('#tocList');
  if (!toc) return;
  toc.innerHTML = '';
  const assembly = state.assembly || [];
  const byFile = new Map();
  state.blocks.forEach((block) => {
    if (block.kind !== 'section' && block.kind !== 'subsection') return;
    const key = block.file || '';
    if (!byFile.has(key)) byFile.set(key, []);
    byFile.get(key).push(block);
  });
  const rows = [];
  const used = new Set();
  assembly.forEach((entry, index) => {
    const list = byFile.get(entry.rel) || [];
    list.forEach((block, position) => {
      rows.push({ block: block, ops: position === 0 ? { index: index, entry: entry } : null });
    });
    used.add(entry.rel);
  });
  byFile.forEach((list, file) => {
    if (used.has(file)) return;
    list.forEach((block) => rows.push({ block: block, ops: null }));
  });
  if (!rows.length) {
    const empty = document.createElement('li');
    empty.className = 'toc-empty';
    empty.textContent = t('np.tocEmpty');
    toc.appendChild(empty);
  }
  rows.forEach((row) => {
    const block = row.block;
    const li = document.createElement('li');
    li.className = 'toc-item' + ((block.level || 1) > 1 ? ' sub' : '');
    const link = document.createElement('a');
    link.href = '#' + block.id;
    link.innerHTML = `<span class="cn">${esc(block.title || block.file || '')}</span>`;
    li.appendChild(link);
    if (row.ops) {
      const last = row.ops.index === assembly.length - 1;
      const ops = document.createElement('span');
      ops.className = 'tm-ops';
      ops.innerHTML = `
        <button type="button" class="tm-btn" data-move="up" data-rel="${esc(block.file || '')}" title="${esc(t('toc.up'))}" ${row.ops.index === 0 ? 'disabled' : ''}>↑</button>
        <button type="button" class="tm-btn" data-move="down" data-rel="${esc(block.file || '')}" title="${esc(t('toc.down'))}" ${last ? 'disabled' : ''}>↓</button>
        <button type="button" class="tm-btn tm-del" data-del="${esc(block.file || '')}" title="${esc(t('toc.del'))}">🗑</button>`;
      li.appendChild(ops);
    }
    toc.appendChild(li);
  });
  // 末尾：新建章节（行内入口，不是独立长条）
  const add = document.createElement('li');
  add.className = 'toc-add';
  add.innerHTML = `<button type="button" id="tocNew">${esc(t('toc.new'))}</button>`;
  toc.appendChild(add);

  $$('#tocList a').forEach((a) => {
    a.addEventListener('click', (ev) => {
      ev.preventDefault();
      const target = document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1)));
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
  $$('#tocList [data-move]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      moveSection(btn.dataset.rel, btn.dataset.move);
    });
  });
  $$('#tocList [data-del]').forEach((btn) => {
    btn.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      deleteSection(btn.dataset.del);
    });
  });
  const newBtn = $('#tocNew');
  if (newBtn) newBtn.addEventListener('click', openNewSection);
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

/* ---------------------------------------------------------------- 封面摘要（段五） */

const ABSTRACT_BLOCK = 'cover-abstract';

async function loadAbstract() {
  const project = state.project;
  const disk = currentDisk();
  const box = $('#coverAbstract');
  if (!box) return;
  if (!project || !disk) { state.abstract = null; box.hidden = true; return; }
  try {
    const data = await getJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/block/${ABSTRACT_BLOCK}`);
    if (!data || data.ok === false) { state.abstract = null; box.hidden = true; return; }
    state.abstract = data;
  } catch (err) {
    state.abstract = null;
    box.hidden = true;
    return;
  }
  renderAbstract();
}

function abstractChipHtml(chip) {
  const raw = chip.raw || '';
  const label = chip.label || '';
  if (label === 'fact') {
    const match = /\\fact\s*\{([^{}]*)\}/.exec(raw);
    const id = match ? match[1].trim() : '';
    return `<span class="prot-chip fc-fact" data-fact="${esc(id)}" tabindex="0" role="button" title="${esc(raw)}">✓ ${esc(id)}</span>`;
  }
  return `<span class="prot-chip" title="${esc(raw)}">${esc(chip.display || raw)}</span>`;
}

function renderAbstract() {
  const box = $('#coverAbstract');
  const body = $('#coverAbstractBody');
  const label = $('#coverAbstractLabel');
  if (!box || !body) return;
  const model = state.abstract;
  if (!model) { box.hidden = true; return; }
  box.hidden = false;
  if (label) label.textContent = t('ab.label');
  const parts = String(model.plain || '').split(/(\ue000P\d+\ue001)/);
  let html = '';
  parts.forEach((part) => {
    if (!part) return;
    if (/^\ue000P\d+\ue001$/.test(part)) {
      const index = part.replace(/\D/g, '');
      const chip = (model.chips || []).find((c) => String(c.i) === index);
      html += chip ? abstractChipHtml(chip) : '';
      return;
    }
    html += esc(part);
  });
  body.innerHTML = html;
  body.classList.add('editable-para');
  body.title = t('ab.edit');
  body.onclick = (ev) => {
    if (ev.target.closest('.fc-fact')) return;   // 芯片走证据卡，不进编辑
    ev.stopPropagation();
    enterEdit(ABSTRACT_BLOCK, '', body);
  };
  bindFactChips(body);
}

/* ---------------------------------------------------------------- 证据卡（段五） */

function bindFactChips(root) {
  $$('.fc[data-fact]', root || document).forEach((chip) => {
    if (chip.dataset.bound === '1') return;
    chip.dataset.bound = '1';
    chip.addEventListener('click', (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      openFactCard(chip.dataset.fact || '', chip);
    });
  });
}

function factRow(key, value, mono) {
  return `<div class="fc-row"><span class="k">${esc(t(key))}</span><span class="fc-v${mono ? ' mono' : ''}">${esc(value || '—')}</span></div>`;
}

function openFactCard(id, anchor) {
  const card = $('#factCard');
  const body = $('#fcBody');
  const foot = $('#fcFoot');
  const idEl = $('#fcId');
  if (!card || !body) return;
  idEl.textContent = id || '—';
  const groups = machineGroups();
  const rows = (groups && groups.ledger && Array.isArray(groups.ledger.rows)) ? groups.ledger.rows : [];
  const row = rows.find((r) => String(r.id) === String(id));
  if (!row) {
    body.innerHTML = `<div class="fc-empty">${esc(t('fc.nofact'))}</div>`;
    foot.innerHTML = '';
  } else {
    body.innerHTML = factRow('fc.claim', row.claim) +
      factRow('fc.value', row.value) +
      factRow('fc.source', row.source_file || row.source_path) +
      factRow('fc.locator', row.locator) +
      factRow('fc.conf', row.confidence) +
      factRow('fc.fp', row.fp_short, true);
    foot.innerHTML = row.source_path
      ? `<span title="${esc(row.source_path)}">${esc(row.source_path)}</span>`
      : '';
  }
  card.hidden = false;
  const rect = anchor.getBoundingClientRect();
  const width = card.offsetWidth || 320;
  const height = card.offsetHeight || 200;
  let left = rect.left - width - 10;
  if (left < 8) left = Math.min(rect.right + 10, window.innerWidth - width - 8);
  let top = rect.top - 8;
  if (top + height > window.innerHeight - 8) top = Math.max(8, window.innerHeight - height - 8);
  card.style.left = Math.max(8, left) + 'px';
  card.style.top = top + 'px';
}

function closeFactCard() {
  const card = $('#factCard');
  if (card) card.hidden = true;
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
  // 段四：AI 面板的说明条走 data-i18n（#seg4Note），不在这里覆盖。
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
  // 段四：换盘＝换一篇稿子，对话上下文跟着重置。
  clearAiConversation();
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
  // 段五：封面摘要（可编辑；写回走段二同一保护通道）。
  await loadAbstract();
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

async function enterEdit(blockId, file, targetEl) {
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
  const target = targetEl || document.getElementById(blockId);
  if (!target) return;
  const keepId = target.id || blockId;
  const editor = buildEditor(model);
  target.replaceWith(editor);
  editor.id = keepId;
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
  renderTocList();
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

/* =====================================================================
   段四：AI 对话（接真后端 /api/chat）＋ 实验报告导入（走真文件）
   ===================================================================== */

/* 后端约定的 fallback 标记：模拟回答的第一行必须是这一句。 */
const AI_FALLBACK_MARK = '模拟回答（未接模型）';

/* 这条接口永远 200；ok=false 表示「模型没接上」，不是请求失败。
   所以不能走 postJSON（它见 ok===false 就抛），要自己接。 */
async function postChat(body) {
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  let data = null;
  try { data = await res.json(); } catch (err) { data = null; }
  if (!data) throw new Error('HTTP ' + res.status);
  return data;
}

/* ---------------------------------------------------------------- AI 对话 */

function aiCtxHtml() {
  const quote = state.ai.quote;
  if (!quote) return '';
  const head = quote.section ? t('ai.ctxHead', { sec: quote.section }) : t('ai.ctxHeadNone');
  return `<div class="ctx-h">${esc(head)}</div><div class="ctx-q">「${esc(quote.text || '')}」</div>`;
}

function renderAiCtx() {
  const el = $('#aiCtx');
  if (!el) return;
  el.innerHTML = aiCtxHtml();
  el.classList.toggle('on', !!state.ai.quote);
}

/* 追加一条气泡。fallback 的回复必须一眼看得出是模拟的。 */
function pushAiMsg(role, text, opts) {
  const host = $('#aiMsgs');
  if (!host) return null;
  const options = opts || {};
  const wrap = document.createElement('div');
  wrap.className = 'msg ' + (role === 'user' ? 'me' : 'ai') + ' msg-js';
  if (options.fallback) wrap.classList.add('fb');
  if (options.waiting) wrap.classList.add('waiting');
  const who = document.createElement('div');
  who.className = 'who';
  who.textContent = role === 'user' ? t('ai.you') : 'AI';
  if (options.fallback) {
    const chip = document.createElement('span');
    chip.className = 'fb-chip';
    chip.textContent = t('ai.fbChip');
    who.appendChild(chip);
  }
  const bub = document.createElement('div');
  bub.className = 'bub';
  bub.textContent = text || '';
  wrap.appendChild(who);
  wrap.appendChild(bub);
  if (options.note) {
    const note = document.createElement('div');
    note.className = 'msg-note';
    note.textContent = options.note;
    wrap.appendChild(note);
  }
  host.appendChild(wrap);
  host.scrollTop = host.scrollHeight;
  return wrap;
}

function clearAiConversation() {
  state.ai.messages = [];
  state.ai.quote = null;
  state.ai.seq += 1;      // 作废在途的请求回复
  renderAiCtx();
  const host = $('#aiMsgs');
  if (!host) return;
  $$('.msg-js', host).forEach((el) => el.remove());
}

function setAiBusy(busy) {
  const send = $('#aiSend');
  if (send) {
    send.disabled = !!busy;
    send.textContent = busy ? t('ai.sending') : t('ai.send');
  }
  $$('#aiFloat .aq').forEach((btn) => { btn.disabled = !!busy; });
}

function aiFallbackNote(data) {
  const code = (data && data.code) || '';
  const msg = (data && data.error) || '';
  const detail = [code, msg].filter(Boolean).join(' · ');
  return t('ai.fbNote', { d: detail ? ' · ' + detail : '' });
}

/* 两条都认：后端给的 fallback 标记，或回复第一行就是约定的那句标记。 */
function isFallbackReply(data, reply) {
  if (data && data.fallback) return true;
  const text = String(reply || '').replace(/^\s+/, '');
  return text.indexOf(AI_FALLBACK_MARK) === 0;
}

async function aiSend(question, mode) {
  if (state.ai.waiting) return;
  const q = String(question || '').trim();
  if (!q) return;
  if (!state.project) { toast(t('ai.noProject')); return; }
  pushAiMsg('user', q);
  state.ai.messages.push({ role: 'user', content: q });
  const wait = pushAiMsg('ai', t('ai.waiting'), { waiting: true });
  state.ai.waiting = true;
  setAiBusy(true);
  const seq = state.ai.seq;
  const payload = {
    project: state.project.id,
    disk: state.disk || '',
    messages: state.ai.messages.map((m) => ({ role: m.role, content: m.content })),
    quote: mode === 'explain' ? null : (state.ai.quote || null),
    mode: mode || 'ask',
  };
  try {
    const data = await postChat(payload);
    if (seq !== state.ai.seq) return;      // 期间清空过：这次回复作废
    if (wait && wait.parentNode) wait.parentNode.removeChild(wait);
    const reply = data && data.reply ? String(data.reply) : '';
    if (!reply) {
      pushAiMsg('ai', t('ai.empty'), { fallback: true, note: aiFallbackNote(data) });
      return;
    }
    const fallback = isFallbackReply(data, reply);
    pushAiMsg('ai', reply, { fallback: fallback, note: fallback ? aiFallbackNote(data) : '' });
    state.ai.messages.push({ role: 'assistant', content: reply });
  } catch (err) {
    if (seq !== state.ai.seq) return;
    if (wait && wait.parentNode) wait.parentNode.removeChild(wait);
    pushAiMsg('ai', t('ai.err', { e: (err && err.message) || String(err) }), { fallback: true });
  } finally {
    if (seq === state.ai.seq) {
      state.ai.waiting = false;
      setAiBusy(false);
    }
  }
}

/* 「问 AI」带引用：切到 AI 页、带上下文、预填问题（人再按发送）。 */
function askAiAbout(text, section, id) {
  state.ai.quote = { text: String(text || ''), section: String(section || ''), id: String(id || '') };
  renderAiCtx();
  switchNavPane('ai');
  const input = $('#aiText');
  if (input) {
    input.value = t('ai.askPara');
    input.focus();
  }
}

/* 段落的悬浮工具条（原型同款）：不占正文排版，悬停段落才浮出来。 */
let paraAskTarget = null;
let paraToolsTimer = null;

function showParaTools(node) {
  const bar = $('#ptools');
  const page = $('#diskBody');
  if (!bar || !page) return;
  const r = node.getBoundingClientRect();
  const pr = page.getBoundingClientRect();
  bar.classList.add('on');
  const width = bar.offsetWidth || 64;
  let left = (r.right - pr.left) - width - 6;
  if (left > pr.width - width - 8) left = pr.width - width - 8;
  if (left < 4) left = 4;
  bar.style.left = left + 'px';
  bar.style.top = (r.top - pr.top + 2) + 'px';
}

function hideParaTools() {
  clearTimeout(paraToolsTimer);
  paraToolsTimer = setTimeout(() => {
    const bar = $('#ptools');
    if (bar) bar.classList.remove('on');
  }, 160);
}

/* 段落 → 悬浮工具条的绑定（原型同款：悬停段落才浮出「问 AI」）。 */
function bindParaTools(node, text, section, id) {
  node.addEventListener('mouseenter', () => {
    paraAskTarget = { text: text, section: section, id: id };
    showParaTools(node);
  });
  node.addEventListener('mouseleave', hideParaTools);
}

/* ---------------------------------------------------------------- 实验报告 */

function reportsApiPath(suffix) {
  const project = state.project;
  if (!project) return null;
  return `/api/project/${encodeURIComponent(project.id)}/reports${suffix || ''}`;
}

function reportStatusLabel(report) {
  if (report && report.status_label) return String(report.status_label);
  const status = (report && report.status) || '';
  return status ? t('rp.st.' + status) : '—';
}

function reportFromLabel(report) {
  const from = (report && report.from) || '';
  if (from === 'import') return t('rp.from.import');
  return from ? String(from) : t('rp.from.unknown');
}

const REPORT_STATUS_CLS = {
  pending_check: 'rp-pending_check',
  signed: 'rp-signed',
  confirmed: 'rp-confirmed',
};

/* 段五：实验报告列表住进导航面板——只导入与删除，不在工作台里编辑报告内容。 */
function reportRowHtml(report) {
  const name = report.name || report.file || report.id || '';
  const file = report.file || '';
  const bound = Number(report.bound || 0);
  const cls = REPORT_STATUS_CLS[report.status || ''] || 'rp-pending_check';
  return `<div class="np-rp-row" data-rp="${esc(report.id || '')}">
    <div class="np-rp-main">
      <div class="np-rp-name" title="${esc(file)}">${esc(name)}</div>
      <div class="np-rp-meta">
        <span class="np-rp-chip ${cls}">${esc(reportStatusLabel(report))}</span>
        <span>${esc(t('rp.card.bound', { n: bound }))}</span>
        <span>${esc(report.time || '')}</span>
      </div>
    </div>
    <button type="button" class="np-rp-del" data-del="${esc(report.id || '')}" title="${esc(t('rp.delAsk'))}">${esc(t('rp.card.del'))}</button>
  </div>`;
}

function renderReports() {
  const list = $('#npReportsList');
  if (!list) return;
  if (!state.project) {
    list.innerHTML = `<div class="ff-empty">${esc(t('rp.noProject'))}</div>`;
    return;
  }
  if (state.reports.loading) {
    list.innerHTML = `<div class="ff-empty">${esc(t('rp.loading'))}</div>`;
    return;
  }
  if (state.reports.error) {
    list.innerHTML = `<div class="ff-empty">${esc(t('rp.loadErr', { e: state.reports.error }))}</div>`;
    return;
  }
  const items = state.reports.list || [];
  if (!items.length) {
    list.innerHTML = `<div class="ff-empty">${esc(t('rp.empty'))}</div>`;
    return;
  }
  list.innerHTML = items.map(reportRowHtml).join('');
  $$('#npReportsList [data-del]').forEach((btn) => {
    btn.addEventListener('click', () => deleteReport(btn.dataset.del));
  });
}

async function loadReports() {
  const path = reportsApiPath('');
  if (!path) return;
  state.reports.loading = true;
  renderReports();
  try {
    const data = await getJSON(path);
    if (data && data.ok === false) throw new Error(data.error || 'REPORTS_FAILED');
    state.reports.list = (data && Array.isArray(data.reports)) ? data.reports : [];
    state.reports.error = '';
  } catch (err) {
    state.reports.list = [];
    state.reports.error = (err && err.message) || String(err);
  }
  state.reports.loading = false;
  renderReports();
}

/* 删除导入记录（草稿）：先确认，再走服务端；报告源文件不动。 */
async function deleteReport(id) {
  if (!id) return;
  if (!window.confirm(t('rp.delAsk'))) return;
  const path = reportsApiPath('/delete');
  if (!path) return;
  try {
    const result = await postJSON(path, { name: id });
    toast(t('rp.deleted'));
    if (result && result.source_file) {
      toast(t('rp.deleted') + '（' + result.source_file + '）');
    }
    await loadReports();
  } catch (err) {
    toast(t('rp.noDelete', { e: (err && err.message) || String(err) }));
  }
}

/* ---------------------------------------------------------------- 导入向导 */

function wzDraftName(file) {
  const name = String(file || '');
  return name.replace(/\.[^.]+$/, '') + '.draft.toml';
}

async function openWizard() {
  if (!state.project) { toast(t('rp.idle')); return; }
  state.wz = {
    step: 1, file: '', fileSize: 0, files: [], rows: [], failed: [],
    suggested: [], sha: '', busy: false, parseError: '',
  };
  const modal = $('#wizardModal');
  if (modal) modal.hidden = false;
  renderWz();
  await loadWzDir();
}

function closeWizard() {
  const modal = $('#wizardModal');
  if (modal) modal.hidden = true;
}

async function loadWzDir() {
  const path = reportsApiPath('/dir');
  if (!path) return;
  try {
    const data = await getJSON(path);
    if (data && data.ok === false) throw new Error(data.error || 'REPORTS_DIR_FAILED');
    state.wz.files = (data && Array.isArray(data.files)) ? data.files : [];
  } catch (err) {
    state.wz.files = [];
    toast(t('wz.s1.upErr', { e: (err && err.message) || String(err) }));
  }
  // 刚上传的文件可能还没进目录列表：自己补一条，别把选中状态弄丢。
  if (state.wz.file && !state.wz.files.some((f) => f.name === state.wz.file)) {
    state.wz.files = [{ name: state.wz.file, size: state.wz.fileSize || 0, mtime: '' }].concat(state.wz.files);
  }
  renderWz();
}

function renderWz() {
  const step = state.wz.step;
  $$('.wstep').forEach((s) => {
    const n = Number(s.getAttribute('data-ws'));
    s.classList.toggle('on', n === step);
    s.classList.toggle('done', n < step);
  });
  ['#wpane1', '#wpane2', '#wpane3'].forEach((sel, i) => {
    const pane = $(sel);
    if (pane) pane.classList.toggle('on', i === step - 1);
  });
  const back = $('#wzBack');
  if (back) back.disabled = step === 1;
  const next = $('#wzNext');
  if (next) {
    next.textContent = step === 3 ? t('wz.confirm') : t('wz.next');
    next.disabled = (step === 1 && !state.wz.file) || (step === 2 && !state.wz.rows.length);
  }
  if (step === 1) renderWzFiles();
  if (step === 2) renderWzRows();
  if (step === 3) renderWzSummary();
}

function renderWzFiles() {
  const host = $('#wzFiles');
  if (!host) return;
  const files = state.wz.files || [];
  if (!files.length) {
    host.innerHTML = `<div class="ff-empty">${esc(t('wz.s1.empty'))}</div>`;
    return;
  }
  host.innerHTML = files.map((f) => {
    const checked = f.name === state.wz.file ? ' checked' : '';
    const meta = t('wz.s1.meta', { size: Number(f.size || 0), mtime: f.mtime || '—' });
    return `<label class="wz-file"><input type="radio" name="wzf" value="${esc(f.name)}"${checked}>` +
      `<span class="rf-n">${esc(f.name)}</span><span class="rf-s">${esc(meta)}</span></label>`;
  }).join('');
}

function renderWzRows() {
  const failedBox = $('#wzFailed');
  const failed = state.wz.failed || [];
  if (failedBox) {
    if (failed.length) {
      failedBox.hidden = false;
      failedBox.innerHTML = `<div class="wz-failed-h">${esc(t('wz.failed'))}</div>` + failed.map((f) => {
        const line = (f && f.line !== undefined && f.line !== null) ? String(f.line) : '';
        return `<div class="wz-failed-row"><span class="wz-f-line">${esc(line)}</span>` +
          `<span class="wz-f-raw">${esc(String((f && f.raw) || ''))}</span>` +
          `<span class="wz-f-err">${esc(String((f && f.error) || ''))}</span></div>`;
      }).join('');
    } else {
      failedBox.hidden = true;
      failedBox.innerHTML = '';
    }
  }
  const status = $('#wzStatus');
  const body = $('#wzRows');
  const table = $('#wzMapTable');
  if (!body || !table) return;
  const rows = state.wz.rows || [];
  if (!rows.length) {
    table.hidden = true;
    if (status) status.innerHTML = `<div class="ff-empty">${esc(state.wz.parseError || t('wz.s2.empty'))}</div>`;
    return;
  }
  table.hidden = false;
  if (status) status.innerHTML = '';
  const targets = [];
  (state.wz.suggested || []).forEach((s) => {
    const tgt = (s && s.target) ? String(s.target) : '';
    if (tgt && targets.indexOf(tgt) < 0) targets.push(tgt);
  });
  body.innerHTML = rows.map((row, i) => {
    const opts = [`<option value="">${esc(t('wz.skip'))}</option>`].concat(
      targets.map((tgt) => `<option value="${esc(tgt)}"${tgt === row.target ? ' selected' : ''}>${esc(tgt)}</option>`)
    ).join('');
    return `<tr>
      <td><input class="wz-in" type="text" data-row="${i}" data-f="id" value="${esc(row.id)}"></td>
      <td><input class="wz-in" type="text" data-row="${i}" data-f="claim" value="${esc(row.claim)}"></td>
      <td><input class="wz-in" type="text" data-row="${i}" data-f="value" value="${esc(row.value)}"></td>
      <td><select class="wzsel" data-row="${i}" data-f="target">${opts}</select></td>
    </tr>`;
  }).join('');
}

function renderWzSummary() {
  const host = $('#wzSummary');
  if (!host) return;
  const rows = state.wz.rows || [];
  const mapped = rows.filter((r) => r.target).length;
  const skipped = rows.length - mapped;
  const disk = currentDisk();
  const lines = [];
  lines.push(`${esc(t('wz.sum.file'))} <code>${esc(state.wz.file || '')}</code>`);
  if (state.wz.sha) lines.push(`${esc(t('wz.sum.sha'))} <code>${esc(state.wz.sha)}</code>`);
  lines.push(`${esc(t('wz.sum.mapped'))} ${mapped} / ${rows.length}`);
  lines.push(`${esc(t('wz.sum.skip'))} ${skipped}`);
  lines.push(`${esc(t('wz.sum.disk'))} <code>${esc(disk ? disk.id : '—')}</code>`);
  lines.push(`${esc(t('wz.sum.project'))} <code>${esc(state.project ? state.project.id : '')}</code>`);
  lines.push(`<b>${esc(t('wz.draftNote', { path: 'facts/draft/' + wzDraftName(state.wz.file) }))}</b>`);
  host.innerHTML = lines.join('<br>');
}

async function parseReport() {
  const path = reportsApiPath('/parse');
  if (!path) return;
  const status = $('#wzStatus');
  const body = $('#wzRows');
  const table = $('#wzMapTable');
  if (table) table.hidden = true;
  if (status) status.innerHTML = `<div class="ff-empty">${esc(t('wz.s2.loading'))}</div>`;
  if (body) body.innerHTML = '';
  try {
    const data = await postJSON(path, { name: state.wz.file });
    const suggested = (data && Array.isArray(data.suggested)) ? data.suggested : [];
    const targets = {};
    suggested.forEach((s) => { if (s && s.id) targets[String(s.id)] = s.target ? String(s.target) : ''; });
    const rows = (data && Array.isArray(data.rows)) ? data.rows : [];
    state.wz.rows = rows.map((r) => {
      const id = (r && r.id !== undefined && r.id !== null) ? String(r.id) : '';
      return {
        id: id,
        claim: (r && r.claim !== undefined && r.claim !== null) ? String(r.claim) : '',
        value: (r && r.value !== undefined && r.value !== null) ? String(r.value) : '',
        source: (r && r.source) ? String(r.source) : '',
        line: (r && r.line !== undefined) ? r.line : null,
        target: targets[id] || '',
      };
    });
    state.wz.failed = (data && Array.isArray(data.failed)) ? data.failed : [];
    state.wz.suggested = suggested;
    state.wz.sha = (data && data.sha256) ? String(data.sha256) : '';
    state.wz.parseError = '';
  } catch (err) {
    state.wz.rows = [];
    state.wz.failed = [];
    state.wz.parseError = t('wz.s2.err', { e: (err && err.message) || String(err) });
  }
  renderWz();
}

async function confirmImport() {
  const path = reportsApiPath('/confirm');
  if (!path) return;
  const source = state.wz.rows || [];
  const rows = source.map((r) => ({
    id: r.id, claim: r.claim, value: r.value, source: r.source, line: r.line,
  }));
  const mapping = {};
  source.forEach((r) => { mapping[r.id] = r.target || ''; });
  const name = state.wz.file;
  try {
    const data = await postJSON(path, {
      name: name,
      report_name: name.replace(/\.[^.]+$/, ''),
      rows: rows,
      mapping: mapping,
    });
    closeWizard();
    toast(t('wz.done', { n: Number((data && data.count) || rows.length), path: (data && data.draft_path) || '' }));
    await loadReports();
  } catch (err) {
    toast(t('wz.fail', { e: (err && err.message) || String(err) }));
  }
}

async function onWzUpload(ev) {
  const input = ev.target;
  const file = input.files && input.files[0];
  if (!file) return;
  const path = reportsApiPath('/upload');
  if (!path) return;
  const nameEl = $('#wzUpName');
  if (nameEl) nameEl.textContent = t('wz.s1.uploading');
  const fd = new FormData();
  fd.append('file', file);
  try {
    const res = await fetch(path, { method: 'POST', body: fd, headers: { 'Accept': 'application/json' } });
    let data = null;
    try { data = await res.json(); } catch (err) { data = null; }
    if (!data || data.ok === false) throw new Error((data && data.error) || ('HTTP ' + res.status));
    state.wz.file = data.name ? String(data.name) : file.name;
    state.wz.fileSize = Number(data.size || file.size || 0);
    if (nameEl) nameEl.textContent = state.wz.file;
    await loadWzDir();
  } catch (err) {
    if (nameEl) nameEl.textContent = t('wz.s1.upErr', { e: (err && err.message) || String(err) });
  } finally {
    input.value = '';
  }
}

function onWzRowEdit(ev) {
  const el = ev.target;
  if (!el || el.dataset.row === undefined || !el.dataset.f) return;
  const row = (state.wz.rows || [])[Number(el.dataset.row)];
  if (!row) return;
  row[el.dataset.f] = el.value;
}

/* ---------------------------------------------------------------- 交互 */

function setView(view) {
  document.body.setAttribute('data-view', view);
  if (view === 'projects') {
    $('#tocList').innerHTML = '';
    $('#bodyBlocks').innerHTML = '';
    state.assembly = [];
  }
  // 段落悬浮工具条只在正文里用。
  const bar = $('#ptools');
  if (bar) bar.classList.remove('on');
  applyLangToggle();
}

/* 段五：导航面板头部的中/EN 切换。
   单语言项目（只有一个盘）→ 整组隐藏；双盘项目 → 照常切盘。 */
function applyLangToggle() {
  const seg = $('#langSeg');
  if (!seg) return;
  const project = state.project;
  const multi = project ? (project.multi_lang !== false && (project.disks || []).length > 1) : true;
  seg.hidden = !multi;
  $$('#langSeg button').forEach((btn) => {
    btn.classList.toggle('on', btn.dataset.lang === state.lang);
  });
}

/* 段五返修三（条目 29）：三枚内容钮互斥——面板显示当前激活钮对应的面，
   右缘钮列（side-tab 族）负责切换；激活态深色底。 */
function switchNavPane(name) {
  state.nav.pane = name;
  $('#paneToc').classList.toggle('on', name === 'toc');
  $('#paneAi').classList.toggle('on', name === 'ai');
  $('#paneReports').classList.toggle('on', name === 'reports');
  $('#npToc').classList.toggle('on', name === 'toc');
  $('#npAi').classList.toggle('on', name === 'ai');
  $('#npReports').classList.toggle('on', name === 'reports');
  // 互斥：切到别的面就把悬浮对话层收起来（对话层属「智能助手」这一面）。
  if (name === 'ai') {
    setAiOpen(true);
    renderAiFace();
  } else {
    setAiOpen(false);
  }
  if (name === 'reports') loadReports();
}

/* 面板里的智能助手面：上下文 + 打开/收起悬浮对话层。 */
function renderAiFace() {
  const ctx = $('#npAiCtx');
  if (ctx) ctx.innerHTML = aiCtxHtml();
  const btn = $('#npAiToggle');
  if (btn) btn.textContent = state.nav.aiOpen ? t('np.aiClose') : t('np.aiOpen');
}

/* 段五：智能助手＝半透明悬浮层，浮在正文上方。 */
function setAiOpen(open) {
  state.nav.aiOpen = !!open;
  const layer = $('#aiFloat');
  if (layer) layer.hidden = !open;
  if (open) {
    const input = $('#aiText');
    if (input) input.focus();
  }
  renderAiFace();
}

/* 段五返修三（条目 29）：收起＝导航面板＋右缘钮列全隐，只剩一枚竖排
   「展开导航」钮；正文拉满。 */
function setNavCollapsed(collapsed) {
  document.body.classList.toggle('nav-collapsed', !!collapsed);
  if (collapsed) setAiOpen(false);
}

/* ---------------------------------------------------------------- 段五：常用功能 */

/* 动作接口永远 200；ok=false 表示「这件事没做成」，不是路由错。
   所以不走 postJSON（它见 ok===false 就抛），自己接，把原因原样呈现。 */
async function postAction(action) {
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) throw new Error(t('rp.noProject'));
  const url = `/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/action`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({ action: action }),
  });
  let data = null;
  try { data = await res.json(); } catch (err) { data = null; }
  if (!data) throw new Error('HTTP ' + res.status);
  return data;
}

function openActionModal(title, html) {
  const modal = $('#modalAction');
  const titleEl = $('#actTitle');
  const body = $('#actBody');
  if (titleEl) titleEl.textContent = title;
  if (body) body.innerHTML = html;
  if (modal) modal.hidden = false;
}

function pdfUrl() {
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return '';
  return `/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/pdf`;
}

async function runPdfAction() {
  openActionModal(t('act.pdfTitle'), `<div class="ff-empty">${esc(t('rp.rerunning'))}</div>`);
  let data = null;
  try {
    data = await postAction('pdf');
  } catch (err) {
    openActionModal(t('act.pdfTitle'),
      `<div class="rp-card-err">${esc((err && err.message) || String(err))}</div>`);
    return;
  }
  if (!data.ok) {
    openActionModal(t('act.pdfTitle'),
      `<div class="act-fail">${esc(t('act.pdfFail'))}</div>` +
      `<div class="rp-card-err">${esc(data.error || data.message || '')}</div>`);
    return;
  }
  const url = pdfUrl();
  openActionModal(t('act.pdfTitle'),
    `<div class="act-ok">${esc(t('act.pdfOk'))}</div>` +
    `<div class="act-kv"><span>${esc(t('act.pdfPages', { n: Number(data.pdf_pages || 0), b: Number(data.pdf_bytes || 0) }))}</span></div>` +
    `<div class="act-kv"><span>${esc(t('act.pdfPath'))}</span><code>${esc(data.pdf_path || '')}</code></div>` +
    `<div class="act-links"><a href="${esc(url)}" target="_blank" rel="noopener">${esc(t('act.pdfPreview'))}</a>` +
    `<a href="${esc(url)}" download="main.pdf">${esc(t('act.pdfDownload'))}</a></div>` +
    `<div class="act-preview"><iframe src="${esc(url)}" title="PDF"></iframe></div>`);
}

async function runBundleAction() {
  openActionModal(t('act.bundleTitle'), `<div class="ff-empty">${esc(t('rp.rerunning'))}</div>`);
  let data = null;
  try {
    data = await postAction('bundle');
  } catch (err) {
    openActionModal(t('act.bundleTitle'),
      `<div class="rp-card-err">${esc((err && err.message) || String(err))}</div>`);
    return;
  }
  const gateRows = (data.gate || []).map((item) => {
    const status = item.status || '';
    return `<div class="act-kv"><span>${esc(item.code || '')} ${esc(item.name || '')}</span>` +
      `<span class="act-gate ${esc(status)}">${esc(status)}</span></div>`;
  }).join('');
  if (!data.ok) {
    openActionModal(t('act.bundleTitle'),
      `<div class="act-fail">${esc(t('act.bundleFail'))}</div>` +
      `<div class="rp-card-err">${esc(data.error || data.failure_reason || '')}</div>` + gateRows);
    return;
  }
  openActionModal(t('act.bundleTitle'),
    `<div class="act-ok">${esc(t('act.bundleOk'))}</div>` +
    `<div class="act-kv"><span>${esc(t('act.bundlePath'))}</span><code>${esc(data.bundle_dir || '')}</code></div>` +
    `<div class="act-kv"><span>${esc(t('act.bundleFiles', { n: Number(data.file_count || 0) }))}</span></div>` +
    `<div class="act-kv"><span>${esc(t('act.bundleGate', { p: Number(data.passed || 0), f: Number(data.failed || 0), w: Number(data.waived || 0) }))}</span></div>` +
    gateRows);
}

async function runOpenDirAction() {
  let data = null;
  try {
    data = await postAction('open_dir');
  } catch (err) {
    toast((err && err.message) || String(err));
    return;
  }
  if (data.ok && data.opened) {
    toast(data.message || t('act.openOk'));
    return;
  }
  // 非 macOS（或 open 失败）：退回「展示路径」，不假装打开过。
  openActionModal(t('act.openTitle'),
    `<div class="act-fail">${esc(data.error || t('act.openUnsupported'))}</div>` +
    `<div class="act-kv"><span>${esc(t('act.pdfPath'))}</span><code>${esc(data.path || '')}</code></div>`);
}

/* ---------------------------------------------------------------- 全检模态（段五） */

function openCheckModal() {
  const modal = $('#modalCheck');
  if (modal) modal.hidden = false;
}

function switchCheckTab(name) {
  $$('.mt-tab').forEach((btn) => btn.classList.toggle('on', btn.dataset.mt === name));
  const report = $('#mtReport');
  const machine = $('#mtMachine');
  if (report) report.classList.toggle('on', name === 'report');
  if (machine) machine.classList.toggle('on', name === 'machine');
  if (name === 'report') renderReport();
  if (name === 'machine') renderMachine();
}

async function runFullCheck() {
  openCheckModal();
  switchCheckTab('report');
  await rerunCheck();
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
  // 段五返修三（条目 29）：右缘钮列——收起导航 ＋ 三枚内容钮（互斥）
  $('#npCollapse').addEventListener('click', () => {
    setNavCollapsed(!document.body.classList.contains('nav-collapsed'));
  });
  $('#navOpen').addEventListener('click', () => { setNavCollapsed(false); });
  $('#npToc').addEventListener('click', () => { switchNavPane('toc'); });
  $('#npReports').addEventListener('click', () => { switchNavPane('reports'); });
  $('#npAi').addEventListener('click', () => { switchNavPane('ai'); });
  $('#npAiToggle').addEventListener('click', () => {
    setAiOpen(!state.nav.aiOpen);
  });
  // 段五：常用功能（弹模态框操作）
  $('#actPdf').addEventListener('click', runPdfAction);
  $('#actCheck').addEventListener('click', runFullCheck);
  $('#actBundle').addEventListener('click', runBundleAction);
  $('#actOpenDir').addEventListener('click', runOpenDirAction);
  $('#actClose').addEventListener('click', () => { $('#modalAction').hidden = true; });
  $('#modalAction').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalAction') $('#modalAction').hidden = true;
  });
  $('#modalCheckClose').addEventListener('click', () => { $('#modalCheck').hidden = true; });
  $('#modalCheck').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalCheck') $('#modalCheck').hidden = true;
  });
  $$('.mt-tab').forEach((btn) => {
    btn.addEventListener('click', () => switchCheckTab(btn.dataset.mt));
  });
  // 段五：证据卡
  $('#fcClose').addEventListener('click', closeFactCard);
  // 段四：AI 对话（真后端；浮层）
  $('#aiSend').addEventListener('click', () => {
    const input = $('#aiText');
    const text = input ? input.value.trim() : '';
    if (!text) return;
    if (input) input.value = '';
    aiSend(text, 'ask');
  });
  $('#aiText').addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' || ev.shiftKey) return;
    ev.preventDefault();
    $('#aiSend').click();
  });
  $$('#aiFloat .aq').forEach((btn) => {
    btn.addEventListener('click', () => aiSend(t('ai.q' + btn.dataset.q + '.text'), 'ask'));
  });
  $('#aiFab').addEventListener('click', clearAiConversation);
  $('#aiBack').addEventListener('click', () => setAiOpen(false));
  $('#askReportRead').addEventListener('click', () => {
    switchNavPane('ai');
    aiSend(t('ai.reportQ'), 'explain');
  });
  $('#ptAsk').addEventListener('click', () => {
    const target = paraAskTarget;
    if (!target) return;
    askAiAbout(target.text, target.section, target.id);
  });
  $('#ptools').addEventListener('mouseenter', () => clearTimeout(paraToolsTimer));
  $('#ptools').addEventListener('mouseleave', hideParaTools);
  // 段五：实验报告列表（导航面板里）
  $('#npImportBtn').addEventListener('click', openWizard);
  // 段四：导入向导（选文件 → 字段映射 → 确认绑定）
  $('#wzFiles').addEventListener('change', (ev) => {
    const input = ev.target;
    if (!input || input.name !== 'wzf') return;
    state.wz.file = input.value;
    renderWz();
  });
  $('#wzUpload').addEventListener('change', onWzUpload);
  $('#wzRows').addEventListener('input', onWzRowEdit);
  $('#wzRows').addEventListener('change', onWzRowEdit);
  $('#wzBack').addEventListener('click', () => {
    if (state.wz.step > 1) { state.wz.step -= 1; renderWz(); }
  });
  $('#wzNext').addEventListener('click', async () => {
    const step = state.wz.step;
    if (step === 1) {
      if (!state.wz.file) { toast(t('wz.nofile')); return; }
      state.wz.step = 2;
      renderWz();
      await parseReport();
      return;
    }
    if (step === 2) {
      if (!state.wz.rows.length) { toast(t('wz.norows')); return; }
      state.wz.step = 3;
      renderWz();
      return;
    }
    await confirmImport();
  });
  $('#wzCancel').addEventListener('click', closeWizard);
  $('#wizardModal').addEventListener('click', (ev) => {
    if (ev.target.id === 'wizardModal') closeWizard();
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
  // 段二：章节管理（目录行内入口）
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
    const check = $('#modalCheck');
    if (check && !check.hidden) check.hidden = true;
    const action = $('#modalAction');
    if (action && !action.hidden) action.hidden = true;
    const wizard = $('#wizardModal');
    if (wizard && !wizard.hidden) closeWizard();
    closeFactCard();
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
    if (ev.target.closest('.navpanel') || ev.target.closest('.modal') || ev.target.closest('.ai-float')) return;
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
  switchNavPane('toc');
  await loadProjects();
  setView('projects');
}

document.addEventListener('DOMContentLoaded', main);
