// 本地工作台连接层：地址校验、带 token 的代理、能力探测。
// 不启动 MiniFactScribe 服务，只测服务器侧的纯函数与 fetch 行为。

import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { after, before, test } from 'node:test';

import {
  normalizeWorkbenchUrl,
  probeWorkbench,
  workbenchFetch,
} from '../miniapp/node/server.mjs';

const TOKEN = 'test-token';
let server;
let base;

before(async () => {
  server = createServer((request, response) => {
    const auth = request.headers.authorization;
    if (auth !== `Bearer ${TOKEN}`) {
      response.writeHead(401, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: false, error: { code: 'UNAUTHORIZED', message: 'bad token' } }));
      return;
    }
    if (request.url === '/api/health') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: true, service: 'workbench', version: '1.3.0' }));
      return;
    }
    if (request.url === '/api/capabilities') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: true, engine: 'python', files: true }));
      return;
    }
    if (request.url === '/api/status') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: true, project: 'demo', facts: 2, sections: 1 }));
      return;
    }
    if (request.url === '/api/audit' && request.method === 'POST') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: true, exit: 1, findings: [{ severity: 'red', code: 'UNMATCHED_NUMBER' }] }));
      return;
    }
    response.writeHead(404, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ ok: false, error: { code: 'NOT_FOUND', message: 'no' } }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});

after(() => new Promise((resolve) => server.close(resolve)));

test('工作台地址只接受本机 http origin', () => {
  assert.equal(normalizeWorkbenchUrl('http://127.0.0.1:61483/'),
    'http://127.0.0.1:61483');
  assert.equal(normalizeWorkbenchUrl('http://localhost:61483'),
    'http://localhost:61483');
  for (const bad of [
    'https://127.0.0.1:61483',
    'http://example.com:61483',
    'http://127.0.0.1:61483/path',
    'http://user:pass@127.0.0.1:61483',
    'http://127.0.0.1:61483?x=1',
  ]) {
    assert.throws(() => normalizeWorkbenchUrl(bad), undefined, bad);
  }
});

test('probeWorkbench 带 token 读出 Python 引擎能力', async () => {
  const caps = await probeWorkbench(base, TOKEN);
  assert.equal(caps.engine, 'python');
  assert.equal(caps.files, true);
});

test('token 不对时拒绝，且错误有可读消息', async () => {
  await assert.rejects(
    () => probeWorkbench(base, 'wrong'),
    /bad token/,
  );
});

test('代理 status / audit 使用 POST 并原样返回结构化结果', async () => {
  const status = await workbenchFetch(base, TOKEN, '/api/status');
  assert.equal(status.project, 'demo');
  assert.equal(status.facts, 2);
  const audit = await workbenchFetch(base, TOKEN, '/api/audit', 'POST');
  assert.equal(audit.exit, 1);
  assert.equal(audit.findings[0].code, 'UNMATCHED_NUMBER');
});
