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
import { mkdtempSync, cpSync, writeFileSync, readdirSync, statSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PLUGIN_ROOT = process.env.FS_PLUGIN_ROOT;
const PAPER_SRC = process.env.FS_PAPER_SRC;
const RESULT_PATH = process.env.FS_RESULT_PATH;

const dataDir = mkdtempSync(join(tmpdir(), 'fs-mcp-datadir-'));
const paperRoot = mkdtempSync(join(tmpdir(), 'fs-mcp-root-'));
cpSync(PAPER_SRC, paperRoot, { recursive: true });

const out = { ok: false, tools: [], calls: {}, errors: [] };

/** 论文目录的文件清单（相对路径 + 大小 + mtime）：用来证明「提议单没碰盘」。 */
function listFiles(dir, prefix = '') {
  const rows = [];
  for (const name of readdirSync(dir).sort()) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      rows.push(...listFiles(full, prefix + name + '/'));
    } else {
      rows.push(prefix + name + ':' + st.size + ':' + st.mtimeMs);
    }
  }
  return rows;
}

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

  // 7) 本批新增：证据锁读数、写作简报、版式、账与证据面的提议单
  const beforeFiles = listFiles(paperRoot);
  out.calls.fs_get_evidence_status =
    (await callTool(8, 'fs_get_evidence_status', out.target)).payload;
  out.calls.fs_get_brief = (await callTool(9, 'fs_get_brief', out.target)).payload;
  out.calls.fs_get_venue =
    (await callTool(10, 'fs_get_venue', { project: out.target.project })).payload;
  out.calls.fs_propose_evidence_freeze =
    (await callTool(11, 'fs_propose_evidence_freeze', { ...out.target, reason: '驱动测试留底' })).payload;
  out.calls.fs_propose_add_fact =
    (await callTool(12, 'fs_propose_add_fact', {
      ...out.target, id: 'Z9', claim: '驱动测试主张', value: '56.25%',
      source: 'results/swb16.md', confidence: 'high',
    })).payload;
  out.calls.fs_list_proposals = (await callTool(13, 'fs_list_proposals', out.target)).payload;
  // 追加事实的提议单：来源得是 mcp（卡片上显示「来自助手」），
  // 事实自己的 source 留在 fact 子对象里（原值不动）。
  const factId = (out.calls.fs_propose_add_fact || {}).id || '';
  try {
    out.calls.add_fact_record = JSON.parse(
      readFileSync(join(dataDir, 'proposals', factId + '.json'), 'utf8'));
  } catch (e) {
    out.errors.push('读追加事实的提议单失败：' + String(e));
  }
  // 提议单只落状态目录：论文目录一个字节都不许动。
  out.paperUnchanged = JSON.stringify(beforeFiles) === JSON.stringify(listFiles(paperRoot));

  out.ok = true;
} catch (error) {
  out.errors.push(String((error && error.stack) || error));
} finally {
  if (handle) { try { await handle.dispose(); } catch { /* 忽略 */ } }
  ac.abort();
  writeFileSync(RESULT_PATH, JSON.stringify(out, null, 2));
}

process.exit(out.ok ? 0 : 1);
