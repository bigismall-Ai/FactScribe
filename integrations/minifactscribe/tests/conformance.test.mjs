// 批 138：Python 原版 ↔ JS 移植件的一致性锁（JS 侧）。
//
// 锁什么：tests/conformance/project.json 是 Python 侧投影脚本对夹具的
// 只读投影。同一份投影喂给 auditProject，判出的**核心错误码多重集**必须与
// tests/conformance/expected.json 里 Python 版的读数完全相等。
//
// 不比行号、不比措辞：两边的文本模型不同（同一个数 JS 记 "47.3ms"、
// Python 记 "47.3"），能锁的只有「哪几个码、各几次」。
//
// 跑法（integrations/minifactscribe）：node --test tests/
// 离线、零依赖（node:test + node:assert）。

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

import { auditProject } from '../miniapp/node/audit.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const CONF = resolve(HERE, '../../../tests/conformance');
const PROJECT = resolve(CONF, 'project.json');
const EXPECTED = resolve(CONF, 'expected.json');

const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'));

/** 只留核心码，做成多重集（出现 0 次的码不写进结果）。 */
function coreCounts(codes, core) {
  const wanted = new Set(core);
  const out = {};
  for (const code of codes) {
    if (!wanted.has(code)) continue;
    out[code] = (out[code] || 0) + 1;
  }
  return out;
}

test('投影夹具在 JS 侧判出同样的核心码多重集', () => {
  const expected = readJson(EXPECTED);
  const project = readJson(PROJECT);
  const result = auditProject(project);
  const codes = result.issues.map((i) => i.code);
  assert.deepEqual(
    coreCounts(codes, expected.core_codes),
    expected.codes,
    'JS 侧的核心码多重集与 expected.json（Python 读数）不一致——'
      + '两份实现已经分家；请按 docs/design/SPEC-CONFORMANCE.md §5 处理',
  );
  assert.equal(result.exitCode, 1, '夹具应当判红（exit 1）');
});

test('投影里的事实账与来源都能被 JS 侧读全（锁不住的部分不做假设）', () => {
  const project = readJson(PROJECT);
  const expected = readJson(EXPECTED);
  assert.ok(Array.isArray(project.facts) && project.facts.length > 0);
  assert.ok(Array.isArray(project.sources) && project.sources.length > 0);
  // 正文是「按 \input 顺序拼好的节」，不是成文：先 Claims 后 Notes。
  const claims = project.manuscript.indexOf('\\section{Claims}');
  const notes = project.manuscript.indexOf('\\section{Notes}');
  assert.ok(claims >= 0 && notes > claims, 'manuscript 没有按 \\input 顺序拼接');
  // 夹具自带的三类红都得在期望里，别在 JS 侧悄悄放宽。
  for (const code of ['UNMATCHED_NUMBER', 'BOUND_MISMATCH', 'MISSING_CITE']) {
    assert.ok(expected.codes[code] > 0, `夹具必须保留 ${code}`);
  }
  // 投影必须自包含：JS 只能靠 project.json 里的东西判，不能回读夹具目录。
  for (const f of project.facts) {
    assert.ok(project.sources.some((s) => s.id === f.source), `来源 ${f.source} 不在投影里`);
  }
});
