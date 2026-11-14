// 事实闸 FactScribe 呈现层回归测试：离线、零依赖（node:test + node:assert）。
//
// 跑法（integrations/minifactscribe 目录）：
//   node --test tests/
//
// 这一组盯的是"人看得懂"这件事，不是判据。判据层的正反例在 audit.test.mjs。
// 之所以要钉死：呈现层的退化（英文码直接怼脸、状态只靠颜色、过期结果冒充现状）
// 不会让任何测试变红，但会让工具变得没法用。

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const HTML = readFileSync(new URL('../miniapp/client/index.html', import.meta.url), 'utf8');
const JS = readFileSync(new URL('../miniapp/client/app.js', import.meta.url), 'utf8');
const CSS = readFileSync(new URL('../miniapp/client/app.css', import.meta.url), 'utf8');
const AUDIT = readFileSync(new URL('../miniapp/node/audit.mjs', import.meta.url), 'utf8');
const SERVER = readFileSync(new URL('../miniapp/node/server.mjs', import.meta.url), 'utf8');
const MINIAPP = readFileSync(new URL('../miniapp/miniapp.json', import.meta.url), 'utf8');
const LAUNCHER = readFileSync(new URL('../miniapp/node/launcher.mjs', import.meta.url), 'utf8');
const PROJECTS = readFileSync(new URL('../miniapp/node/projects.mjs', import.meta.url), 'utf8');

/** 从 app.js 里取出 ISSUE_LABEL 的键。 */
function issueLabelKeys() {
  const block = JS.slice(JS.indexOf('const ISSUE_LABEL = {'), JS.indexOf('};', JS.indexOf('const ISSUE_LABEL = {')));
  return new Set([...block.matchAll(/^\s{2}'?([A-Z_]+)'?:/gm)].map((m) => m[1]));
}

/** 引擎里出现过的全部违规码：issue(...) 调用 + PRESCRIPTIONS 的键。 */
function engineCodes() {
  const codes = new Set();
  for (const m of AUDIT.matchAll(/issue\(\s*'(?:red|yellow)'\s*,\s*'([A-Z_]+)'/g)) codes.add(m[1]);
  const block = AUDIT.slice(AUDIT.indexOf('export const PRESCRIPTIONS = {'), AUDIT.indexOf('};', AUDIT.indexOf('export const PRESCRIPTIONS = {')));
  for (const m of block.matchAll(/^\s{2}([A-Z_]+):\s*\{/gm)) codes.add(m[1]);
  return codes;
}

// ------------------------------------------------------- 1. 违规码必须有人话

test('引擎里的每个违规码都有中文短名：新增码不许只留英文常量', () => {
  const labels = issueLabelKeys();
  const missing = [...engineCodes()].filter((c) => !labels.has(c)).sort();
  assert.deepEqual(missing, [], '这些违规码还没有中文短名：' + missing.join('、'));
});

test('中文短名本身真的是中文，且不是空串', () => {
  const block = JS.slice(JS.indexOf('const ISSUE_LABEL = {'), JS.indexOf('};', JS.indexOf('const ISSUE_LABEL = {')));
  const pairs = [...block.matchAll(/^\s{2}'?([A-Z_]+)'?:\s*'([^']*)'/gm)];
  assert.ok(pairs.length > 20, '短名表不该只有几条');
  for (const [, code, label] of pairs) {
    assert.match(label, /[\u4e00-\u9fff]/, code + ' 的短名里没有中文');
  }
});

// ------------------------------------------------------------- 2. 过期要说出来

test('改了内容但没重跑审计，界面必须声明结果已过期', () => {
  assert.match(JS, /function refreshStale\(\)/, '客户端应有过期判定');
  assert.match(JS, /state\.auditSig/, '应记录审计时的内容指纹');
  assert.match(JS, /sigOf\(state\.project\)\s*!==\s*state\.auditSig/, '过期判定应基于内容指纹比对');
  assert.match(HTML, /id="stale-banner"/, '页面应有过期提示条');
  assert.match(HTML, /id="btn-rerun"/, '过期时要有"重新审计"的出路');
});

test('过期时顶栏结论不能继续用红/黄牌冒充现状', () => {
  assert.match(JS, /verdict-stale/, '应有独立的过期样式分支');
  const block = JS.slice(JS.indexOf('function renderVerdict'), JS.indexOf('// ------------------------------------------------------------------ 正文'));
  assert.match(block, /state\.stale[\s\S]*结果已过期/, '过期时应显示"结果已过期"而不是旧的绿/黄/红');
});

test('审计前先保存：否则服务端审旧稿，结论却按新稿记为新鲜', () => {
  const block = JS.slice(JS.indexOf('async function runAudit'), JS.indexOf('async function loadDemo'));
  assert.match(block, /await saveNow\(\)/, '审计前必须先把当前项目落到服务端');
  assert.match(block, /if \(!saved\)/, '保存失败时不能继续审计');
  assert.match(block, /saveNow\(\)[\s\S]*api\('\/api\/audit'/, '保存必须发生在审计请求之前');
});

test('[hidden] 必须压过组件自己的 display：否则"隐藏"只改了属性', () => {
  assert.match(
    CSS,
    /\[hidden\]\s*\{\s*display:\s*none\s*!important/,
    '组件用了 display:flex 时，hidden 属性会被顶掉，必须有全局兜底规则'
  );
});

// --------------------------------------------------- 3. 判定不能只靠颜色

test('数字判定同时给符号和文字：色弱与单色打印也读得出', () => {
  assert.match(JS, /const CHIP = \{/, '应有判定符号表');
  for (const key of ['ok', 'warn', 'bad', 'mute']) {
    assert.match(JS, new RegExp(key + ':\\s*\\{\\s*sym:'), key + ' 判定应有符号');
  }
  assert.match(JS, /chip-sym/, '符号应渲染进 chip');
  assert.match(HTML, /chip-legend/, '页面应有判定图例');
  for (const sym of ['✓', '!', '✕']) {
    assert.ok(HTML.includes(sym), '图例里应有符号 ' + sym);
  }
});

// ----------------------------------------------- 4. 术语与位置要说人话

test('事实账与覆盖矩阵用同一套状态词', () => {
  assert.match(JS, /const USED_IN_LABEL = \{/, '应有状态词映射表');
  assert.match(JS, /'已内联绑定':\s*'已绑定'/, '"已内联绑定"应统一显示为"已绑定"');
});

test('问题位置翻成人话，不再直接甩 "正文:12"', () => {
  assert.match(JS, /function formatLocation/, '应有位置格式化函数');
  assert.match(JS, /正文 第 /, '正文位置应带行号说明');
});

test('内部违规码降级为次要信息，中文短名当主角', () => {
  assert.match(JS, /issue-label/, '问题卡应有中文短名元素');
  assert.match(JS, /class="code" title="内部违规码"/, '违规码应标成内部信息');
});

// ------------------------------------------------- 5. 危险动作必须先确认

test('覆盖项目、删事实、改哈希都要先确认', () => {
  assert.match(HTML, /id="demo-confirm"/, '载入演示数据应有确认');
  assert.match(HTML, /id="fact-delete-confirm"/, '删除事实应有确认');
  assert.match(JS, /data-rehash-confirm/, '更新哈希应有确认');
  assert.match(JS, /确认更新/, '更新哈希的确认要说清后果');
});

test('删除按钮只在编辑态出现，不给一个永远灰着的按钮', () => {
  assert.match(JS, /\$\('#btn-delete-fact'\)\.hidden = !f/, '删除按钮应随编辑态显隐');
});

// ------------------------------------------------------ 6. 表单要能填错

test('必填字段有标记与字段级错误，不靠一个 toast 打发了事', () => {
  assert.ok((HTML.match(/aria-required="true"/g) || []).length >= 4, '必填字段应有 aria-required');
  assert.match(HTML, /id="form-errors"/, '应有错误摘要区');
  assert.match(HTML, /class="field-error"/, '应有字段级错误位');
  assert.match(JS, /function validateFact/, '应有校验函数');
  assert.match(JS, /function showFormErrors/, '应有错误呈现函数');
});

// --------------------------------------------------- 7. 表头与表格可读

test('表头不换行：中文表头被压成竖排时整张表都读不下去', () => {
  assert.match(
    CSS,
    /\.data-table th\s*\{[^}]*white-space:\s*nowrap/,
    '表头应 nowrap'
  );
});

test('正文与 bib 的编辑框有可见 label，不只靠 aria-label', () => {
  assert.match(HTML, /for="manuscript-input"/, '正文应有可见 label');
  assert.match(HTML, /for="bib-input"/, 'bib 应有可见 label');
});

// -------------------------------------------------------- 8. 服务端别乱报 500

test('未知路径回 404 而不是 500：content-type 不能是 undefined', () => {
  assert.match(
    SERVER,
    /function sendText\([^)]*type\s*=\s*'text\/plain/,
    'sendText 的 content-type 必须有默认值'
  );
});

test('本地工作台是独立入口，并明确与本地草稿不是同一个项目', () => {
  assert.match(HTML, /id="panel-workbench"/, '应有独立的工作台面板');
  assert.match(HTML, /id="btn-workbench-connect"/, '应有连接按钮');
  assert.match(HTML, /不是同一个项目/, '界面必须说清工作台项目与本地草稿不同');
  assert.match(JS, /\/api\/workbench/, '客户端应调用工作台代理接口');
  assert.match(JS, /runWorkbenchAudit/, '应有工作台审计入口');
});

test('工作台可载入项目并按节保存，且保存前说明写给工作台项目', () => {
  assert.match(HTML, /id="btn-workbench-load"/, '应有载入项目按钮');
  assert.match(HTML, /id="workbench-section-select"/, '应有节选择');
  assert.match(HTML, /id="btn-workbench-save"/, '应有保存按钮');
  assert.match(HTML, /写给工作台项目，不是本地草稿/, '必须说明写入目标');
  assert.match(JS, /wb\('\/project'\)/, '应载入工作台项目（经 wb 适配）');
  assert.match(JS, /wb\('\/sections'\)/, '应能保存工作台章节（经 wb 适配）');
  assert.match(JS, /MODE\.mini \? '\/api\/workbench' : '\/api'/, 'MiniApp 走 Node 代理，网页直连 Python');
});


test('AI 起草是独立入口：页面发起 agent，输出只进候选区', () => {
  assert.match(MINIAPP, /"agentAccess": \["session.run", "session.read"\]/, '必须声明 session.run + session.read');
  assert.match(HTML, /id="panel-ai"/, '应有 AI 起草面板');
  assert.match(HTML, /id="btn-ai-run"/, '应有生成候选按钮');
  assert.match(HTML, /id="ai-candidate"/, '应有候选正文区');
  assert.match(JS, /mcode\?\.miniapp\?\.agent/, '应从页面调用宿主 agent');
  assert.match(JS, /agent\.run/, '应调用 agent.run');
  assert.match(JS, /text\.delta/, '应流式接收 text.delta');
  assert.match(JS, /permission\.requested/, '应把审批交给用户');
  assert.match(JS, /acceptAi/, '采纳后才写工作台');
});


test('非项目对话打开时能检测并报错：AI 必须 fail-closed', () => {
  assert.match(MINIAPP, /"hostAccess": \["navigation.read"\]/, '需要 navigation.read 才能判断打开位置');
  assert.match(HTML, /id="session-banner"/, '应有非对话提示条');
  assert.match(JS, /host\.navigation\.getState/, '应读取 navigation.getState');
  assert.match(JS, /hostView === 'conversation'/, '只有 conversation 才允许 AI');
  assert.match(JS, /AI 起草已禁用/, '未知/非对话时要明说禁用');
});


test('能从当前对话读项目文件夹（session.read），没有就提示', () => {
  assert.match(JS, /agent\.session\(\)/, '应读当前对话的 session');
  assert.match(JS, /workspaceDir/, '应读 workspaceDir');
  assert.match(JS, /isDefaultWorkspace/, '要区分默认工作区');
  assert.match(HTML, /id="workbench-host-path"/, '工作台应显示当前对话项目');
  assert.match(JS, /当前对话没有项目文件夹/, '没有项目文件夹时要提示');
});


test('论文项目＝文件夹：列表、路径校验、切换即换文件夹', () => {
  assert.match(HTML, /id="project-select"/, '应有最近项目下拉');
  assert.match(HTML, /id="project-path"/, '应有项目文件夹输入');
  assert.match(HTML, /id="btn-project-add"/, '应能把文件夹加入列表');
  assert.match(HTML, /id="btn-project-forget"/, '应能从列表移除（不动文件夹）');
  assert.match(HTML, /id="btn-workbench-start"/, '应有一键启动');
  assert.match(HTML, /id="btn-workbench-stop"/, '应能停止');
  assert.match(HTML, /id="workbench-allow-write"/, '写权限必须是显式开关');
  assert.match(JS, /\/api\/projects/, '项目列表走 Node 接口');
  assert.match(JS, /\/api\/workbench\/start/, '启动走 Node 接口');
  assert.match(JS, /用当前对话项目/, '应能用当前对话的文件夹');
  assert.match(PROJECTS, /paperkit\.toml/, '校验项目必须含 paperkit.toml');
  assert.match(PROJECTS, /MAX_PROJECTS/, '登记册必须有上限，不能无限长');
});

test('一键启动只跑固定命令：不过 shell、不收任意命令', () => {
  assert.match(LAUNCHER, /shell: false/, '子进程不能过 shell');
  assert.match(LAUNCHER, /'serve', project, '--port', '0', '--json'/, '参数顺序固定');
  assert.match(LAUNCHER, /--allow-write/, '写权限要显式传');
  assert.doesNotMatch(LAUNCHER, /execSync|shell: true|spawn\(\s*['"]sh/, '不许拼 shell 命令');
  assert.match(SERVER, /\/api\/workbench\/start/, 'Node 侧要有启动路由');
  assert.match(SERVER, /stopServe/, '断开/退出要收子进程');
  assert.match(SERVER, /resolveProjectDir/, '启动前必须重新校验文件夹');
});

test('宿主上下文检测真的在启动时跑，不是只定义', () => {
  assert.match(JS, /await detectHostContext\(\)/, 'init 必须先问宿主打开位置');
  assert.match(JS, /session-banner/, '非对话要能看见提示条');
});


test('一套界面两种启动：宿主检测决定显示哪一区', () => {
  assert.match(JS, /mcode\?\.miniapp/, '靠宿主对象判断是不是 MiniApp');
  assert.match(JS, /showHostUi/, '宿主专属区由一个开关控制');
  assert.match(JS, /applyMode/, '启动时要应用模式');
  assert.match(JS, /data-tab="' \+ tab \+ '"/, '按页签逐个显隐');
  assert.match(JS, /'manuscript', 'ledger', 'refs', 'protect', 'audit', 'ai'/, '草稿与 AI 页签算宿主专属');
});

test('网页模式：直连 Python、要 token、藏掉宿主专属按钮', () => {
  assert.match(JS, /MODE\.mini \? '\/api\/workbench' : '\/api'/, '接口按模式分流');
  assert.match(JS, /Authorization = 'Bearer ' \+ state\.token/, '网页模式带 token');
  assert.match(JS, /showTokenPanel/, '缺 token 要提示粘贴');
  assert.match(HTML, /id="token-panel"/, '需要 token 面板');
  assert.match(JS, /这是 MiniApp 专属按钮/, '网页里启动按钮要说明为什么不能点');
});

test('开发模式 --dev：网页也显示宿主专属区，并说明只是预览', () => {
  assert.match(JS, /get\('dev'\) === '1'/, '页面认 ?dev=1');
  assert.match(JS, /开发模式：宿主专属的按钮和输入都显示出来了/, '要说清只是界面预览');
});

test('编译、事实、证据在统一界面里都有入口', () => {
  assert.match(HTML, /id="btn-wb-build"/, '应有编译 PDF');
  assert.match(HTML, /id="wb-fact-form"/, '应有工作台事实表单');
  assert.match(HTML, /id="btn-wb-freeze"/, '应有证据冻结');
  assert.match(JS, /wb\('\/build'\)/, '编译走工作台接口');
  assert.match(JS, /wb\('\/evidence'\)/, '证据走工作台接口');
  assert.match(JS, /wb\('\/pdf'\)/, 'PDF 走工作台接口');
});


test('网页也能管项目：不带路径启动，页面里选文件夹', () => {
  assert.match(JS, /chooseProject/, '网页里选项目要让服务切过去');
  assert.match(JS, /还没有选论文项目/, '未选项目要说清下一步');
  assert.match(JS, /\/api\/projects/, '项目列表与加入走同一接口');
  assert.match(HTML, /id="project-select"/, '最近项目下拉两种模式都该在');
  assert.match(HTML, /id="btn-project-add"/, '加入项目列表两种模式都该在');
  assert.doesNotMatch(JS, /'#btn-project-add', '#btn-project-host',/, '网页里不能禁用加入按钮');
});
