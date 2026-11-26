// 行尾保真：CRLF / LF / 混合三种文件走一遍「打开→编辑→保存」必须原样回来。
//
// 跑法（integrations/minifactscribe 目录）：
//   node --test integrations/minifactscribe/tests/*.test.mjs
//
// 背景（为什么浏览器这一层要管行尾）：
//   * HTML 规范规定 textarea 的 API value 归一为 LF——真 Chrome 158 实测：
//     textarea.value = "A\r\nB" 读回来是 "A\nB"。浏览器拿不到 CRLF。
//   * 引擎的读路径（factscribe/config.py 的 read_text）做通用换行翻译，
//     CRLF 在到达浏览器之前就变成 LF 了。接口层也拿不到原始行尾。
//   * 行尾的真相只在磁盘上的原文件里，所以由 Node 代理在保存时按原风格摆回去。

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer as createNetServer, createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, test } from 'node:test';

import {
  applyEnding, detectEol, dominantEnding, sameContent, splitKeepEnds, toLfOnly,
} from '../miniapp/node/eol.mjs';
import { resolveInRoot, start } from '../miniapp/node/server.mjs';

const PLUGIN_ROOT = new URL('..', import.meta.url).pathname;
const REPO_ROOT = new URL('../../..', import.meta.url).pathname;

let home;
let dataDir;
let base;
let dispose;
let savedHome;
let savedPythonPath;

// ---------------------------------------------------------------- 小工具

/** 数一数文本里的行尾（测试自己算一遍，不信被测代码的结论）。 */
function eolStats(text) {
  const crlf = (text.match(/\r\n/g) || []).length;
  const lf = (text.match(/(?<!\r)\n/g) || []).length;
  const cr = (text.match(/\r(?!\n)/g) || []).length;
  return { crlf, lf, cr };
}

/** 浏览器那一层：textarea 的 .value（HTML 规范归一为 LF）。 */
function browserValue(text) {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = createNetServer();
    probe.once('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const port = probe.address().port;
      probe.close(() => resolve(port));
    });
  });
}

// ------------------------------------------------------- 1. 行尾模块本身

test('行尾模块：切分时行尾单独摘出来，行内容一字不动', () => {
  const parts = splitKeepEnds('甲\r\n乙\n丙');
  assert.deepEqual(parts.map((p) => p.content), ['甲', '乙', '丙']);
  assert.deepEqual(parts.map((p) => p.ending), ['\r\n', '\n', '']);
});

test('行尾模块：落单的 \r 是正文里的字符，不当行尾', () => {
  const parts = splitKeepEnds('甲\r乙\n丙');
  assert.deepEqual(parts.map((p) => p.content), ['甲\r乙', '丙']);
  assert.deepEqual(parts.map((p) => p.ending), ['\n', '']);
});

test('行尾模块：认出 CRLF / LF / 混合三种文件', () => {
  assert.equal(detectEol('a\r\nb\r\nc').style, 'crlf');
  assert.equal(detectEol('a\nb\nc').style, 'lf');
  assert.equal(detectEol('a\r\nb\nc').style, 'mixed');
  assert.equal(detectEol('单行没有换行').style, 'none');
});

test('行尾模块：主导行尾取多数，计数相同取 CRLF（与引擎 textio 同一口径）', () => {
  assert.equal(dominantEnding('a\r\nb\r\nc\n'), '\r\n');
  assert.equal(dominantEnding('a\nb\nc\r\n'), '\n');
  assert.equal(dominantEnding('a\r\nb\n'), '\r\n');
  assert.equal(dominantEnding('没有换行'), '\n');
});

test('行尾模块：换行尾不动内容，末行有没有换行也照旧', () => {
  const source = '第一段\n第二段\n第三段';
  const out = applyEnding(source, '\r\n');
  assert.equal(out, '第一段\r\n第二段\r\n第三段');
  assert.equal(out.endsWith('\r\n'), false, '原来末尾没换行，换完还是没有');
  assert.equal(applyEnding('a\n', '\r\n'), 'a\r\n', '原来末尾有换行，换完还是有');
});

test('行尾模块：传给引擎的形态一律 LF，不带 \r', () => {
  assert.equal(toLfOnly('a\r\nb\r\nc'), 'a\nb\nc');
  assert.equal(toLfOnly('a\r\nb\nc'), 'a\nb\nc');
});

test('行尾模块：内容一致只看行内容，行尾不同不算内容不同', () => {
  assert.equal(sameContent('a\r\nb', 'a\nb'), true);
  assert.equal(sameContent('a\r\nb', 'a\nb\nc'), false);
  assert.equal(sameContent('a\r\nb', 'a\nxb'), false);
});

// --------------------------------------------- 2. 代理这一层：三种往返
//
// 假上游扮演 Python 引擎的写路径。writeMode 用来模拟两种引擎：
//   'verbatim'          —— 字节保真的引擎（textio 那条分支合进来之后的样子）
//   'windowsTranslate'  —— Python 文本模式：Windows 上把每个 '\n' 翻成 '\r\n'

let fake = null;   // { server, seen, project, writeMode }

async function startFakeUpstream(project, writeMode) {
  const seen = [];
  const server = createServer((request, response) => {
    const reply = (code, body) => {
      response.writeHead(code, { 'content-type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    const chunks = [];
    request.on('data', (chunk) => chunks.push(chunk));
    request.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8');
      let body = {};
      try { body = raw ? JSON.parse(raw) : {}; } catch { body = {}; }
      if (request.url === '/api/health') return reply(200, { ok: true, service: 'workbench' });
      if (request.url === '/api/capabilities') return reply(200, { ok: true, engine: 'python' });
      if (request.url === '/api/status') return reply(200, { ok: true, root: project });
      if (request.url === '/api/project') {
        return reply(200, {
          ok: true, root: project,
          sections: [{ file: 'sections/01.tex', text: 'x' }],
        });
      }
      if (request.url === '/api/sections' && request.method === 'PUT') {
        seen.push(body);
        // 模拟引擎写盘：verbatim 原样写；windowsTranslate 按 Python 文本模式翻。
        const text = writeMode === 'windowsTranslate'
          ? body.text.replace(/\r\n/g, '\n').replace(/\n/g, '\r\n')
          : body.text;
        writeFileSync(join(project, body.file), text, 'utf8');
        return reply(200, { ok: true, file: body.file, bytes: Buffer.byteLength(text, 'utf8') });
      }
      return reply(404, { ok: false, error: { code: 'NOT_FOUND', message: 'no' } });
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  fake = { server, seen, project, writeMode, url: 'http://127.0.0.1:' + server.address().port };
  return fake;
}

async function stopFakeUpstream() {
  if (!fake) return;
  await new Promise((resolve) => fake.server.close(resolve));
  fake = null;
}

async function call(path, options = {}) {
  const res = await fetch(base + path, {
    headers: { 'content-type': 'application/json' },
    ...options,
  });
  const text = await res.text();
  let body;
  try { body = JSON.parse(text); } catch { body = text; }
  return { status: res.status, body };
}

/** 造一个项目：只有一节 sections/01.tex，行尾由调用方给。 */
function makeProject(originalBytes) {
  const project = mkdtempSync(join(tmpdir(), 'fs-eol-project-'));
  mkdirSync(join(project, 'sections'), { recursive: true });
  writeFileSync(join(project, 'factscribe.toml'),
    '[project]\ntitle = "EOL"\nsections = "sections/*.tex"\n', 'utf8');
  writeFileSync(join(project, 'sections/01.tex'), Buffer.from(originalBytes, 'utf8'));
  return project;
}

/** 走一遍「打开→编辑→保存」，返回保存后磁盘上的字节。 */
async function roundTrip(original, editedText, writeMode) {
  const project = makeProject(original);
  await startFakeUpstream(project, writeMode);
  try {
    const connect = await call('/api/workbench', {
      method: 'PUT',
      body: JSON.stringify({ url: fake.url, token: 'fake-token' }),
    });
    assert.equal(connect.status, 200, JSON.stringify(connect.body));
    // 打开：引擎给的是归一过的 LF（这一层本来就拿不到 CRLF）。
    const view = await call('/api/workbench/project');
    assert.equal(view.status, 200, JSON.stringify(view.body));
    // 保存：把编辑后的正文送进去。
    const saved = await call('/api/workbench/sections', {
      method: 'PUT',
      body: JSON.stringify({ file: 'sections/01.tex', text: editedText }),
    });
    assert.equal(saved.status, 200, JSON.stringify(saved.body));
    return {
      saved,
      seen: fake.seen[fake.seen.length - 1],
      onDisk: readFileSync(join(project, 'sections/01.tex'), 'utf8'),
    };
  } finally {
    await stopFakeUpstream();
    rmSync(project, { recursive: true, force: true });
  }
}

before(async () => {
  home = mkdtempSync(join(tmpdir(), 'minifactscribe-eol-'));
  dataDir = join(home, 'data');
  mkdirSync(dataDir, { recursive: true });
  savedHome = process.env.HOME;
  process.env.HOME = home;
  savedPythonPath = process.env.PYTHONPATH;
  process.env.PYTHONPATH = [REPO_ROOT, savedPythonPath].filter(Boolean).join(':');
  const port = await freePort();
  const controller = new AbortController();
  ({ dispose } = await start({
    dataDir,
    pluginRoot: PLUGIN_ROOT,
    listen: { host: '127.0.0.1', port },
    signal: controller.signal,
    logger: { debug() {}, info() {}, warn() {}, error() {} },
  }));
  base = 'http://127.0.0.1:' + port;
});

after(async () => {
  if (dispose) await dispose();
  process.env.HOME = savedHome;
  if (savedPythonPath === undefined) delete process.env.PYTHONPATH;
  else process.env.PYTHONPATH = savedPythonPath;
  rmSync(home, { recursive: true, force: true });
});

test('CRLF 文件：保存后仍是 CRLF，一个字节不多一个字节不少', async () => {
  const original = '\\section{引言}\r\n\r\n这是一段中文，含全角括号（）与 emoji 🧪。\r\n值是 12.5 \\fact{X} 与引用 \\\\cite{key1}。\r\n最后一行。\r\n';
  const browser = browserValue(original);          // 浏览器只给得出 LF
  assert.equal(eolStats(browser).crlf, 0, '浏览器这一层拿不到 CRLF（前题）');

  const out = await roundTrip(original, browser, 'verbatim');
  assert.equal(out.onDisk, original, 'CRLF 文件保存后必须逐字节回到原样');
  assert.equal(eolStats(out.onDisk).crlf, 5);
  assert.equal(eolStats(out.onDisk).lf, 0, '不许出现混合行尾');
  assert.equal(out.saved.body.bytes, Buffer.byteLength(original, 'utf8'),
    '响应里的字节数要等于落盘后的真实大小');
});

test('CRLF 文件：引擎是 Windows 文本模式（会把 \n 翻成 \r\n）也保得住', async () => {
  const original = '第一行\r\n第二行\r\n第三行\r\n';
  const out = await roundTrip(original, browserValue(original), 'windowsTranslate');
  assert.equal(out.onDisk, original, '引擎翻了行尾，代理要按原风格校正回来');
  assert.equal(out.onDisk.includes('\r\r\n'), false, '绝不能出现 \r\r\n');
});

test('LF 文件：保存后仍是 LF，逐字节一致', async () => {
  const original = '\\section{引言}\n\n这是一段中文，含全角括号（）与 emoji 🧪。\n值是 12.5 \\fact{X} 与引用 \\\\cite{key1}。\n最后一行。\n';
  const out = await roundTrip(original, browserValue(original), 'verbatim');
  assert.equal(out.onDisk, original, 'LF 文件保存后必须逐字节回到原样');
  assert.equal(eolStats(out.onDisk).crlf, 0);
  assert.equal(eolStats(out.onDisk).lf, 5);
});

test('LF 文件：Windows 上引擎会把 \n 翻成 \r\n，代理要改回 LF', async () => {
  const original = '第一行\n第二行\n第三行\n';
  const out = await roundTrip(original, browserValue(original), 'windowsTranslate');
  assert.equal(out.onDisk, original, 'LF 文件在 Windows 上也不许被写成 CRLF');
  assert.equal(eolStats(out.onDisk).crlf, 0);
});

test('混合行尾文件：保存后统一成主导行尾，不留混合', async () => {
  const original = '第一行\r\n第二行\r\n第三行\n第四行\n';
  const out = await roundTrip(original, browserValue(original), 'verbatim');
  assert.equal(eolStats(out.onDisk).crlf, 4, 'CRLF 占多数就统一成 CRLF');
  assert.equal(eolStats(out.onDisk).lf, 0, '不许留混合行尾');
  assert.equal(out.onDisk.replace(/\r\n/g, '\n'), original.replace(/\r\n/g, '\n'),
    '内容（去掉行尾后）必须一字不动');
});

test('传给引擎的正文不带 \r：引擎那一层不会被写出 \r\r\n', async () => {
  const original = '第一行\r\n第二行\r\n';
  const out = await roundTrip(original, browserValue(original), 'windowsTranslate');
  assert.equal(out.seen.text.includes('\r'), false, '引擎收到的正文里不许有 \r');
  assert.equal(out.seen.text, '第一行\n第二行\n');
});

test('保存时新增的行按文件既有风格写：CRLF 文件补进去的行也是 CRLF', async () => {
  const original = '第一行\r\n第二行\r\n';
  const edited = '第一行\n新增的一行\n第二行\n';   // 用户在中间插了一行
  const out = await roundTrip(original, edited, 'verbatim');
  assert.equal(out.onDisk, '第一行\r\n新增的一行\r\n第二行\r\n',
    '新行要用文件既有风格，不能混进 LF');
  assert.equal(eolStats(out.onDisk).lf, 0);
});

test('用户输入的字符原样保留：全角、emoji、\fact{}/\cite{} 标记一个不动', async () => {
  const original = '数值 12.5 \\fact{X}，引用 \\\\cite{key1}。\r\n全角（括号）与 emoji 🧪🚀。\r\n';
  const edited = browserValue(original).replace('12.5', '13.75');
  const out = await roundTrip(original, edited, 'verbatim');
  assert.ok(out.onDisk.includes('13.75'), '改过的数字要写进去');
  assert.ok(out.onDisk.includes('\\fact{X}'), '标记不许被改写');
  assert.ok(out.onDisk.includes('\\\\cite{key1}'), '标记不许被改写');
  assert.ok(out.onDisk.includes('（括号）'), '全角字符不许被改写');
  assert.ok(out.onDisk.includes('🧪🚀'), 'emoji 不许被改写');
  assert.equal(eolStats(out.onDisk).crlf, 2, '行尾还是 CRLF');
});

test('保存时不碰文件里别人刚改过的内容', async () => {
  const project = makeProject('第一行\r\n第二行\r\n');
  await startFakeUpstream(project, 'verbatim');
  try {
    const connect = await call('/api/workbench', {
      method: 'PUT',
      body: JSON.stringify({ url: fake.url, token: 'fake-token' }),
    });
    assert.equal(connect.status, 200);
    await call('/api/workbench/project');
    // 模拟「保存的同时有人改了文件」：引擎写回来的内容与我们要的不一样。
    fake.server.removeAllListeners('request');
    fake.server.on('request', (request, response) => {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: true }));
      writeFileSync(join(project, 'sections/01.tex'), '别人写的第三行\r\n', 'utf8');
    });
    const saved = await call('/api/workbench/sections', {
      method: 'PUT',
      body: JSON.stringify({ file: 'sections/01.tex', text: '第一行\n第二行\n' }),
    });
    assert.equal(saved.status, 200);
    assert.equal(readFileSync(join(project, 'sections/01.tex'), 'utf8'), '别人写的第三行\r\n',
      '内容被别处改过，就不要覆盖它');
  } finally {
    await stopFakeUpstream();
    rmSync(project, { recursive: true, force: true });
  }
});

test('越界路径不写盘：../ 逃出项目根的一律不碰', () => {
  assert.equal(resolveInRoot('/tmp/proj', '../outside.tex'), null);
  assert.equal(resolveInRoot('/tmp/proj', '/etc/passwd'), null);
  assert.equal(resolveInRoot('/tmp/proj', 'sections/01.tex'), '/tmp/proj/sections/01.tex');
});

// ------------------------------- 3. 真引擎端到端（这台机器有 Python 才跑）

/** 这台机器能不能 import factscribe（要能起真引擎）。 */
function pythonCanImport() {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn('python3', ['-c', 'import factscribe.serve'], {
        stdio: 'ignore',
        shell: false,
        env: { ...process.env, PYTHONPATH: [REPO_ROOT, process.env.PYTHONPATH].filter(Boolean).join(':') },
      });
    } catch {
      resolve(false);
      return;
    }
    child.once('error', () => resolve(false));
    child.once('exit', (code) => resolve(code === 0));
  });
}

test('真引擎端到端：CRLF 文件走一遍真 serve，保存后仍是 CRLF', async (t) => {
  const usable = await pythonCanImport();
  if (!usable) {
    t.skip('这台机器没有能 import factscribe 的 python3');
    return;
  }
  const original = '\section{引言}\r\n\r\n中文正文，含全角（）与 emoji 🧪。\r\n值是 12.5 \\fact{X}。\r\n';
  const project = mkdtempSync(join(tmpdir(), 'fs-eol-real-'));
  mkdirSync(join(project, 'sections'), { recursive: true });
  mkdirSync(join(project, 'facts'), { recursive: true });
  writeFileSync(join(project, 'factscribe.toml'),
    '[project]\ntitle = "EOL"\nauthors = ["probe"]\nsections = "sections/*.tex"\nfacts = "facts/*.toml"\nbib = "refs.bib"\n', 'utf8');
  writeFileSync(join(project, 'facts/01-core.toml'),
    '[[fact]]\nid = "A1"\nclaim = "探针数字"\nvalue = "1.0"\nsource = "sections/01.tex"\nlocator = "§一"\nconfidence = "high"\n', 'utf8');
  writeFileSync(join(project, 'refs.bib'), '', 'utf8');
  writeFileSync(join(project, 'sections/01.tex'), Buffer.from(original, 'utf8'));

  try {
    const started = await call('/api/workbench/start', {
      method: 'POST',
      body: JSON.stringify({ path: project, allowWrite: true }),
    });
    assert.equal(started.status, 200, JSON.stringify(started.body));

    const view = await call('/api/workbench/project');
    assert.equal(view.status, 200, JSON.stringify(view.body));
    const section = view.body.sections.find((s) => s.file === 'sections/01.tex');
    assert.ok(section, '引擎要认得出这一节');
    // 读侧口径（迁入 main 正确性基线后）：接口层给的是**原样**正文——
    // CRLF 不在读侧被翻译掉。旧断言「接口层给的是归一过的 LF」锁的是
    // 修正前的行为（读侧翻译 ⇒ 行尾在进浏览器前就丢了），现已反过来：
    // 浏览器拿到的就是磁盘上的字节，保存时按原样写回。
    assert.equal(eolStats(section.text).crlf, 4,
      '接口层给的应是原样正文（CRLF 不在读侧被翻译掉）');
    assert.equal(eolStats(section.text).lf, 0);

    const saved = await call('/api/workbench/sections', {
      method: 'PUT',
      body: JSON.stringify({ file: 'sections/01.tex', text: browserValue(section.text) }),
    });
    assert.equal(saved.status, 200, JSON.stringify(saved.body));

    const onDisk = readFileSync(join(project, 'sections/01.tex'), 'utf8');
    assert.equal(onDisk, original, 'CRLF 文件保存后必须逐字节回到原样');
    assert.equal(eolStats(onDisk).crlf, 4);
    assert.equal(eolStats(onDisk).lf, 0);

    await call('/api/workbench', { method: 'DELETE' });
  } finally {
    await call('/api/workbench', { method: 'DELETE' });
    rmSync(project, { recursive: true, force: true });
  }
});
