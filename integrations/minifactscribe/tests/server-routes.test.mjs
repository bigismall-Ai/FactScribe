// Node 领域服务的路由面：项目登记册、启动校验、停止。
// 不 spawn 真 Python——启动失败路径用「不是论文项目」验证，避免测试依赖本机装了 factscribe。

import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { createServer as createNetServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { after, before, test } from 'node:test';

import { start } from '../miniapp/node/server.mjs';

const PLUGIN_ROOT = new URL('..', import.meta.url).pathname;

let home;
let dataDir;
let base;
let dispose;
let savedHome;

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
