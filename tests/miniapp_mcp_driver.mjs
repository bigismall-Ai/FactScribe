// 仓内 MCP 面考题的驱动脚本（tests/test_miniapp_mcp_tools.py 调用它）。
//
// 真起 Node 薄壳（miniapp/node/server.mjs），走 **MCP 协议**驱动宿主那条路：
//   initialize → tools/list → tools/call（fs_status / fs_get_report(lang=en) /
//   fs_get_style / fs_mirror_check）。
//
// 目的：证明这两条新工具**宿主能直接调用**并拿回结构化读数，且报告的英文
// 读数里没有中文残留。
//
// 结果写成 JSON 文件（FS_RESULT_PATH），进程退出码 0＝全程没抛异常。
import { pathToFileURL } from 'node:url';
import { createServer as createNetServer } from 'node:http';
import { mkdtempSync, cpSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PLUGIN_ROOT = process.env.FS_PLUGIN_ROOT;
const PAPER_SRC = process.env.FS_PAPER_SRC;
const RESULT_PATH = process.env.FS_RESULT_PATH;

const dataDir = mkdtempSync(join(tmpdir(), 'fs-mcp-datadir-'));
const paperRoot = mkdtempSync(join(tmpdir(), 'fs-mcp-root-'));
cpSync(PAPER_SRC, paperRoot, { recursive: true });

const out = { ok: false, tools: [], calls: {}, errors: [] };

const port = await new Promise((resolve, reject) => {
  const s = createNetServer();
  s.on('error', reject);
  s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
});

const logger = {
  info: (m) => {},
  warn: (m) => {},
  error: (m) => out.errors.push(String(m).slice(0, 200)),
  debug: (m) => {},
};

const agentStub = {
  async models() { return { models: [], default: null }; },
  async run() { return { sessionId: 's', status: 'finished', text: '' }; },
  async reply() {},
  async answer() {},
};

const ac = new AbortController();
const mod = await import(pathToFileURL(join(PLUGIN_ROOT, 'miniapp', 'node', 'server.mjs')).href);

let handle = null;
try {
  handle = await mod.start({
    pluginId: 'factscribe', pluginRoot: PLUGIN_ROOT, dataDir,
    listen: { host: '127.0.0.1', port }, signal: ac.signal, logger, agent: agentStub,
  });
  const base = 'http://127.0.0.1:' + port;

  const postJson = async (path, body) => {
    const res = await fetch(base + path, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON */ }
    return { status: res.status, json, text };
  };

  // 1) 论文根
  const setup = await postJson('/api/miniapp/setup', { root: paperRoot });
  out.setupStatus = setup.status;

  // 2) MCP：initialize
  const init = await postJson('/mcp/factscribe', {
    jsonrpc: '2.0', id: 1, method: 'initialize',
    params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'driver', version: '1' } },
  });
  out.initialize = init.json;

  // 3) MCP：tools/list
  const list = await postJson('/mcp/factscribe', {
    jsonrpc: '2.0', id: 2, method: 'tools/list', params: {},
  });
  const tools = (list.json && list.json.result && list.json.result.tools) || [];
  out.tools = tools.map((t) => ({
    name: t.name,
    title: t.title,
    readOnly: Boolean(t.annotations && t.annotations.readOnlyHint),
    required: (t.inputSchema && t.inputSchema.required) || [],
    properties: Object.keys((t.inputSchema && t.inputSchema.properties) || {}),
  }));

  // 4) MCP：tools/call —— 取项目/盘 id
  const callTool = async (id, name, args) => {
    const res = await postJson('/mcp/factscribe', {
      jsonrpc: '2.0', id, method: 'tools/call', params: { name, arguments: args || {} },
    });
    const result = res.json && res.json.result;
    const text = result && result.content && result.content[0] && result.content[0].text;
    let payload = null;
    try { payload = JSON.parse(text); } catch { payload = { raw: text }; }
    return { isError: Boolean(result && result.isError), payload };
  };

  const status = await callTool(3, 'fs_status', {});
  out.calls.fs_status = status.payload;
  const projects = (status.payload && status.payload.projects) || [];
  const first = projects[0] || {};
  const disk = (first.disks || [])[0] || {};
  out.target = { project: first.id || '', disk: disk.id || '' };

  // 5) 报告：中文与英文各一次
  out.calls.report_zh = (await callTool(4, 'fs_get_report', out.target)).payload;
  out.calls.report_en = (await callTool(5, 'fs_get_report', { ...out.target, lang: 'en' })).payload;

  // 6) 两条新工具
  out.calls.fs_get_style = (await callTool(6, 'fs_get_style', out.target)).payload;
  out.calls.fs_mirror_check = (await callTool(7, 'fs_mirror_check', out.target)).payload;

  out.ok = true;
} catch (error) {
  out.errors.push(String((error && error.stack) || error));
} finally {
  if (handle) { try { await handle.dispose(); } catch { /* 忽略 */ } }
  ac.abort();
  writeFileSync(RESULT_PATH, JSON.stringify(out, null, 2));
}

process.exit(out.ok ? 0 : 1);
