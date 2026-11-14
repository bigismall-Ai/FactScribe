// 论文项目登记册与一键启动：只测纯函数与子进程握手，不连真项目。
// 一个文件夹就是一个论文项目——这里的每个用例都围绕这条。

import assert from 'node:assert/strict';
import { chmodSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

import { serveArgs, startServe, stopServe } from '../miniapp/node/launcher.mjs';
import {
  emptyRegistry, MAX_PROJECTS, readProjectName, readRegistry, removeProject,
  resolveProjectDir, upsertProject, writeRegistry,
} from '../miniapp/node/projects.mjs';

function tempHome() {
  return mkdtempSync(join(tmpdir(), 'minifactscribe-home-'));
}

function makeProject(root, title) {
  const dir = join(root, 'paper-' + Math.random().toString(36).slice(2, 8));
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'paperkit.toml'),
    '[project]\ntitle = "' + title + '"\nauthors = ["测试"]\nbuild = "true"\n', 'utf8');
  return dir;
}

test('文件夹就是项目：认 paperkit.toml，缺了就不是项目', () => {
  const home = tempHome();
  const good = makeProject(home, '我的论文');
  // macOS 的 /var 是 /private/var 的软链；登记册存真实路径
  assert.deepEqual(resolveProjectDir(good, home), { path: realpathSync(good), name: '我的论文' });

  const bare = join(home, 'not-a-project');
  mkdirSync(bare, { recursive: true });
  assert.throws(() => resolveProjectDir(bare, home), /不是论文项目：缺 paperkit\.toml/);
  assert.throws(() => resolveProjectDir(join(home, 'nope'), home), /文件夹不存在/);
  assert.throws(() => resolveProjectDir('relative/dir', home), /绝对路径/);
  assert.throws(() => resolveProjectDir('', home), /请填论文项目文件夹/);
  rmSync(home, { recursive: true, force: true });
});

test('项目名读 [project] title，读不到用文件夹名', () => {
  const home = tempHome();
  const dir = join(home, 'untitled-folder');
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, 'paperkit.toml'), '[project]\nauthors = ["x"]\n', 'utf8');
  assert.equal(readProjectName(dir), 'untitled-folder');
  assert.equal(readProjectName(join(home, 'missing')), 'missing');
  rmSync(home, { recursive: true, force: true });
});

test('登记册：置顶、去重、限量、可移除，落盘在 ~/.factscribe/projects.json', async () => {
  const home = tempHome();
  const a = makeProject(home, '甲');
  const b = makeProject(home, '乙');
  await writeRegistry(home, upsertProject(emptyRegistry(), { path: a, name: '甲' }));
  let registry = await readRegistry(home);
  assert.deepEqual(registry.projects.map((p) => p.path), [a]);
  assert.equal(registry.lastPath, a);

  await writeRegistry(home, upsertProject(registry, { path: b, name: '乙' }));
  registry = await readRegistry(home);
  assert.deepEqual(registry.projects.map((p) => p.path), [b, a], '最近用的排最前');
  assert.equal(registry.lastPath, b);

  // 重复加入不产生第二条
  registry = upsertProject(registry, { path: a, name: '甲' });
  assert.equal(registry.projects.filter((p) => p.path === a).length, 1);
  assert.equal(registry.projects[0].path, a);

  registry = removeProject(registry, a);
  assert.equal(registry.projects.some((p) => p.path === a), false);
  assert.equal(registry.lastPath, '');

  // 坏文件当空册，不因此拒绝启动
  writeFileSync(join(home, '.factscribe', 'projects.json'), '{not json', 'utf8');
  assert.deepEqual((await readRegistry(home)).projects, []);

  const many = emptyRegistry();
  for (let i = 0; i < MAX_PROJECTS + 5; i += 1) {
    many.projects.push({ path: '/p/' + i, name: 'p' + i, lastOpenedAt: '' });
  }
  let capped = many;
  for (let i = 0; i < MAX_PROJECTS + 5; i += 1) capped = upsertProject(capped, { path: '/p/' + i, name: 'p' + i });
  assert.equal((await writeRegistry(home, capped), (await readRegistry(home)).projects.length), MAX_PROJECTS);
  rmSync(home, { recursive: true, force: true });
});

test('启动命令固定：只换项目路径，开关只加两个已知参数', () => {
  assert.deepEqual(serveArgs({ project: '/x' }),
    ['serve', '/x', '--port', '0', '--json']);
  assert.deepEqual(serveArgs({ project: '/x', allowWrite: true, allowBuild: true }),
    ['serve', '/x', '--port', '0', '--json', '--allow-write', '--allow-build']);
});

test('一键启动：读首行 JSON 握手，停止时收掉子进程', async () => {
  const home = tempHome();
  const project = makeProject(home, '握手测试');
  const fake = join(home, 'fake-python.sh');
  writeFileSync(fake, [
    '#!/bin/sh',
    'echo "starting up"',
    'printf \'%s\\n\' \'{"event":"listening","ok":true,"url":"http://127.0.0.1:65001","token":"tok-1","project":"/tmp/demo"}\'',
    'exec sleep 30',
  ].join('\n') + '\n', 'utf8');
  chmodSync(fake, 0o755);

  const started = await startServe({ project, python: fake, timeoutMs: 8000 });
  assert.equal(started.url, 'http://127.0.0.1:65001');
  assert.equal(started.token, 'tok-1');
  assert.ok(started.pid > 0);
  assert.equal(await stopServe(started.child), true);
  // 被信号结束的进程 exitCode 是 null，改用 signalCode 判断确实没了
  assert.ok(started.child.exitCode !== null || started.child.signalCode !== null);

  // 解释器能跑但命令失败：直接报错并带 stderr，不静默换形状
  const bad = join(home, 'bad-python.sh');
  writeFileSync(bad, '#!/bin/sh\necho "boom: 项目配置坏了" >&2\nexit 2\n', 'utf8');
  chmodSync(bad, 0o755);
  await assert.rejects(startServe({ project, python: bad, timeoutMs: 5000 }), /boom: 项目配置坏了/);
  rmSync(home, { recursive: true, force: true });
});

test('一键启动：解释器不存在时给出可操作提示', async () => {
  const home = tempHome();
  const project = makeProject(home, '解释器缺失');
  const missing = join(home, 'no-such-python');
  // PATH 上通常也没有 factscribe，这里两个候选都会失败
  const savedPath = process.env.PATH;
  process.env.PATH = home;
  try {
    await assert.rejects(startServe({ project, python: missing, timeoutMs: 4000 }),
      /启动工作台失败/);
  } finally {
    process.env.PATH = savedPath;
    rmSync(home, { recursive: true, force: true });
  }
});
