// Node 领域服务的路由面：项目登记册、启动校验、停止。
// 不 spawn 真 Python——启动失败路径用「不是论文项目」验证，避免测试依赖本机装了 factscribe。

import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { createServer as createNetServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, test } from 'node:test';

import { start } from '../miniapp/node/server.mjs';

const PLUGIN_ROOT = new URL('..', import.meta.url).pathname;
// 仓库根：包路径指过去，python3 -m factscribe.samples 才 import 得到。
const REPO_ROOT = new URL('../../..', import.meta.url).pathname;

/** 这台机器能不能 import factscribe（装示例要靠它）。 */
function pythonCanImportSamples() {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn('python3', ['-c', 'import factscribe.samples'], {
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

let home;
let dataDir;
let base;
let dispose;
let savedHome;
let savedPythonPath;

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

async function call(path, options = {}) {
  const res = await fetch(base + path, {
    headers: { 'content-type': 'application/json' },
    ...options,
  });
  const text = await res.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = text;
  }
  return { status: res.status, body };
}

before(async () => {
  home = mkdtempSync(join(tmpdir(), 'minifactscribe-routes-'));
  dataDir = join(home, 'data');
  mkdirSync(dataDir, { recursive: true });
  savedHome = process.env.HOME;
  process.env.HOME = home;
  // 装示例靠 `python3 -m factscribe.samples`：把仓库根放进包路径，
  // 这台机器没装 factscribe 也能 import 到源码。
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

test('项目登记册路由：加入、列出、移除', async () => {
  const project = join(home, 'paper-one');
  mkdirSync(project, { recursive: true });
  writeFileSync(join(project, 'paperkit.toml'), '[project]\ntitle = "第一篇"\n', 'utf8');

  let res = await call('/api/projects');
  assert.equal(res.status, 200);
  assert.deepEqual(res.body.projects, []);
  assert.match(res.body.dir, /\.factscribe$/);

  res = await call('/api/projects', { method: 'POST', body: JSON.stringify({ path: project }) });
  assert.equal(res.status, 200);
  assert.equal(res.body.project.name, '第一篇');
  assert.equal(res.body.project.path, realpathSync(project));
  assert.equal(res.body.lastPath, realpathSync(project));

  res = await call('/api/projects');
  assert.equal(res.body.projects.length, 1);
  assert.equal(res.body.projects[0].name, '第一篇');

  res = await call('/api/projects?path=' + encodeURIComponent(realpathSync(project)), { method: 'DELETE' });
  assert.equal(res.status, 200);
  assert.deepEqual(res.body.projects, []);
  assert.equal(res.body.lastPath, '');
});

test('启动前重新校验：不是论文项目就 400，不进 spawn', async () => {
  const bare = join(home, 'plain-folder');
  mkdirSync(bare, { recursive: true });
  const res = await call('/api/workbench/start', {
    method: 'POST',
    body: JSON.stringify({ path: bare }),
  });
  assert.equal(res.status, 400);
  assert.equal(res.body.error.code, 'PROJECT_INVALID');
  assert.match(res.body.error.message, /paperkit\.toml/);

  const missing = await call('/api/workbench/start', {
    method: 'POST',
    body: JSON.stringify({ path: join(home, 'nope') }),
  });
  assert.equal(missing.status, 400);
});

test('解释器/包路径只收命令或绝对路径，不收参数', async () => {
  const bad = await call('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ python: 'python3 -c "print(1)"' }),
  });
  assert.equal(bad.status, 400);
  assert.match(bad.body.error.message, /不能带空格或参数/);

  const badPath = await call('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ pythonpath: '/tmp/x; rm -rf /' }),
  });
  assert.equal(badPath.status, 400);

  const ok = await call('/api/projects', {
    method: 'POST',
    body: JSON.stringify({ python: 'python3', pythonpath: '/tmp/repo' }),
  });
  assert.equal(ok.status, 200);
  assert.equal(ok.body.python, 'python3');
  assert.equal(ok.body.pythonpath, '/tmp/repo');
});

test('工作台状态：未启动时 running=false；停止是幂等的', async () => {
  const state = await call('/api/workbench');
  assert.equal(state.status, 200);
  assert.equal(state.body.running, false);
  assert.equal(state.body.configured, false);

  const stop = await call('/api/workbench/stop', { method: 'POST' });
  assert.equal(stop.status, 200);
  assert.equal(stop.body.running, false);
  assert.equal(stop.body.stopped, false);
});


test('统一界面的静态资源：/app.js 与 /app.css 由 Node 供', async () => {
  const js = await call('/app.js');
  assert.equal(js.status, 200);
  assert.match(js.body, /wb\('\/project'\)/, '应返回统一界面脚本');
  const css = await call('/app.css');
  assert.equal(css.status, 200);
  assert.match(css.body, /\.layout/);
  const page = await call('/minifactscribe');
  assert.equal(page.status, 200);
  assert.match(page.body, /\/app\.js/, '页面引用绝对路径，两种服务器都能供');
});

test('报告代理：列表与动作都转发，上游的 403 原样带回', async () => {
  const upstream = createServer((request, response) => {
    const reply = (code, body) => {
      response.writeHead(code, { 'content-type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    if (request.url === '/api/health') {
      return reply(200, { ok: true, service: 'workbench' });
    }
    if (request.url === '/api/capabilities') {
      return reply(200, { ok: true, engine: 'python' });
    }
    if (request.url === '/api/reports') {
      return reply(200, {
        ok: true,
        workspace: '/tmp/ws',
        reports: [{
          path: 'experiments/e/reports/r.report.toml', id: 'r',
          experiment: 'e', status: 'final', metrics: 1, locked: true,
          signed: false, reason: '', lock_ok: true, card: [],
        }],
      });
    }
    if (request.url === '/api/reports/action' && request.method === 'POST') {
      let body = '';
      request.on('data', (chunk) => { body += chunk; });
      request.on('end', () => {
        const parsed = JSON.parse(body || '{}');
        if (parsed.action === 'lock') {
          return reply(403, {
            ok: false,
            error: { code: 'READ_ONLY', message: 'serve 当前是只读模式' },
          });
        }
        return reply(200, { ok: true, action: parsed.action, result: { by: parsed.by } });
      });
      return;
    }
    return reply(404, { ok: false, error: { code: 'NOT_FOUND', message: 'no' } });
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  const upstreamUrl = 'http://127.0.0.1:' + upstream.address().port;
  try {
    const connect = await call('/api/workbench', {
      method: 'PUT',
      body: JSON.stringify({ url: upstreamUrl, token: 'upstream-token' }),
    });
    assert.equal(connect.status, 200, JSON.stringify(connect.body));

    const list = await call('/api/workbench/reports');
    assert.equal(list.status, 200);
    assert.equal(list.body.reports.length, 1);
    assert.equal(list.body.reports[0].id, 'r');

    const signed = await call('/api/workbench/reports', {
      method: 'POST',
      body: JSON.stringify({ action: 'sign', report: 'x', by: '张三' }),
    });
    assert.equal(signed.status, 200);
    assert.equal(signed.body.result.by, '张三');

    const denied = await call('/api/workbench/reports', {
      method: 'POST',
      body: JSON.stringify({ action: 'lock', report: 'x' }),
    });
    assert.equal(denied.status, 403, '上游的 403 要原样带回，不能变成 502');
    assert.equal(denied.body.error.code, 'READ_ONLY');
  } finally {
    await new Promise((resolve) => upstream.close(resolve));
  }
});

test('章节增删改代理：create / rename / delete 三条都转发，409 原样带回', async () => {
  const seen = [];
  const upstream = createServer((request, response) => {
    const reply = (code, body) => {
      response.writeHead(code, { 'content-type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    if (request.url === '/api/health') {
      return reply(200, { ok: true, service: 'workbench' });
    }
    if (request.url === '/api/capabilities') {
      return reply(200, { ok: true, engine: 'python' });
    }
    if (request.url.startsWith('/api/sections/')) {
      let body = '';
      request.on('data', (chunk) => { body += chunk; });
      request.on('end', () => {
        const parsed = JSON.parse(body || '{}');
        seen.push({ path: request.url, body: parsed });
        if (request.url === '/api/sections/delete') {
          return reply(409, {
            ok: false,
            error: {
              code: 'SECTION_REFERENCED',
              message: '正文还在引用它',
              references: [{ file: 'main.tex', line: 7 }],
            },
          });
        }
        return reply(200, { ok: true, file: parsed.file || parsed.to || '' });
      });
      return;
    }
    return reply(404, { ok: false, error: { code: 'NOT_FOUND', message: 'no' } });
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  const upstreamUrl = 'http://127.0.0.1:' + upstream.address().port;
  try {
    const connect = await call('/api/workbench', {
      method: 'PUT',
      body: JSON.stringify({ url: upstreamUrl, token: 'upstream-token' }),
    });
    assert.equal(connect.status, 200, JSON.stringify(connect.body));

    const created = await call('/api/workbench/sections/create', {
      method: 'POST',
      body: JSON.stringify({ file: 'sections/99-new.tex' }),
    });
    assert.equal(created.status, 200);
    assert.equal(created.body.file, 'sections/99-new.tex');

    const renamed = await call('/api/workbench/sections/rename', {
      method: 'POST',
      body: JSON.stringify({ from: 'sections/99-new.tex', to: 'sections/99-b.tex' }),
    });
    assert.equal(renamed.status, 200);
    assert.equal(renamed.body.file, 'sections/99-b.tex');

    const deleted = await call('/api/workbench/sections/delete', {
      method: 'POST',
      body: JSON.stringify({ file: 'sections/99-b.tex' }),
    });
    assert.equal(deleted.status, 409, '上游的 409（还被引用）要原样带回');
    assert.equal(deleted.body.error.code, 'SECTION_REFERENCED');
    assert.equal(deleted.body.error.references[0].file, 'main.tex');

    assert.deepEqual(seen.map((s) => s.path), [
      '/api/sections/create',
      '/api/sections/rename',
      '/api/sections/delete',
    ], '三条代理路径都要打到上游');
    assert.equal(seen[1].body.from, 'sections/99-new.tex');
    assert.equal(seen[1].body.to, 'sections/99-b.tex');
  } finally {
    await new Promise((resolve) => upstream.close(resolve));
  }
});

test('示例论文代理：转发到工作台的 /api/samples/guide，上游的 400 原样带回', async () => {
  const seen = [];
  const upstream = createServer((request, response) => {
    const reply = (code, body) => {
      response.writeHead(code, { 'content-type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    if (request.url === '/api/health') {
      return reply(200, { ok: true, service: 'workbench' });
    }
    if (request.url === '/api/capabilities') {
      return reply(200, { ok: true, engine: 'python' });
    }
    if (request.url === '/api/samples/guide' && request.method === 'POST') {
      let body = '';
      request.on('data', (chunk) => { body += chunk; });
      request.on('end', () => {
        const parsed = JSON.parse(body || '{}');
        seen.push(parsed);
        if (parsed.reset) {
          return reply(400, {
            ok: false,
            error: { code: 'SAMPLE_COPY_FAILED', message: '复制示例失败' },
          });
        }
        return reply(200, { ok: true, path: '/tmp/guide', created: true, reset: false });
      });
      return;
    }
    return reply(404, { ok: false, error: { code: 'NOT_FOUND', message: 'no' } });
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  const upstreamUrl = 'http://127.0.0.1:' + upstream.address().port;
  try {
    const connect = await call('/api/workbench', {
      method: 'PUT',
      body: JSON.stringify({ url: upstreamUrl, token: 'upstream-token' }),
    });
    assert.equal(connect.status, 200, JSON.stringify(connect.body));

    const res = await call('/api/workbench/samples/guide', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    assert.equal(res.status, 200, JSON.stringify(res.body));
    assert.equal(res.body.path, '/tmp/guide');
    assert.deepEqual(seen, [{ reset: false }], '要 POST 到上游的 /api/samples/guide');

    const bad = await call('/api/workbench/samples/guide', {
      method: 'POST',
      body: JSON.stringify({ reset: true }),
    });
    assert.equal(bad.status, 400, '上游的 400 要原样带回');
    assert.equal(bad.body.error.code, 'SAMPLE_COPY_FAILED');
    assert.deepEqual(seen[1], { reset: true }, 'reset 要传给上游');
  } finally {
    await call('/api/workbench', { method: 'DELETE' });
    await new Promise((resolve) => upstream.close(resolve));
  }
});

test('示例论文：还没连工作台时也让 Python 装一份（兜底）', async (t) => {
  const usable = await pythonCanImportSamples();
  if (!usable) {
    t.skip('这台机器没有能 import factscribe 的 python3');
    return;
  }
  await call('/api/workbench', { method: 'DELETE' });  // 确保没有工作台在连
  const res = await call('/api/workbench/samples/guide', {
    method: 'POST',
    body: JSON.stringify({}),
  });
  assert.equal(res.status, 200, JSON.stringify(res.body));
  assert.equal(res.body.ok, true);
  assert.match(res.body.path, /[/\\]samples[/\\]guide$/);
  assert.equal(res.body.created, true);
  assert.ok(existsSync(join(res.body.path, 'paperkit.toml')), '示例要真的落地');
  assert.ok(existsSync(join(res.body.path, 'sections')), '示例要带着章节');

  const again = await call('/api/workbench/samples/guide', {
    method: 'POST',
    body: JSON.stringify({}),
  });
  assert.equal(again.status, 200);
  assert.equal(again.body.created, false, '已存在且没要求重置 → 不重写');
});


test('节页码代理：file 查询串原样送到 Python', async () => {
  const seen = [];
  const upstream = createServer((request, response) => {
    const reply = (code, body) => {
      response.writeHead(code, { 'content-type': 'application/json' });
      response.end(JSON.stringify(body));
    };
    if (request.url === '/api/health') return reply(200, { ok: true, service: 'workbench' });
    if (request.url === '/api/capabilities') return reply(200, { ok: true, engine: 'python' });
    if (request.url.startsWith('/api/section-page')) {
      seen.push(request.url);
      return reply(200, { ok: true, page: 3, pages: 9, found: true, title: 'Intro', file: 'sections/01.tex' });
    }
    return reply(404, { ok: false, error: { code: 'NOT_FOUND', message: 'no' } });
  });
  await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
  const upstreamUrl = 'http://127.0.0.1:' + upstream.address().port;
  try {
    const connect = await call('/api/workbench', {
      method: 'PUT',
      body: JSON.stringify({ url: upstreamUrl, token: 'upstream-token' }),
    });
    assert.equal(connect.status, 200, JSON.stringify(connect.body));
    const res = await call('/api/workbench/section-page?file=' + encodeURIComponent('sections/01.tex'));
    assert.equal(res.status, 200);
    assert.equal(res.body.page, 3);
    assert.equal(seen.length, 1);
    assert.match(seen[0], /file=sections%2F01\.tex/);
  } finally {
    await new Promise((resolve) => upstream.close(resolve));
  }
});
