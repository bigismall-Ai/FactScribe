// tests/miniapp_python_discovery.mjs —— Python 解释器发现的实测驱动。
//
// 由 tests/test_miniapp_python_discovery.py 调用（也���单独跑：
//   FS_RESULT_PATH=/tmp/r.json node tests/miniapp_python_discovery.mjs
//
// 三类读数都来自**真跑**：
//   1. 候选表（纯函数）：macOS 顺序与老实现逐项比对；Windows 形态逐项点名；
//   2. 探针分类（真 spawn）：拿假解释器脚本（吐 3.9 / 吐 3.12 / 退出码 1 / 根本不存在）
//      跑真实的 probePythonCandidate，验证「命令不存在」与「版本过低」被分成两类；
//   3. 文案：拿发现状态喂给 pythonFailureMessage，看它有没有把版本号、路径、FS_PYTHON 说清楚。
import { mkdtempSync, mkdirSync, writeFileSync, chmodSync } from 'node:fs';
import { EventEmitter } from 'node:events';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  pythonCandidates,
  windowsInstallPaths,
  discoverPython,
  probePythonCandidate,
  pythonFailureMessage,
  pythonAdvice,
} from '../miniapp/miniapp/node/python_discovery.mjs';

const RESULT_PATH = process.env.FS_RESULT_PATH;
const out = { ok: false, errors: [] };

/** 造一个假解释器：吐版本号的脚本（用来测「版本够 / 版本低」）。 */
function fakeInterpreter(dir, name, version) {
  const full = join(dir, name);
  writeFileSync(full, '#!/bin/sh\nprintf \'FSVER:' + version + '\\nFSEXE:' + full + '\'\n', 'utf8');
  chmodSync(full, 0o755);
  return full;
}

/** 造一个假解释器：跑得起来但读不出版本（Windows Store 别名就是这种）。 */
function fakeBroken(dir, name) {
  const full = join(dir, name);
  writeFileSync(full, '#!/bin/sh\necho "python was not found; run without arguments to install from the Microsoft Store" >&2\nexit 9009\n', 'utf8');
  chmodSync(full, 0o755);
  return full;
}

/**
 * 造一个「进程先退出、stdout 数据后到」的假 spawn。
 *
 * 真机上就是这样：解释器吐完版本号就退出，stdout 的字节还留在管道里，
 * Node 的 'exit' 事件并不保证管道已被读空（'close' 才是）。机器一忙
 * （CI runner 五个矩阵并行），'exit' 就会先于 stdout 的 'data' 到达。
 *
 * 用注入的 spawnFn 把这个时序**钉死**在测试里：不看机器忙不忙，
 * 探针都必须等 stdout 读完再下结论，不许把「读得出版本」误报成「读不出版本」。
 */
function lateStdoutSpawn(stdoutText) {
  return function fakeSpawn() {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stdout.setEncoding = () => {};
    child.stderr = new EventEmitter();
    child.stderr.setEncoding = () => {};
    child.kill = () => {};
    setImmediate(() => {
      child.emit('exit', 0);
      setImmediate(() => {
        child.stdout.emit('data', stdoutText);
        child.stdout.emit('end');
        child.stderr.emit('end');
        child.emit('close', 0);
      });
    });
    return child;
  };
}

try {
  const tmp = mkdtempSync(join(tmpdir(), 'fs-pydisc-'));

  // ---- ① 候选表（纯函数）----
  const mac = pythonCandidates('darwin', {});
  out.macCandidates = mac.map((c) => (c.args.length ? c.command + ' ' + c.args.join(' ') : c.command));
  // macOS 候选顺序不许因为这次改动而变：FS_PYTHON 仍然排第一。
  const macWithEnv = pythonCandidates('darwin', { FS_PYTHON: '/custom/python3' });
  out.macCandidatesWithEnv = macWithEnv.map((c) => (c.args.length ? c.command + ' ' + c.args.join(' ') : c.command));
  out.macKinds = macWithEnv.map((c) => c.kind);
  // Linux 也要是老顺序（同一套非 Windows 分支）。
  out.linuxCandidates = pythonCandidates('linux', {}).map((c) => (c.args.length ? c.command + ' ' + c.args.join(' ') : c.command));

  const winEnv = {
    LOCALAPPDATA: 'C:\\Users\\mo\\AppData\\Local',
    PROGRAMFILES: 'C:\\Program Files',
    SystemDrive: 'C:',
  };
  const win = pythonCandidates('win32', winEnv);
  out.winCandidates = win.map((c) => ({
    label: c.args.length ? c.command + ' ' + c.args.join(' ') : c.command,
    kind: c.kind,
  }));
  out.winPaths = windowsInstallPaths(winEnv);

  // ---- ② 探针分类（真 spawn）----
  const py39 = fakeInterpreter(tmp, 'python39', '3.9');
  const py312 = fakeInterpreter(tmp, 'python312', '3.12');
  const broken = fakeBroken(tmp, 'python-alias');
  const missing = join(tmp, 'no-such-dir', 'python');

  out.probe = {
    missing: await probePythonCandidate({ command: missing, args: [], kind: 'name' }),
    tooOld: await probePythonCandidate({ command: py39, args: [], kind: 'name' }),
    ready: await probePythonCandidate({ command: py312, args: [], kind: 'name' }),
    broken: await probePythonCandidate({ command: broken, args: [], kind: 'name' }),
  };
  // 本机真解释器也过一遍探针（证明探针脚本对真 Python 有效）。
  out.realProbe = await probePythonCandidate({ command: 'python3', args: [], kind: 'name' });

  // ---- ②之补：进程先退出、stdout 数据后到（时序钉死，不靠机器忙不忙）----
  out.lateStdout = await probePythonCandidate(
    { command: '/fake/late-python', args: [], kind: 'name' },
    { spawnFn: lateStdoutSpawn('FSVER:3.9\nFSEXE:/fake/late-python') }
  );

  // ---- ③ 发现流程（注入探针：模拟各种 Windows 现场）----
  // 3a. 只有 py 启动器：py 报 3.12 → 成功，且命令带前缀参数
  const onlyPy = await discoverPython({
    platform: 'win32',
    env: {},
    exists: () => false,
    probe: async (c) => (c.command === 'py' ? { status: 'ready', version: '3.12' } : { status: 'missing' }),
  });
  out.onlyPy = { ok: onlyPy.ok, command: onlyPy.command, args: onlyPy.args, version: onlyPy.version };

  // 3a-2. 只有 py 启动器、且必须带 -3 才认得（裸 py 不可用的情况）
  const pyLauncher = await discoverPython({
    platform: 'win32',
    env: {},
    exists: () => false,
    probe: async (c) => (c.command === 'py' && c.args.length === 1 && c.args[0] === '-3'
      ? { status: 'ready', version: '3.11' }
      : { status: 'missing' }),
  });
  out.pyLauncher = { ok: pyLauncher.ok, command: pyLauncher.command, args: pyLauncher.args, version: pyLauncher.version };

  // 3b. 装了 3.12 但不在 PATH：靠 LOCALAPPDATA 拼出的绝对路径找到。
  //     Windows 路径恒用反斜杠（path.win32 语义），所以这里的文件系统是**模拟**的：
  //     真实存在性由注入的 exists 判定，路径本身由模块自己算出来（不手写，免得抄错）。
  const localRoot = 'C:\\Users\\mo\\AppData\\Local';
  const expectedPath = windowsInstallPaths({ LOCALAPPDATA: localRoot })
    .find((p) => p.indexOf('Python312') !== -1);
  const offPath = await discoverPython({
    platform: 'win32',
    env: { LOCALAPPDATA: localRoot },
    exists: (p) => p === expectedPath,
    probe: async (c) => (c.command === expectedPath ? { status: 'ready', version: '3.12' } : { status: 'missing' }),
  });
  out.offPath = {
    ok: offPath.ok,
    command: offPath.command,
    kind: offPath.candidate ? offPath.candidate.kind : null,
    expectedPath,
  };

  // 3c. 只装了 3.9：全部候选都太老
  const tooOldState = await discoverPython({
    platform: 'win32',
    env: {},
    exists: () => false,
    probe: async (c) => ({
      status: 'old',
      version: c.command === 'python' ? '3.8' : '3.9',
      executable: 'C:\\Python39\\python.exe',
    }),
  });
  out.tooOld = {
    found: tooOldState.found.map((f) => ({ command: f.command, version: f.version })),
    message: pythonFailureMessage(tooOldState, { platform: 'win32' }),
  };

  // 3d. 什么都没找到
  const nothingState = await discoverPython({
    platform: 'win32',
    env: {},
    exists: () => false,
    probe: async () => ({ status: 'missing' }),
  });
  out.nothing = {
    message: pythonFailureMessage(nothingState, { platform: 'win32' }),
    advice: pythonAdvice(nothingState),
  };

  // 3e. 命令在、但读不出版本（Store 别名）
  const aliasState = await discoverPython({
    platform: 'win32',
    env: {},
    exists: () => false,
    probe: async (c) => (c.command === 'python'
      ? { status: 'broken', detail: 'exit_9009', stderr: 'python was not found; run without arguments to install from the Microsoft Store' }
      : { status: 'missing' }),
  });
  out.alias = { message: pythonFailureMessage(aliasState, { platform: 'win32' }) };

  // 3f. FS_PYTHON 指错了
  const badEnvState = await discoverPython({
    platform: 'win32',
    env: { FS_PYTHON: 'C:\\Python312\\python.exe' },
    exists: () => false,
    probe: async (c) => (c.kind === 'env' ? { status: 'missing' } : { status: 'missing' }),
  });
  out.badEnv = { missingEnv: badEnvState.missingEnv, message: pythonFailureMessage(badEnvState, { platform: 'win32' }) };

  // 3g. 找到但在 PATH 之外 → 非致命提醒
  out.advice = pythonAdvice(offPath);

  out.ok = true;
} catch (error) {
  out.errors.push(String((error && error.stack) || error));
}

if (RESULT_PATH) {
  const { writeFileSync } = await import('node:fs');
  writeFileSync(RESULT_PATH, JSON.stringify(out, null, 2), 'utf8');
}
process.exit(out.ok ? 0 : 1);
