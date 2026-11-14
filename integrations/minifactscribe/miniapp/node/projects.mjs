// 论文项目登记册：文件夹就是项目。
//
// 一个论文项目＝一个含 `paperkit.toml` 的文件夹。这里只登记「哪些文件夹是论文项目」
// 和「上次用哪个」，不复制正文、不写项目文件夹。
//
// 落盘位置固定为 `~/.factscribe/projects.json`（不是 dataDir）：dataDir 由宿主创建、
// 位置不透明且可能变化，重装插件就丢；登记册要跨重装可用，且用户能自己看、自己删。

import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { isAbsolute, join, resolve } from 'node:path';

export const REGISTRY_VERSION = 1;
export const MAX_PROJECTS = 30;
export const CONFIG_NAME = 'paperkit.toml';

export function homeDir(explicit) {
  return String(explicit || process.env.HOME || homedir());
}

export function factscribeDir(home) {
  return join(homeDir(home), '.factscribe');
}

export function registryPath(home) {
  return join(factscribeDir(home), 'projects.json');
}

export function emptyRegistry() {
  return { version: REGISTRY_VERSION, projects: [], lastPath: '', python: '', pythonpath: '' };
}

export function normalizeRegistry(raw) {
  const list = Array.isArray(raw?.projects) ? raw.projects : [];
  const seen = new Set();
  const projects = [];
  for (const item of list) {
    const path = String(item?.path ?? '').trim();
    if (!path || seen.has(path)) continue;
    seen.add(path);
    projects.push({
      path,
      name: String(item?.name ?? ''),
      lastOpenedAt: String(item?.lastOpenedAt ?? ''),
    });
  }
  return {
    version: REGISTRY_VERSION,
    projects,
    lastPath: String(raw?.lastPath ?? ''),
    python: String(raw?.python ?? ''),
    pythonpath: String(raw?.pythonpath ?? ''),
  };
}

export async function readRegistry(home) {
  try {
    return normalizeRegistry(JSON.parse(await readFile(registryPath(home), 'utf8')));
  } catch {
    // 没有登记册、或文件被手改坏：当作空册，不因此拒绝启动
    return emptyRegistry();
  }
}

export async function writeRegistry(home, registry) {
  const dir = factscribeDir(home);
  await mkdir(dir, { recursive: true });
  const file = registryPath(home);
  const tmp = file + '.tmp';
  await writeFile(tmp, JSON.stringify(normalizeRegistry(registry), null, 2) + '\n',
    { encoding: 'utf8', mode: 0o600 });
  await rename(tmp, file);
}

/** `~` 展开 + 绝对化 + 必须是论文项目；返回 { path, name }。 */
export function resolveProjectDir(raw, home) {
  const text = String(raw ?? '').trim();
  if (!text) throw new Error('请填论文项目文件夹');
  const base = homeDir(home);
  let expanded = text;
  if (text === '~') expanded = base;
  else if (text.startsWith('~/')) expanded = join(base, text.slice(2));
  if (!isAbsolute(expanded)) throw new Error('请填绝对路径（以 / 开头）');
  if (!existsSync(expanded)) throw new Error('文件夹不存在：' + expanded);
  if (!statSync(expanded).isDirectory()) throw new Error('不是文件夹：' + expanded);
  let dir = resolve(expanded);
  try {
    dir = realpathSync(dir);
  } catch {
    // realpath 失败（权限等）时保留 resolve 结果，后面的存在性检查会再拦一次
  }
  if (!existsSync(join(dir, CONFIG_NAME))) {
    throw new Error('这个文件夹不是论文项目：缺 ' + CONFIG_NAME + '（' + dir + '）');
  }
  return { path: dir, name: readProjectName(dir) };
}

/** 项目显示名：优先 `[project] title` / `name`，读不到就用文件夹名。 */
export function readProjectName(dir) {
  const fallback = String(dir).split('/').filter(Boolean).pop() || String(dir);
  let text = '';
  try {
    text = readTextSync(join(dir, CONFIG_NAME));
  } catch {
    return fallback;
  }
  if (!text) return fallback;
  const projectBlock = /\[project\]([\s\S]*?)(?:\n\s*\[|\s*$)/.exec(text);
  const scoped = projectBlock ? projectBlock[1] : text;
  const match = /^\s*(?:title|name)\s*=\s*"([^"]+)"/m.exec(scoped)
    || /^\s*(?:title|name)\s*=\s*'([^']+)'/m.exec(scoped);
  const name = match ? match[1].trim() : '';
  return name || fallback;
}

/** 项目的一句话简介（`[project] description`；读不到就是空串）。 */
export function readProjectDescription(dir) {
  let text = '';
  try {
    text = readTextSync(join(dir, CONFIG_NAME));
  } catch {
    return '';
  }
  if (!text) return '';
  const projectBlock = /\[project\]([\s\S]*?)(?:\n\s*\[|\s*$)/.exec(text);
  const scoped = projectBlock ? projectBlock[1] : text;
  const match = /^\s*description\s*=\s*"([^"]*)"/m.exec(scoped)
    || /^\s*description\s*=\s*'([^']*)'/m.exec(scoped);
  return match ? match[1].trim() : '';
}

/** 内置示例论文的位置（`~/.factscribe/samples/guide`）。 */
export function guideProjectPath(home) {
  return join(factscribeDir(home), 'samples', 'guide');
}

/** 这个路径是不是内置示例论文？（列表里要把它挑出去） */
export function isGuidePath(path, home) {
  const target = guideProjectPath(home);
  const text = String(path ?? '');
  try {
    return resolve(text) === resolve(target);
  } catch {
    return text === target;
  }
}

function readTextSync(file) {
  // 只读一个小配置；调用方是同步路径校验，这里不为它改成异步
  try {
    return statSync(file).isFile() ? readFileSync(file, 'utf8') : '';
  } catch {
    return '';
  }
}

/** 加入/更新一个项目：置顶并标为上次使用。 */
export function upsertProject(registry, { path, name, at }) {
  const reg = normalizeRegistry(registry);
  const when = at || new Date().toISOString();
  const rest = reg.projects.filter((p) => p.path !== path);
  const entry = { path, name: name || readProjectName(path), lastOpenedAt: when };
  return {
    ...reg,
    projects: [entry, ...rest].slice(0, MAX_PROJECTS),
    lastPath: path,
  };
}

export function removeProject(registry, path) {
  const reg = normalizeRegistry(registry);
  return {
    ...reg,
    projects: reg.projects.filter((p) => p.path !== path),
    lastPath: reg.lastPath === path ? '' : reg.lastPath,
  };
}

export function touchProject(registry, path, at) {
  const reg = normalizeRegistry(registry);
  const found = reg.projects.find((p) => p.path === path);
  if (!found) return reg;
  return upsertProject(reg, { path, name: found.name, at });
}
