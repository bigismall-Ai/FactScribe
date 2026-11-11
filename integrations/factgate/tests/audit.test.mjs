// 事实闸 FactGate 测试：离线、零依赖（node:test + node:assert）。
//
// 跑法（integrations/factgate 目录）：
//   node --test tests/
//
// 覆盖三类：
//   1. 数字归一化与值域（对齐上游 facts.py 的语义）
//   2. 判据层：红黄牌的触发与不触发（每个码都要有正反两例）
//   3. 呈现层折叠与联网核验并入

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { test } from 'node:test';

import {
  auditProject,
  factValueKeys,
  foldIssues,
  formatKey,
  mergeVerifyIssues,
  numberKey,
  protectDiff,
} from '../miniapp/node/audit.mjs';
import { buildDemoProject } from '../miniapp/node/demo.mjs';

const sha256 = (t) => createHash('sha256').update(String(t ?? ''), 'utf8').digest('hex');

// ---------------------------------------------------------------- 数字归一化

test('千分位、量级后缀与单位归一', () => {
  assert.equal(formatKey(numberKey('1,234', '', false)), '1234');
  assert.equal(formatKey(numberKey('53', 'k', false)), '53000');
  assert.equal(formatKey(numberKey('5', 'M', false)), '5000000');
  assert.equal(formatKey(numberKey('5', 'B', false)), '5000000000');
});

test('单位只作量纲不参与换算', () => {
  // 5ms 与 5s 都是 5：单位只标量纲，不参与换算，所以规范键相同
  assert.equal(formatKey(numberKey('5', '', false)), '5');
  // 量级后缀才换算
  assert.equal(formatKey(numberKey('5', 'k', false)), '5000');
});

test('百分号：值域同时接受裸值与带号值', () => {
  const keys = factValueKeys('56.25%');
  // 56.25% = 9/16；百分号除以 100，所以裸值 0.5625 也在值域里
  assert.ok(keys.has('9/16'));
  assert.ok(keys.has('225/4'));
});

test('值域无隐式四舍五入（上游 R-04）', () => {
  const keys = factValueKeys('0.9');
  assert.ok(keys.has('9/10'));
  assert.ok(!keys.has('9.1/10'));
  assert.ok(!keys.has('91/100'));
});

test('分数值域给出精确分数商', () => {
  const keys = factValueKeys('10/16');
  assert.ok(keys.has('5/8')); // 10/16 约分后的精确商
  assert.ok(keys.has('10/1')); // 字面分子
  assert.ok(keys.has('16/1')); // 字面分母
});

// ---------------------------------------------------------------- 判据层

const codes = (audit, sev) =>
  (sev === 'red' ? audit.red : audit.yellow).map((i) => i.code);

test('演示项目：红牌与黄牌符合预期', () => {
  const a = auditProject(buildDemoProject(sha256));
  assert.equal(a.verdict, 'red');
  assert.equal(a.exitCode, 1);
  assert.deepEqual(codes(a, 'red').sort(), ['BIB_NO_STABLE_ID', 'MISSING_CITE', 'UNMATCHED_NUMBER']);
  assert.ok(codes(a, 'yellow').includes('UNBOUND_NUMBER'));
  assert.ok(codes(a, 'yellow').includes('UNUSED_BIB'));
});

test('账外数字判红，回得到账判黄', () => {
  const p = buildDemoProject(sha256);
  const a = auditProject(p);
  // 47.3 账外 → 红
  assert.ok(a.red.some((i) => i.code === 'UNMATCHED_NUMBER' && /47\.3/.test(i.message)));
  // 表格里的 10 / 8 / 16 回得到账但没绑定 → 黄
  assert.ok(a.yellow.some((i) => i.code === 'UNBOUND_NUMBER'));
});

test('内联绑定：行内数字必须在绑定事实的值域里', () => {
  const p = buildDemoProject(sha256);
  p.manuscript = p.manuscript.replace('10 道\\fact{A1}', '10 道\\fact{A3}');
  const a = auditProject(p);
  assert.ok(a.red.some((i) => i.code === 'BOUND_MISMATCH'));
});

test('引用了 bib 里没有的 key 判红（引用族 fail-closed）', () => {
  const p = buildDemoProject(sha256);
  const a = auditProject(p);
  assert.ok(a.red.some((i) => i.code === 'MISSING_CITE' && /ghost2024/.test(i.message)));
});

test('bib 条目缺稳定标识判红', () => {
  const p = buildDemoProject(sha256);
  const a = auditProject(p);
  assert.ok(a.red.some((i) => i.code === 'BIB_NO_STABLE_ID'));
});

test('派生事实：expr 重算与 value 不符判红', () => {
  const p = buildDemoProject(sha256);
  const f = p.facts.find((x) => x.id === 'A2');
  f.value = '99%';
  const a = auditProject(p);
  assert.ok(a.red.some((i) => i.code === 'EXPR_MISMATCH'));
});

test('派生事实：expr 与 value 一致时不报', () => {
  const p = buildDemoProject(sha256);
  const a = auditProject(p);
  assert.ok(!a.red.some((i) => i.code === 'EXPR_MISMATCH'));
});

test('重复 fact id 判红', () => {
  const p = buildDemoProject(sha256);
  p.facts.push({ ...p.facts[0] });
  const a = auditProject(p);
  assert.ok(a.red.some((i) => i.code === 'DUPLICATE_ID'));
});

// ---------------------------------------------------- 据未改（哈希现算）

test('来源材料被改动 → SOURCE_SHA256_MISMATCH（红）', () => {
  const p = buildDemoProject(sha256);
  p.sources[0].text = p.sources[0].text.replace('56.25%', '56.26%');
  const a = auditProject(p);
  assert.ok(a.red.some((i) => i.code === 'SOURCE_SHA256_MISMATCH'));
});

test('来源材料没改动 → 不报失配', () => {
  const p = buildDemoProject(sha256);
  const a = auditProject(p);
  assert.ok(!a.red.some((i) => i.code === 'SOURCE_SHA256_MISMATCH'));
});

test('账本没记来源哈希 → MISSING_SOURCE_SHA256（红）', () => {
  const p = buildDemoProject(sha256);
  p.facts[0].sourceSha256 = '';
  const a = auditProject(p);
  assert.ok(a.red.some((i) => i.code === 'MISSING_SOURCE_SHA256'));
});

// ---------------------------------------------------------------- 改写保护

test('改写保护：只改标点全绿', () => {
  const r = protectDiff('结果为 10/16。', '结果为 10/16。');
  assert.equal(r.issues.length, 0);
});

test('改写保护：改数字判红', () => {
  const r = protectDiff('结果为 10/16。', '结果为 11/16。');
  assert.ok(r.issues.some((i) => i.code === 'PROTECT_NUMBER'));
});

test('改写保护：改事实标记判红', () => {
  const r = protectDiff('10\\fact{A1}', '10\\fact{A2}');
  assert.ok(r.issues.some((i) => i.code === 'PROTECT_FACT'));
});

test('改写保护：改引用判红', () => {
  const r = protectDiff('见 \\cite{a2020}。', '见 \\cite{b2021}。');
  assert.ok(r.issues.some((i) => i.code === 'PROTECT_CITE'));
});

// ------------------------------------------------------------ 呈现层折叠

test('呈现层折叠：同一来源的失配合并成一条，判定条数不变', () => {
  const p = buildDemoProject(sha256);
  p.sources[0].text = p.sources[0].text.replace('56.25%', '56.26%');
  const a = auditProject(p);
  const raw = a.red.filter((i) => i.code === 'SOURCE_SHA256_MISMATCH').length;
  const shown = a.redShown.filter((i) => i.code === 'SOURCE_SHA256_MISMATCH').length;
  assert.equal(raw, 3);
  assert.equal(shown, 1);
  assert.equal(a.redCount, a.red.length);
});

test('折叠函数：非失配类原样透传', () => {
  const issues = [{ severity: 'red', code: 'MISSING_CITE', message: 'x', location: '正文:1' }];
  assert.equal(foldIssues(issues).length, 1);
});

// ------------------------------------------------------------ 联网核验并入

test('联网核验：被引用的条目查无此文 → CITE_FAKE（红）', () => {
  const a = auditProject(buildDemoProject(sha256));
  const verify = {
    total: 1,
    failures: 0,
    results: [{ key: 'pretend2025', status: 'not_found', kind: 'doi', id: '10.1/x' }],
  };
  const m = mergeVerifyIssues(a, verify);
  assert.ok(m.red.some((i) => i.code === 'CITE_FAKE'));
});

test('联网核验：未被引用的条目不判死', () => {
  const a = auditProject(buildDemoProject(sha256));
  const verify = {
    total: 1,
    failures: 0,
    results: [{ key: 'lewis2020rag', status: 'not_found', kind: 'doi', id: '10.1/x' }],
  };
  const m = mergeVerifyIssues(a, verify);
  assert.ok(!m.red.some((i) => i.code === 'CITE_FAKE'));
});

test('联网核验：并入后派生视图要重算，不能沿用旧的', () => {
  const a = auditProject(buildDemoProject(sha256));
  const verify = {
    total: 1,
    failures: 0,
    results: [{ key: 'pretend2025', status: 'not_found', kind: 'doi', id: '10.1/x' }],
  };
  const m = mergeVerifyIssues(a, verify);
  assert.equal(m.redShown.length, m.red.length);
  assert.ok(m.redShown.some((i) => i.code === 'CITE_FAKE'));
});

test('联网核验：半数以上没核验成 → RESOLVE_DEGRADED（黄）', () => {
  const a = auditProject(buildDemoProject(sha256));
  const verify = {
    total: 4,
    failures: 3,
    results: [{ key: 'x', status: 'unverified', kind: 'doi', id: 'x' }],
  };
  const m = mergeVerifyIssues(a, verify);
  assert.ok(m.yellow.some((i) => i.code === 'RESOLVE_DEGRADED'));
});