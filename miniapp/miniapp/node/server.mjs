// @ts-check
// FactScribe 论文工作台 — MiniMax Code MiniApp Node 入口（零 npm 依赖，只用 node: 标准库）。
//
// 分工（方案 A「Node 薄壳」）：
//   - 本文件（薄壳）：占住宿主分配的 127.0.0.1 端口、伺服静态页面（miniapp/client/）、
//     把 /api/* 反向代理给 Python 引擎、在 /mcp/factscribe 上提供 6 个只读 MCP 工具；
//     并负责 Python 子进程的生死——宿主只停 Node，不会发现也不会替我们收子进程。
//   - Python 引擎（vendored 于 miniapp/node/engine/factscribe/）：
//     `python3 -m factscribe workbench --root <论文根> --port 0 --json --no-browser`，
//     stdout 首行是 listening JSON 握手（内含真实端口）；业务大脑（项目发现、
//     章节渲染、写回保护链、检查报告）全在它那边，本文件一行业务不做。
//
// 纪律（官方 docs/runtime.md / security.md 口径）：
//   - stdout/stdin 归宿主：本文件绝不 console.log；Python 子进程 stdio 走管道
//     （stdout 只取首行握手后即排掉，stderr 逐行转 context.logger）；
//   - start() 装完全部路由、listen 成功后才 resolve（resolve 即就绪信号）；
//   - dispose() 2 秒内收干净：关 HTTP 服务＋SIGTERM→SIGKILL 杀 Python 子进程；
//   - 状态随变随写 dataDir（同目录临时文件再改名，原子写）——宿主随时可能停进程；
//   - 所有路由先过回环守卫（Host 必须是本机回环名；带 Origin 必须是自己端口，
//     防 DNS rebinding / 跨站页面打接口）。

import { spawn } from 'node:child_process';
import { createReadStream, promises as fs } from 'node:fs';
import { createServer, request as httpRequest } from 'node:http';
import { delimiter, join, resolve as resolvePath, sep } from 'node:path';
import { homedir } from 'node:os';

// ---------------------------------------------------------------- 常量

/** MCP 端点路径（与 miniapp.json 的 mcpEndpoints 一致）。 */
export const MCP_PATH = '/mcp/factscribe';

/** 页面路由（与 miniapp.json 的 surface.path 一致）。 */
const SURFACE_PATH = '/workbench';

/** 设置路由：v1 的论文根目录配置页与收表接口。 */
const SETUP_PATHS = { api: '/api/miniapp/setup' };

/** 插件包内的载荷位置（相对 context.pluginRoot）。 */
const CLIENT_DIR = join('miniapp', 'client');
const ENGINE_DIR = join('miniapp', 'node', 'engine');

const SERVER_INFO = { name: 'factscribe', version: '1.0.0' }; // 与 plugin.json 保持一致

const STATIC_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.png': 'image/png',
};

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1']);
const MAX_BODY_BYTES = 1024 * 1024;
const ENGINE_START_TIMEOUT_MS = 20000;
const PYTHON_PROBE_TIMEOUT_MS = 15000;

// ---------------------------------------------------------------- 小件

class HttpError extends Error {
  /** @param {number} status @param {string} code @param {string} [message] */
  constructor(status, code, message) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.userMessage = message || code;
  }
}

/** @param {number} ms */
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** @param {string} hostHeader */
function hostnameOf(hostHeader) {
  const h = hostHeader.trim().toLowerCase();
  const bracketed = /^\[([^\]]*)\]/.exec(h);
  if (bracketed) return bracketed[1];
  const colon = h.lastIndexOf(':');
  return colon === -1 ? h : h.slice(0, colon);
}

/**
 * 回环守卫（照 cq-viewer 的实现形）：Host 头必须是本机回环名；浏览器带来的
 * Origin 必须是本监听端口自己。宿主的 MCP 客户端是 Node 进程，不带 Origin。
 * @param {import('node:http').IncomingMessage} request @param {number} port
 */
function isLoopbackRequest(request, port) {
  const host = request.headers.host;
  if (host !== undefined && !LOOPBACK_HOSTS.has(hostnameOf(host))) return false;
  const origin = request.headers.origin;
  if (origin === undefined) return true;
  let url;
  try {
    url = new URL(origin);
  } catch {
    return false; // 包括 "null"（沙箱 iframe、file://）
  }
  const originPort = Number(url.port || (url.protocol === 'https:' ? 443 : 80));
  return url.protocol === 'http:' && LOOPBACK_HOSTS.has(hostnameOf(url.host)) && originPort === port;
}

/**
 * JSON-only 请求体（跨站页面发不出 application/json——没有 CORS 预检就过不来）。
 * @param {import('node:http').IncomingMessage} request
 * @param {number} [maxBytes]
 */
function readJsonBody(request, maxBytes = MAX_BODY_BYTES) {
  const type = String(request.headers['content-type'] || '').toLowerCase();
  if (!type.startsWith('application/json')) {
    request.resume();
    return Promise.reject(new HttpError(415, 'json_required', '请求体要 application/json'));
  }
  return new Promise((resolve, reject) => {
    let size = 0;
    let tooLarge = false;
    /** @type {Buffer[]} */
    const chunks = [];
    request.on('data', (chunk) => {
      if (tooLarge) return; // 继续排掉，错误应答才送得出去
      size += chunk.length;
      if (size > maxBytes) {
        tooLarge = true;
        chunks.length = 0;
        reject(new HttpError(413, 'body_too_large', '请求体太大'));
        return;
      }
      chunks.push(chunk);
    });
    request.on('end', () => {
      if (tooLarge) return;
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      } catch {
        reject(new HttpError(400, 'invalid_json', '请求体不是合法 JSON'));
      }
    });
    request.on('error', reject);
  });
}

/**
 * @param {import('node:http').ServerResponse} response
 * @param {number} status
 * @param {unknown} payload
 */
function sendJson(response, status, payload) {
  if (response.headersSent) {
    response.destroy();
    return;
  }
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
  response.end(JSON.stringify(payload));
}

/** @param {import('node:http').Server} server @param {string} host @param {number} port */
function listen(server, host, port) {
  return new Promise((resolve, reject) => {
    /** @param {Error} error */
    const onError = (error) => reject(error);
    server.once('error', onError);
    server.listen(port, host, () => {
      server.off('error', onError);
      resolve(undefined);
    });
  });
}

/** @param {import('node:http').Server} server */
function close(server) {
  return new Promise((resolve) => {
    server.close(() => resolve(undefined));
  });
}

// ---------------------------------------------------------------- 配置（dataDir）

const CONFIG_FILE = 'config.json';

/** @param {string} dataDir @returns {Promise<string>} 当前配置的论文根（未配置＝空串） */
async function readConfig(dataDir) {
  try {
    const raw = await fs.readFile(join(dataDir, CONFIG_FILE), 'utf8');
    const data = JSON.parse(raw);
    return typeof data?.root === 'string' ? data.root : '';
  } catch {
    return '';
  }
}

/** 原子写：同目录临时文件 → rename。宿主随时可能停进程，状态必须随变随落盘。 */
async function writeConfig(dataDir, root) {
  await fs.mkdir(dataDir, { recursive: true });
  const final = join(dataDir, CONFIG_FILE);
  const tmp = join(dataDir, `${CONFIG_FILE}.${process.pid}.tmp`);
  await fs.writeFile(tmp, `${JSON.stringify({ root }, null, 2)}\n`, 'utf8');
  await fs.rename(tmp, final);
}

/** 展开 ~ 开头的家目录写法，并解析成绝对路径。 */
function expandRoot(input) {
  const raw = String(input || '').trim();
  if (!raw) return '';
  const expanded = raw === '~' ? homedir() : raw.startsWith('~/') ? join(homedir(), raw.slice(2)) : raw;
  return resolvePath(expanded);
}

// ---------------------------------------------------------------- 首次设置页（未配置论文根时显示）

/**
 * @param {string} presetRoot 配置里有但目录不在这台机器上时，预填出来供改
 * @param {string[]} warnings 额外提示（如目录不存在、Python 缺失）
 */
function setupPageHtml(presetRoot, warnings) {
  const warnHtml = warnings.map((w) => `<p class="warn">${escapeHtml(w)}</p>`).join('');
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FactScribe · 首次设置</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         background: #f2f5f9; color: #1d2b3a; display: flex; min-height: 100vh; align-items: center; }
  main { margin: 0 auto; max-width: 560px; padding: 32px 28px; background: #fff; border-radius: 12px;
         box-shadow: 0 6px 24px rgba(29, 43, 58, .08); }
  h1 { font-size: 20px; margin: 0; }
  p { line-height: 1.7; font-size: 14px; }
  /* 中/EN 常显：首启页也有界面语言开关（同一枚，不藏）。 */
  .top { display: flex; align-items: center; gap: 12px; margin: 0 0 12px; }
  form { display: flex; gap: 8px; margin: 18px 0 6px; }
  input { flex: 1; font-size: 14px; padding: 9px 12px; border: 1px solid #c6d0dc; border-radius: 8px; }
  button { font-size: 14px; padding: 9px 20px; border: 0; border-radius: 8px; background: #2b4a6f; color: #fff; cursor: pointer; }
  button:disabled { opacity: .6; cursor: default; }
  .lang-seg { display: flex; gap: 2px; background: #ececeb; border-radius: 8px; padding: 3px; margin-left: auto; }
  .lang-seg button { min-width: 40px; font-family: inherit; font-size: 12.5px; padding: 4px 10px; border: none;
                     border-radius: 6px; background: transparent; color: #6b7a8c; cursor: pointer; }
  .lang-seg button.on { background: #fff; color: #1d2b3a; font-weight: 600; box-shadow: 0 1px 2px rgba(29, 43, 58, .12); }
  .warn { color: #a5482a; }
  .fine { color: #6b7a8c; font-size: 12px; }
  #msg { min-height: 20px; }
  @media (prefers-color-scheme: dark) {
    body { background: #131a22; color: #dbe4ee; }
    main { background: #1d2733; box-shadow: none; }
    input { background: #131a22; color: #dbe4ee; border-color: #3a4a5c; }
    .lang-seg { background: #27323f; }
    .lang-seg button { color: #9fb0c3; }
    .lang-seg button.on { background: #131a22; color: #dbe4ee; }
  }
</style>
</head>
<body>
<main>
  <div class="top">
    <h1 id="h1">FactScribe 论文工作台</h1>
    <div class="lang-seg" id="langSeg" role="group" aria-label="language">
      <button type="button" data-lang="zh" class="on">中</button>
      <button type="button" data-lang="en">EN</button>
    </div>
  </div>
  <p id="desc">第一次使用，先告诉我论文文件夹在哪里：这个目录下面（三层以内）放着一个个含
     <code>factscribe.toml</code> 的论文项目。我只读它来列出项目和章节；之后在页面里改正文时，
     才会写入该目录下 sections/ 的 .tex 文件（原子写、留 .bak、改动有指纹闸保护）。</p>
  ${warnHtml}
  <form id="f">
    <input id="root" type="text" placeholder="/Users/you/papers" autocomplete="off"
           spellcheck="false" value="${escapeHtml(presetRoot)}" autofocus>
    <button type="submit" id="go">应用</button>
  </form>
  <p id="msg"></p>
  <p class="fine" id="fine">支持 ~ 开头的家目录写法。配置只存在本插件的私有数据目录里，随时回这里改。</p>
</main>
<script>
  var DICT = {
    zh: {
      title: 'FactScribe · 首次设置',
      h1: 'FactScribe 论文工作台',
      desc: '第一次使用，先告诉我论文文件夹在哪里：这个目录下面（三层以内）放着一个个含 <code>factscribe.toml</code> 的论文项目。我只读它来列出项目和章节；之后在页面里改正文时，才会写入该目录下 sections/ 的 .tex 文件（原子写、留 .bak、改动有指纹闸保护）。',
      go: '应用',
      ph: '/Users/you/papers',
      fine: '支持 ~ 开头的家目录写法。配置只存在本插件的私有数据目录里，随时回这里改。',
      empty: '先填一个文件夹路径。',
      applying: '正在应用……',
      saved: '已保存，正在进入工作台……',
      savedWarn: '已保存，但引擎没起来：',
      fail: '保存失败，请检查路径。',
      neterr: '网络出错，请重试。'
    },
    en: {
      title: 'FactScribe · First-time setup',
      h1: 'FactScribe Paper Workbench',
      desc: 'First run: tell me where your papers live. That folder holds one paper project per subfolder (within three levels) containing a <code>factscribe.toml</code>. I only read it to list projects and sections; only when you edit text in the page do I write .tex files under that project sections/ directory (atomic write, a .bak kept, every change guarded by a fingerprint check).',
      go: 'Apply',
      ph: '/Users/you/papers',
      fine: 'A leading ~ means your home folder. The setting lives only in this plugin private data directory; come back here any time to change it.',
      empty: 'Type a folder path first.',
      applying: 'Applying…',
      saved: 'Saved. Opening the workbench…',
      savedWarn: 'Saved, but the engine did not start: ',
      fail: 'Could not save. Please check the path.',
      neterr: 'Network error. Please retry.'
    }
  };
  var lang = 'zh';
  function applyLang(next) {
    lang = (next === 'en') ? 'en' : 'zh';
    var d = DICT[lang];
    document.documentElement.lang = (lang === 'en') ? 'en' : 'zh-CN';
    document.title = d.title;
    document.getElementById('h1').textContent = d.h1;
    document.getElementById('desc').innerHTML = d.desc;
    document.getElementById('go').textContent = d.go;
    document.getElementById('fine').textContent = d.fine;
    document.getElementById('root').setAttribute('placeholder', d.ph);
    var buttons = document.querySelectorAll('#langSeg button');
    for (var i = 0; i < buttons.length; i += 1) {
      buttons[i].classList.toggle('on', buttons[i].getAttribute('data-lang') === lang);
    }
  }
  document.getElementById('langSeg').addEventListener('click', function (event) {
    var target = event.target;
    var button = (target && target.closest) ? target.closest('button[data-lang]') : null;
    if (!button) return;
    applyLang(button.getAttribute('data-lang'));
  });
  applyLang(lang);
  var form = document.getElementById('f');
  var msg = document.getElementById('msg');
  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var button = document.getElementById('go');
    var d = DICT[lang];
    var root = document.getElementById('root').value.trim();
    if (!root) { msg.textContent = d.empty; return; }
    button.disabled = true;
    msg.textContent = d.applying;
    fetch('${SETUP_PATHS.api}', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root: root })
    }).then(function (res) { return res.json(); }).then(function (data) {
      if (data && data.ok) {
        msg.textContent = data.warning ? (d.savedWarn + data.warning) : d.saved;
        setTimeout(function () { location.reload(); }, data.warning ? 2500 : 400);
      } else {
        msg.textContent = (data && data.error) || d.fail;
        button.disabled = false;
      }
    }).catch(function () {
      msg.textContent = d.neterr;
      button.disabled = false;
    });
  });
</script>
</body>
</html>
`;
}

/** @param {string} s */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] || c);
}

// ---------------------------------------------------------------- Python 引擎（vendored，子进程）

/**
 * 引擎管理：spawn／探活／重启／收尸，全部收在这个闭包里。
 * 引擎 lazily 启动：首个业务请求（页面代理或 MCP 工具）需要时才拉起。
 * @param {{ context: { logger: Logger, dataDir: string, pluginRoot: string }, log: Logger }} env
 */
function createEngine(env) {
  const { context, log } = env;
  const engineDir = join(context.pluginRoot, ENGINE_DIR);

  /** @type {import('node:child_process').ChildProcess | null} */
  let child = null;
  let port = 0; // 引擎真实端口（握手行拿到后填）
  let engineRoot = ''; // 当前引擎用的论文根
  /** @type {Promise<void> | null} */
  let starting = null;
  let failedAt = 0;
  let lastFailure = '';
  let intentionalStop = false;
  /** @type {Promise<string> | null} */
  let pythonProbe = null;

  /** Python 命令发现：FS_PYTHON → python3 → python（全探版本 ≥3.10），缓存结果。 */
  function findPython() {
    if (!pythonProbe) {
      pythonProbe = (async () => {
        const candidates = [
          process.env.FS_PYTHON,
          'python3',
          'python', // Windows 装机常常只有这个名字
          '/usr/bin/python3',
          '/opt/homebrew/bin/python3',
          '/usr/local/bin/python3',
        ].filter((c) => typeof c === 'string' && c.length > 0);
        for (const candidate of /** @type {string[]} */ (candidates)) {
          try {
            await runProbe(candidate);
            return candidate;
          } catch {
            /* 试下一个 */
          }
        }
        return '';
      })();
    }
    return pythonProbe;
  }

  /** @param {string} command */
  function runProbe(command) {
    return new Promise((resolve, reject) => {
      // stdout/stdin 绝不继承（归宿主）；探测输出两边都不要。
      const child_ = spawn(command, ['-c', 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)'],
        { stdio: ['ignore', 'ignore', 'ignore'] });
      const timer = setTimeout(() => {
        try { child_.kill('SIGKILL'); } catch { /* 已退出 */ }
        reject(new Error('probe_timeout'));
      }, PYTHON_PROBE_TIMEOUT_MS);
      child_.on('error', (error) => { clearTimeout(timer); reject(error); });
      child_.on('exit', (code) => { clearTimeout(timer); (code === 0 ? resolve : reject)(undefined); });
    });
  }

  /**
   * 读引擎 stdout 的首行 listening JSON 握手（cli.py --json），拿到真实端口。
   * 超时或子进程先退 → 失败；其余 stdout 内容一律排掉（不归我们）。
   * @param {import('node:child_process').ChildProcess} c
   */
  function readHandshake(c) {
    return new Promise((resolve, reject) => {
      let buf = '';
      let tail = '';
      let settled = false;
      const timer = setTimeout(() => finish(new HttpError(503, 'engine_start_timeout', 'Python 引擎启动超时（20 秒内没等到就绪握手）')), ENGINE_START_TIMEOUT_MS);
      c.stderr?.setEncoding('utf8');
      c.stderr?.on('data', (chunk) => {
        for (const line of String(chunk).split('\n')) {
          const text = line.trim();
          if (!text) continue;
          tail = `${tail}\n${text}`.slice(-1600);
          log.info(`factscribe.engine: ${text.slice(0, 400)}`);
        }
      });
      c.stdout?.setEncoding('utf8');
      c.stdout?.on('data', (chunk) => {
        buf += String(chunk);
        const nl = buf.indexOf('\n');
        if (nl === -1) return;
        finish(null, buf.slice(0, nl).trim());
      });
      c.once('exit', (code, signal) => finish(new HttpError(503, 'engine_died', `Python 引擎启动即退（${signal || code}）。${tail.trim().slice(-400)}`)));
      /**
       * @param {null | HttpError} err
       * @param {string} [line]
       */
      function finish(err, line) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        c.stdout?.removeAllListeners('data');
        c.removeAllListeners('exit');
        c.stdout?.resume(); // 余下的 stdout 一律排掉，绝不堆积、绝不进宿主
        if (err) reject(err);
        else resolve(/** @type {string} */ (line));
      }
    });
  }

  /**
   * 拉起引擎（已在跑就先收掉旧的）。resolve 时引擎已在内部端口上就绪。
   * @param {string} root 论文根目录
   */
  async function start(root) {
    intentionalStop = false;
    lastFailure = '';
    const python = await findPython();
    if (!python) {
      failedAt = Date.now();
      lastFailure = '本机没有找到可用的 Python 3（需要 ≥3.10）。装一个 python3，或设环境变量 FS_PYTHON 指到你的 Python。';
      throw new HttpError(503, 'python_missing', lastFailure);
    }
    const c = spawn(python, ['-B', '-m', 'factscribe', 'workbench', '--root', root, '--port', '0', '--json', '--no-browser', '--state-dir', context.dataDir], {
      stdio: ['ignore', 'pipe', 'pipe'], // stdout 管道取握手行；绝不继承宿主 stdout
      env: {
        ...process.env,
        PYTHONPATH: engineDir + delimiter + (process.env.PYTHONPATH || ''),
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
        PYTHONDONTWRITEBYTECODE: '1', // 不往载荷里写 __pycache__（写盘只许 dataDir 与论文根）
      },
      cwd: context.dataDir, // 引擎不该依赖工作目录；放进宿主给的私有目录最保险
    });
    child = c;
    engineRoot = root;
    port = 0;
    log.info(`factscribe.engine.spawn root=${root.length} chars`);
    c.once('exit', (code, signal) => {
      if (child === c) {
        child = null;
        port = 0;
        if (!intentionalStop) log.warn(`factscribe.engine.exit ${signal || code}`);
      }
    });
    const line = await readHandshake(c);
    let realPort = 0;
    try {
      const handshake = JSON.parse(line);
      if (handshake?.event !== 'listening') throw new Error(`event=${handshake?.event}`);
      realPort = Number(new URL(String(handshake.url)).port);
    } catch {
      stop();
      failedAt = Date.now();
      lastFailure = 'Python 引擎握手行读不懂（不是预期的 listening JSON）。';
      throw new HttpError(503, 'engine_handshake_invalid', lastFailure);
    }
    if (!realPort) {
      stop();
      failedAt = Date.now();
      lastFailure = 'Python 引擎握手行里没有可用端口。';
      throw new HttpError(503, 'engine_handshake_invalid', lastFailure);
    }
    port = realPort;
    log.info(`factscribe.engine.ready port=${port}`);
  }

  /** 收尸：SIGTERM → 700ms 后还在就 SIGKILL；整体 ≤ 900ms。 */
  function stop() {
    const c = child;
    child = null;
    port = 0;
    if (!c) return Promise.resolve();
    intentionalStop = true;
    return new Promise((resolve) => {
      if (c.exitCode !== null || c.signalCode) return resolve();
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        resolve(undefined);
      };
      const killer = setTimeout(() => {
        try { c.kill('SIGKILL'); } catch { /* 已退出 */ }
      }, 700);
      c.once('exit', () => { clearTimeout(killer); finish(); });
      try { c.kill('SIGTERM'); } catch { clearTimeout(killer); finish(); }
      setTimeout(() => { clearTimeout(killer); finish(); }, 900);
    });
  }

  /** 引擎在跑就返回；没跑且配置了论文根就（重新）拉起。 */
  async function ensureReady() {
    if (child && port) return;
    if (starting) return starting;
    const configured = await readConfig(context.dataDir);
    if (!configured) {
      throw new HttpError(503, 'not_configured', '还没有配置论文根目录：请打开 FactScribe 工作台页面，完成一次首次设置。');
    }
    if (Date.now() - failedAt < 5000 && lastFailure) {
      throw new HttpError(503, 'engine_start_failed', lastFailure);
    }
    starting = start(configured).then(() => { failedAt = 0; }, (error) => {
      failedAt = Date.now();
      lastFailure = error?.userMessage || String(error);
      throw error;
    });
    try {
      await starting;
    } finally {
      starting = null;
    }
  }

  /** 换论文根：收旧的、起新的（设置页应用时走这里）。 */
  async function restart(root) {
    pythonProbe = null; // 用户可能刚装好 Python，重探
    await stop();
    await start(root);
  }

  return {
    ensureReady,
    restart,
    stop,
    /** 设置页诊断用：本机探到可用 Python（≥3.10）了吗（带缓存，探过即记）。 */
    pythonAvailable: async () => Boolean(await findPython()),
    /** @returns {number} 引擎端口（0＝没在跑） */
    get port() { return port; },
    /** @returns {string} 当前引擎的论文根 */
    get root() { return engineRoot; },
    get running() { return Boolean(child && port); },
  };
}

// ---------------------------------------------------------------- 引擎 HTTP 客户端（MCP 工具用）

/**
 * 对引擎内部端口发一个 POST（JSON 体），回解析好的 JSON。
 * 建提议单要用它（GET 不够）。语义与 engineGet 一致：非 200 或 ok=false → HttpError。
 * @param {number} port @param {string} path @param {object} body
 */
async function enginePost(port, path, body) {
  const payload = await new Promise((resolve, reject) => {
    const raw = Buffer.from(JSON.stringify(body ?? {}), 'utf8');
    const upstream = httpRequest({ host: '127.0.0.1', port, path, method: 'POST', headers: { 'content-type': 'application/json', 'content-length': String(raw.length), accept: 'application/json' } }, (res) => {
      const chunks = [];
      let size = 0;
      res.on('data', (chunk) => {
        size += chunk.length;
        if (size <= 8 * 1024 * 1024) chunks.push(chunk);
      });
      res.on('end', () => {
        let data = null;
        try {
          data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        } catch {
          /* 非 JSON 按空处理 */
        }
        resolve({ status: res.statusCode || 0, data });
      });
      res.on('error', reject);
    });
    upstream.on('error', (error) => reject(new HttpError(502, 'engine_unreachable', `引擎端口够不着（${error?.code || error}）`)));
    upstream.end(raw);
  });
  if (payload.status !== 200 || !payload.data || payload.data.ok === false) {
    const message = payload.data?.error || `引擎返回 HTTP ${payload.status}`;
    const codeName = typeof payload.data?.code === 'string' && payload.data.code
      ? payload.data.code
      : payload.status === 409 ? 'conflict'
        : payload.status === 404 ? 'not_found'
          : payload.status === 400 ? 'bad_request'
            : 'engine_error';
    throw new HttpError(payload.status === 200 ? 502 : payload.status, codeName, String(message));
  }
  return payload.data;
}

/**
 * 对引擎内部端口发一个 GET，回解析好的 JSON。非 200 或 ok=false → HttpError（带上人话）。
 * @param {number} port @param {string} pathWithQuery
 */
async function engineGet(port, pathWithQuery) {
  const payload = await new Promise((resolve, reject) => {
    const upstream = httpRequest({ host: '127.0.0.1', port, path: pathWithQuery, method: 'GET', headers: { accept: 'application/json' } }, (res) => {
      const chunks = [];
      let size = 0;
      res.on('data', (chunk) => {
        size += chunk.length;
        if (size <= 8 * 1024 * 1024) chunks.push(chunk);
      });
      res.on('end', () => {
        let data = null;
        try {
          data = JSON.parse(Buffer.concat(chunks).toString('utf8'));
        } catch {
          /* 非 JSON 按空处理 */
        }
        resolve({ status: res.statusCode || 0, data });
      });
      res.on('error', reject);
    });
    upstream.on('error', (error) => reject(new HttpError(502, 'engine_unreachable', `引擎端口够不着（${error?.code || error}）`)));
    upstream.end();
  });
  if (payload.status !== 200 || !payload.data || payload.data.ok === false) {
    const message = payload.data?.error || `引擎返回 HTTP ${payload.status}`;
    const codeName = typeof payload.data?.code === 'string' && payload.data.code
      ? payload.data.code
      : payload.status === 404 ? 'not_found'
        : payload.status === 400 ? 'bad_request'
          : payload.status === 409 ? 'conflict'
            : 'engine_error';
    throw new HttpError(payload.status === 200 ? 502 : payload.status, codeName, String(message));
  }
  return payload.data;
}

// ---------------------------------------------------------------- MCP 工具面（6 个，全部只读）

const READ_ANNOTATIONS = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false };

const PROJECT_DISK = {
  project: { type: 'string', minLength: 1, maxLength: 200, description: '项目 ID（先 fs_status 拿清单）' },
  disk: { type: 'string', minLength: 1, maxLength: 200, description: '稿盘 ID（同一项目的语言盘，如 paper / paper-zh）' },
};

const TRUNCATE_NOTE = '结果已截断；更多内容请在 FactScribe 工作台页面查看。';

/** @type {{name: string, title: string, description: string, inputSchema: any, annotations: Record<string, boolean>}[]} */
const TOOLS = [
  {
    name: 'fs_status',
    title: '稿况总览',
    description:
      '【只读】列出 FactScribe 工作台当前的论文项目清单与正在使用的论文根目录：每个项目带语言盘（稿盘）列表，' +
      '每盘带章节数、事实条数、写作进度。一切其他 fs_* 工具都要先从这里拿 project 与 disk 两个 ID。' +
      '改稿类工具 v1 没有（v2 以「提议-确认」方式提供）。',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
    annotations: READ_ANNOTATIONS,
  },
  {
    name: 'fs_get_outline',
    title: '看目录树',
    description:
      '【只读】看某个稿盘的目录树（标题级）：每节给出 id / 所在文件 / 级别 / 标题 / 指纹 sha。' +
      '标题级条目的 id 可以直接用于后续检索定位；要读正文用 fs_read_section（传 file 或 block）。',
    inputSchema: {
      type: 'object',
      properties: PROJECT_DISK,
      required: ['project', 'disk'],
      additionalProperties: false,
    },
    annotations: READ_ANNOTATIONS,
  },
  {
    name: 'fs_read_section',
    title: '读一段正文',
    description:
      '【只读】读稿盘里的一段（或一个文件的全部块）正文。block 与 file 二选一：' +
      '传 block＝单段（先 fs_get_outline 或按 file 读时拿到块 id）；传 file＝该文件全部块按顺序返回。' +
      '返回的 text 是该段 LaTeX 原文——页面上的保护芯片（\\fact{} / \\cite{} / 绑定数字）在这里还原为原始命令形态。' +
      '注意：\\fact{}、\\cite{} 与绑定数字是事实账锚点，任何改稿都不得动它们（v1 也没有改稿工具）。',
    inputSchema: {
      type: 'object',
      properties: {
        ...PROJECT_DISK,
        block: { type: 'string', maxLength: 200, description: '块 id（二选一；如 sec01-p3、cover-abstract）' },
        file: { type: 'string', maxLength: 300, description: 'sections/ 下的文件相对路径（二选一；如 sections/01_intro.tex）' },
      },
      required: ['project', 'disk'],
      additionalProperties: false,
    },
    annotations: READ_ANNOTATIONS,
  },
  {
    name: 'fs_get_report',
    title: '看检查报告',
    description:
      '【只读】看某个稿盘的最新检查报告（体检摘要＋发现清单＋声明→绑定→回账→出证四步链）。' +
      'health.status 为 red/yellow/ok；findings 里每条带 severity / code / message / location，' +
      '改稿建议要以报告读数为依据；报告本身不会因读它而变化。',
    inputSchema: {
      type: 'object',
      properties: PROJECT_DISK,
      required: ['project', 'disk'],
      additionalProperties: false,
    },
    annotations: READ_ANNOTATIONS,
  },
  {
    name: 'fs_query_facts',
    title: '查事实账本',
    description:
      '【只读】查某个稿盘的事实账本（facts/*.toml 聚合出的账本表）：每条带 id / 主张 / 绑定值 / 置信度 / 来源文件与定位 / 指纹。' +
      '正文里的数字凡带 \\fact{} 就绑定到这里的 value——写任何涉及数字的内容前先来这里对账，' +
      '账上没有的数字不得编造。可选 query 按子串过滤（对 id / 主张 / 值 / 来源文件）。',
    inputSchema: {
      type: 'object',
      properties: {
        ...PROJECT_DISK,
        query: { type: 'string', maxLength: 200, description: '可选：子串过滤（大小写不敏感，对 id/主张/值/来源文件匹配）' },
      },
      required: ['project', 'disk'],
      additionalProperties: false,
    },
    annotations: READ_ANNOTATIONS,
  },
  {
    name: 'fs_search_kb',
    title: '搜知识库',
    description:
      '【只读】搜项目知识库。不传 path＝列文件清单（可选 query 按文件名/路径子串过滤）；' +
      '传 path＝返回该文件的可读文本预览（文本类直接读，PDF 只登记不提取）。',
    inputSchema: {
      type: 'object',
      properties: {
        ...PROJECT_DISK,
        query: { type: 'string', maxLength: 200, description: '可选：文件名/路径子串过滤' },
        path: { type: 'string', maxLength: 300, description: '可选：要读的文件相对路径（项目目录内；给了就返回文本预览）' },
      },
      required: ['project', 'disk'],
      additionalProperties: false,
    },
    annotations: READ_ANNOTATIONS,
  },
  {
    name: 'fs_propose_edit',
    title: '提议改稿（待人确认）',
    description:
      '【提议，不写盘】把一段改稿提成一**张提议单**：落宿主私有目录，**不碰正文**。' +
      '人在页面的「待确认」差异卡里看到改前/改后，由人点「采纳写回」才真正落盘；不采纳就什么都不写。' +
      'block 传段 id（先 fs_get_outline 或 fs_read_section 拿），text 是该段的完整替换 LaTeX。' +
      '铁律：不得凭空造 \\fact{} / \\cite{} 与账上没有的数字——写之前先 fs_query_facts 对账。',
    inputSchema: {
      type: 'object',
      properties: {
        ...PROJECT_DISK,
        block: { type: 'string', maxLength: 200, description: '要改的段 id（如 01-intro-s1）' },
        text: { type: 'string', maxLength: 8000, description: '该段的完整替换 LaTeX（不含 \\fact{} / \\cite{} 等保护面命令）' },
        rationale: { type: 'string', maxLength: 500, description: '可选：为什么这么改（给人看的）' },
      },
      required: ['project', 'disk', 'block', 'text'],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: false, destructiveHint: false, idempotentHint: false, openWorldHint: false },
  },
  {
    name: 'fs_list_proposals',
    title: '看待确认的提议单',
    description:
      '【只读】列当前待人确认的提议单：每条带 id、目标段、改前/改后、警告与理由。' +
      '用 fs_propose_edit 建单后用它核对；真正的采纳由人在页面点，助手这边没有写入接口。',
    inputSchema: {
      type: 'object',
      properties: { ...PROJECT_DISK },
      required: ['project', 'disk'],
      additionalProperties: false,
    },
    annotations: READ_ANNOTATIONS,
  },
];

const TOOLS_BY_NAME = new Map(TOOLS.map((t) => [t.name, t]));

const INSTRUCTIONS = [
  'FactScribe 论文工作台（本机论文写作工具）的只读检索面：查稿况 → 看目录 → 读正文 → 看检查报告 → 对事实账 → 搜知识库。',
  '典型顺序：fs_status 拿项目与稿盘 ID → fs_get_outline 看目录 → fs_read_section 读某文件/某段 → fs_get_report 看体检 → fs_query_facts 对数字与引用的账 → fs_search_kb 翻项目资料。',
  '铁律：正文里 \\fact{}、\\cite{} 与绑定数字是事实账锚点；账上没有的数字与文献不得编造；涉及数字的论述先 fs_query_facts 对账。',
  'v1 的六个检索工具全部只读；v2 加了写稿面，但只有「提议」：fs_propose_edit 建一张提议单（不写盘），由人在页面的「待确认」差异卡里点「采纳写回」才落盘。助手这边没有任何直接改正文的接口。',
  '工具结果设了长度上限，超限会带 truncated 标记——需要更多请让用户打开 FactScribe 工作台页面查看。',
].join('\n');

/**
 * 组装 MCP 的 tools/call 分发服务（每个工具＝转发引擎既有 GET 端点＋整形＋截断）。
 * @param {(pathWithQuery: string) => Promise<any>} get 引擎 GET 客户端
 * @param {(path: string, body: object) => Promise<any>} post 引擎 POST 客户端
 */
function createToolService(get, post) {
  /** @param {string} s @param {number} max */
  const cap = (s, max) => {
    const text = String(s ?? '');
    return text.length > max ? { text: text.slice(0, max), truncated: true } : { text, truncated: false };
  };

  return {
    /** fs_status */
    async status() {
      const data = await get('/api/projects');
      const projects = /** @type {any[]} */ (data.projects || []).map((p) => ({
        id: p.id,
        name: p.name,
        root: p.root,
        langs: p.langs,
        multi_lang: Boolean(p.multi_lang),
        disks: /** @type {any[]} */ (p.disks || []).map((d) => ({
          id: d.id,
          lang: d.lang,
          name: d.name,
          subtitle: d.subtitle || '',
          sections: d.sections,
          facts: d.facts,
          progress: d.progress,
          last_opened: d.last_opened || '',
        })),
      }));
      return { root: data.root, count: data.count, projects, note: '后续 fs_* 工具都要传这里拿到的 project 与 disk。' };
    },

    /** fs_get_outline */
    async outline(args) {
      const { project, disk } = args;
      const data = await get(`/api/disk/${encodeURIComponent(project)}/${encodeURIComponent(disk)}/sections`);
      const all = /** @type {any[]} */ (data.blocks || []);
      const entries = all
        .filter((b) => b.kind !== 'para' && b.kind !== 'ai_draft')
        .map((b) => ({ id: b.id, file: b.file, kind: b.kind, level: b.level, title: b.title || '', title_en: b.title_en || '', sha: b.sha }));
      const truncated = entries.length > 400;
      const out = {
        project, disk,
        lang: data.lang || '',
        total_blocks: data.count || all.length,
        entry_count: entries.length,
        entries: truncated ? entries.slice(0, 400) : entries,
        hint: '段落级正文用 fs_read_section（传 file 或 block）读取。',
      };
      if (truncated) {
        out.truncated = true;
        out.note = TRUNCATE_NOTE;
      }
      return out;
    },

    /** fs_read_section */
    async readSection(args) {
      const { project, disk, block, file } = args;
      if (block && file) {
        throw new HttpError(400, 'invalid_arguments', 'block 与 file 二选一。');
      }
      if (block) {
        const data = await get(`/api/disk/${encodeURIComponent(project)}/${encodeURIComponent(disk)}/block/${encodeURIComponent(block)}`);
        const capped = cap(data.raw, 8000);
        const out = {
          project, disk,
          id: data.id, file: data.file, kind: data.kind, title: data.title || '',
          sha: data.sha,
          text: capped.text,
          note: 'text 为该段 LaTeX 原文：\\fact{} / \\cite{} / 绑定数字保持原始命令形态（页面上的芯片由它们渲染），改稿不得动它们。',
        };
        if (capped.truncated) {
          out.truncated = true;
          out.note += TRUNCATE_NOTE;
        }
        return out;
      }
      if (file) {
        const data = await get(`/api/disk/${encodeURIComponent(project)}/${encodeURIComponent(disk)}/sections`);
        const blocks = /** @type {any[]} */ (data.blocks || []).filter((b) => b.file === file);
        if (!blocks.length) {
          throw new HttpError(404, 'no_such_file', `这个盘上没有叫 ${file} 的正文文件（先 fs_get_outline 对一眼）。`);
        }
        let budget = 24000;
        let truncated = false;
        const items = [];
        for (const b of blocks) {
          const room = Math.min(8000, budget);
          if (room <= 0) {
            truncated = true;
            break;
          }
          const capped = cap(b.raw, room);
          budget -= capped.text.length;
          if (capped.truncated) truncated = true;
          items.push({ id: b.id, kind: b.kind, title: b.title || '', sha: b.sha, text: capped.text });
        }
        const out = { project, disk, file, block_count: blocks.length, blocks: items };
        if (truncated) {
          out.truncated = true;
          out.note = TRUNCATE_NOTE;
        }
        return out;
      }
      throw new HttpError(400, 'invalid_arguments', 'block 与 file 至少给一个（二选一）。');
    },

    /** fs_get_report */
    async report(args) {
      const { project, disk } = args;
      const data = await get(`/api/disk/${encodeURIComponent(project)}/${encodeURIComponent(disk)}/report`);
      const health = data.health || {};
      const findings = /** @type {any[]} */ (data.findings || []);
      const truncated = findings.length > 40;
      const out = {
        project, disk,
        generated_at: data.generated_at || '',
        health: {
          status: health.status,
          red: health.red, yellow: health.yellow, hints: health.hints,
          facts: health.facts, sections: health.sections,
          digest_short: health.digest_short || '',
          numbers: health.numbers || {},
          citations: health.citations || {},
          bib_unused: (health.bib_unused || []).slice(0, 20),
        },
        finding_count: findings.length,
        findings: (truncated ? findings.slice(0, 40) : findings).map((f) => ({
          severity: f.severity, code: f.code, message: f.message, location: f.location || '',
        })),
        chain: data.chain || [],
        evidence: data.evidence || {},
      };
      if (truncated) {
        out.truncated = true;
        out.note = TRUNCATE_NOTE;
      }
      return out;
    },

    /** fs_query_facts */
    async facts(args) {
      const { project, disk } = args;
      const query = String(args.query || '').trim().toLowerCase();
      const data = await get(`/api/disk/${encodeURIComponent(project)}/${encodeURIComponent(disk)}/machine`);
      const ledger = data.groups?.ledger || {};
      const all = /** @type {any[]} */ (ledger.rows || []);
      const filtered = query
        ? all.filter((r) => `${r.id} ${r.claim} ${r.value} ${r.source_file}`.toLowerCase().includes(query))
        : all;
      const truncated = filtered.length > 100;
      const rows = (truncated ? filtered.slice(0, 100) : filtered).map((r) => ({
        id: r.id, claim: r.claim || '', value: r.value || '',
        confidence: r.confidence || '', kind: r.kind || 'claim',
        source_file: r.source_file || '', locator: r.locator || '',
        file: r.file || '', line: r.line || 0, fp_short: r.fp_short || '',
      }));
      const out = {
        project, disk,
        ledger_total: ledger.total ?? all.length,
        digest_short: ledger.digest_short || '',
        selected: rows.length,
        query: query || undefined,
        rows,
      };
      if (truncated) {
        out.truncated = true;
        out.note = TRUNCATE_NOTE;
      }
      return out;
    },

    /** fs_search_kb */
    async searchKb(args) {
      const { project, disk } = args;
      const query = String(args.query || '').trim().toLowerCase();
      const path = String(args.path || '').trim();
      if (path) {
        const data = await get(`/api/project/${encodeURIComponent(project)}/knowledge/preview?path=${encodeURIComponent(path)}`);
        const capped = cap(data.text, 4000);
        const out = {
          project,
          name: data.name, path: data.path, ext: data.ext,
          size_label: data.size_label || '', sha256: data.sha256 || '',
          status: data.status, status_label: data.status_label || '',
          text: capped.text,
          note: data.note || '',
        };
        if (capped.truncated || data.truncated) {
          out.truncated = true;
          out.note = (out.note ? `${out.note} ` : '') + TRUNCATE_NOTE;
        }
        return out;
      }
      const data = await get(`/api/project/${encodeURIComponent(project)}/knowledge`);
      const all = /** @type {any[]} */ (data.files || []);
      const filtered = query
        ? all.filter((f) => `${f.name} ${f.path} ${f.ext}`.toLowerCase().includes(query))
        : all;
      const truncated = filtered.length > 50;
      const out = {
        project,
        dir: data.dir || '',
        count: data.count ?? all.length,
        selected: filtered.length,
        query: query || undefined,
        files: (truncated ? filtered.slice(0, 50) : filtered).map((f) => ({
          name: f.name, path: f.path, size_label: f.size_label || '', ext: f.ext,
          status: f.status, status_label: f.status_label || '', in_knowledge: Boolean(f.in_knowledge),
        })),
        hint: '看某个文件的内容：再调一次并传 path。',
      };
      if (truncated) {
        out.truncated = true;
        out.note = TRUNCATE_NOTE;
      }
      return out;
    },

    /** fs_propose_edit —— 只建单，不写盘 */
    async proposeEdit(args) {
      const { project, disk, block, text, rationale } = args;
      const base = `/api/disk/${encodeURIComponent(project)}/${encodeURIComponent(disk)}`;
      // 先读这一段的现状（拿文件路径与指纹）：提议要基于一份确定的原文。
      const current = await get(`${base}/block/${encodeURIComponent(block)}`);
      const data = await post(`${base}/proposal`, {
        kind: 'block_edit',
        file: current.file,
        block,
        text,
        expect_sha: current.sha || '',
        source: 'mcp',
        rationale: rationale || '',
      });
      const proposal = data.proposal || {};
      const before = cap(proposal.before_text, 2000);
      const after = cap(proposal.after_text, 2000);
      return {
        project, disk,
        id: proposal.id || '',
        kind: proposal.kind || 'block_edit',
        file: proposal.file || current.file,
        block: proposal.block || block,
        before_sha: proposal.before_sha || '',
        before_text: before.text,
        after_text: after.text,
        warnings: proposal.warnings || [],
        rationale: proposal.rationale || '',
        status: proposal.status || 'pending',
        note: '这是一张提议单，**正文还没动**。请用户在 FactScribe 工作台的「待确认」差异卡里看过再采纳——不采纳就什么都不写。',
      };
    },

    /** fs_list_proposals —— 只读 */
    async listProposals(args) {
      const { project, disk } = args;
      const data = await get(`/api/disk/${encodeURIComponent(project)}/${encodeURIComponent(disk)}/proposal`);
      const rows = /** @type {any[]} */ (data.proposals || []);
      const truncated = rows.length > 20;
      const items = (truncated ? rows.slice(0, 20) : rows).map((p) => ({
        id: p.id,
        kind: p.kind,
        file: p.file,
        block: p.block,
        rationale: p.rationale || '',
        created_at: p.created_at || '',
        status: p.status,
        warnings: p.warnings || [],
        before_text: cap(p.before_text, 1200).text,
        after_text: cap(p.after_text, 1200).text,
      }));
      const out = {
        project, disk,
        count: data.count ?? rows.length,
        proposals: items,
        note: '真正的采纳由人在页面点「采纳写回」；助手这边没有写入接口。',
      };
      if (truncated) {
        out.truncated = true;
        out.note += TRUNCATE_NOTE;
      }
      return out;
    },
  };
}

// ---------------------------------------------------------------- MCP 协议层（streamable-http，JSON 应答）

/**
 * @typedef {ReturnType<typeof createToolService>} ToolService
 */

/**
 * 组装 MCP 请求处理器（照 cq-viewer 的零依赖手写形）。
 * @param {ToolService} services
 * @param {(message: string) => void} log
 */
function createMcpHandler(services, log) {
  /** @param {any} message */
  const handleMessage = async (message) => {
    if (!message || typeof message !== 'object' || Array.isArray(message)) {
      return rpcError(null, -32600, 'Invalid Request');
    }
    if (message.id === undefined || message.id === null) return null; // notification / response：无应答
    const id = message.id;
    switch (message.method) {
      case 'initialize':
        return {
          jsonrpc: '2.0',
          id,
          result: {
            protocolVersion: typeof message.params?.protocolVersion === 'string' ? message.params.protocolVersion : '2025-06-18',
            capabilities: { tools: { listChanged: false } },
            serverInfo: SERVER_INFO,
            instructions: INSTRUCTIONS,
          },
        };
      case 'ping':
        return { jsonrpc: '2.0', id, result: {} };
      case 'tools/list':
        return { jsonrpc: '2.0', id, result: { tools: TOOLS } };
      case 'tools/call': {
        const name = message.params?.name;
        const tool = typeof name === 'string' ? TOOLS_BY_NAME.get(name) : undefined;
        if (!tool) return rpcError(id, -32602, `Unknown tool: ${typeof name === 'string' ? name : '(missing)'}`);
        const args = message.params?.arguments ?? {};
        const issues = validate(tool.inputSchema, args, 'arguments');
        if (issues.length) {
          return result(id, failure('invalid_arguments', `参数不正确：${issues.join('；')}`));
        }
        log(`factscribe.mcp.call ${tool.name}`);
        try {
          const data = await dispatch(services, tool.name, args);
          return result(id, success(data));
        } catch (error) {
          const e = /** @type {any} */ (error);
          const known = e instanceof HttpError;
          return result(id, failure(known ? e.code : 'internal_error', known ? e.userMessage : '工作台内部出错，请重试'));
        }
      }
      default:
        return rpcError(id, -32601, `Method not found: ${String(message.method)}`);
    }
  };

  /** @param {unknown} body */
  return async (body) => {
    if (Array.isArray(body)) {
      if (body.length === 0) return rpcError(null, -32600, 'Invalid Request');
      /** @type {any[]} */
      const replies = [];
      for (const m of body) {
        const r = await handleMessage(m);
        if (r) replies.push(r);
      }
      return replies.length ? replies : null;
    }
    return handleMessage(body);
  };
}

/** @param {any} id @param {any} payload */
function result(id, payload) {
  return { jsonrpc: '2.0', id, result: payload };
}

/** @param {Record<string, unknown>} data */
function success(data) {
  const structuredContent = { ok: true, ...data };
  return { content: [{ type: 'text', text: JSON.stringify(structuredContent, null, 2) }], structuredContent };
}

/** @param {string} code @param {string} message */
function failure(code, message) {
  const structuredContent = { ok: false, error: { code, message } };
  return { isError: true, content: [{ type: 'text', text: JSON.stringify(structuredContent, null, 2) }], structuredContent };
}

/** @param {unknown} id @param {number} code @param {string} message */
function rpcError(id, code, message) {
  return { jsonrpc: '2.0', id: id ?? null, error: { code, message } };
}

/** @param {ToolService} services @param {string} name @param {any} args */
function dispatch(services, name, args) {
  switch (name) {
    case 'fs_status': return services.status();
    case 'fs_get_outline': return services.outline(args);
    case 'fs_read_section': return services.readSection(args);
    case 'fs_get_report': return services.report(args);
    case 'fs_query_facts': return services.facts(args);
    case 'fs_search_kb': return services.searchKb(args);
    case 'fs_propose_edit': return services.proposeEdit(args);
    case 'fs_list_proposals': return services.listProposals(args);
    default: throw new Error('unreachable');
  }
}

/**
 * 工具入参的最小 JSON Schema 校验（照 cq-viewer 的子集实现形）。
 * @param {any} schema @param {unknown} value @param {string} path
 * @returns {string[]}
 */
export function validate(schema, value, path) {
  /** @type {string[]} */
  const issues = [];
  const types = schema.type === undefined ? [] : Array.isArray(schema.type) ? schema.type : [schema.type];
  if (types.length && !types.some((t) => isType(t, value))) {
    issues.push(`${path} 应为 ${types.join(' 或 ')}`);
    return issues;
  }
  if (typeof value === 'string') {
    if (schema.minLength !== undefined && value.length < schema.minLength) issues.push(`${path} 不能为空`);
    if (schema.maxLength !== undefined && value.length > schema.maxLength) issues.push(`${path} 太长`);
    if (schema.pattern !== undefined && !new RegExp(schema.pattern).test(value)) issues.push(`${path} 格式不对`);
  }
  if (isType('object', value)) {
    const obj = /** @type {Record<string, unknown>} */ (value);
    const props = schema.properties ?? {};
    for (const req of schema.required ?? []) if (!Object.hasOwn(obj, req)) issues.push(`缺少 ${path}.${req}`);
    for (const [k, v] of Object.entries(obj)) {
      if (props[k]) issues.push(...validate(props[k], v, `${path}.${k}`));
      else if (schema.additionalProperties === false) issues.push(`${path}.${k} 不是可用参数`);
    }
  }
  return issues;
}

/** @param {string} type @param {unknown} value */
function isType(type, value) {
  switch (type) {
    case 'object':
      return value !== null && typeof value === 'object' && !Array.isArray(value);
    case 'number':
      return typeof value === 'number' && Number.isFinite(value);
    case 'integer':
      return Number.isInteger(value);
    case 'array':
      return Array.isArray(value);
    default:
      return typeof value === type;
  }
}

// ---------------------------------------------------------------- 入口

/** @typedef {{debug: (message: string, fields?: Record<string, string>) => void, info: (message: string, fields?: Record<string, string>) => void, warn: (message: string, fields?: Record<string, string>) => void, error: (message: string, fields?: Record<string, string>) => void}} Logger */

/**
 * MiniApp 入口：装完全部路由、listen 成功后才 resolve；返回 { dispose }。
 * @param {{ pluginId: string, pluginRoot: string, dataDir: string, listen: { host: string, port: number }, signal: AbortSignal, logger: Logger }} context
 * @returns {Promise<{ dispose: () => Promise<void> }>}
 */
export async function start(context) {
  const log = context.logger;
  const clientRoot = join(context.pluginRoot, CLIENT_DIR);

  const engine = createEngine({ context, log });

  // 页面与 MCP 工具共用的引擎 GET 客户端（先确保引擎在跑，再发请求）。
  const toolService = createToolService(
    async (pathWithQuery) => {
      await engine.ensureReady();
      return engineGet(engine.port, pathWithQuery);
    },
    async (path, body) => {
      await engine.ensureReady();
      return enginePost(engine.port, path, body);
    },
  );
  const handleMcp = createMcpHandler(toolService, (message) => log.info(message));

  /** @type {Map<string, string>} */
  const pageCache = new Map();
  async function setupPage() {
    const key = 'setup';
    if (pageCache.has(key)) return /** @type {string} */ (pageCache.get(key));
    const configured = await readConfig(context.dataDir);
    /** @type {string[]} */
    const warnings = [];
    if (configured) {
      warnings.push(`已保存的路径（${configured}）在这台机器上不存在或不是文件夹，请改一个真实的目录。`);
    }
    let pythonOk = false;
    try {
      pythonOk = await engine.pythonAvailable();
    } catch {
      pythonOk = false;
    }
    if (!pythonOk) warnings.push('没找到 python3：FactScribe 的引擎是 Python 写的，装好 Python ≥3.10 再来。');
    const html = setupPageHtml(configured, warnings);
    pageCache.set(key, html);
    return html;
  }

  /**
   * 反向代理：页面同源请求 /api/* 透传给 Python 引擎内部端口（只回环）。
   * @param {import('node:http').IncomingMessage} request
   * @param {import('node:http').ServerResponse} response
   */
  async function proxyApi(request, response) {
    await engine.ensureReady();
    const target = engine.port;
    const headers = { ...request.headers };
    delete headers.host;
    const upstream = httpRequest(
      { host: '127.0.0.1', port: target, path: request.url || '/api/', method: request.method, headers },
      (res) => {
        response.writeHead(res.statusCode || 502, res.headers);
        res.pipe(response);
      },
    );
    upstream.on('error', (error) => {
      if (!response.headersSent) {
        sendJson(response, 502, { ok: false, error: `引擎没应答（${error?.code || error}），稍后重试或回设置页检查。`, code: 502 });
      } else {
        response.destroy();
      }
    });
    response.on('close', () => upstream.destroy());
    request.on('error', () => upstream.destroy());
    request.pipe(upstream);
  }

  /**
   * 静态页面：client/ 三件套，防路径越界。
   * @param {import('node:http').ServerResponse} response
   * @param {string} rel
   */
  async function serveStatic(response, rel) {
    if (!/^[\w.-]+$/.test(rel) || rel.includes('..')) {
      return sendJson(response, 403, { ok: false, error: '路径越界', code: 403 });
    }
    const target = join(clientRoot, rel);
    const resolved = resolvePath(target);
    if (resolved !== clientRoot && !resolved.startsWith(clientRoot + sep)) {
      return sendJson(response, 403, { ok: false, error: '路径越界', code: 403 });
    }
    let body;
    try {
      body = await fs.readFile(resolved);
    } catch {
      return sendJson(response, 404, { ok: false, error: `没有这个文件：${rel}`, code: 404 });
    }
    response.writeHead(200, {
      'content-type': STATIC_TYPES[resolved.slice(resolved.lastIndexOf('.'))] || 'application/octet-stream',
      'cache-control': 'no-cache',
    });
    response.end(body);
  }

  const server = createServer((request, response) => {
    void handle(request, response);
  });

  async function handle(request, response) {
    const url = new URL(request.url ?? '/', 'http://miniapp.local');
    const path = url.pathname;
    const method = request.method ?? 'GET';

    // 每条路由先过回环守卫。
    if (!isLoopbackRequest(request, context.listen.port)) {
      return sendJson(response, 403, { ok: false, error: 'forbidden', code: 403 });
    }

    // MCP：宿主的 MCP 客户端走回环 POST（Streamable HTTP）。
    if (path === MCP_PATH) {
      if (method !== 'POST') {
        response.writeHead(405, { allow: 'POST', 'content-type': 'application/json; charset=utf-8' });
        response.end(JSON.stringify({ error: 'method_not_allowed' }));
        return;
      }
      let body;
      try {
        const raw = await readRawBody(request, MAX_BODY_BYTES);
        body = raw.length ? JSON.parse(raw.toString('utf8')) : undefined;
      } catch {
        return sendJson(response, 400, { error: 'invalid_json' });
      }
      const reply = await handleMcp(body);
      if (reply === null) {
        response.writeHead(202);
        response.end();
        return;
      }
      return sendJson(response, 200, reply);
    }

    // 首次设置：未配置论文根（或配置的目录不在了）→ 页面路由伺服设置页。
    const configured = await readConfig(context.dataDir);
    const configuredOk = Boolean(configured) && (await isDir(configured));
    if (!configuredOk && (method === 'GET' || method === 'HEAD') && (path === SURFACE_PATH || path === '/' || path === '/index.html')) {
      const html = await setupPage();
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
      response.end(html);
      return;
    }

    // 设置收表：写配置（原子写）→ 换根重启引擎 → 页面 reload 回工作台。
    if (method === 'POST' && path === SETUP_PATHS.api) {
      let body;
      try {
        body = /** @type {any} */ (await readJsonBody(request));
      } catch (error) {
        const e = /** @type {HttpError} */ (error);
        return sendJson(response, e.status, { ok: false, error: e.userMessage, code: e.status });
      }
      let root = '';
      try {
        root = expandRoot(body?.root);
      } catch {
        root = '';
      }
      if (!root || !(await isDir(root))) {
        return sendJson(response, 400, { ok: false, error: '这个目录不存在或不是文件夹，请填一个真实路径。' });
      }
      await writeConfig(context.dataDir, root);
      /** @type {string | undefined} */
      let warning;
      try {
        await engine.restart(root);
      } catch (error) {
        warning = /** @type {HttpError} */ (error)?.userMessage || String(error);
      }
      return sendJson(response, 200, warning ? { ok: true, warning } : { ok: true });
    }

    // 工作台页面与静态三件套（由 Node 直接伺服，与引擎无关）。
    if ((method === 'GET' || method === 'HEAD') && (path === SURFACE_PATH || path === '/' || path === '/index.html')) {
      const index = resolvePath(join(clientRoot, 'index.html'));
      const body = await fs.readFile(index);
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-cache' });
      response.end(body);
      return;
    }
    if ((method === 'GET' || method === 'HEAD') && path.startsWith('/static/')) {
      return serveStatic(response, path.slice('/static/'.length));
    }

    // 业务请求：全部透传 Python 引擎（设置接口除外，上面已收）。
    if (path === '/api' || path.startsWith('/api/')) {
      try {
        return await proxyApi(request, response);
      } catch (error) {
        const e = /** @type {HttpError} */ (error);
        const status = typeof e?.status === 'number' ? e.status : 502;
        return sendJson(response, status, { ok: false, error: e?.userMessage || '引擎暂不可用', code: status });
      }
    }

    return sendJson(response, 404, { ok: false, error: 'not_found', code: 404 });
  }

  await listen(server, context.listen.host, context.listen.port);
  log.info('factscribe.listening');

  let disposed = false;
  const dispose = async () => {
    if (disposed) return;
    disposed = true;
    context.signal.removeEventListener('abort', onAbort);
    server.closeAllConnections?.();
    server.closeIdleConnections?.();
    await Promise.race([close(server), delay(400)]);
    await engine.stop(); // 宿主只停 Node；Python 子进程必须亲手收
  };
  const onAbort = () => {
    void dispose();
  };
  context.signal.addEventListener('abort', onAbort, { once: true });
  if (context.signal.aborted) await dispose();

  return { dispose };
}

/** @param {string} path */
async function isDir(path) {
  try {
    return (await fs.stat(path)).isDirectory();
  } catch {
    return false;
  }
}

/**
 * 读取原始请求体（MCP 用：宿主客户端的 Content-Type 不一定带 application/json）。
 * @param {import('node:http').IncomingMessage} request
 * @param {number} maxBytes
 */
function readRawBody(request, maxBytes) {
  return new Promise((resolve, reject) => {
    let size = 0;
    let tooLarge = false;
    /** @type {Buffer[]} */
    const chunks = [];
    request.on('data', (chunk) => {
      if (tooLarge) return;
      size += chunk.length;
      if (size > maxBytes) {
        tooLarge = true;
        chunks.length = 0;
        reject(new HttpError(413, 'body_too_large', '请求体太大'));
        return;
      }
      chunks.push(chunk);
    });
    request.on('end', () => {
      if (!tooLarge) resolve(Buffer.concat(chunks));
    });
    request.on('error', reject);
  });
}
