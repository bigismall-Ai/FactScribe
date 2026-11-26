// tests/save_probe_driver.mjs —— 「保存会改内容」的真浏览器实测驱动。
//
// 用法：node tests/save_probe_driver.mjs <workbench-url> <章节文件绝对路径> \
//        [事实ID] [探针] [块ID] [插入点] [模式]
// 输出一行 JSON：{"probe": {...}}
//
// 场景：在正文里 \fact{E5} 芯片旁放一个带数字的探针（默认 [HOSTBAK1]），
// 连续保存两次，每次都读回：① 客户端实际发出去的正文（散文＋token）
// ② 落盘文件里探针是否完整 ③ 页面 DOM 里探针是否完整。
//
// 两种模式：
//   normal（默认）：正常连存两次。
//   stale：保存应答回来时**块仍被聚焦**（DOM 不重绘）——这条路上旧口径会
//   把用户没打过的字改掉（保护面序号整体错位）。拦一下 /edit 的应答，把光标
//   放回块里再放行，模拟「保存完又点了回来」。
//
// 缺 Chrome / Node 过旧时退出码 3，调用方按「跳过」处理。

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const URL_APP = process.argv[2];
const SECTION_FILE = process.argv[3];
const FACT_ID = process.argv[4] || 'E5';
const BLOCK_ID = process.argv[6] || '';
const WHERE = process.argv[7] || 'after_fact';
const PROBE = process.argv[5] || '[HOSTBAK1]';
const MODE = process.argv[8] || 'normal';
if (!URL_APP || !SECTION_FILE) {
  console.log(JSON.stringify({ error: 'usage: url sectionfile [factid] [probe] [blockid] [where] [normal|stale]' }));
  process.exit(2);
}

const CHROME_CANDIDATES = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
];
const chrome = CHROME_CANDIDATES.find((p) => existsSync(p));
if (!chrome) { console.log(JSON.stringify({ error: 'no chrome' })); process.exit(3); }

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function httpJson(port, path, method) {
  const res = await fetch('http://127.0.0.1:' + port + path, { method: method || 'GET' });
  return res.json();
}

class CDP {
  constructor(ws) { this.ws = ws; this.id = 0; this.pending = new Map(); this.handlers = []; }
  static async attach(wsUrl) {
    const ws = new WebSocket(wsUrl);
    const cdp = new CDP(ws);
    await new Promise((res, rej) => { ws.onopen = () => res(); ws.onerror = () => rej(new Error('ws error')); });
    ws.onmessage = (ev) => cdp.onMsg(JSON.parse(ev.data));
    return cdp;
  }
  onMsg(msg) {
    if (msg.id && this.pending.has(msg.id)) {
      const p = this.pending.get(msg.id); this.pending.delete(msg.id);
      if (msg.error) p.rej(new Error(JSON.stringify(msg.error))); else p.res(msg.result);
    } else if (msg.method) { for (const h of this.handlers) h(msg); }
  }
  send(method, params) {
    const id = ++this.id;
    return new Promise((res, rej) => {
      this.pending.set(id, { res, rej });
      this.ws.send(JSON.stringify({ id: id, method: method, params: params || {} }));
      setTimeout(() => { if (this.pending.has(id)) { this.pending.delete(id); rej(new Error('timeout ' + method)); } }, 30000);
    });
  }
  on(fn) { this.handlers.push(fn); }
}

async function evaluate(cdp, expression) {
  const r = await cdp.send('Runtime.evaluate', { expression: expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) {
    throw new Error('EVAL ' + (r.exceptionDetails.exception && r.exceptionDetails.exception.description
      ? r.exceptionDetails.exception.description : r.exceptionDetails.text));
  }
  return r.result.value;
}

const HOOK = `
window.__reqs = [];
(function () {
  const orig = window.fetch;
  window.fetch = function (input, init) {
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.indexOf('/edit') >= 0 && init && init.body) {
        window.__reqs.push(JSON.parse(init.body));
      }
    } catch (err) { /* 记不上不影响实测 */ }
    return orig.apply(this, arguments);
  };
})();
`;

const CARET_AFTER_CHIP = (factId, blockFilter, where) => `(() => {
  const block = ${blockFilter ? `document.querySelector('[data-block-id="${blockFilter}"]')` : 'null'};
  const scope = block || document;
  const chip = scope.querySelector('[data-fact="${factId}"]');
  if (!chip) return null;
  const host = chip.closest('[data-block-id]');
  if (!host) return null;
  host.focus();
  const parent = chip.parentNode;
  const kids = Array.prototype.slice.call(parent.childNodes);
  const at = kids.indexOf(chip);
  let target = chip;
  let offset = at + 1;
  const mode = ${JSON.stringify(where || 'after_fact')};
  if (mode === 'after_num' || mode === 'before_num') {
    // 事实芯片前面那枚数字芯片（紧邻的上一枚 prot-chip）
    for (let i = at - 1; i >= 0; i--) {
      const k = kids[i];
      if (k.nodeType === 1 && k.dataset && k.dataset.token) { target = k; break; }
    }
    offset = kids.indexOf(target) + (mode === 'after_num' ? 1 : 0);
  }
  const range = document.createRange();
  range.setStart(parent, offset);
  range.collapse(true);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  return { blockId: host.dataset.blockId, blockText: host.textContent };
})()`;

const BLOCK_SNAPSHOT = `(() => {
  const host = document.querySelector('[data-block-id="' + (window.__probeBlock || '') + '"]');
  if (!host) return null;
  return { text: host.textContent, html: host.innerHTML };
})()`;

async function main() {
  const port = 9700 + Math.floor(Math.random() * 400);
  const profile = mkdtempSync(join(tmpdir(), 'fs-probe-'));
  const proc = spawn(chrome, ['--headless=new', '--remote-debugging-port=' + port, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--window-size=1600,1000', 'about:blank'],
    { stdio: 'ignore' });
  const cleanup = () => { try { proc.kill('SIGKILL'); } catch (e) {} try { rmSync(profile, { recursive: true, force: true }); } catch (e) {} };
  try {
    let ready = false;
    for (let i = 0; i < 60 && !ready; i++) {
      await sleep(250);
      try { await httpJson(port, '/json/version'); ready = true; } catch (e) { /* 还没起来 */ }
    }
    if (!ready) throw new Error('chrome did not start');
    const target = await httpJson(port, '/json/new?about:blank', 'PUT');
    const cdp = await CDP.attach(target.webSocketDebuggerUrl);
    await cdp.send('Page.enable');
    await cdp.send('Runtime.enable');
    await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true });
    await cdp.send('Page.navigate', { url: URL_APP });
    await sleep(2500);
    await evaluate(cdp, HOOK);
    let nPara = await evaluate(cdp, "document.querySelectorAll('[data-block-id]').length");
    if (!nPara) {
      const btn = await evaluate(cdp, "(() => { const b = Array.from(document.querySelectorAll('button')).find((e) => (e.textContent || '').trim() === '打开'); if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()");
      if (btn) {
        await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: btn.x, y: btn.y, button: 'left', clickCount: 1 });
        await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: btn.x, y: btn.y, button: 'left', clickCount: 1 });
      }
      await sleep(2500);
    }
    const chipInfo = await evaluate(cdp, CARET_AFTER_CHIP(FACT_ID, BLOCK_ID, WHERE));
    if (!chipInfo) {
      const diag = await evaluate(cdp, "JSON.stringify({ blocks: document.querySelectorAll('[data-block-id]').length, facts: Array.from(document.querySelectorAll('[data-fact]')).map((e) => e.dataset.fact).slice(0, 40), view: (document.querySelector('#viewProjects') || {}).hidden, buttons: Array.from(document.querySelectorAll('button')).map((b) => (b.textContent || '').trim()).slice(0, 20) })");
      throw new Error('fact chip not found: ' + FACT_ID + ' diag=' + diag);
    }
    await evaluate(cdp, "window.__probeBlock = " + JSON.stringify(chipInfo.blockId));

    const before = readFileSync(SECTION_FILE, 'utf8');
    const domBefore = await evaluate(cdp, BLOCK_SNAPSHOT);

    // ① 探针落进正文（真实插入：IME 提交路径，浏览器会派发 input 事件）
    await cdp.send('Input.insertText', { text: PROBE });
    await sleep(250);
    const domAfterType = await evaluate(cdp, BLOCK_SNAPSHOT);

    // ② 失焦 → 自动保存（第一次）
    // stale 模式：拦下 /edit 的请求，把光标放回块里再放行——模拟「保存完又
    // 点了回来」：应答回来时块仍被聚焦 → DOM 不重绘 → 保护面序号还是旧的。
    const paused = [];
    if (MODE === 'stale') {
      cdp.on((msg) => { if (msg.method === 'Fetch.requestPaused') paused.push(msg.params.requestId); });
      await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*/edit*', requestStage: 'Request' }] });
    }
    await evaluate(cdp, "(() => { const a = document.activeElement; if (a && a.blur) a.blur(); return true; })()");
    if (MODE === 'stale') {
      await sleep(500);
      await evaluate(cdp, CARET_AFTER_CHIP(FACT_ID, BLOCK_ID, WHERE));
      // 飞行途中用户又点了回来、还又打了一个字 → 应答回来时 DOM 不该重绘
      await cdp.send('Input.insertText', { text: 'Z' });
      await sleep(150);
      const focusState = await evaluate(cdp, '(() => { const a = document.activeElement; const blk = document.querySelector(' + JSON.stringify('[data-block-id="' + chipInfo.blockId + '"]') + '); return { active: a ? (a.tagName + "#" + (a.id || "")) : "null", insideBlock: !!(blk && a && blk.contains(a)) }; })()');
      const held = paused.splice(0);
      for (const rid of held) {
        await cdp.send('Fetch.continueRequest', { requestId: rid });
      }
      console.error('[stale] 拦下请求=' + held.length + ' 焦点=' + JSON.stringify(focusState));
    }
    await sleep(1800);
    const afterSave1 = readFileSync(SECTION_FILE, 'utf8');
    const domStateSel = JSON.stringify('[data-block-id="' + chipInfo.blockId + '"]');
    const domState1 = await evaluate(cdp, '(() => { const n = document.querySelector(' + domStateSel + '); return n ? { stale: n.dataset.stale || "", dirty: n.dataset.dirty || "" } : null; })()');
    const domAfterSave1 = await evaluate(cdp, BLOCK_SNAPSHOT);
    const reqs1 = await evaluate(cdp, "JSON.stringify(window.__reqs)");

    // ③ 再打一个字（让块重新变脏）→ 再失焦 → 第二次保存
    // stale 模式：那一个字已经在飞行途中打过了（DOM 没重绘，脏标记还在）
    if (MODE !== 'stale') {
      await evaluate(cdp, CARET_AFTER_CHIP(FACT_ID, BLOCK_ID, WHERE));
      await cdp.send('Input.insertText', { text: 'Z' });
      await sleep(200);
    }
    await evaluate(cdp, "(() => { const a = document.activeElement; if (a && a.blur) a.blur(); return true; })()");
    if (MODE === 'stale') {
      await sleep(500);
      for (const rid of paused.splice(0)) {
        await cdp.send('Fetch.continueRequest', { requestId: rid });
      }
    }
    await sleep(1800);
    const afterSave2 = readFileSync(SECTION_FILE, 'utf8');
    const domAfterSave2 = await evaluate(cdp, BLOCK_SNAPSHOT);
    const reqs2 = await evaluate(cdp, "JSON.stringify(window.__reqs)");

    const reqs = JSON.parse(reqs2);
    const out = {
      blockId: chipInfo.blockId,
      probe: PROBE,
      domBefore: domBefore ? domBefore.text : null,
      domAfterType: domAfterType ? domAfterType.text : null,
      domAfterSave1: domAfterSave1 ? domAfterSave1.text : null,
      domAfterSave2: domAfterSave2 ? domAfterSave2.text : null,
      fileHasProbeBefore: before.indexOf(PROBE) >= 0,
      fileHasProbeAfterSave1: afterSave1.indexOf(PROBE) >= 0,
      fileHasProbeAfterSave2: afterSave2.indexOf(PROBE) >= 0,
      fileStableAcrossSaves: afterSave1 === afterSave2,
      fileAfterSave1Snippet: snippet(afterSave1, PROBE),
      fileAfterSave2Snippet: snippet(afterSave2, PROBE),
      domState1: domState1,
      mode: MODE,
      requests: reqs.map((r) => ({ block: r.block, file: r.file, expect_sha: r.expect_sha || '', text: r.text })),
      requestsCount: reqs.length,
    };
    console.log(JSON.stringify({ probe: out }));
    cleanup();
    process.exit(0);
  } catch (err) {
    cleanup();
    console.log(JSON.stringify({ error: String((err && err.message) || err) }));
    process.exit(1);
  }
}

function snippet(text, needle) {
  const i = text.indexOf('HOSTBAK');
  if (i < 0) return null;
  return text.slice(Math.max(0, i - 40), i + 40);
}

main();
