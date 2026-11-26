// 事实闸 · Node 服务
// 一个 Node 领域服务：所有写操作走这里，提交后再广播。
// 持久化落在 context.dataDir；浏览器只管呈现。

import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { pythonFrom, installSample, serveArgs, startServe, stopServe } from './launcher.mjs';
import {
  applyEnding, detectEol, dominantEnding, sameContent, toLfOnly,
} from './eol.mjs';
import {
  factscribeDir, isGuidePath, readProjectDescription, readRegistry, removeProject,
  resolveProjectDir, upsertProject, writeRegistry,
} from './projects.mjs';


const CLIENT_DIR = 'miniapp/client';
const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
};

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

/** 把相对路径安全地落在项目根里：越界（..、绝对路径）一律 null。 */
export function resolveInRoot(root, rel) {
  const base = String(root ?? '').trim();
  const relPath = String(rel ?? '').trim();
  if (!base || !relPath) return null;
  if (relPath.includes('\0')) return null;
  const rootPath = resolve(base);
  const target = resolve(base, relPath);
  if (target !== rootPath && !target.startsWith(rootPath + sep)) return null;
  return target;
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

/**
 * 代理转发，但把上游的 400/403 原样带回。
 *
 * 只读（READ_ONLY）、路径越界（PATH_ESCAPE）是「用户或项目自己的问题」，不该
 * 一律变成 502；连不上上游才算传输失败。
 */
export async function workbenchProxy(base, token, path, method = 'GET', body = null) {
  const headers = { authorization: `Bearer ${token}` };
  if (body !== null) headers['content-type'] = 'application/json';
  let response;
  try {
    response = await fetch(base + path, {
      method,
      headers,
      ...(body !== null ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(10000),
    });
  } catch (err) {
    throw new Error('连不上本地工作台：' + err.message);
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error('工作台返回的不是 JSON');
  }
  if (!response.ok || data?.ok === false) {
    return { status: response.status >= 400 ? response.status : 400, data };
  }
  return { status: 200, data };
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

  // 论文项目根：引擎的 /api/project、/api/status 都带 root。记住它，
  // 保存时才能去磁盘上读原文件的真行尾——接口层给过来的是归一过的 LF。
  let projectRoot = '';

  function rememberRoot(data) {
    const root = typeof data?.root === 'string' ? data.root.trim() : '';
    if (root) projectRoot = root;
    return projectRoot;
  }

  /** 没记住就问引擎要一次（/api/status 比 /api/project 轻）。 */
  async function ensureProjectRoot() {
    if (projectRoot) return projectRoot;
    if (!workbench) return '';
    try {
      const data = await workbenchFetch(workbench.url, workbench.token, '/api/status');
      rememberRoot(data);
    } catch {
      // 问不到就按「没有根」处理：只是不保行尾，不影响保存本身。
    }
    return projectRoot;
  }

  /**
   * 保存一节：先把行尾按原文件的风格摆回去，再交给引擎写。
   *
   * 引擎那一层拿到的是 LF 形态（不带 '\r'）：Windows 上引擎的写路径是
   * Python 文本模式（newline=None），每个 '\n' 会被翻成 '\r\n'，
   * 已经带 '\r' 的还会被写成 '\r\r\n'（内容损坏）。所以 '\r' 绝不
   * 进引擎那一层，行尾由这里在引擎写完之后按原风格校正。
   */
  async function prepareSectionWrite(body) {
    const file = String(body?.file ?? '');
    const text = typeof body?.text === 'string' ? body.text : null;
    if (!file || text === null) return { payload: body, target: null, intended: null };
    const root = await ensureProjectRoot();
    const target = resolveInRoot(root, file);
    if (!target) return { payload: body, target: null, intended: null };
    let original;
    try {
      original = await readFile(target, 'utf8');   // node 读文件不做换行翻译
    } catch {
      return { payload: body, target: null, intended: null };
    }
    const ending = dominantEnding(original);
    return {
      payload: { ...body, text: toLfOnly(applyEnding(text, ending)) },
      target,
      intended: applyEnding(text, ending),
      style: detectEol(original).style,
    };
  }

  /**
   * 引擎写完之后核对字节：只差行尾才改回原风格，内容不一样一个字也不动。
   */
  async function settleSectionBytes(prepared) {
    if (!prepared.target || prepared.intended === null) return null;
    let actual;
    try {
      actual = await readFile(prepared.target, 'utf8');
    } catch {
      return { style: prepared.style, repaired: false, note: '读不回写后的文件' };
    }
    const bytes = Buffer.byteLength(actual, 'utf8');
    if (actual === prepared.intended) {
      return { style: prepared.style, repaired: false, bytes };
    }
    if (!sameContent(actual, prepared.intended)) {
      // 内容不一样＝文件在这期间被别处改过：不动它，也不覆盖别人的改动。
      return { style: prepared.style, repaired: false, bytes, note: '文件内容已被别处改动' };
    }
    const tmp = prepared.target + '.eol-tmp';
    try {
      await writeFile(tmp, prepared.intended, 'utf8');
      await rename(tmp, prepared.target);
    } catch (err) {
      await rm(tmp, { force: true }).catch(() => {});
      return {
        style: prepared.style, repaired: false, bytes,
        note: '行尾校正失败：' + err.message,
      };
    }
    return {
      style: prepared.style, repaired: true,
      bytes: Buffer.byteLength(prepared.intended, 'utf8'),
    };
  }

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
          projects: registry.projects.map((p) => ({
            ...p,
            description: readProjectDescription(p.path),
            guide: isGuidePath(p.path),
          })),
          lastPath: registry.lastPath,
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
      if (request.method === 'POST' && path === '/api/workbench/samples/guide') {
        // 内置示例论文：优先代理给已连上的 Python 工作台（同一个接口）；
        // 还没连上工作台就让 Python 直接装一份——示例得先落地,
        // 才谈得上拿它当项目打开。
        try {
          const body = await readBody(request);
          const reset = Boolean(body?.reset);
          if (workbench) {
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/samples/guide', 'POST', { reset });
            sendJson(response, upstream.status, upstream.data);
            return;
          }
          const registry = await readRegistry();
          const data = await installSample({
            reset,
            python: registry.python || pythonFrom(),
            pythonPath: registry.pythonpath,
          });
          sendJson(response, 200, { ok: true, ...data });
        } catch (err) {
          sendJson(response, 500, {
            ok: false,
            error: { code: 'SAMPLE_INSTALL_FAILED', message: err.message },
          });
        }
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
            const data = await workbenchFetch(workbench.url, workbench.token,
              '/api/project');
            // 记住项目根：保存时要去磁盘上读原文件的真行尾（接口层给的是 LF）。
            rememberRoot(data);
            sendJson(response, 200, data);
            return;
          }
          if (request.method === 'PUT' && path === '/api/workbench/sections') {
            const body = await readBody(request);
            // 行尾先按原文件的风格摆回去，再交给引擎写；写完核对字节。
            const prepared = await prepareSectionWrite(body);
            // 上游的 400/403/409 原样带回（指纹闸拒写＝409）：写盘的成败由
            // 引擎说了算，代理不许替它压成一个说不清的 502——压掉之后，
            // 「这一节在别处被改过」与「本地工作台连不上」长得一模一样。
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/sections', 'PUT', prepared.payload);
            if (upstream.status !== 200) {
              // 没写成功就不碰磁盘：行尾校正那步只对「真写下去了」有意义，
              // 对着没写成功的目标做校正等于拿旧内容盖回去。
              sendJson(response, upstream.status, upstream.data);
              return;
            }
            const eol = await settleSectionBytes(prepared);
            // bytes 报落盘后的真实大小：引擎那一层拿到的是 LF 形态，
            // 它的字节数比实际文件小（CRLF 每行多一个 \r）。
            sendJson(response, 200, eol
              ? { ...upstream.data, ...(eol.bytes == null ? {} : { bytes: eol.bytes }), eol }
              : upstream.data);
            return;
          }
          // 章节增删改：上游的 400/403/409 原样带回（409 = 还被正文引用）。
          for (const action of ['create', 'rename', 'delete']) {
            if (request.method === 'POST'
              && path === '/api/workbench/sections/' + action) {
              const body = await readBody(request);
              const upstream = await workbenchProxy(workbench.url, workbench.token,
                '/api/sections/' + action, 'POST', body);
              sendJson(response, upstream.status, upstream.data);
              return;
            }
          }
          if (request.method === 'POST' && path === '/api/workbench/projects/create') {
            // 新建论文项目：只有 Python 工作台会写盘（要 --allow-write），
            // 上游的 400/403/409 原样带回。
            const body = await readBody(request);
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/projects/create', 'POST', body);
            sendJson(response, upstream.status, upstream.data);
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/projects/update') {
            // 改项目名与简介：写登记册 + factscribe.toml，同样只有 Python 会写盘。
            const body = await readBody(request);
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/projects/update', 'POST', body);
            sendJson(response, upstream.status, upstream.data);
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
          if (request.method === 'GET' && path === '/api/workbench/reports') {
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/reports');
            sendJson(response, upstream.status, upstream.data);
            return;
          }
          if (request.method === 'GET' && path === '/api/workbench/citations') {
            // 引用页：多 bib 汇总 + 每条的状态（只读，上游 400 原样带回）。
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/citations');
            sendJson(response, upstream.status, upstream.data);
            return;
          }
          if (request.method === 'POST' && (path === '/api/workbench/reports'
            || path === '/api/workbench/reports/action')) {
            const body = await readBody(request);
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/reports/action', 'POST', body);
            sendJson(response, upstream.status, upstream.data);
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/reports/template') {
            // 新建报告模板：只有 Python 工作台会写盘（要 --allow-write），
            // 上游的 400/403/409 原样带回。
            const body = await readBody(request);
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/reports/template', 'POST', body);
            sendJson(response, upstream.status, upstream.data);
            return;
          }
          if (request.method === 'POST' && (path === '/api/workbench/citations/add'
            || path === '/api/workbench/citations/delete')) {
            // 引用增删：写 bib 的活只有 Python 工作台能干（要 --allow-write），
            // 上游的 400/403/404/409 原样带回。
            const action = path.endsWith('/add') ? 'add' : 'delete';
            const body = await readBody(request);
            const upstream = await workbenchProxy(workbench.url, workbench.token,
              '/api/citations/' + action, 'POST', body);
            sendJson(response, upstream.status, upstream.data);
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/build') {
            const body = await readBody(request);
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/build', 'POST', body));
            return;
          }
          if (request.method === 'POST' && path === '/api/workbench/browser') {
            if (!workbench?.token) throw new Error('还没有可用 token');
            openInBrowser(workbench.url + '/?token=' + encodeURIComponent(workbench.token));
            sendJson(response, 200, { ok: true, opened: true });
            return;
          }
          if (request.method === 'GET' && path === '/api/workbench/section-page') {
            const file = new URL(request.url ?? '/', 'http://x').searchParams.get('file') || '';
            sendJson(response, 200,
              await workbenchFetch(workbench.url, workbench.token,
                '/api/section-page?file=' + encodeURIComponent(file)));
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
          if (request.method === 'GET' && path === '/api/workbench/asset') {
            // 读图：二进制原样转发，上游给什么 Content-Type 就给什么。
            // 上游的 400/404 原样带回（路径越界是用户的问题，不该变成 502）。
            const rel = new URL(request.url ?? '/', 'http://x').searchParams.get('path') || '';
            const upstream = await fetch(
              workbench.url + '/api/asset?path=' + encodeURIComponent(rel),
              {
                headers: { authorization: `Bearer ${workbench.token}` },
                signal: AbortSignal.timeout(30000),
              }
            );
            if (!upstream.ok) {
              const detail = await upstream.text();
              response.writeHead(upstream.status, {
                'content-type': upstream.headers.get('content-type')
                  || 'application/json; charset=utf-8',
                'cache-control': 'no-store',
              });
              response.end(detail);
              return;
            }
            const buffer = Buffer.from(await upstream.arrayBuffer());
            response.writeHead(200, {
              'content-type': upstream.headers.get('content-type') || 'application/octet-stream',
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

