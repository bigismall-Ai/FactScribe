/* FactScribe 工作台 · 段二（写回与章节管理）
   交互结构移植自 workbench-redesign/prototype-v4.html；
   段一做只读骨架，段二接上写回（正文就地编辑）与章节管理（调序/删除/新建）。 */
'use strict';

/* 浏览器端错误计数（自查用）：window.__errs 全程应为 0。
   段六起沿用这个约定——交付前在浏览器里读一次这个数。 */
window.__errs = 0;
window.addEventListener('error', () => { window.__errs += 1; });
window.addEventListener('unhandledrejection', () => { window.__errs += 1; });

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => [...(r || document).querySelectorAll(s)];

const TOKEN_RE = /\ue000P\d+\ue001/;

const I18N = {
  zh: {
    'nav.projects': '项目管理', 'tb.new': '新建',
    'doc.title': 'FactScribe 工作台',
    'err.loadProjects': '读项目失败：{e}',
    'err.loadSections': '读章节失败：{e}',
    'err.openBlock': '打不开这一段：{e}',
    'err.saveFailed': '没保存上：{e}',
    'err.tocFailed': '目录操作失败：{e}',
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
    'ai.clear': '清空',
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
'edit.savedBadge': '已保存',     'edit.saved': '已保存（原稿留在 .bak）',
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
    'np.more': '更多',
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
    'rp.deletedFile': '已删掉这条导入记录（源文件 {f} 没动）',
    'rp.noDelete': '这条记录删不掉：{e}',
    'ab.label': '摘要', 'ab.edit': '点击编辑摘要', 'ab.saved': '摘要已保存',
    'ab.missing': '这个盘的主文件里没有 abstract 环境。',
    'fc.title': '证据', 'fc.nofact': '账本里没有这条事实。',
    'fc.claim': '断言', 'fc.value': '值', 'fc.source': '出处',
    'fc.locator': '定位', 'fc.fp': '指纹', 'fc.conf': '置信',
    'check.title': '全检结果', 'check.tabReport': '检查报告',
    'check.tabMachine': '机器底账', 'rp.card.del': '删除',
    /* ---- 段六 ---- */
    'np.kb': '知识库', 'np.kbUpload': '上传文件',
    'np.venue': '版式', 'np.venueGuide': '选刊指南',
    'para.more': '段落动作', 'para.edit': '编辑',
    'para.continue': '续写', 'para.rewrite': '改写', 'para.ask': '提问',
    'para.menu': '这一段的动作',
    'ai.modeIdea': '聊想法', 'ai.modePaper': '写论文',
    'ai.discipline': '示例数不是你的结果：没有真实跑出来的数，不要写进稿。',
    'ai.copy': '复制', 'ai.writeIn': '写进稿',
    'ai.copied': '已复制到剪贴板', 'ai.copyFail': '复制不了：{e}',
    'ai.written': '已写进稿（在那一段之后，标着「AI 草稿」）',
    'ai.writeFail': '写不进稿：{e}',
    'ai.writeNoTarget': '这条回复没有对应的段落，先用段落菜单里的动作再试。',
    'ai.continueQ': '接着这一段往下写。',
    'ai.rewriteQ': '把这一段改写得更好。',
    'ai.askQ': '这一段有什么可改的？',
    'ai.actionDone': '动作已发出',
    'kb.empty': '项目目录里还没有可收进知识库的文件。',
    'kb.loading': '正在读文件…', 'kb.loadErr': '读知识库失败：{e}',
    'kb.pick': '点左边一个文件看内容。',
    'kb.status': '处理状态', 'kb.size': '大小', 'kb.path': '路径',
    'kb.preview': '内容预览', 'kb.truncated': '（预览已截断）',
    'kb.uploadOk': '已上传：{name}', 'kb.uploadErr': '上传失败：{e}',
    'kb.noFile': '没有选中文件。', 'kb.pending': '待提取', 'kb.ready': '可用',
    'kb.pdfNote': 'PDF 只登记文件名与大小，文本提取段七接入。',
    'kb.actPreview': '预览', 'kb.actDelete': '删除',
    'kb.sourceNote': '源文件由章节管理管',
    'kb.delTitle': '删除知识库文件',
    'kb.delAsk': '删掉这个知识库文件？\n（只删 knowledge/ 里的这份；项目源文件不动）',
    'kb.deleted': '已删掉这个知识库文件', 'kb.delFail': '删不掉：{e}',
    'kb.sha': 'sha256', 'kb.fullNote': '完整内容请打开原文件',
    'rp.actDetail': '详情', 'rp.id': 'id', 'rp.claim': '断言', 'rp.value': '值',
    'rp.boundList': '绑定清单', 'rp.detailEmpty': '这条记录没有绑定条目。',
    'rp.delConfirmTitle': '删除这条导入记录？',
    'rp.delConfirmBody': '只删草稿记录，报告源文件不动。',
    'confirm.ok': '确定', 'confirm.cancel': '取消',
    'more.rpNote': '导入进来的都在待核对区；转正走闸，不在面板里',
    'more.kbNote': '源文件只读；上传的资料才可删除',
    'vn.venue': '目标刊物 / 会议', 'vn.venuePh': '例如：ACL 2026',
    'vn.deadline': '截稿日期', 'vn.save': '保存版式配置',
    'vn.lockTag': '语言盘锁定',
    'vn.lockZh': '这一盘是中文稿：版式只管排版与刊物要求，不动语言盘——中文稿不能换成英文刊。',
    'vn.lockEn': '这一盘是英文稿：版式只管排版与刊物要求，不动语言盘——要写中文稿就另开一个中文盘。',
    'vn.tplArticle': 'article（通用单栏论文版式）',
    'vn.saved': '版式配置已存进 workbench.toml',
    'vn.saveErr': '存不了：{e}', 'vn.preview': '首页预览',
    'vn.templates': '模板库', 'vn.tplBuilding': '模板库建设中',
    'vn.previewNone': '这个盘还没编译过 PDF：先点「渲染 PDF」，再回来看首页预览。',
    'vn.previewBtn': '渲染并预览首页',
    'vn.previewErr': '渲染失败：{e}',
    'vn.dueSoon': '截稿提醒：{d}', 'vn.overdue': '已过截稿日 {d} 天',
    'vn.dueNormal': '距截稿 {d} 天',
    'guide.title': '选刊指南', 'guide.go': '按目标版式预览并开写',
    'guide.h1': '一、贡献是什么形状',
    'guide.p1': '先说清你多出来的那一点是什么：新方法、新数据、新测量，还是新的失效边界。' +
      '贡献形状决定你能投哪一类刊物——方法类看新颖性，数据类看覆盖与可复现，' +
      '边界类看这个结论别人多久会自己撞上。说不清形状，选刊就只剩碰运气。',
    'guide.h2': '二、读者是谁',
    'guide.p2': '读者决定你得把哪部分放前面。审稿人每天读十几篇稿子，' +
      '只对「和我要解决的问题相关」的那几段有耐心。' +
      '所以先问：谁会读这份稿子，他是来找方法的还是来找结论的？' +
      '两类读者的入口段不一样，把两拨人塞在同一段里，两拨人都读不下去。',
    'guide.h3': '三、截稿与双投',
    'guide.p3': '截稿日决定你的时间盒：倒排到「最后一版能编过」，' +
      '别倒排到最后一刻。双投规则各家不同，而且常常一年一改——' +
      '投稿之前去看该刊当年的作者须知，别拿去年的记忆投稿。' +
      '扩展会议、连续出版物这些名目看着像加分项，实际规则最容易被忽略。',
    'guide.h4': '四、影响因子怎么用',
    'guide.p4': '影响因子是刊物层面的平均数，不是你这篇稿子的分数。' +
      '它能帮你排除明显不匹配的刊物（比如只发综述的刊），' +
      '但不能替代「这篇稿子会被谁读」的判断。' +
      '拿它当唯一依据，很容易把稿子投到没人读你这类问题的地方去。',
    'guide.foot': '目标刊物定了以后，把它填进上面的表单——版式面会照着它给首页预览，' +
      '截稿日临近时导航钮会提醒你。语言盘不动：中文稿还是中文稿。',
    'draft.badge': 'AI 草稿',
    'draft.hint': '这是 AI 写的草稿块，不是正文。点它可以改，也可以删掉。',
    'draft.deleted': 'AI 草稿块已删掉',
    'draft.delFail': '删不掉：{e}',
  },
  en: {
    'nav.projects': 'Projects', 'tb.new': 'New',
    'doc.title': 'FactScribe Workbench',
    'err.loadProjects': 'Could not load projects: {e}',
    'err.loadSections': 'Could not load sections: {e}',
    'err.openBlock': 'Could not open this paragraph: {e}',
    'err.saveFailed': 'Save failed: {e}',
    'err.tocFailed': 'Contents action failed: {e}',
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
    'ai.clear': 'Clear',
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
    'toc.manage': 'Sections', 'toc.new': '+ New section', 'toc.newT': 'New section',
    'toc.newTitle': 'Section title', 'toc.newTitlePh': 'e.g. Experimental setup',
    'toc.newSlug': 'File name (optional)', 'toc.newSlugPh': 'setup',
    'toc.create': 'Create', 'toc.up': 'Move up', 'toc.down': 'Move down',
    'toc.del': 'Delete', 'toc.delAsk': 'Move this section to sections/attic/ (reversible)?',
    'toc.done': 'Contents updated',
    'edit.hint': 'Click a paragraph to edit; Esc or click outside to save.',
    'edit.savedBadge': 'Saved',
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
    'np.pdf': 'Render PDF', 'np.check': 'Run full check',
    'np.bundle': 'Export submission bundle',
    'np.openDir': 'Open project folder', 'np.collapse': 'Hide panel',
    'np.toc': 'Contents',
    'np.ai': 'Assistant', 'np.reports': 'Reports', 'np.import': 'Import',
    'np.more': 'More',
    'nav.open': 'Show panel', 'np.tocEmpty': 'This disk has no sections yet.',
    'act.pdfTitle': 'Render PDF', 'act.bundleTitle': 'Export submission bundle',
    'act.openTitle': 'Open project folder', 'act.close': 'Close',
    'act.pdfOk': 'Build finished', 'act.pdfFail': 'The build did not succeed',
    'act.pdfPages': '{n} pages · {b} bytes', 'act.pdfPreview': 'Preview',
    'act.pdfDownload': 'Download PDF', 'act.pdfPath': 'Output path',
    'act.bundleOk': 'Submission bundle exported',
    'act.bundleFail': 'The manifest gate did not pass',
    'act.bundlePath': 'Bundle folder', 'act.bundleFiles': '{n} files in the bundle',
    'act.bundleGate': 'Manifest gate: {p} passed / {f} failed / {w} waived',
    'act.openOk': 'Opened in Finder',
    'act.openUnsupported': 'This is not macOS — here is the path.',
    'rp.delAsk': 'Remove this import record?\n(Only the draft record goes; the report file itself stays.)',
    'rp.deleted': 'Import record removed (source file untouched)',
    'rp.deletedFile': 'Import record removed (source file {f} untouched)',
    'rp.noDelete': 'Could not remove this record: {e}',
    'ab.label': 'Abstract', 'ab.edit': 'Click to edit the abstract',
    'ab.saved': 'Abstract saved',
    'ab.missing': 'The root file of this disk has no abstract environment.',
    'fc.title': 'Evidence', 'fc.nofact': 'No such fact in the ledger.',
    'fc.claim': 'Claim', 'fc.value': 'Value', 'fc.source': 'Source',
    'fc.locator': 'Locator', 'fc.fp': 'Fingerprint', 'fc.conf': 'Confidence',
    'check.title': 'Full check result', 'check.tabReport': 'Check report',
    'check.tabMachine': 'Machine view', 'rp.card.del': 'Delete',
    /* ---- segment six ---- */
    'np.kb': 'Knowledge base', 'np.kbUpload': 'Upload file',
    'np.venue': 'Venue', 'np.venueGuide': 'Venue guide',
    'para.more': 'Paragraph actions', 'para.edit': 'Edit',
    'para.continue': 'Continue', 'para.rewrite': 'Rewrite', 'para.ask': 'Ask',
    'para.menu': 'Actions for this paragraph',
    'ai.modeIdea': 'Brainstorm', 'ai.modePaper': 'Write paper',
    'ai.discipline': 'Example numbers are not your results: nothing you did not actually run belongs in the draft.',
    'ai.copy': 'Copy', 'ai.writeIn': 'Write into draft',
    'ai.copied': 'Copied to the clipboard',
    'ai.copyFail': 'Copy failed: {e}',
    'ai.written': 'Written into the draft (right after that paragraph, tagged "AI draft")',
    'ai.writeFail': 'Could not write into the draft: {e}',
    'ai.writeNoTarget': 'This reply has no paragraph attached — use a paragraph action first.',
    'ai.continueQ': 'Continue this paragraph.',
    'ai.rewriteQ': 'Rewrite this paragraph better.',
    'ai.askQ': 'What could be improved in this paragraph?',
    'ai.actionDone': 'Action sent',
    'kb.empty': 'No file in this project directory can go into the knowledge base yet.',
    'kb.loading': 'Reading files…', 'kb.loadErr': 'Could not load the knowledge base: {e}',
    'kb.pick': 'Pick a file on the left to read it.',
    'kb.status': 'Status', 'kb.size': 'Size', 'kb.path': 'Path',
    'kb.preview': 'Preview', 'kb.truncated': '(preview truncated)',
    'kb.uploadOk': 'Uploaded: {name}', 'kb.uploadErr': 'Upload failed: {e}',
    'kb.noFile': 'No file selected.', 'kb.pending': 'extraction pending',
    'kb.ready': 'Ready',
    'kb.pdfNote': 'PDF: name and size only — text extraction lands in the next stage.',
    'kb.actPreview': 'Preview', 'kb.actDelete': 'Delete',
    'kb.sourceNote': 'Source files are managed by the section manager',
    'kb.delTitle': 'Delete knowledge-base file',
    'kb.delAsk': 'Delete this knowledge-base file?\n(Only the copy under knowledge/ goes; project sources stay untouched.)',
    'kb.deleted': 'Knowledge-base file deleted', 'kb.delFail': 'Could not delete: {e}',
    'kb.sha': 'sha256', 'kb.fullNote': 'Open the original file for the full content',
    'rp.actDetail': 'Details', 'rp.id': 'id', 'rp.claim': 'Claim', 'rp.value': 'Value',
    'rp.boundList': 'Bound items', 'rp.detailEmpty': 'This record has no bound items.',
    'rp.delConfirmTitle': 'Delete this import record?',
    'rp.delConfirmBody': 'Only the draft record goes; the report source file stays.',
    'confirm.ok': 'OK', 'confirm.cancel': 'Cancel',
    'more.rpNote': 'Imported reports sit in the pending-check zone; promoting them goes through the gate, not this panel.',
    'more.kbNote': 'Source files are read-only; only uploaded material can be deleted.',
    'vn.venue': 'Target journal / conference', 'vn.venuePh': 'e.g. ACL 2026',
    'vn.deadline': 'Deadline', 'vn.save': 'Save venue config',
    'vn.lockTag': 'Language lock',
    'vn.lockZh': 'This disk is a Chinese draft: the venue pane changes layout and venue requirements only, never the language disk — a Chinese draft cannot be swapped for an English venue.',
    'vn.lockEn': 'This disk is an English draft: the venue pane changes layout and venue requirements only, never the language disk — open a separate Chinese disk for Chinese.',
    'vn.tplArticle': 'article (general single-column paper layout)',
    'vn.saved': 'Venue config saved into workbench.toml',
    'vn.saveErr': 'Could not save: {e}', 'vn.preview': 'First-page preview',
    'vn.templates': 'Template library', 'vn.tplBuilding': 'Template library under construction',
    'vn.previewNone': 'This disk has no compiled PDF yet: render one first, then come back for the preview.',
    'vn.previewBtn': 'Render and preview the first page',
    'vn.previewErr': 'Render failed: {e}',
    'vn.dueSoon': 'Deadline reminder: {d}', 'vn.overdue': '{d} days past the deadline',
    'vn.dueNormal': '{d} days to the deadline',
    'guide.title': 'Venue guide', 'guide.go': 'Preview against this venue and start writing',
    'guide.h1': '1. What shape is the contribution',
    'guide.p1': 'Say first what you add that was not there: a new method, new data, a new measurement, ' +
      'or a newly mapped failure boundary. The shape decides which venues are even open to you — ' +
      'method papers live on novelty, data papers on coverage and reproducibility, ' +
      'boundary papers on how long before somebody else bumps into the same wall. ' +
      'If you cannot state the shape, picking a venue is just luck.',
    'guide.h2': '2. Who the reader is',
    'guide.p2': 'The reader decides what has to come first. A reviewer reads a dozen papers a day ' +
      'and stays patient only with the parts that look relevant to their own problem. ' +
      'So ask who will read this: are they after the method or after the conclusion? ' +
      'Those two audiences need different opening paragraphs, and one paragraph serving both ' +
      'loses both.',
    'guide.h3': '3. Deadlines and double submission',
    'guide.p3': 'The deadline is your time box: back-plan to the last version that still compiles, ' +
      'not to the last minute. Double-submission rules differ per venue and often change yearly, ' +
      'so read that venue\'s current author instructions instead of trusting last year\'s memory. ' +
      'Journal extensions and rolling venues sound like bonus tracks but carry the rules people forget.',
    'guide.h4': '4. How to use an impact factor',
    'guide.p4': 'An impact factor is an average across a journal, not a score for your paper. ' +
      'It usefully rules out mismatched venues (a letters-only journal, say), ' +
      'but it cannot replace the judgement "who will read this". ' +
      'Treating it as the only criterion is a reliable way to publish where nobody reads your problem.',
    'guide.foot': 'Once the venue is settled, put it in the form above — the venue pane previews ' +
      'the first page against it, and the navigation button warns you as the deadline nears. ' +
      'The language disk never changes: a Chinese draft stays a Chinese draft.',
    'draft.badge': 'AI draft',
    'draft.hint': 'This is an AI-written draft block, not body text. Click it to edit, or delete it.',
    'draft.deleted': 'AI draft block deleted',
    'draft.delFail': 'Could not delete: {e}',
  },
};

const state = {
  lang: 'zh',
  projects: [],
  project: null,
  disk: null,
  blocks: [],
  meta: null,
  nav: { pane: 'toc' },   // 段五：导航面板（目录/智能助手/更多 三面互斥）
  blocksMeta: {},          // 条目 37：块身份（文件＋章节）——原地替换后重新绑定用
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
  ai: { messages: [], quote: null, waiting: false, seq: 0, mode: 'paper' },  // 段四：AI 对话（真后端）；段六：两档模式
  reports: { list: [], loading: false, error: '', detail: null }, // 段四：实验报告
  kb: { files: [], loading: false, error: '', current: '', detail: null },   // 段六：知识库
  venue: { data: null, loading: false, error: '', msg: '' },                // 段六：版式
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
  document.title = t('doc.title');
  $$('[data-i18n]').forEach((el) => { el.textContent = t(el.getAttribute('data-i18n')); });
  $$('[data-i18n-ph]').forEach((el) => { el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph'))); });
  $$('[data-i18n-title]').forEach((el) => { el.setAttribute('title', t(el.getAttribute('data-i18n-title'))); });
  $$('[data-i18n-aria]').forEach((el) => { el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria'))); });
  $('#langSeg').querySelectorAll('button').forEach((btn) => {
    btn.classList.toggle('on', btn.dataset.lang === state.lang);
  });
  document.body.classList.toggle('panel-en', state.lang === 'en');
  // 段五：报告列表在导航面板里，跟着语言重画。
  renderReports();
  renderKb();
  renderVenue();
  applyLangToggle();
  // 条目 33：applyI18n 会把钮里的文字整个重写，截稿徽标要补回来。
  updateDeadlineBadge();
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
    toast(t('err.loadProjects', { e: err.message }));
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
    } else if (block.kind === 'ai_draft') {
      // 段六：AI 草稿块——独立成块，不混进正文；可再编辑，也可删掉。
      const holder = document.createElement('div');
      holder.innerHTML = block.html || '';
      const node = holder.firstElementChild;
      if (node) {
        const wrap = document.createElement('div');
        wrap.className = 'ai-draft';
        wrap.id = block.id;
        wrap.dataset.file = block.file || '';
        wrap.dataset.kind = 'ai_draft';
        const badge = document.createElement('span');
        badge.className = 'ai-draft-badge';
        badge.textContent = t('draft.badge');
        const body = document.createElement('div');
        body.className = 'ai-draft-body';
        body.innerHTML = node.innerHTML || '';
        const hint = document.createElement('div');
        hint.className = 'ai-draft-hint';
        hint.textContent = t('draft.hint');
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'ai-draft-del';
        del.textContent = '×';
        del.title = t('draft.badge');
        del.addEventListener('click', (ev) => {
          ev.stopPropagation();
          deleteAiDraft(block.file || '', block.id);
        });
        wrap.appendChild(badge);
        wrap.appendChild(body);
        wrap.appendChild(hint);
        wrap.appendChild(del);
        wrap.dataset.blockId = block.id;
        wrap.addEventListener('click', (ev) => {
          ev.stopPropagation();
          enterEdit(block.id, block.file || '', wrap);
        });
        host.appendChild(wrap);
      }
    } else {
      const holder = document.createElement('div');
      holder.innerHTML = block.html || '';
      const node = holder.firstElementChild;
      if (node) {
        node.id = block.id;
        node.dataset.file = block.file || '';
        // 条目 37：块身份写进 DOM——保存时读回，与渲染闭包同源，杜绝错位。
        node.dataset.blockId = block.id;
        node.classList.add('editable-para');
        // 条目 37：块身份（文件＋章节）留一份，原地替换后据此重新绑定。
        state.blocksMeta[block.id] = { file: block.file || '', section: curSec };
        node.addEventListener('click', (ev) => {
          ev.stopPropagation();
          enterEdit(block.id, block.file || '', node);
        });
        bindParaTools(node, (node.textContent || '').replace(/\s+/g, ' ').trim(), curSec, block.id, block.file || '');
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
  // 条目 33：走 setView，左栏头部的常用功能组才会跟着渲染出来。
  setView('workbench');
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
    toast(t('err.loadSections', { e: err.message }));
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
  // 段六：版式配置跟着当前盘走（截稿徽标立刻可显示）。
  loadVenue();
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

/* 条目 37：同步挂载的编辑器——不等模型，先把这一段变成可输入的。
   （老实现先 await 模型再挂载，点两段时后到的模型会盖掉先到的，
   于是保存带错 (file, block-id)——根因就在这个 await 缺口。） */
function buildPlainEditor(source) {
  const host = document.createElement('div');
  host.className = 'editing';
  host.setAttribute('contenteditable', 'true');
  host.setAttribute('spellcheck', 'false');
  host.innerHTML = source.innerHTML || '';
  host.querySelectorAll('[id]').forEach((node) => node.removeAttribute('id'));
  return host;
}

/* 模型到了再补保护面芯片——用户没动过字才补，不吃掉输入。 */
function upgradeEditor(host, model) {
  const fresh = buildEditor(model);
  host.innerHTML = '';
  while (fresh.firstChild) host.appendChild(fresh.firstChild);
}

function placeCaretAtEnd(host) {
  const range = document.createRange();
  range.selectNodeContents(host);
  range.collapse(false);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

/* 条目 37：单击即进入编辑——编辑器**同步**挂载，敲字一定落在编辑态里。 */
function enterEdit(blockId, file, targetEl) {
  if (state.editing) saveEdit();          // 上一次编辑先落盘（不阻塞本次挂载）
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return;
  const target = targetEl || document.getElementById(blockId);
  if (!target) return;
  // 身份以 DOM 为准：渲染闭包写进去的 data-block-id / data-file。
  const realId = target.dataset.blockId || blockId;
  const realFile = target.dataset.file || file || '';
  const keepId = target.id || realId;
  const editor = buildPlainEditor(target);
  const plainAtMount = collectPlain(editor);
  target.replaceWith(editor);
  editor.id = keepId;
  editor.dataset.blockId = realId;
  editor.dataset.file = realFile;
  state.editSeq = (state.editSeq || 0) + 1;
  state.editing = { id: realId, file: realFile, host: editor, orig: target,
                    seq: state.editSeq };
  editor.focus();
  placeCaretAtEnd(editor);
  // 可编辑模型（保护面芯片）后台补齐；失败也不影响编辑与保存。
  getJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/block/${encodeURIComponent(realId)}`)
    .then((model) => {
      if (!model || model.ok === false) return;
      if (!state.editing || state.editing.host !== editor) return;
      if (collectPlain(editor) !== plainAtMount) return;   // 用户已经动手了 → 不动
      upgradeEditor(editor, model);
    })
    .catch(() => { /* 模型拿不到：照样能编辑能保存 */ });
  // blur 自动保存（点芯片不算离开）。
  editor.addEventListener('blur', () => {
    setTimeout(() => {
      if (!state.editing || state.editing.host !== editor) return;
      if (editor.contains(document.activeElement)) return;
      saveEdit();
    }, 120);
  });
}

/* 条目 36：把一个块原地换成新 html（不整篇重载，滚动位置不动）。 */
function replaceBlockNode(blockId, html) {
  const old = document.getElementById(blockId);
  if (!old || !html) return false;
  const holder = document.createElement('div');
  holder.innerHTML = html;
  const node = holder.firstElementChild;
  if (!node) return false;
  node.id = blockId;
  // 条目 37：块身份与可编辑性跟着走——存一次之后这一段还能再点开编辑。
  const meta = (state.blocksMeta && state.blocksMeta[blockId]) || {};
  node.classList.add('editable-para');
  node.dataset.blockId = blockId;
  node.dataset.file = old.dataset.file || meta.file || '';
  node.addEventListener('click', (ev) => {
    ev.stopPropagation();
    enterEdit(blockId, node.dataset.file || '', node);
  });
  bindParaTools(node, (node.textContent || '').replace(/\s+/g, ' ').trim(),
                meta.section || '', blockId, node.dataset.file || '');
  old.replaceWith(node);
  return true;
}

/* 条目 36：把一个新块插到锚点之后（AI 草稿插入用）。 */
function insertBlockAfter(anchorId, blockId, html) {
  const anchor = document.getElementById(anchorId);
  if (!anchor || !html) return false;
  const holder = document.createElement('div');
  holder.innerHTML = html;
  const node = holder.firstElementChild;
  if (!node) return false;
  node.id = blockId;
  anchor.after(node);
  return true;
}

/* 条目 36：原地删掉一个块（AI 草稿删除用）。 */
function removeBlockNode(blockId) {
  const node = document.getElementById(blockId);
  if (!node) return false;
  node.remove();
  return true;
}

/* 条目 36：本地还原进入编辑前的那个节点（取消编辑 / 保存失败时用）。 */
function restoreEditedNode(editing) {
  if (!editing || !editing.host || !editing.orig) return false;
  editing.host.replaceWith(editing.orig);
  return true;
}

/* 条目 37：可见的「已保存」角标（1.5s 自动消失）。 */
function showSavedBadge(blockId) {
  const node = document.getElementById(blockId);
  if (!node) return;
  const badge = document.createElement('span');
  badge.className = 'save-badge';
  badge.textContent = t('edit.savedBadge');
  node.appendChild(badge);
  setTimeout(() => { if (badge.parentNode) badge.remove(); }, 1500);
}

async function saveEdit() {
  const editing = state.editing;
  if (!editing) return;
  state.editing = null;
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return;
  const text = collectPlain(editing.host);
  // 条目 37：写回寻址与渲染闭包同源——身份从**正在编辑的这个 DOM 节点**读回。
  const file = editing.host.dataset.file || editing.file || '';
  const blockId = editing.host.dataset.blockId || editing.id;
  try {
    const result = await postJSON(`/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/edit`, {
      file: file,
      block: blockId,
      text: text,
    });
    (result.warnings || []).forEach((text) => toast(text));
    toast(t('edit.saved'));
    // 条目 36：只换掉这一块，不整篇 loadDisk（滚动位置保持）。
    if (state.editSeq !== editing.seq) return;   // 期间又开了一段新编辑 → 不动 DOM
    if (replaceBlockNode(blockId, result.html)) { showSavedBadge(blockId); return; }
    restoreEditedNode(editing);
  } catch (err) {
    toast(t('err.saveFailed', { e: err.message }));
    if (state.editSeq === editing.seq) restoreEditedNode(editing);
  }
}

/* 条目 36：取消编辑＝零网络请求，本地还原进入编辑前的原文。 */
async function cancelEdit() {
  if (!state.editing) return;
  const editing = state.editing;
  state.editing = null;
  restoreEditedNode(editing);
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
    toast(t('err.tocFailed', { e: err.message }));
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
  /* 段六：回复卡带动作钮（复制／写进稿）。 */
  if (options.actions && options.actions.length) {
    const acts = document.createElement('div');
    acts.className = 'msg-acts';
    options.actions.forEach((act) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mact' + (act.kind ? ' ' + act.kind : '');
      btn.textContent = t(act.label);
      btn.addEventListener('click', () => {
        if (typeof act.onClick === 'function') act.onClick(text || '', btn);
      });
      acts.appendChild(btn);
    });
    wrap.appendChild(acts);
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
  $$('#aiPane .aq').forEach((btn) => { btn.disabled = !!busy; });
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

async function aiSend(question, mode, action) {
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
  const useMode = mode === 'explain' ? 'explain' : (mode || state.ai.mode || 'paper');
  const useAction = action || 'ask';
  const quote = useMode === 'explain' ? null : (state.ai.quote || null);
  const payload = {
    project: state.project.id,
    disk: state.disk || '',
    messages: state.ai.messages.map((m) => ({ role: m.role, content: m.content })),
    quote: quote,
    mode: useMode,
    action: useAction,
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
    /* 段六：段落三动作的回复带「复制」「写进稿」两枚钮。 */
    const actions = (useAction !== 'ask' && quote && quote.file)
      ? [
        { label: 'ai.copy', onClick: (text) => copyReply(text) },
        { label: 'ai.writeIn', kind: 'primary', onClick: (text) => writeIntoDraft(text) },
      ]
      : [];
    pushAiMsg('ai', reply, {
      fallback: fallback,
      note: fallback ? aiFallbackNote(data) : '',
      actions: actions,
    });
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

/* 段六：复制回复（剪贴板不可用时明说，不假装复制过）。 */
async function copyReply(text) {
  const value = String(text || '');
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
      toast(t('ai.copied'));
      return;
    }
  } catch (err) {
    toast(t('ai.copyFail', { e: (err && err.message) || String(err) }));
    return;
  }
  toast(t('ai.copyFail', { e: 'clipboard unavailable' }));
}

/* 段六：写进稿——以 AI 标记块插到那一段之后（不混进正文）。 */
async function writeIntoDraft(text) {
  const quote = state.ai.quote;
  if (!quote || !quote.file || !quote.id) {
    toast(t('ai.writeNoTarget'));
    return;
  }
  const body = String(text || '').trim();
  if (!body) { toast(t('ai.writeNoTarget')); return; }
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) { toast(t('ai.writeNoTarget')); return; }
  const url = `/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/draft/insert`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ file: quote.file, block: quote.id, text: body }),
    });
    const data = await res.json();
    if (!res.ok || !data || data.ok === false) {
      toast(t('ai.writeFail', { e: (data && data.error) || ('HTTP ' + res.status) }));
      return;
    }
    toast(t('ai.written'));
    // 条目 36：草稿块原地插到那一段之后，不整篇重载。
    if (data.block && data.html && insertBlockAfter(data.after, data.block, data.html)) return;
    await loadDisk();
  } catch (err) {
    toast(t('ai.writeFail', { e: (err && err.message) || String(err) }));
  }
}

/* 段六：删掉一个 AI 草稿块。 */
async function deleteAiDraft(file, blockId) {
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return;
  const url = `/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/draft/delete`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ file: file, block: blockId }),
    });
    const data = await res.json();
    if (!res.ok || !data || data.ok === false) {
      toast(t('draft.delFail', { e: (data && data.error) || ('HTTP ' + res.status) }));
      return;
    }
    toast(t('draft.deleted'));
    // 条目 36：草稿块原地消失，不整篇重载。
    if (removeBlockNode(data.block || blockId)) return;
    await loadDisk();
  } catch (err) {
    toast(t('draft.delFail', { e: (err && err.message) || String(err) }));
  }
}

/* 段六：模式切换（聊想法／写论文）——两档的系统提示不同。 */
function setAiMode(mode) {
  const name = (mode === 'idea') ? 'idea' : 'paper';
  state.ai.mode = name;
  $$('#aiModes .ai-mode').forEach((btn) => {
    btn.classList.toggle('on', btn.dataset.mode === name);
  });
}

/* 「问 AI」带引用：切到 AI 页、带上下文、预填问题（人再按发送）。 */
function askAiAbout(text, section, id, file) {
  state.ai.quote = { text: String(text || ''), section: String(section || ''),
                     id: String(id || ''), file: String(file || '') };
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
function bindParaTools(node, text, section, id, file) {
  node.addEventListener('mouseenter', () => {
    paraAskTarget = { text: text, section: section, id: id, file: file || '',
                      rect: node.getBoundingClientRect() };
    showParaTools(node);
  });
  node.addEventListener('mouseleave', hideParaTools);
}

/* 段六：段落 ⋯ 菜单（编辑 ＋ 续写／改写／提问）。 */
function closeParaMenu() {
  const menu = $('#paraMenu');
  if (menu) menu.hidden = true;
}

function openParaMenu() {
  const target = paraAskTarget;
  if (!target) return;
  const menu = $('#paraMenu');
  const page = $('#diskBody');
  if (!menu || !page) return;
  menu.hidden = false;
  const pr = page.getBoundingClientRect();
  const mr = menu.getBoundingClientRect();
  let left = 12;
  let top = 12;
  if (target.rect) {
    left = Math.min(Math.max(8, target.rect.left - pr.left), pr.width - mr.width - 8);
    top = Math.min(Math.max(8, target.rect.top - pr.top), pr.height - mr.height - 8);
  }
  menu.style.left = left + 'px';
  menu.style.top = top + 'px';
}

/* 段六：段落三动作——都走 /api/chat（带段落引用上下文，action 字段区分）。 */
async function paraAction(action) {
  const target = paraAskTarget;
  closeParaMenu();
  if (!target) return;
  const label = action === 'continue' ? t('ai.continueQ')
    : (action === 'rewrite' ? t('ai.rewriteQ') : t('ai.askQ'));
  state.ai.quote = { text: String(target.text || ''), section: String(target.section || ''),
                     id: String(target.id || ''), file: String(target.file || '') };
  renderAiCtx();
  switchNavPane('ai');
  await aiSend(label, state.ai.mode || 'paper', action);
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
    <div class="np-rp-acts">
      <button type="button" class="np-rp-act" data-detail="${esc(report.id || '')}">${esc(t('rp.actDetail'))}</button>
      <button type="button" class="np-rp-del" data-del="${esc(report.id || '')}" title="${esc(t('rp.delAsk'))}">${esc(t('rp.card.del'))}</button>
    </div>
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
    btn.addEventListener('click', (ev) => { ev.stopPropagation(); deleteReport(btn.dataset.del); });
  });
  $$('#npReportsList [data-detail]').forEach((btn) => {
    btn.addEventListener('click', (ev) => { ev.stopPropagation(); openReportDetail(btn.dataset.detail); });
  });
  $$('#npReportsList .np-rp-row').forEach((row) => {
    row.addEventListener('click', () => openReportDetail(row.dataset.rp || ''));
  });
}

/* 条目 35：实验报告详情模态（报告名＋状态＋来源文件/sha256＋绑定清单）。 */
async function openReportDetail(id) {
  if (!id) return;
  const modal = $('#modalRp');
  const title = $('#rpModalTitle');
  const body = $('#rpModalBody');
  if (!modal || !title || !body) return;
  const url = reportsApiPath('/detail') + '?name=' + encodeURIComponent(id);
  try {
    const data = await getJSON(url);
    title.textContent = data.name || id;
    const meta = [
      `<div class="kbd-kv"><span>${esc(t('rp.card.file'))}</span><span>${esc(data.report || data.file || '')}</span></div>`,
      `<div class="kbd-kv"><span>${esc(t('kb.sha'))}</span><code>${esc(data.report_sha256 || '—')}</code></div>`,
      `<div class="kbd-kv"><span>${esc(t('rp.card.time'))}</span><span>${esc(data.time || '')}</span></div>`,
    ];
    const rows = (data.facts || []).map((f) => `<tr>`
      + `<td class="rp-b-id">${esc(f.id || '')}</td>`
      + `<td class="rp-b-claim">${esc(f.claim || '')}</td>`
      + `<td class="rp-b-value">${esc(f.value || '')}</td></tr>`).join('');
    const table = rows
      ? `<table class="rp-b-table"><thead><tr><th>${esc(t('rp.id'))}</th><th>${esc(t('rp.claim'))}</th><th>${esc(t('rp.value'))}</th></tr></thead><tbody>${rows}</tbody></table>`
      : `<p class="kbd-note">${esc(t('rp.detailEmpty'))}</p>`;
    body.innerHTML = `<div class="rp-d-status"><span class="np-rp-chip rp-pending_check">${esc(t('rp.st.pending_check'))}</span></div>`
      + meta.join('')
      + `<div class="kbd-title">${esc(t('rp.boundList'))}</div>` + table;
  } catch (err) {
    title.textContent = id;
    body.innerHTML = `<div class="kbd-note err">${esc((err && err.message) || String(err))}</div>`;
  }
  modal.dataset.report = id;
  modal.hidden = false;
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
  const ok = await askConfirm({ title: t('rp.delConfirmTitle'),
                                body: t('rp.delConfirmBody'), okLabel: t('confirm.ok') });
  if (!ok) return;
  const path = reportsApiPath('/delete');
  if (!path) return;
  try {
    const result = await postJSON(path, { name: id });
    toast(t('rp.deleted'));
    if (result && result.source_file) {
      toast(t('rp.deletedFile', { f: result.source_file }));
    }
    await loadReports();
  } catch (err) {
    toast(t('rp.noDelete', { e: (err && err.message) || String(err) }));
  }
}

/* 条目 35：通用确认模态（删除前问一句；Esc/遮罩/取消都算「不删」）。 */
let confirmResolver = null;

function askConfirm(opts) {
  const modal = $('#modalConfirm');
  const title = $('#cfTitle');
  const body = $('#cfBody');
  const ok = $('#cfOk');
  if (!modal || !title || !body || !ok) return Promise.resolve(false);
  const conf = opts || {};
  title.textContent = conf.title || '';
  body.textContent = conf.body || '';
  ok.textContent = conf.okLabel || t('confirm.ok');
  modal.hidden = false;
  return new Promise((resolve) => { confirmResolver = resolve; });
}

function closeConfirm(result) {
  const modal = $('#modalConfirm');
  if (modal) modal.hidden = true;
  const fn = confirmResolver;
  confirmResolver = null;
  if (typeof fn === 'function') fn(!!result);
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
  // 条目 33：左栏头部的常用功能组（中/EN ＋ PDF/全检/导出/开目录）
  // 只在 workbench 视图渲染；项目列表/新建视图整组不渲染。
  const tools = $('#lhTools');
  if (tools) tools.hidden = (view !== 'workbench');
  applyLangToggle();
}

/* 段五返修七（条目 33）：中/EN 切换搬到左栏头部。
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

/* 段五返修八（条目 34）：右栏工具条＝三枚切换钮（目录／智能助手／更多）。
   三面互斥；智能助手＝侧栏里的嵌入式对话面板（不再是浮层）。
   已激活再点「智能助手」＝无操作（收起整个侧栏用最左的图标收起钮）。 */
function switchNavPane(name) {
  if (name === 'ai' && state.nav.pane === 'ai') return;
  state.nav.pane = name;
  $('#paneToc').classList.toggle('on', name === 'toc');
  $('#paneAi').classList.toggle('on', name === 'ai');
  $('#paneMore').classList.toggle('on', name === 'more');
  $('#npToc').classList.toggle('on', name === 'toc');
  $('#npAi').classList.toggle('on', name === 'ai');
  $('#npMore').classList.toggle('on', name === 'more');
  if (name === 'ai') renderAiFace();
  // 条目 33：实验报告／知识库／版式都并进「更多」这一面，切过去就把三段都拉起来。
  if (name === 'more') {
    loadReports();
    loadKb();
    loadVenue();
  }
}

/* 面板里的智能助手面：条目 34 起助手就在侧栏面板里，这里只刷引用上下文。 */
function renderAiFace() {
  renderAiCtx();
}

/* 条目 34：半透明浮层整条拆除——助手＝侧栏里的一枚互斥面板钮。 */
function setNavCollapsed(collapsed) {
  document.body.classList.toggle('nav-collapsed', !!collapsed);
}

/* ---------------------------------------------------------------- 段六：知识库 */

function kbApiPath(suffix) {
  const project = state.project;
  if (!project) return null;
  return `/api/project/${encodeURIComponent(project.id)}/knowledge${suffix || ''}`;
}

function kbStatusLabel(file) {
  if (!file) return '';
  if (file.status === 'pending') return t('kb.pending');
  return t('kb.ready');
}

function renderKb() {
  const list = $('#kbFiles');
  if (!list) return;
  list.innerHTML = '';
  if (state.kb.loading) {
    const li = document.createElement('li');
    li.className = 'kb-empty';
    li.textContent = t('kb.loading');
    list.appendChild(li);
    return;
  }
  if (state.kb.error) {
    const li = document.createElement('li');
    li.className = 'kb-empty';
    li.textContent = state.kb.error;
    list.appendChild(li);
    return;
  }
  if (!state.kb.files.length) {
    const li = document.createElement('li');
    li.className = 'kb-empty';
    li.textContent = t('kb.empty');
    list.appendChild(li);
    return;
  }
  state.kb.files.forEach((file) => {
    const li = document.createElement('li');
    li.className = 'kb-file' + (state.kb.current === file.path ? ' on' : '');
    li.dataset.path = file.path;
    const head = document.createElement('div');
    head.className = 'kbf-head';
    const name = document.createElement('span');
    name.className = 'kbf-name';
    name.textContent = file.name;
    const meta = document.createElement('span');
    meta.className = 'kbf-meta';
    meta.textContent = `${file.size_label} · ${kbStatusLabel(file)}`;
    head.appendChild(name);
    head.appendChild(meta);
    li.appendChild(head);
    /* 条目 35：行动作收口——人人有「预览」；「删除」只给 knowledge/ 里的
       文本文件（项目源文件由章节管理管，PDF 只登记不删）。 */
    const acts = document.createElement('div');
    acts.className = 'kbf-acts';
    const prev = document.createElement('button');
    prev.type = 'button';
    prev.className = 'kbf-act';
    prev.textContent = t('kb.actPreview');
    prev.addEventListener('click', (ev) => { ev.stopPropagation(); previewKbFile(file.path); });
    acts.appendChild(prev);
    if (file.in_knowledge && file.status !== 'pending') {
      const del = document.createElement('button');
      del.type = 'button';
      del.className = 'kbf-act kbf-act-del';
      del.textContent = t('kb.actDelete');
      del.addEventListener('click', (ev) => { ev.stopPropagation(); askDeleteKbFile(file); });
      acts.appendChild(del);
    }
    li.appendChild(acts);
    if (!file.in_knowledge) {
      const note = document.createElement('div');
      note.className = 'kbf-note';
      note.textContent = t('kb.sourceNote');
      li.appendChild(note);
    }
    li.addEventListener('click', () => previewKbFile(file.path));
    list.appendChild(li);
  });
}

/* 条目 35：知识库预览改模态框（不再是侧栏内嵌框）。 */
function openKbModal(data) {
  const modal = $('#modalKb');
  const title = $('#kbModalTitle');
  const body = $('#kbModalBody');
  if (!modal || !title || !body) return;
  const info = data || {};
  title.textContent = info.name || '';
  const meta = [
    `<div class="kbd-kv"><span>${esc(t('kb.path'))}</span><code>${esc(info.path || '')}</code></div>`,
    `<div class="kbd-kv"><span>${esc(t('kb.size'))}</span><span>${esc(info.size_label || '—')}</span></div>`,
    `<div class="kbd-kv"><span>${esc(t('kb.sha'))}</span><code>${esc(info.sha256 || '—')}</code></div>`,
    `<div class="kbd-kv"><span>${esc(t('kb.status'))}</span><span>${esc(info.status === 'pending' ? t('kb.pending') : t('kb.ready'))}</span></div>`,
  ];
  let content = '';
  if (info.error) {
    content = `<div class="kbd-note err">${esc(info.error)}</div>`;
  } else if (info.status === 'pending') {
    content = `<div class="kbd-note">${esc(t('kb.pdfNote'))}</div>`;
  } else {
    const lines = String(info.text || '').split('\n');
    const cut = lines.slice(0, 200);
    const more = lines.length > 200 || info.truncated;
    content = `<div class="kbd-title">${esc(t('kb.preview'))}</div>`
      + `<pre class="kbd-text">${esc(cut.join('\n'))}</pre>`
      + (more ? `<div class="kbd-note">${esc(t('kb.fullNote'))}</div>` : '');
  }
  body.innerHTML = meta.join('') + content;
  modal.hidden = false;
}

async function loadKb() {
  const url = kbApiPath('');
  if (!url) return;
  state.kb.loading = true;
  state.kb.error = '';
  renderKb();
  try {
    const data = await getJSON(url);
    state.kb.files = (data && data.files) || [];
    state.kb.error = '';
  } catch (err) {
    state.kb.files = [];
    state.kb.error = t('kb.loadErr', { e: (err && err.message) || String(err) });
  } finally {
    state.kb.loading = false;
    renderKb();
  }
}

async function previewKbFile(path) {
  state.kb.current = path;
  const url = kbApiPath('/preview') + '?path=' + encodeURIComponent(path);
  renderKb();
  try {
    const data = await getJSON(url);
    state.kb.detail = data;
    openKbModal(data);
  } catch (err) {
    openKbModal({ name: path, path: path, text: '', size_label: '—',
                  error: (err && err.message) || String(err) });
  }
}

/* 条目 35：删除知识库文件（只许 knowledge/ 里的）——先确认，再走服务端写闸。 */
async function deleteKbFile(path) {
  const url = kbApiPath('/delete');
  if (!url) return;
  try {
    await postJSON(url, { path: path });
    toast(t('kb.deleted'));
    if (state.kb.current === path) state.kb.current = '';
    await loadKb();
  } catch (err) {
    toast(t('kb.delFail', { e: (err && err.message) || String(err) }));
  }
}

function askDeleteKbFile(file) {
  askConfirm({ title: t('kb.delTitle'), body: t('kb.delAsk'), okLabel: t('confirm.ok') })
    .then((ok) => { if (ok) deleteKbFile(file.path); });
}

async function uploadKbFile(event) {
  const input = event.target;
  if (!input || !input.files || !input.files.length) {
    toast(t('kb.noFile'));
    return;
  }
  const file = input.files[0];
  const form = new FormData();
  form.append('file', file, file.name);
  const url = kbApiPath('/upload');
  try {
    const res = await fetch(url, { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok || !data || data.ok === false) {
      toast(t('kb.uploadErr', { e: (data && data.error) || ('HTTP ' + res.status) }));
      return;
    }
    toast(t('kb.uploadOk', { name: data.name || file.name }));
    state.kb.current = '';
    state.kb.detail = null;
    await loadKb();
  } catch (err) {
    toast(t('kb.uploadErr', { e: (err && err.message) || String(err) }));
  } finally {
    input.value = '';
  }
}

/* ---------------------------------------------------------------- 段六：版式 */

function venueApiPath(suffix) {
  const project = state.project;
  if (!project) return null;
  return `/api/project/${encodeURIComponent(project.id)}/venue${suffix || ''}`;
}

function renderVenue() {
  const data = state.venue.data;
  const venueInput = $('#vnVenue');
  const deadlineInput = $('#vnDeadline');
  const lock = $('#vnLock');
  const info = $('#vnDeadlineInfo');
  const tpl = $('#vnTemplates');
  const msg = $('#vnMsg');
  if (msg) msg.textContent = state.venue.msg || '';
  if (!data) {
    if (venueInput) venueInput.value = '';
    if (deadlineInput) deadlineInput.value = '';
    if (lock) lock.innerHTML = '';
    if (info) info.innerHTML = '';
    if (tpl) tpl.innerHTML = '';
    return;
  }
  if (venueInput && document.activeElement !== venueInput) venueInput.value = data.venue || '';
  if (deadlineInput && document.activeElement !== deadlineInput) deadlineInput.value = data.deadline || '';
  if (lock) {
    const lockData = data.lang_lock || {};
    const note = lockData.note_key ? t(lockData.note_key) : (lockData.note || '');
    lock.innerHTML = `<span class="vn-lock-tag">${esc(t('vn.lockTag'))}</span><span>${esc(note)}</span>`;
    lock.classList.toggle('locked', !!(data.lang_lock && data.lang_lock.locked));
  }
  if (info) {
    const days = data.days_left;
    let text = '';
    if (days === null || days === undefined) {
      text = '';
    } else if (data.overdue) {
      text = t('vn.overdue', { d: Math.abs(days) });
    } else if (data.due_soon) {
      text = t('vn.dueSoon', { d: days });
    } else {
      text = t('vn.dueNormal', { d: days });
    }
    info.innerHTML = text ? `<span>${esc(text)}</span>` : '';
    info.classList.toggle('soon', !!(data.due_soon && !data.overdue));
    info.classList.toggle('late', !!data.overdue);
  }
  if (tpl) {
    const items = data.templates || [];
    tpl.innerHTML = items.map((item) => `
      <div class="vn-tpl-row">
        <span class="vn-tpl-name">${esc(item.name_key ? t(item.name_key) : (item.name || item.id || ''))}</span>
        <span class="vn-tpl-note">${esc(item.note_key ? t(item.note_key) : (item.note || ''))}</span>
      </div>`).join('');
  }
}

async function loadVenue() {
  const url = venueApiPath('');
  if (!url) return;
  state.venue.loading = true;
  try {
    const data = await getJSON(url);
    state.venue.data = data;
    state.venue.error = '';
  } catch (err) {
    state.venue.data = null;
    state.venue.error = t('vn.saveErr', { e: (err && err.message) || String(err) });
  } finally {
    state.venue.loading = false;
    renderVenue();
    updateDeadlineBadge();
  }
}

async function saveVenueConfig() {
  const url = venueApiPath('');
  if (!url) return;
  const venue = ($('#vnVenue') || {}).value || '';
  const deadline = ($('#vnDeadline') || {}).value || '';
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ venue: venue.trim(), deadline: deadline.trim() }),
    });
    const data = await res.json();
    if (!res.ok || !data || data.ok === false) {
      state.venue.msg = t('vn.saveErr', { e: (data && data.error) || ('HTTP ' + res.status) });
      renderVenue();
      return;
    }
    state.venue.data = data;
    state.venue.msg = t('vn.saved');
    renderVenue();
    updateDeadlineBadge();
  } catch (err) {
    state.venue.msg = t('vn.saveErr', { e: (err && err.message) || String(err) });
    renderVenue();
  }
}

/* 段六：截稿提醒徽标（到期前 7 天，导航钮上带提醒）。
   条目 33：版式已并进「更多」面板，徽标改挂在「更多」钮上（钮面无文字，只有徽标）。 */
function updateDeadlineBadge() {
  const btn = $('#npMore');
  if (!btn) return;
  let badge = btn.querySelector('.dl-badge');
  const data = state.venue.data;
  const soon = !!(data && (data.due_soon || data.overdue));
  if (!soon) {
    if (badge) badge.remove();
    btn.classList.remove('has-due');
    return;
  }
  if (!badge) {
    badge = document.createElement('span');
    badge.className = 'dl-badge';
    btn.appendChild(badge);
  }
  badge.textContent = data.overdue ? '!' : String(data.days_left);
  btn.classList.add('has-due');
}

/* 首页预览：走现有的渲染 PDF 链路（真渲染，出预览）。 */
async function renderVenuePreview() {
  const host = $('#vnPreview');
  if (!host) return;
  const project = state.project;
  const disk = currentDisk();
  if (!project || !disk) return;
  host.innerHTML = `<div class="vn-prev-note">${esc(t('rp.rerunning'))}</div>`;
  try {
    const data = await postAction('pdf');
    if (!data.ok) {
      host.innerHTML = `<div class="vn-prev-note err">${esc(data.error || data.message || t('vn.previewErr', { e: '' }))}</div>`;
      return;
    }
  } catch (err) {
    host.innerHTML = `<div class="vn-prev-note err">${esc(t('vn.previewErr', { e: (err && err.message) || String(err) }))}</div>`;
    return;
  }
  const url = `/api/disk/${encodeURIComponent(project.id)}/${encodeURIComponent(disk.id)}/pdf?t=${Date.now()}`;
  host.innerHTML = `<iframe class="vn-prev-frame" title="preview" src="${url}"></iframe>`;
}

/* ---------------------------------------------------------------- 段六：选刊指南 */

const VENUE_GUIDE_KEYS = [
  ['guide.h1', 'guide.p1'],
  ['guide.h2', 'guide.p2'],
  ['guide.h3', 'guide.p3'],
  ['guide.h4', 'guide.p4'],
];

function renderGuide() {
  const body = $('#guideBody');
  if (!body) return;
  const parts = [];
  VENUE_GUIDE_KEYS.forEach((pair) => {
    parts.push(`<h3 class="guide-h">${esc(t(pair[0]))}</h3>`);
    parts.push(`<p class="guide-p">${esc(t(pair[1]))}</p>`);
  });
  parts.push(`<p class="guide-foot">${esc(t('guide.foot'))}</p>`);
  body.innerHTML = parts.join('');
}

function openVenueGuide() {
  renderGuide();
  const modal = $('#modalGuide');
  if (modal) modal.hidden = false;
}

function closeVenueGuide() {
  const modal = $('#modalGuide');
  if (modal) modal.hidden = true;
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
  // 条目 33：字标可点，与 [Projects] 同去项目管理视图。
  $('#goBrand').addEventListener('click', () => { setView('projects'); loadProjects(); });
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
  // 段五返修七（条目 33）：右栏工具条＝纯图标收起钮 ＋ 三枚切换钮（互斥）
  $('#npCollapse').addEventListener('click', () => {
    setNavCollapsed(!document.body.classList.contains('nav-collapsed'));
  });
  $('#navOpen').addEventListener('click', () => { setNavCollapsed(false); });
  $('#npToc').addEventListener('click', () => { switchNavPane('toc'); });
  $('#npAi').addEventListener('click', () => { switchNavPane('ai'); });
  // 条目 33：实验报告／知识库／版式三段合并进「更多」面板，工具条只剩一枚钮。
  $('#npMore').addEventListener('click', () => { switchNavPane('more'); });
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
  $$('#aiPane .aq').forEach((btn) => {
    btn.addEventListener('click', () => aiSend(t('ai.q' + btn.dataset.q + '.text'), 'ask'));
  });
  $('#aiFab').addEventListener('click', clearAiConversation);
  // 段六：模式切换（聊想法／写论文）
  $('#aiModes').addEventListener('click', (ev) => {
    const btn = ev.target.closest('button[data-mode]');
    if (!btn) return;
    setAiMode(btn.dataset.mode);
  });
  $('#askReportRead').addEventListener('click', () => {
    switchNavPane('ai');
    aiSend(t('ai.reportQ'), 'explain');
  });
  $('#ptAsk').addEventListener('click', () => {
    const target = paraAskTarget;
    if (!target) return;
    askAiAbout(target.text, target.section, target.id, target.file);
  });
  // 段六：段落 ⋯ 菜单（编辑 ＋ 续写／改写／提问）
  $('#ptMore').addEventListener('click', (ev) => {
    ev.stopPropagation();
    openParaMenu();
  });
  $('#miEdit').addEventListener('click', () => {
    const target = paraAskTarget;
    closeParaMenu();
    if (!target) return;
    enterEdit(target.id, target.file || '');
  });
  $('#miContinue').addEventListener('click', () => paraAction('continue'));
  $('#miRewrite').addEventListener('click', () => paraAction('rewrite'));
  $('#miAsk').addEventListener('click', () => paraAction('ask'));
  $('#paraMenu').addEventListener('click', (ev) => ev.stopPropagation());
  $('#ptools').addEventListener('mouseenter', () => clearTimeout(paraToolsTimer));
  $('#ptools').addEventListener('mouseleave', hideParaTools);
  // 段六：知识库上传
  $('#npKbUploadBtn').addEventListener('click', () => $('#npKbUpload').click());
  $('#npKbUpload').addEventListener('change', uploadKbFile);
  // 段六：版式（存配置 ＋ 首页预览 ＋ 选刊指南）
  $('#vnSave').addEventListener('click', saveVenueConfig);
  $('#vnPreviewBtn').addEventListener('click', renderVenuePreview);
  $('#npVenueGuideBtn').addEventListener('click', openVenueGuide);
  $('#guideClose').addEventListener('click', closeVenueGuide);
  $('#guideGo').addEventListener('click', () => {
    closeVenueGuide();
    switchNavPane('more');
    renderVenuePreview();
  });
  $('#modalGuide').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalGuide') closeVenueGuide();
  });
  // 段五：实验报告列表（导航面板里）
  $('#npImportBtn').addEventListener('click', openWizard);
  // 条目 35：知识库预览模态 ＋ 报告详情模态 ＋ 通用确认模态
  $('#kbModalClose').addEventListener('click', () => { $('#modalKb').hidden = true; });
  $('#modalKb').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalKb') $('#modalKb').hidden = true;
  });
  $('#rpModalClose').addEventListener('click', () => { $('#modalRp').hidden = true; });
  $('#modalRp').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalRp') $('#modalRp').hidden = true;
  });
  $('#rpModalDel').addEventListener('click', () => {
    const id = $('#modalRp').dataset.report || '';
    $('#modalRp').hidden = true;
    deleteReport(id);
  });
  $('#cfOk').addEventListener('click', () => closeConfirm(true));
  $('#cfCancel').addEventListener('click', () => closeConfirm(false));
  $('#modalConfirm').addEventListener('click', (ev) => {
    if (ev.target.id === 'modalConfirm') closeConfirm(false);
  });
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
    // 条目 35：知识库预览／报告详情／确认框都吃 Esc
    const kbModal = $('#modalKb');
    if (kbModal && !kbModal.hidden) kbModal.hidden = true;
    const rpModal = $('#modalRp');
    if (rpModal && !rpModal.hidden) rpModal.hidden = true;
    const cfModal = $('#modalConfirm');
    if (cfModal && !cfModal.hidden) closeConfirm(false);
    const check = $('#modalCheck');
    if (check && !check.hidden) check.hidden = true;
    const action = $('#modalAction');
    if (action && !action.hidden) action.hidden = true;
    const wizard = $('#wizardModal');
    if (wizard && !wizard.hidden) closeWizard();
    const guide = $('#modalGuide');
    if (guide && !guide.hidden) closeVenueGuide();
    closeFactCard();
    closeParaMenu();
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
    if (ev.target.closest('.navpanel') || ev.target.closest('.modal')) return;
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
