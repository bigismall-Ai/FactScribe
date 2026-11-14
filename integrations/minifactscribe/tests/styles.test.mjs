// 事实闸 FactScribe 暗色模式回归测试：离线、零依赖（node:test + node:assert）。
//
// 跑法（integrations/minifactscribe 目录）：
//   node --test tests/
//
// 背景：宿主面板是暗色时踩过两个坑，都不是"看起来不对"，而是可复现的规则问题，
// 所以在这里把不变量钉死，防止样式被改回去：
//   1. 暗色下 hover 主按钮，底色被 .btn:hover 抢走 → 白底深字变成深底深字，按钮"消失"。
//   2. 页面没声明 color-scheme，浏览器原生滚动条仍按浅色渲染 → 暗色里一根近白竖条，特别刺眼。

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const CSS = readFileSync(new URL('../miniapp/client/app.css', import.meta.url), 'utf8');

/** 取某个 @media 块的内容（花括号配平）。 */
function mediaBlock(query) {
  const at = CSS.indexOf(`@media ${query}`);
  assert.notEqual(at, -1, `样式里缺少 @media ${query}`);
  const open = CSS.indexOf('{', at);
  let depth = 0;
  for (let i = open; i < CSS.length; i += 1) {
    if (CSS[i] === '{') depth += 1;
    else if (CSS[i] === '}') {
      depth -= 1;
      if (depth === 0) return CSS.slice(open + 1, i);
    }
  }
  throw new Error(`@media ${query} 块没有闭合`);
}

/** 取出某段 CSS 里所有 `--变量: 值;` 声明。 */
function varsOf(block) {
  const out = {};
  for (const m of block.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) out[m[1]] = m[2].trim();
  return out;
}

/** #rgb / #rrggbb / #rrggbbaa → [r, g, b]；不是 hex 就返回 null。 */
function rgb(value) {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(String(value).trim());
  if (!m) return null;
  const h = m[1];
  const hex = h.length === 3 ? [...h].map((c) => c + c).join('') : h.slice(0, 6);
  return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
}

/** 相对亮度（0..1）。 */
function luminance(value) {
  const c = rgb(value);
  if (!c) return null;
  const [r, g, b] = c.map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

// ------------------------------------------------------- 1. 原生控件跟随主题

test('声明 color-scheme：原生滚动条与表单控件跟随系统，不强制主题', () => {
  const lightBlock = CSS.slice(CSS.indexOf(':root,'), CSS.indexOf('@media'));
  assert.match(
    lightBlock,
    /color-scheme:\s*light dark;/,
    '浅色块应声明 light dark（两套都支持，跟随系统）'
  );

  const darkBlock = mediaBlock('(prefers-color-scheme: dark)');
  assert.match(darkBlock, /color-scheme:\s*dark;/, '系统为暗色时原生控件应走暗色');
});

// ------------------------------------------------------------- 2. 滚动条配色

test('滚动条滑块用安静中性灰，不能用接近纯白的边框色', () => {
  assert.match(
    CSS,
    /scrollbar-color:\s*var\(--mcode-text-subtle\)\s+transparent/,
    '标准 scrollbar-color 应给中性灰 + 透明轨道'
  );
  assert.doesNotMatch(
    CSS,
    /scrollbar-color:[^;]*--mcode-border-strong/,
    '--mcode-border-strong 在暗色下接近纯白，用它做滑块比默认还刺眼'
  );
  assert.match(
    CSS,
    /::-webkit-scrollbar-thumb\s*\{[^}]*background:\s*var\(--mcode-text-subtle\)/,
    'WebKit 滑块底色应为 --mcode-text-subtle'
  );
  assert.match(CSS, /::-webkit-scrollbar-track\s*\{[^}]*background:\s*transparent/, '轨道应透明，与表面色融在一起');
});

test('暗色下 --mcode-text-subtle 确实比 --mcode-border-strong 暗，否则滑块还是刺眼', () => {
  const dark = varsOf(mediaBlock('(prefers-color-scheme: dark)'));
  const subtle = luminance(dark['--mcode-text-subtle']);
  const strong = luminance(dark['--mcode-border-strong']);
  assert.ok(subtle !== null && strong !== null, '暗色变量应是 hex，便于比较');
  assert.ok(
    subtle < strong * 0.6,
    `滑块色 ${dark['--mcode-text-subtle']} 不应接近 ${dark['--mcode-border-strong']}`
  );
});

// --------------------------------------------------------- 3. 主按钮 hover

test('主按钮 hover 时底色与文字色不变：不能被 .btn:hover 抢走', () => {
  assert.match(
    CSS,
    /\.btn-primary,\s*\.btn-primary:hover\s*\{[^}]*background:\s*var\(--mcode-primary-action-bg\)[^}]*color:\s*var\(--mcode-primary-action-text\)/,
    '主按钮（含 :hover）必须同时声明底色与文字色，hover 时才能保持白底深字'
  );
});

test('.btn-primary:hover 声明在 .btn:hover 之后：同特异性靠后者生效', () => {
  const generic = CSS.indexOf('.btn:hover');
  const primary = CSS.indexOf('.btn-primary:hover');
  assert.notEqual(generic, -1);
  assert.notEqual(primary, -1);
  assert.ok(primary > generic, '主按钮规则必须排在通用 .btn:hover 之后，否则通用规则会赢');
});

test('暗色下主按钮是亮底暗字，hover 不能翻转让按钮隐形', () => {
  const dark = varsOf(mediaBlock('(prefers-color-scheme: dark)'));
  const bg = luminance(dark['--mcode-primary-action-bg']);
  const fg = luminance(dark['--mcode-primary-action-text']);
  assert.ok(bg > 0.5, '暗色下主按钮底色应是亮色');
  assert.ok(fg < 0.2, '暗色下主按钮文字应是暗色');
  assert.ok(bg - fg > 0.4, '亮底暗字必须有足够对比，否则 hover 时像消失');
});

// ------------------------------------------------------- 4. 次级按钮 hover

test('次级按钮 hover 由语义变量混合，不写死主题色值', () => {
  assert.match(
    CSS,
    /\.btn:hover\s*\{[^}]*color-mix\(in srgb,\s*var\(--mcode-surface-muted\)/,
    '次级按钮 hover 应从语义变量混色，浅色压深、暗色提亮'
  );
  assert.doesNotMatch(CSS, /\.btn:hover\s*\{[^}]*#[0-9a-f]{3,6}/i, '组件样式里不应散落主题色值');
});