// 一键启动本地工作台：固定命令、不经过 shell、首行 JSON 握手。
//
// 只允许这两种形状（参数顺序固定，项目路径单独作为位置参数）：
//   <python> -m factscribe serve <项目> --port 0 --json [--allow-write] [--allow-build]
//   factscribe serve <项目> --port 0 --json [--allow-write] [--allow-build]
// 页面传来的任何字段都不会变成命令、管道或环境变量。

import { spawn } from 'node:child_process';
import { delimiter } from 'node:path';
import { createInterface } from 'node:readline';

export const START_TIMEOUT_MS = 20000;
export const STOP_GRACE_MS = 3000;
export const DEFAULT_PYTHON = 'python3';

/** 固定参数；顺序即契约。 */
export function serveArgs({ project, allowWrite = false, allowBuild = false }) {
  const args = ['serve', project, '--port', '0', '--json'];
  if (allowWrite) args.push('--allow-write');
  if (allowBuild) args.push('--allow-build');
  return args;
}

export function pythonFrom(env = process.env) {
  const raw = String(env.FACTSCRIBE_PYTHON ?? '').trim();
  return raw || DEFAULT_PYTHON;
}

function attempts(python) {
  return [
    { cmd: python, prefix: ['-m', 'factscribe'], label: python + ' -m factscribe' },
    { cmd: 'factscribe', prefix: [], label: 'factscribe' },
  ];
}

/**
 * 启动并等首行 JSON。成功返回 { url, token, project, pid, child, command }。
 * 失败抛错，错误里带 stderr 尾巴（原样给用户看）。
 */
export async function startServe(options) {
  const {
    project,
    allowWrite = false,
    allowBuild = false,
    python = pythonFrom(),
    pythonPath = '',
    timeoutMs = START_TIMEOUT_MS,
  } = options || {};
  if (!project) throw new Error('缺少项目文件夹');
  const failures = [];
  for (const attempt of attempts(python)) {
    try {
      return await spawnAndHandshake(attempt, { project, allowWrite, allowBuild, pythonPath, timeoutMs });
    } catch (err) {
      failures.push({ label: attempt.label, error: err });
      // 只有「解释器/模块找不到」才换下一个形状；其它错误说明命令真跑过并失败了
      if (!err.retryable) break;
    }
  }
  const detail = failures.map((f) => f.error.message).join('\n');
  const first = failures[0]?.label || python;
  throw new Error(
    '启动工作台失败（先试 ' + first + '）：\n' + detail +
    '\n提示：需要能 import factscribe 的 Python（pip install factscribe 或用装好它的解释器），' +
    '也可以在 ~/.factscribe/projects.json 里填 python 路径，或设环境变量 FACTSCRIBE_PYTHON。'
  );
}

function spawnAndHandshake(attempt, { project, allowWrite, allowBuild, pythonPath, timeoutMs }) {
  return new Promise((resolvePromise, rejectPromise) => {
    const args = [...attempt.prefix, ...serveArgs({ project, allowWrite, allowBuild })];
    let child;
    try {
      child = spawn(attempt.cmd, args, {
        cwd: project,
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: false,
        env: { ...process.env, ...childPythonPath(pythonPath) },
      });
    } catch (err) {
      rejectPromise(markRetryable(err));
      return;
    }

    let settled = false;
    let stderr = '';
    let stdoutTail = '';
    let lines = null;
    const timer = setTimeout(() => {
      finish(new Error('工作台 ' + Math.round(timeoutMs / 1000) + ' 秒内没有报出监听地址' + tail()));
    }, timeoutMs);

    function tail() {
      const text = (stderr || stdoutTail).trim().split('\n').slice(-8).join('\n');
      return text ? '\n' + text : '';
    }

    function cleanup() {
      clearTimeout(timer);
      lines?.close?.();
    }

    function finish(err, value) {
      if (settled) return;
      settled = true;
      cleanup();
      if (err) {
        // 握手失败不能留一个后台进程继续占着端口
        try {
          child.kill('SIGKILL');
        } catch {
          // 已经退出
        }
        rejectPromise(err);
      } else {
        resolvePromise(value);
      }
    }

    const lines2 = createInterface({ input: child.stdout });
    lines = lines2;
    lines2.on('line', (line) => {
      const text = String(line ?? '').trim();
      if (!text) return;
      if (!text.startsWith('{')) {
        stdoutTail = (stdoutTail + '\n' + text).slice(-4000);
        return;
      }
      let payload;
      try {
        payload = JSON.parse(text);
      } catch {
        stdoutTail = (stdoutTail + '\n' + text).slice(-4000);
        return;
      }
      if (payload?.event !== 'listening' || !payload?.url || !payload?.token) return;
      finish(null, {
        url: String(payload.url),
        token: String(payload.token),
        project: String(payload.project || project),
        command: attempt.label,
        child,
        pid: child.pid,
      });
    });

    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => {
      stderr = (stderr + chunk).slice(-8000);
    });

    child.once('error', (err) => {
      finish(markRetryable(err));
    });

    child.once('exit', (code, signal) => {
      if (settled) return;
      const reason = signal ? '被信号 ' + signal + ' 结束' : '退出码 ' + code;
      const err = new Error('工作台启动后立即结束（' + reason + '）' + tail());
      err.retryable = /No module named ['"]?factscribe|ModuleNotFoundError/.test(stderr);
      finish(err);
    });
  });
}

/** 显式给的包路径拼到 PYTHONPATH 前面；空值不动环境。 */
export function childPythonPath(pythonPath, base = process.env.PYTHONPATH) {
  const extra = String(pythonPath ?? '').trim();
  if (!extra) return {};
  const parts = extra.split(delimiter).map((s) => s.trim()).filter(Boolean);
  if (!parts.length) return {};
  return { PYTHONPATH: [parts.join(delimiter), base].filter(Boolean).join(delimiter) };
}

function markRetryable(err) {
  const code = err && err.code;
  err.retryable = code === 'ENOENT' || /No module named|ModuleNotFoundError/.test(String(err.message));
  return err;
}

/** 停掉子进程：先 SIGTERM，宽限后 SIGKILL；子进程已退出则直接返回。 */
export function stopServe(child, { graceMs = STOP_GRACE_MS } = {}) {
  if (!child || child.exitCode !== null || child.signalCode) {
    return Promise.resolve(false);
  }
  return new Promise((resolvePromise) => {
    let done = false;
    const finish = (killed) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      resolvePromise(killed);
    };
    const timer = setTimeout(() => {
      try {
        child.kill('SIGKILL');
      } catch {
        // 已退出
      }
      finish(true);
    }, graceMs);
    child.once('exit', () => finish(true));
    try {
      child.kill('SIGTERM');
    } catch {
      finish(false);
    }
  });
}
