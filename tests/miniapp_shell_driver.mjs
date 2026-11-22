// 仓内运行时考题的驱动脚本（tests/test_miniapp_shell_models.py 调用它）。
//
// 真起 Node 薄壳 + 两个桩：
//   * 宿主 Agent 桩（带模型目录：两个模型，各自的思考等级档位）；
//   * OpenAI 兼容桩后端（记录收到的请求，回一句固定答案）。
//
// 结果写成 JSON 文件（FS_RESULT_PATH），进程退出码 0＝全程没抛异常。
import { pathToFileURL } from 'node:url';
import { createServer } from 'node:http';
import { createServer as createNetServer } from 'node:net';
import { mkdtempSync, cpSync, existsSync, statSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const PLUGIN_ROOT = process.env.FS_PLUGIN_ROOT;
const PAPER_SRC = process.env.FS_PAPER_SRC;
const RESULT_PATH = process.env.FS_RESULT_PATH;

const dataDir = mkdtempSync(join(tmpdir(), 'fs-shm-datadir-'));
const paperRoot = mkdtempSync(join(tmpdir(), 'fs-shm-root-'));
cpSync(PAPER_SRC, paperRoot, { recursive: true });

const out = { ok: false, steps: [], logs: [] };
const note = (name, value) => { out.steps.push({ name, value }); };

// —— 桩 1：OpenAI 兼容后端 ——
const openaiHits = [];
const openai = createServer((req, res) => {
  let body = '';
  req.on('data', (chunk) => { body += chunk; });
  req.on('end', () => {
    openaiHits.push({ url: req.url, method: req.method, headers: req.headers, body });
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ choices: [{ message: { content: '自定义模型答：材料已收到。' } }] }));
  });
});
await new Promise((resolve) => openai.listen(0, '127.0.0.1', resolve));
const openaiPort = openai.address().port;

// —— 桩 2：宿主 Agent（带模型目录） ——
const agentCalls = [];
const catalog = {
  models: [
    {
      providerId: 'minimax', modelId: 'MiniMax-M3', displayName: 'MiniMax-M3',
      thinking: { efforts: ['low', 'medium', 'high'], default: 'medium' },
      variants: ['thinking', ''],
    },
    {
      providerId: 'minimax', modelId: 'MiniMax-M3.1-Flash', displayName: 'MiniMax-M3.1-Flash',
      thinking: { efforts: ['low', 'high'] },
      variants: ['thinking'],
    },
  ],
  default: { providerId: 'minimax', modelId: 'MiniMax-M3.1-Flash' },
};
const agentStub = {
  async models() { return catalog; },
  async run(input) {
    agentCalls.push({
      text: String(input.text || '').slice(0, 80),
      model: input.model,
      sessionId: input.sessionId || '',
    });
    return { sessionId: 'sess-shell-test', status: 'finished', text: '宿主模型答：材料已收到。' };
  },
  async reply() {},
  async answer() {},
};

const port = await new Promise((resolve, reject) => {
  const s = createNetServer();
  s.on('error', reject);
  s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
});

const logger = {
  info: (m) => out.logs.push('INFO ' + String(m)),
  warn: (m) => out.logs.push('WARN ' + String(m)),
  error: (m) => out.logs.push('ERROR ' + String(m)),
  debug: (m) => out.logs.push('DEBUG ' + String(m)),
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
  const req = async (path, opts) => {
    const res = await fetch(base + path, Object.assign({ redirect: 'manual' }, opts || {}));
    const text = await res.text();
    let json = null;
    try { json = JSON.parse(text); } catch { /* 非 JSON 按空处理 */ }
    return { status: res.status, text, json };
  };
  const postJson = (path, body) => req(path, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body),
  });

  // 1) 论文根
  const setup = await postJson('/api/miniapp/setup', { root: paperRoot });
  note('setup', setup.status);

  // 2) 项目与盘
  const projects = await req('/api/projects');
  const list = (projects.json && projects.json.projects) || [];
  const project = list[0];
  const disk = project && project.disks && project.disks[0];
  note('project', { id: project && project.id, disk: disk && disk.id, count: list.length });
  const chatBody = (selection) => ({
    project: project.id,
    disk: disk.id,
    messages: [{ role: 'user', content: '总结一下这篇稿子' }],
    modelSelection: selection,
  });

  // 3) 模型清单
  const models = await req('/api/ai/models?project=' + encodeURIComponent(project.id)
    + '&disk=' + encodeURIComponent(disk.id));
  note('models', models.json);

  // 4) 自定义模型
  const created = await postJson('/api/ai/custom-models', {
    label: '我的本地模型',
    baseUrl: 'http://127.0.0.1:' + openaiPort + '/v1',
    model: 'qwen-32b',
    apiKey: 'secret-key-123',
  });
  note('customCreated', created.json);
  const listed = await req('/api/ai/custom-models');
  note('customListed', listed.json);
  note('customLeak', listed.text.indexOf('secret-key-123') >= 0);
  const customId = created.json && created.json.models && created.json.models[0]
    ? created.json.models[0].id : '';

  // 5) 宿主模型＋思考等级
  const chatHost = await postJson('/api/chat', chatBody({ id: 'host:minimax/MiniMax-M3', effort: 'high' }));
  note('chatHost', { status: chatHost.status, json: chatHost.json });

  // 6) 宿主默认（不带 model）
  const chatDefault = await postJson('/api/chat', chatBody({ id: 'host:default', effort: '' }));
  note('chatDefault', { status: chatDefault.status, json: chatDefault.json });

  // 7) 自定义模型
  const chatCustom = await postJson('/api/chat', chatBody({ id: 'custom:' + customId, effort: '' }));
  note('chatCustom', { status: chatCustom.status, json: chatCustom.json });

  // 8) 宿主不认的模型
  const chatBad = await postJson('/api/chat', chatBody({ id: 'host:minimax/Nope', effort: '' }));
  note('chatBadModel', { status: chatBad.status, json: chatBad.json });

  // 9) 选了引擎本地后端的模型 → 不该走宿主 Agent（老宿主没有目录时的路径）
  const chatEngine = await postJson('/api/chat', chatBody({ id: 'engine:qwen-7b', effort: '' }));
  note('chatEngine', { status: chatEngine.status, json: chatEngine.json });

  // 10) 落盘位置与权限
  const store = join(dataDir, 'custom-models.json');
  note('store', {
    exists: existsSync(store),
    mode: existsSync(store) ? (statSync(store).mode & 0o777).toString(8) : '',
    inPaperRoot: existsSync(join(paperRoot, 'custom-models.json')),
  });

  out.agentCalls = agentCalls;
  out.openaiHits = openaiHits.map((hit) => {
    let parsed = null;
    try { parsed = JSON.parse(hit.body); } catch { /* 非 JSON 按空处理 */ }
    const content = parsed && parsed.messages && parsed.messages[0]
      ? String(parsed.messages[0].content || '') : '';
    return {
      url: hit.url,
      method: hit.method,
      auth: hit.headers.authorization || '',
      model: parsed ? parsed.model : '',
      contentLen: content.length,
      contentHasMaterial: content.indexOf('材料') >= 0,
      stream: parsed ? parsed.stream : null,
    };
  });
  out.ok = true;
} catch (error) {
  out.error = String((error && error.stack) || error);
} finally {
  try { if (handle && handle.dispose) await handle.dispose(); } catch { /* ignore */ }
  try { openai.close(); } catch { /* ignore */ }
}
writeFileSync(RESULT_PATH, JSON.stringify(out));
process.exit(out.ok ? 0 : 1);
