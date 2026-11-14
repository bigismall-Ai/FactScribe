// 事实闸 · Node 服务
// 一个 Node 领域服务：所有写操作走这里，提交后再广播。
// 持久化落在 context.dataDir；浏览器只管呈现。

import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize } from 'node:path';
import { auditProject, mergeVerifyIssues, parseBib, protectDiff, stableIdOf } from './audit.mjs';
import { buildDemoProject } from './demo.mjs';
import { pythonFrom, serveArgs, startServe, stopServe } from './launcher.mjs';
import {
  factscribeDir, readRegistry, removeProject, resolveProjectDir, upsertProject,
  writeRegistry,
} from './projects.mjs';


const CLIENT_DIR = 'miniapp/client';
const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
};

function sha256(text) {
  return createHash('sha256').update(String(text ?? ''), 'utf8').digest('hex');
}

// ---------------------------------------------------------------- 本地工作台
// 只连本机 `factscribe serve`。地址必须回环，不把 token 暴露给页面。

export function normalizeWorkbenchUrl(raw) {
  const text = String(raw ?? '').trim();
  let url;
  try {
    url = new URL(text);
  } catch {
    throw new Error('工作台地址不是合法 URL');
  }
  if (url.protocol !== 'http:') throw new Error('工作台只支持 http://（本机回环）');
  if (!['127.0.0.1', 'localhost'].includes(url.hostname)) {
    throw new Error('工作台只允许 127.0.0.1 / localhost');
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error('工作台地址不能带账号、查询串或锚点');
  }
  if (url.pathname !== '/' && url.pathname !== '') {
    throw new Error('工作台地址只填 origin，不带路径');
  }
  return url.origin;
}

export async function workbenchFetch(base, token, path, method = 'GET', body = null) {
  const headers = { authorization: `Bearer ${token}` };
  if (body !== null) headers['content-type'] = 'application/json';
  const response = await fetch(base + path, {
    method,
    headers,
    ...(body !== null ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(10000),
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('工作台返回的不是 JSON');
  }
  if (!response.ok || data?.ok === false) {
    const reason = data?.error?.message || data?.error || `HTTP ${response.status}`;
    throw new Error(String(reason));
  }
  return data;
}

export async function probeWorkbench(base, token) {
  const health = await workbenchFetch(base, token, '/api/health');
  if (!health?.ok) throw new Error('工作台 health 未通过');
  const caps = await workbenchFetch(base, token, '/api/capabilities');
  if (caps?.engine !== 'python') throw new Error('工作台不是 Python 引擎');
  return caps;
}

export async function start(context) {
  const dataDir = context.dataDir;
  const projectFile = join(dataDir, 'project.json');
  const verifyFile = join(dataDir, 'verify.json');
  const workbenchFile = join(dataDir, 'workbench.json');
  await mkdir(dataDir, { recursive: true });

  let workbench = null;
  try {
    const saved = JSON.parse(await readFile(workbenchFile, 'utf8'));
    const url = normalizeWorkbenchUrl(saved?.url);
    const token = String(saved?.token ?? '').trim();
    // 一键启动的工作台跟着本进程活；宿主重启后旧地址已经死了，不要伪装成还连着
    if (token && !saved?.managed) workbench = { url, token };
  } catch {
    workbench = null;
  }

  // 一键启动的子进程：只有本进程能停；dispose 时一并收掉
  let run = null;
  let starting = null;

  async function stopRun() {
    if (!run) return false;
    const current = run;
    run = null;
    await stopServe(current.child);
    return true;
  }

  async function persistWorkbench() {
    if (!workbench) {
      await rm(workbenchFile, { force: true }).catch(() => {});
      return;
    }
    const tmp = workbenchFile + '.tmp';
    await writeFile(tmp, JSON.stringify(workbench, null, 2),
      { encoding: 'utf8', mode: 0o600 });
    await rename(tmp, workbenchFile);
  }

  let project = null;
  let lastVerify = null;
  let verifyLoadInfo = 'not-loaded';
  try {
    project = JSON.parse(await readFile(projectFile, 'utf8'));
  } catch {
    project = buildDemoProject(sha256);
  }
  project = normalizeProject(project);

  // 核验结果落盘：否则重启/刷新后 CITE_FAKE 这类红牌会静默消失，
  // 用户会以为问题被修好了——那比多报一张牌危险得多。
  try {
    const saved = JSON.parse(await readFile(verifyFile, 'utf8'));
    const want = verifyBasis(project);
    if (saved && saved.verify && saved.basis === want) {
      lastVerify = saved.verify;
      verifyLoadInfo = 'restored:' + (saved.verify.results?.length ?? 0);
    } else {
      lastVerify = null;
      verifyLoadInfo = 'mismatch:saved=' + (saved?.basis?.slice(0, 12) || 'none') + ',want=' + want.slice(0, 12);
    }
  } catch (err) {
    lastVerify = null;
    verifyLoadInfo = 'readfailed:' + err.message;
  }

  // 核验结果的适用基线：正文与 bib 一致才算同一轮结论
  function verifyBasis(p) {
    return sha256(String(p.manuscript ?? '') + '\u0000' + String(p.bib ?? ''));
  }

  async function persist() {
    const tmp = projectFile + '.tmp';
    await writeFile(tmp, JSON.stringify(project, null, 2), 'utf8');
    await rename(tmp, projectFile);
  }

  async function persistVerify() {
    const tmp = verifyFile + '.tmp';
    await writeFile(tmp, JSON.stringify({ basis: verifyBasis(project), verify: lastVerify }, null, 2), 'utf8');
    await rename(tmp, verifyFile);
  }

  async function readBody(req) {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 8 * 1024 * 1024) throw new Error('请求体过大');
      chunks.push(chunk);
    }
    if (!chunks.length) return {};
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  }

  function sendJson(res, code, payload) {
    res.writeHead(code, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(payload));
  }

  function sendText(res, code, body, type = 'text/plain; charset=utf-8') {
    // type 必须有默认值：漏传会让 writeHead 抛 "Invalid value undefined for
    // header content-type"，把本该是 404 的未知路径变成 500。
    res.writeHead(code, { 'content-type': type });
    res.end(body);
  }

  // ---------------------------------------------------------- 引用在线核验

  function normalizeTitle(text) {
    return String(text ?? '')
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fff]+/g, ' ')
      .trim();
  }

  function titleSimilarity(a, b) {
    const ta = new Set(normalizeTitle(a).split(' ').filter(Boolean));
    const tb = new Set(normalizeTitle(b).split(' ').filter(Boolean));
    if (!ta.size || !tb.size) return 0;
    let inter = 0;
    for (const x of ta) if (tb.has(x)) inter += 1;
    const union = ta.size + tb.size - inter;
    const jaccard = inter / (union || 1);
    const na = normalizeTitle(a);
    const nb = normalizeTitle(b);
    const contains = na && nb && (na.includes(nb) || nb.includes(na)) ? 1 : 0;
    return Math.max(jaccard, contains * 0.85);
  }

  async function checkCrossref(entry, sid) {
    const url = 'https://api.crossref.org/works/' + encodeURIComponent(sid.value);
    const res = await fetch(url, {
      headers: { 'user-agent': 'FactScribe/1.0 (MiniMax Code Mini App; local verification)' },
      signal: AbortSignal.timeout(12000),
    });
    if (res.status === 404) return { status: 'not_found', detail: 'Crossref 没有这条 DOI。' };
    if (!res.ok) return { status: 'unverified', detail: 'Crossref 返回 ' + res.status + '。' };
    const data = await res.json();
    const m = data.message || {};
    const remoteTitle = Array.isArray(m.title) ? m.title[0] : m.title || '';
    const sim = titleSimilarity(entry.fields.title || '', remoteTitle || '');
    return {
      status: sim >= 0.6 ? 'verified' : 'suspect',
      detail: remoteTitle ? 'Crossref 标题：' + remoteTitle : 'Crossref 无标题字段。',
      remoteTitle,
      similarity: Number(sim.toFixed(3)),
    };
  }

  async function checkArxiv(entry, sid) {
    const url = 'https://export.arxiv.org/api/query?id_list=' + encodeURIComponent(sid.value) + '&max_results=1';
    const res = await fetch(url, {
      headers: { 'user-agent': 'FactScribe/1.0 (MiniMax Code Mini App; local verification)' },
      signal: AbortSignal.timeout(12000),
    });
    if (!res.ok) return { status: 'unverified', detail: 'arXiv 返回 ' + res.status + '。' };
    const xml = await res.text();
    const titles = [...xml.matchAll(/<title>([\s\S]*?)<\/title>/g)].map((m) => m[1].trim());
    const remoteTitle = titles.length > 1 ? titles[1] : '';
    if (!remoteTitle) return { status: 'not_found', detail: 'arXiv 没有这条记录。' };
    const sim = titleSimilarity(entry.fields.title || '', remoteTitle);
    return {
      status: sim >= 0.6 ? 'verified' : 'suspect',
      detail: 'arXiv 标题：' + remoteTitle,
      remoteTitle,
      similarity: Number(sim.toFixed(3)),
    };
  }

  async function verifyCitations(current) {
    const entries = parseBib(current.bib ?? '');
    const results = [];
    let failures = 0;
    for (const entry of entries) {
      const sid = stableIdOf(entry);
      if (!sid) {
        results.push({ key: entry.key, status: 'no_id', detail: '没有稳定标识，本地判红，不做在线核验。' });
        continue;
      }
      let r;
      try {
        r = sid.kind === 'doi' ? await checkCrossref(entry, sid) : await checkArxiv(entry, sid);
      } catch (err) {
        r = { status: 'unverified', detail: '请求失败：' + (err.name === 'TimeoutError' ? '超时' : err.message) };
      }
      if (r.status === 'unverified') failures += 1;
      results.push({ key: entry.key, kind: sid.kind, id: sid.value, ...r });
    }
    return { results, failures, total: results.length };
  }

  // ---------------------------------------------------------- 导出

  function buildReport(current, audit, verify) {
    const out = [];
    const verdictText = { green: '绿', red: '红', yellow: '黄' }[audit.verdict];
    out.push('# 事实闸审计报告');
    out.push('');
    out.push('- 结论：**' + verdictText + '**（退出码 ' + audit.exitCode + '）');
    const redShownN = (audit.redShown || audit.red).length;
    const yellowShownN = (audit.yellowShown || audit.yellow).length;
    out.push(
      '- 红牌 ' + redShownN + (redShownN === audit.red.length ? ' 项' : ' 类（' + audit.red.length + ' 条）') +
        '，黄牌 ' + yellowShownN + (yellowShownN === audit.yellow.length ? ' 项' : ' 类（' + audit.yellow.length + ' 条）')
    );
    if (audit.stats) {
      const pct = audit.stats.denom ? Math.round((audit.stats.bound / audit.stats.denom) * 100) : 0;
      out.push('- 内联绑定：' + audit.stats.bound + '/' + audit.stats.denom + '（' + pct + '%）');
    }
    out.push('- 事实账：' + (current.facts || []).length + ' 条；来源材料：' + (current.sources || []).length + ' 份');
    out.push('');
    out.push('> 绿只说明三件事：账有据、据未改、文有绑。它不说明结论为真。');
    out.push('');
    for (const group of [['红牌', audit.redShown || audit.red], ['黄牌', audit.yellowShown || audit.yellow]]) {
      if (!group[1].length) continue;
      out.push('## ' + group[0] + '（' + group[1].length + '）');
      out.push('');
      for (const i of group[1]) {
        out.push('- **' + i.code + '** ' + i.message + (i.location ? '  _(' + i.location + ')_' : ''));
        const p = audit.prescriptions[i.code];
        if (p) {
          out.push('  - 处方：' + p.title);
          for (const s of p.steps) out.push('    - ' + s);
        }
      }
      out.push('');
    }
    if (verify && verify.results && verify.results.length) {
      out.push('## 引用在线核验');
      out.push('');
      for (const r of verify.results) {
        out.push('- ' + r.key + '：' + r.status + (r.detail ? ' — ' + r.detail : ''));
      }
      out.push('');
    }
    return out.join('\n');
  }

  function buildMatrix(audit) {
    const out = ['# 追溯矩阵', ''];
    out.push('| 事实 | 主张 | 值 | 来源 | 正文位置 | 状态 |');
    out.push('| --- | --- | --- | --- | --- | --- |');
    for (const row of audit.matrix.facts) {
      const at = row.boundLines.length ? row.boundLines.map((l) => 'L' + l).join(', ') : '—';
      out.push('| ' + row.id + ' | ' + row.claim + ' | ' + row.value + ' | ' + row.source + ' | ' + at + ' | ' + row.usedIn + ' |');
    }
    out.push('');
    out.push('| 引用 key | 标题 | 稳定标识 | 引用次数 |');
    out.push('| --- | --- | --- | --- |');
    for (const row of audit.matrix.citations) {
      const sid = row.stableId ? row.stableId.kind + ':' + row.stableId.value : '无';
      out.push('| ' + row.key + ' | ' + row.title + ' | ' + sid + ' | ' + row.cited + ' |');
    }
    out.push('');
    return out.join('\n');
  }

  function buildManifest(current, audit) {
    return JSON.stringify(
      {
        tool: 'minifactscribe',
        project: current.name || 'untitled',
        generatedAt: new Date().toISOString(),
        verdict: audit.verdict,
        exitCode: audit.exitCode,
        files: [
          { path: 'manuscript', sha256: sha256(current.manuscript ?? ''), bytes: String(current.manuscript ?? '').length },
          { path: 'refs.bib', sha256: sha256(current.bib ?? ''), bytes: String(current.bib ?? '').length },
          ...(current.sources || []).map((s) => ({
            path: 'sources/' + s.id,
            sha256: s.sha256 || sha256(s.text ?? ''),
            bytes: String(s.text ?? '').length,
          })),
        ],
        facts: (current.facts || []).map((f) => ({
          id: f.id,
          claim: f.claim,
          value: f.value,
          source: f.source,
          sourceSha256: f.sourceSha256,
          locator: f.locator,
        })),
        note: '哈希只保证「事后没被改过」，不保证「记录的就是真实发生过的」。',
      },
      null,
      2,
    );
  }

  // ---------------------------------------------------------- 路由

  const server = createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', 'http://miniapp.local');
    const path = url.pathname;
    try {
      if (request.method === 'GET' && (path === '/minifactscribe' || path === '/minifactscribe/')) {
        const html = await readFile(join(context.pluginRoot, CLIENT_DIR, 'index.html'));
        sendText(response, 200, html, CONTENT_TYPES['.html']);
        return;
      }
      if (request.method === 'GET' && (path === '/app.js' || path === '/app.css')) {
        try {
          const file = await readFile(join(context.pluginRoot, CLIENT_DIR, path.slice(1)));
          sendText(response, 200, file, CONTENT_TYPES[extname(path)] || 'application/octet-stream');
        } catch {
          sendText(response, 404, 'not_found');
        }
        return;
      }
      if (request.method === 'GET' && path.startsWith('/minifactscribe/')) {
        const rel = normalize(path.slice('/minifactscribe/'.length)).replace(/^(\.\.(\/|\\))+/, '');
        if (rel.includes('..')) {
          sendText(response, 404, 'not_found');
          return;
        }
        let file;
        try {
          file = await readFile(join(context.pluginRoot, CLIENT_DIR, rel));
        } catch {
          // 静态资源不存在是 404，不是 500——面板里误点链接不该看到服务端错误
          sendText(response, 404, 'not_found');
          return;
        }
        sendText(response, 200, file, CONTENT_TYPES[extname(rel)] || 'application/octet-stream');
        return;
      }
      if (request.method === 'GET' && path === '/api/workbench') {
        sendJson(response, 200, {
          ok: true, configured: Boolean(workbench),
          url: workbench?.url || '', tokenSet: Boolean(workbench?.token),
          running: Boolean(run), project: run?.project || '',
          pid: run?.pid || 0,
          mode: run ? { write: Boolean(run.allowWrite), build: Boolean(run.allowBuild) } : null,
        });
        return;
      }
      if (request.method === 'PUT' && path === '/api/workbench') {
        try {
          const body = await readBody(request);
          const url = normalizeWorkbenchUrl(body.url);
          const token = String(body.token ?? '').trim()
            || (workbench?.url === url ? workbench.token : '');
          if (!token) throw new Error('token 不能为空');
          const capabilities = await probeWorkbench(url, token);
          // 手动连到别的工作台：先停掉我们自己拉起的那个，别留孤儿进程
          if (run) await stopRun();
          workbench = { url, token };
          await persistWorkbench();
          sendJson(response, 200, {
            ok: true, configured: true, url, tokenSet: true,
            capabilities,
          });
        } catch (err) {
          sendJson(response, 400, {
            ok: false,
            error: { code: 'WORKBENCH_CONNECT_FAILED', message: err.message },
          });
        }
        return;
      }
      if (request.method === 'DELETE' && path === '/api/workbench') {
        await stopRun();
        workbench = null;
        await persistWorkbench();
        sendJson(response, 200, { ok: true, configured: false, running: false });
        return;
      }
      if (request.method === 'GET' && path === '/api/projects') {
        const registry = await readRegistry();
        sendJson(response, 200, {
          ok: true, dir: factscribeDir(), python: registry.python || pythonFrom(),
          pythonpath: registry.pythonpath,
          projects: registry.projects, lastPath: registry.lastPath,
        });
        return;
      }
      if (request.method === 'POST' && path === '/api/projects') {
        try {
          const body = await readBody(request);
          let registry = await readRegistry();
          if (body?.python !== undefined) {
            const python = String(body.python ?? '').trim();
            if (python && !/^[\w./-]+$/.test(python)) {
              throw new Error('Python 解释器只填命令名或绝对路径，不能带空格或参数');
            }
            registry = { ...registry, python };
            await writeRegistry(undefined, registry);
          }
          if (body?.pythonpath !== undefined) {
            const pythonpath = String(body.pythonpath ?? '').trim();
            if (pythonpath && !/^[\w./:~-]+$/.test(pythonpath)) {
              throw new Error('包路径只填绝对路径（多个用 : 分隔），不能带空格或参数');
            }
            registry = { ...registry, pythonpath };
            await writeRegistry(undefined, registry);
          }
          if (body?.path !== undefined) {
            const resolved = resolveProjectDir(body.path);
            registry = upsertProject(registry, resolved);
            await writeRegistry(undefined, registry);
            sendJson(response, 200, {
              ok: true, project: resolved, projects: registry.projects,
              lastPath: registry.lastPath, python: registry.python,
              pythonpath: registry.pythonpath,
            });
            return;
          }
          sendJson(response, 200, {
            ok: true, projects: registry.projects,
            lastPath: registry.lastPath, python: registry.python,
            pythonpath: registry.pythonpath,
          });
        } catch (err) {
          sendJson(response, 400, {
            ok: false, error: { code: 'PROJECT_INVALID', message: err.message },
          });
        }
        return;
      }
      if (request.method === 'DELETE' && path === '/api/projects') {
        const target = url.searchParams.get('path') || '';
        let registry = await readRegistry();
        registry = removeProject(registry, String(target));
        await writeRegistry(undefined, registry);
        sendJson(response, 200, {
          ok: true, projects: registry.projects, lastPath: registry.lastPath,
        });
        return;
      }
      if (request.method === 'POST' && path === '/api/workbench/start') {
        if (starting) {
          sendJson(response, 409, {
            ok: false,
            error: { code: 'WORKBENCH_STARTING', message: '上一次启动还没结束，稍等一下' },
          });
          return;
        }
        let body = {};
        try {
          body = await readBody(request);
        } catch (err) {
          sendJson(response, 400, { ok: false, error: { code: 'BAD_BODY', message: err.message } });
          return;
        }
        let target;
        try {
          target = resolveProjectDir(body.path);
        } catch (err) {
          sendJson(response, 400, {
            ok: false, error: { code: 'PROJECT_INVALID', message: err.message },
          });
          return;
        }
        starting = (async () => {
          if (run && run.project !== target.path) await stopRun();
          if (run && run.project === target.path) return { ...run, reused: true };
          const registry = await readRegistry();
          const python = registry.python || pythonFrom();
          const started = await startServe({
            project: target.path,
            allowWrite: Boolean(body.allowWrite),
            allowBuild: Boolean(body.allowBuild),
            python,
            pythonPath: registry.pythonpath,
          });
          run = {
            ...started,
            allowWrite: Boolean(body.allowWrite),
            allowBuild: Boolean(body.allowBuild),
            startedAt: new Date().toISOString(),
          };
          // 服务自己挂了（崩溃/被外部杀）：界面不能继续显示「运行中」
          started.child.once('exit', () => {
            if (run?.child !== started.child) return;
            run = null;
            if (workbench?.managed) {
              workbench = null;
              void persistWorkbench().catch(() => undefined);
            }
          });
          // 一键启动的服务只归本进程管；地址和 token 不落盘给别人用
          workbench = { url: started.url, token: started.token, managed: true };
          await persistWorkbench();
          await writeRegistry(undefined, upsertProject(registry, target));
          return { ...run, reused: false };
        })();
        try {
          const started = await starting;
          sendJson(response, 200, {
            ok: true, running: true, reused: Boolean(started.reused),
            url: started.url, project: started.project, pid: started.pid,
            command: started.command,
            allowWrite: Boolean(started.allowWrite),
            allowBuild: Boolean(started.allowBuild),
            tokenSet: true,
          });
        } catch (err) {
          sendJson(response, 502, {
            ok: false,
            error: { code: 'WORKBENCH_START_FAILED', message: err.message },
          });
        } finally {
          starting = null;
        }
        return;
      }
      if (request.method === 'POST' && path === '/api/workbench/stop') {
        const stopped = await stopRun();
        if (workbench?.managed) {
          workbench = null;
          await persistWorkbench();
        }
        sendJson(response, 200, { ok: true, running: false, stopped });
        return;
      }
      if (path.startsWith('/api/workbench/')) {
        if (!workbench) {
          sendJson(response, 400, {
            ok: false,
            error: { code: 'WORKBENCH_NOT_CONFIGURED',
                     message: '还没有连接本地工作台' },
          });
          return;
        }
        try {
          if (request.method === 'GET' && path === '/api/workbench/status') {
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token, '/api/status'));
            return;
          }
          if (request.method === 'GET' && path === '/api/workbench/brief') {
            const section = new URL(request.url ?? '/', 'http://x').searchParams.get('section');
            const suffix = section ? '?section=' + encodeURIComponent(section) : '';
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/brief' + suffix));
            return;
          }
          if (request.method === 'GET' && path === '/api/workbench/project') {
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/project'));
            return;
          }
          if (request.method === 'PUT' && path === '/api/workbench/sections') {
            const body = await readBody(request);
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/sections', 'PUT', body));
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/facts') {
            const body = await readBody(request);
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/facts', 'POST', body));
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/audit') {
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/audit', 'POST'));
            return;
          }
          if (request.method === 'GET' && path === '/api/workbench/evidence') {
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token, '/api/evidence'));
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/evidence/freeze') {
            const body = await readBody(request);
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/evidence/freeze', 'POST', body));
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/evidence/unfreeze') {
            const body = await readBody(request);
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/evidence/unfreeze', 'POST', body));
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/build') {
            const body = await readBody(request);
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/build', 'POST', body));
            return;
          }
          if (request.method === 'GET' && path === '/api/workbench/pdf') {
            const upstream = await fetch(workbench.url + '/api/pdf', {
              headers: { authorization: `Bearer ${workbench.token}` },
              signal: AbortSignal.timeout(30000),
            });
            if (!upstream.ok) {
              throw new Error('PDF 还没生成或不可读（HTTP ' + upstream.status + '）');
            }
            const buffer = Buffer.from(await upstream.arrayBuffer());
            response.writeHead(200, {
              'content-type': 'application/pdf',
              'content-length': buffer.length,
              'cache-control': 'no-store',
            });
            response.end(buffer);
            return;
          }
          sendJson(response, 404, {
            ok: false,
            error: { code: 'NOT_FOUND', message: '没有这个接口：' + path },
          });
        } catch (err) {
          sendJson(response, 502, {
            ok: false,
            error: { code: 'WORKBENCH_UPSTREAM', message: err.message },
          });
        }
        return;
      }
      if (request.method === 'GET' && path === '/api/state') {
        sendJson(response, 200, { ok: true, project, verify: lastVerify, verifyBasis: verifyBasis(project), verifyLoad: verifyLoadInfo });
        return;
      }
      if (request.method === 'PUT' && path === '/api/project') {
        const body = await readBody(request);
        const before = verifyBasis(project);
        project = normalizeProject(body.project || {});
        // 正文或 bib 变了，上一轮的联网核验结论不再适用——作废，别拿旧结论判新内容
        if (verifyBasis(project) !== before) {
          lastVerify = null;
          await persistVerify();
        }
        await persist();
        sendJson(response, 200, { ok: true, project });
        return;
      }
      if (request.method === 'POST' && path === '/api/demo') {
        project = buildDemoProject(sha256);
        lastVerify = null;
        await persistVerify();
        await persist();
        sendJson(response, 200, { ok: true, project });
        return;
      }
      if (request.method === 'POST' && path === '/api/audit') {
        // 审计一律带上已核验结论，避免刷新后红牌静默消失
        const base = auditProject(project);
        const audit = lastVerify ? mergeVerifyIssues(base, lastVerify) : base;
        sendJson(response, 200, { ok: true, audit, verify: lastVerify });
        return;
      }
      if (request.method === 'POST' && path === '/api/verify') {
        const verify = await verifyCitations(project);
        lastVerify = verify;
        await persistVerify();
        sendJson(response, 200, { ok: true, verify, audit: mergeVerifyIssues(auditProject(project), verify) });
        return;
      }
      if (request.method === 'POST' && path === '/api/protect') {
        const body = await readBody(request);
        sendJson(response, 200, { ok: true, result: protectDiff(body.before ?? '', body.after ?? '') });
        return;
      }
      if (request.method === 'GET' && path === '/api/export/report.md') {
        const base_audit = auditProject(project);
        const audit = lastVerify ? mergeVerifyIssues(base_audit, lastVerify) : base_audit;
        sendText(response, 200, buildReport(project, audit, lastVerify), 'text/markdown; charset=utf-8');
        return;
      }
      if (request.method === 'GET' && path === '/api/export/matrix.md') {
        const audit = auditProject(project);
        sendText(response, 200, buildMatrix(audit), 'text/markdown; charset=utf-8');
        return;
      }
      if (request.method === 'GET' && path === '/api/export/manifest.json') {
        const audit = auditProject(project);
        sendText(response, 200, buildManifest(project, audit), 'application/json; charset=utf-8');
        return;
      }
      sendText(response, 404, 'not_found');
    } catch (err) {
      context.logger.warn('minifactscribe.request.failed', { path, message: err.message });
      sendJson(response, 500, { ok: false, error: err.message });
    }
  });

  await new Promise((resolve, reject) => {
    const onError = (error) => reject(error);
    server.once('error', onError);
    server.listen(context.listen.port, context.listen.host, () => {
      server.off('error', onError);
      resolve();
    });
  });
  context.logger.info('minifactscribe.runtime.listening');

  let disposal;
  const dispose = () => {
    if (disposal) return disposal;
    context.signal.removeEventListener('abort', onAbort);
    // 子进程由我们自己收；宿主只停入口进程，不会替你发现孤儿
    const stopChild = stopRun().catch(() => false);
    disposal = Promise.all([
      new Promise((resolve, reject) => {
        server.close((error) => (error ? reject(error) : resolve()));
      }),
      stopChild,
    ]).then(() => undefined);
    return disposal;
  };
  const onAbort = () => {
    void dispose().catch(() => undefined);
  };
  context.signal.addEventListener('abort', onAbort, { once: true });
  if (context.signal.aborted) await dispose();

  return { dispose };
}

function normalizeProject(project) {
  const p = project && typeof project === 'object' ? project : {};
  return {
    name: String(p.name ?? '未命名项目'),
    note: String(p.note ?? ''),
    manuscript: String(p.manuscript ?? ''),
    bib: String(p.bib ?? ''),
    sources: Array.isArray(p.sources)
      ? p.sources.map((s) => ({
          id: String(s.id ?? ''),
          name: String(s.name ?? s.id ?? ''),
          text: String(s.text ?? ''),
          sha256: String(s.sha256 ?? ''),
        }))
      : [],
    facts: Array.isArray(p.facts)
      ? p.facts.map((f) => ({
          id: String(f.id ?? ''),
          claim: String(f.claim ?? ''),
          value: String(f.value ?? ''),
          source: String(f.source ?? ''),
          sourceSha256: String(f.sourceSha256 ?? ''),
          locator: String(f.locator ?? ''),
          confidence: String(f.confidence ?? ''),
          derivedFrom: Array.isArray(f.derivedFrom) ? f.derivedFrom.map(String) : [],
          expr: String(f.expr ?? ''),
          dupOk: Boolean(f.dupOk),
          notes: String(f.notes ?? ''),
        }))
      : [],
    protect: {
      before: String((p.protect && p.protect.before) ?? ''),
      after: String((p.protect && p.protect.after) ?? ''),
    },
  };
}
