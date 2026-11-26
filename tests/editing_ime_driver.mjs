// tests/editing_ime_driver.mjs —— 条目 44：正文编辑「跟手度」的真浏览器实测驱动。
//
// 用法：node tests/editing_ime_driver.mjs <workbench-url>
// 输出一行 JSON：{"english": {...}, "imeBadge": {...}, "restore": {...}}
//
// 真浏览器（Chrome headless）＋ CDP 真键盘事件（Input.dispatchKeyEvent）
// 与真 IME 组合输入（Input.imeSetComposition）——不是模拟 dispatchEvent。
// 缺 Chrome / Node 过旧时退出码 3，调用方按「跳过」处理。

import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const URL_APP = process.argv[2];
if (!URL_APP) { console.log(JSON.stringify({ error: 'no url' })); process.exit(2); }

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

const INSTR = [
  'window.__m = { inputs: [], mut: [], comps: [], t0: performance.now(), pending: null };',
  "document.addEventListener('keydown', (e) => { window.__m.pending = { key: e.key, t: performance.now() }; }, true);",
  "document.addEventListener('input', (e) => { const now = performance.now(); const p = window.__m.pending; const rec = { d: p ? +(now - p.t).toFixed(2) : null, composing: !!e.isComposing }; window.__m.inputs.push(rec); window.__m.pending = null; requestAnimationFrame((t) => { rec.paint = +(t - now).toFixed(2); }); }, true);",
  "['compositionstart','compositionupdate','compositionend'].forEach((n) => { document.addEventListener(n, (e) => { window.__m.comps.push({ type: n, data: e.data }); }, true); });",
  "const mo = new MutationObserver((recs) => { for (const r of recs) { window.__m.mut.push({ type: r.type, tgt: (r.target && r.target.nodeName) + (r.target && r.target.id ? '#' + r.target.id : ''), added: Array.from(r.addedNodes).map((n) => n.nodeName + '.' + (n.className || '')).join('|') }); } });",
  "mo.observe(document.body, { childList: true, subtree: true, characterData: true });",
  "window.__caret = () => { const s = window.getSelection(); if (!s || !s.rangeCount) return null; const r = s.getRangeAt(0); const rect = r.getBoundingClientRect(); return { node: s.anchorNode && s.anchorNode.nodeName, offset: s.anchorOffset, x: +rect.x.toFixed(1), y: +rect.y.toFixed(1), ctx: (s.anchorNode ? s.anchorNode.textContent : '').slice(Math.max(0, s.anchorOffset - 14), s.anchorOffset) }; };",
  "window.__reset = () => { const m = window.__m; m.inputs.length = 0; m.mut.length = 0; m.comps.length = 0; m.t0 = performance.now(); m.pending = null; return true; };",
].join('\n');

async function evaluate(cdp, expression) {
  const r = await cdp.send('Runtime.evaluate', { expression: expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error('EVAL ' + (r.exceptionDetails.exception && r.exceptionDetails.exception.description ? r.exceptionDetails.exception.description : r.exceptionDetails.text) + ' @' + r.exceptionDetails.lineNumber + ':' + r.exceptionDetails.columnNumber + ' expr=' + expression.slice(0, 120));
  return r.result.value;
}

async function mouseClick(cdp, x, y) {
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x, y: y });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: x, y: y, button: 'left', clickCount: 1 });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x, y: y, button: 'left', clickCount: 1 });
}

async function clickByText(cdp, text) {
  const rect = await evaluate(cdp, "(() => { const els = Array.from(document.querySelectorAll('button')); const hit = els.find((e) => (e.textContent || '').trim() === " + JSON.stringify(text) + " && e.offsetParent !== null); if (!hit) return null; const r = hit.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()");
  if (!rect) throw new Error('no button ' + text);
  await mouseClick(cdp, rect.x, rect.y);
}

async function clickPara(cdp, id) {
  const rect = await evaluate(cdp, "(() => { const el = document.querySelector('[data-block-id=\"" + id + "\"]'); if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x + r.width * 0.3, y: r.y + 24 }; })()");
  if (!rect) throw new Error('no para ' + id);
  await mouseClick(cdp, rect.x, rect.y);
}

async function key(cdp, ch, code, vk) {
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', text: ch, key: ch, code: code, windowsVirtualKeyCode: vk });
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: ch, code: code, windowsVirtualKeyCode: vk });
}

const caretEnd = (id) => "(() => { const el = document.querySelector('[data-block-id=\"" + id + "\"]'); const r = document.createRange(); r.selectNodeContents(el); r.collapse(false); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); return true; })()";

async function main() {
  const port = 9200 + Math.floor(Math.random() * 500);
  const profile = mkdtempSync(join(tmpdir(), 'fs-cdp-'));
  const proc = spawn(chrome, ['--headless=new', '--remote-debugging-port=' + port, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--window-size=1440,900', 'about:blank'],
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
    await cdp.send('Network.enable');
    await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
    await cdp.send('Emulation.setFocusEmulationEnabled', { enabled: true });
    await cdp.send('Page.navigate', { url: URL_APP });
    await sleep(2500);
    let nPara = await evaluate(cdp, "document.querySelectorAll('.editable-para').length");
    if (!nPara) { await clickByText(cdp, '打开'); await sleep(2500); }
    const blocks = await evaluate(cdp, "Array.from(document.querySelectorAll('.editable-para')).map((e) => e.dataset.blockId)");
    if (!blocks.length) throw new Error('no editable paragraph');
    await evaluate(cdp, INSTR);
    const A = blocks[0];
    const B = blocks[1] || blocks[0];

    // ① 英文逐键：按键→上屏延迟、每键 DOM 变动
    await clickPara(cdp, A);
    await evaluate(cdp, caretEnd(A));
    await evaluate(cdp, 'window.__reset()');
    const nodes0 = await evaluate(cdp, "document.getElementsByTagName('*').length");
    for (let i = 0; i < 60; i++) { await key(cdp, 'a', 'KeyA', 65); await sleep(8); }
    const english = await evaluate(cdp, "(() => { const m = window.__m; const ds = m.inputs.map((x) => x.d).filter((x) => x !== null); const ps = m.inputs.map((x) => x.paint).filter((x) => x !== undefined && x !== null); const stat = (a) => a.length ? { n: a.length, min: Math.min.apply(null, a), max: Math.max.apply(null, a), avg: +(a.reduce((s, v) => s + v, 0) / a.length).toFixed(2) } : null; return { nInputs: m.inputs.length, down2input: stat(ds), input2paint: stat(ps), mutNonChar: m.mut.filter((x) => x.type !== 'characterData').length, mutTotal: m.mut.length, nodes: document.getElementsByTagName('*').length }; })()");
    english.nodes0 = nodes0;

    // ② 组合进行中保存响应回来：角标不得进编辑宿主，光标不得被甩进角标
    const paused = [];
    cdp.on((msg) => { if (msg.method === 'Fetch.requestPaused') paused.push(msg.params.requestId); });
    await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*/edit*', requestStage: 'Request' }] });
    await clickPara(cdp, A);
    await evaluate(cdp, caretEnd(A));
    await evaluate(cdp, 'window.__reset()');
    await key(cdp, 'x', 'KeyX', 88);
    await sleep(80);
    await clickPara(cdp, B);
    await sleep(300);
    await clickPara(cdp, A);
    await evaluate(cdp, caretEnd(A));
    await cdp.send('Input.imeSetComposition', { text: 'zhongwen', selectionStart: 8, selectionEnd: 8 });
    await sleep(120);
    const kidsBefore = await evaluate(cdp, "document.querySelector('[data-block-id=\"" + A + "\"]').childNodes.length");
    for (const rid of paused) await cdp.send('Fetch.continueRequest', { requestId: rid });
    await sleep(700);
    const afterBadge = await evaluate(cdp, "(() => { const el = document.querySelector('[data-block-id=\"" + A + "\"]'); const b = document.querySelector('.save-badge'); return { badgeInHost: !!el.querySelector('.save-badge'), badgeInBody: !!document.body.querySelector('.save-badge'), badgeParent: b ? b.parentElement.tagName : null, kids: el.childNodes.length, kidsBefore: " + kidsBefore + ", tail: el.textContent.slice(-14), caret: window.__caret(), comps: window.__m.comps.map((c) => c.type) }; })()");
    await cdp.send('Input.imeSetComposition', { text: 'zhongwenhu', selectionStart: 11, selectionEnd: 11 });
    await sleep(150);
    const nextComp = await evaluate(cdp, "(() => ({ caret: window.__caret(), comps: window.__m.comps.map((c) => c.type) }))()");
    await cdp.send('Fetch.disable');

    // ③ 整块替换 DOM 前后光标偏移不变
    const restore = await evaluate(cdp, "(() => { const el = document.querySelector('[data-block-id=\"" + A + "\"]'); const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let nd = w.nextNode(); let i = 0; while (nd) { const len = nd.nodeValue.length; if (i >= 2 && len > 6) { const r = document.createRange(); r.setStart(nd, Math.min(4, len)); r.collapse(true); const s = window.getSelection(); s.removeAllRanges(); s.addRange(r); break; } nd = w.nextNode(); i++; } const before = window.__caret(); applyBlockHtml(el.dataset.blockId, el.outerHTML); const after = window.__caret(); return { before: before, after: after }; })()");

    console.log(JSON.stringify({ english: english, imeBadge: { afterBadge: afterBadge, nextComposition: nextComp }, restore: restore }));
    cleanup();
    process.exit(0);
  } catch (err) {
    cleanup();
    console.log(JSON.stringify({ error: String((err && err.message) || err) }));
    process.exit(1);
  }
}

main();
