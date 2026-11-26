// 代理写盘的状态码透传：上游的判定码不许被代理吞掉。
//
// 缺陷：PUT /api/workbench/sections 走的是 workbenchFetch，而 workbenchFetch
// 遇非 2xx 就抛异常；异常一路落到路由的 catch，统统变成 502 WORKBENCH_UPSTREAM。
// 于是「这一节在别处被改过」（409 BLOCK_STALE）与「本地工作台连不上」（502）
// 在调用方眼里长得一模一样——写盘失败被说成了连不上，状态码这一层信息全丢了。
//
// 这里钉死三条路径（外加一条同机制的 403）：
//   上游 409 → 代理回 409（错误体照上游原样带回）
//   上游 400 → 代理回 400
//   上游 200 → 代理回 200，且仍带行尾回填后的 bytes 与 eol 字段
//
// 引擎侧一个字节都不动：这里只验代理层「原样转发」这一件事。

import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createServer as createNetServer } from 'node:net';
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, test } from 'node:test';

import { start } from '../miniapp/node/server.mjs';

const PLUGIN_ROOT = new URL('..', import.meta.url).pathname;
const TOKEN = 'stub-token';

// 原稿：CRLF 行尾（浏览器那一层给过来的是 LF，行尾由代理按原文件风格摆回去）。
const ORIGINAL = '第一行\r\n第二行\r\n';
// 编辑后的正文：浏览器归一过的 LF。
const EDITED_LF = '改过的第一行\n改过的第二行\n';
// 代理行尾回填之后应该落盘的形态。
const EDITED_CRLF = '改过的第一行\r\n改过的第二行\r\n';

// 上游这一次要回什么：每个用例改一次。
let upstreamStatus = 200;
let upstreamBody = { ok: true, saved: true };

let home;
let dataDir;
let projectRoot;
let sectionFile;
let upstream;
let dispose;
let base;

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

/** 把原稿放回去：各用例互不依赖，谁先谁后都一样。 */
function resetSection() {
  writeFileSync(sectionFile, ORIGINAL, 'utf8');
}

/** 走完整代理路径保存一节，回 {status, body}。 */
async function save(text) {
  const res = await fetch(base + '/api/workbench/sections', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ file: 'sections/01.tex', text }),
  });
  const raw = await res.text();
  let body;
  try {
    body = JSON.parse(raw);
  } catch {
    body = raw;
  }
  return { status: res.status, body };
}

before(async () => {
  home = mkdtempSync(join(tmpdir(), 'minifactscribe-sections-status-'));
  dataDir = join(home, 'data');
  mkdirSync(dataDir, { recursive: true });
  projectRoot = join(home, 'paper');
  mkdirSync(join(projectRoot, 'sections'), { recursive: true });
  sectionFile = join(projectRoot, 'sections', '01.tex');
  resetSection();

  // 假上游：照引擎的形状回码——失败是非 2xx ＋ ok:false，成功是 200 ＋ ok:true。
  upstream = createServer(async (request, response) => {
    if (request.url === '/api/status') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: true, root: projectRoot, project: 'paper' }));
      return;
    }
    if (request.url === '/api/sections' && request.method === 'PUT') {
      let raw = '';
      for await (const chunk of request) raw += chunk;
      const body = JSON.parse(raw);
      if (upstreamStatus === 200) {
        // 真引擎会把收到的正文写进文件；这里照做，行尾回填才有得验。
        writeFileSync(join(projectRoot, body.file), body.text, 'utf8');
      }
      response.writeHead(upstreamStatus, { 'content-type': 'application/json' });
      response.end(JSON.stringify(upstreamBody));
      return;
    }
    response.writeHead(404, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ ok: false, error: { code: 'NOT_FOUND', message: 'no' } }));
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));

  writeFileSync(join(dataDir, 'workbench.json'), JSON.stringify({
    url: 'http://127.0.0.1:' + upstream.address().port,
    token: TOKEN,
  }), 'utf8');

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
  if (upstream) await new Promise((resolve) => upstream.close(resolve));
  rmSync(home, { recursive: true, force: true });
});

test('上游 409（指纹闸拒写）：代理原样回 409，错误体照上游带回', async () => {
  resetSection();
  upstreamStatus = 409;
  upstreamBody = {
    ok: false,
    error: { code: 'BLOCK_STALE', message: '这段在别处已被改动，请重新编辑。' },
  };

  const res = await save(EDITED_LF);

  assert.equal(res.status, 409, '上游 409 必须原样回传，不能被压成 200/502');
  assert.equal(res.body.ok, false);
  assert.equal(res.body.error.code, 'BLOCK_STALE');
  assert.equal(res.body.error.message, '这段在别处已被改动，请重新编辑。');
  // 失败路径不许带成功路径的字段（eol/bytes 是「真写下去了」才有的）。
  assert.equal(res.body.eol, undefined);
  assert.equal(res.body.bytes, undefined);
  // 拒写时磁盘上的正文一个字都不许动。
  assert.equal(readFileSync(sectionFile, 'utf8'), ORIGINAL);
});

test('上游 400（参数不对）：代理原样回 400', async () => {
  resetSection();
  upstreamStatus = 400;
  upstreamBody = {
    ok: false,
    error: { code: 'REPORT_INVALID', message: '正文不能为空' },
  };

  const res = await save(EDITED_LF);

  assert.equal(res.status, 400, '上游 400 必须原样回传，不能被压成 200/502');
  assert.equal(res.body.ok, false);
  assert.equal(res.body.error.code, 'REPORT_INVALID');
  assert.equal(res.body.error.message, '正文不能为空');
  assert.equal(res.body.eol, undefined);
  assert.equal(readFileSync(sectionFile, 'utf8'), ORIGINAL);
});

test('上游 403（同源闸）：代理原样回 403', async () => {
  resetSection();
  upstreamStatus = 403;
  upstreamBody = {
    ok: false,
    error: { code: 'CROSS_ORIGIN', message: '跨源请求不接：只允许本监听地址（同源）' },
  };

  const res = await save(EDITED_LF);

  assert.equal(res.status, 403, '上游 403 必须原样回传，不能被压成 200/502');
  assert.equal(res.body.ok, false);
  assert.equal(res.body.error.code, 'CROSS_ORIGIN');
  assert.equal(readFileSync(sectionFile, 'utf8'), ORIGINAL);
});

test('上游 200：仍是 200，且仍带行尾回填后的 bytes 与 eol', async () => {
  resetSection();
  upstreamStatus = 200;
  upstreamBody = { ok: true, saved: true };

  const res = await save(EDITED_LF);

  assert.equal(res.status, 200);
  assert.equal(res.body.ok, true);
  assert.equal(res.body.saved, true);
  // 行尾回填后落盘的形态：原文件是 CRLF，回填后仍是 CRLF。
  assert.equal(res.body.eol.style, 'crlf');
  assert.equal(res.body.eol.repaired, true);
  assert.equal(res.body.bytes, Buffer.byteLength(EDITED_CRLF, 'utf8'));
  assert.equal(res.body.eol.bytes, Buffer.byteLength(EDITED_CRLF, 'utf8'));
  // 内容逐字保留，行尾按原风格回填。
  assert.equal(readFileSync(sectionFile, 'utf8'), EDITED_CRLF);
});
