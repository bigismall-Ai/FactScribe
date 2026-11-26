// tests/miniapp_ui_driver.mjs —— 三件用户诉求的真浏览器实测驱动。
//
// 用法：node tests/miniapp_ui_driver.mjs <workbench-url> [fact-id]
// 输出一行 JSON（每件一段读数）。真 Chrome（headless）＋ CDP 真鼠标/真键盘
// 事件——不是模拟 dispatchEvent。缺 Chrome / Node 过旧时退出码 3（按「跳过」处理）。
//
// 覆盖三件：
//   ① 标题/章节名：目录里的改名钮（改章节名）＋ 封面上的笔（改论文标题）；
//   ② 右栏宽度：拖分隔条改左右比例，刷新后还在；
//   ③ 保护面：段落 ⋯ 菜单里的「插入事实」（数字来自事实账）。
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const URL_APP = process.argv[2];
const FACT_ID = process.argv[3] || 'A4';
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

async function evaluate(cdp, expression) {
  const r = await cdp.send('Runtime.evaluate', { expression: expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) {
    const d = r.exceptionDetails;
    throw new Error('EVAL ' + (d.exception && d.exception.description ? d.exception.description : d.text) +
      ' @' + d.lineNumber + ':' + d.columnNumber + ' expr=' + expression.slice(0, 160));
  }
  return r.result.value;
}

async function mouseClick(cdp, x, y) {
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: x, y: y });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: x, y: y, button: 'left', clickCount: 1 });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: x, y: y, button: 'left', clickCount: 1 });
}

async function mouseDrag(cdp, fromX, fromY, toX, toY) {
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: fromX, y: fromY });
  await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', x: fromX, y: fromY, button: 'left', clickCount: 1 });
  const steps = 8;
  for (let i = 1; i <= steps; i++) {
    await cdp.send('Input.dispatchMouseEvent', {
      type: 'mouseMoved', x: fromX + (toX - fromX) * i / steps, y: fromY + (toY - fromY) * i / steps,
      button: 'left', buttons: 1,
    });
    await sleep(20);
  }
  await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: toX, y: toY, button: 'left', clickCount: 1 });
}

// 点一个元素（真鼠标）：先滚进视口，再取中心点。
async function clickSel(cdp, selector) {
  const rect = await evaluate(cdp, "(() => { const el = document.querySelector(" + JSON.stringify(selector) +
    "); if (!el) return null; el.scrollIntoView({block:'center'}); const r = el.getBoundingClientRect();" +
    " return { x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height }; })()");
  if (!rect) throw new Error('no element ' + selector);
  await mouseClick(cdp, rect.x, rect.y);
  return rect;
}

async function fill(cdp, selector, text) {
  await evaluate(cdp, "(() => { const el = document.querySelector(" + JSON.stringify(selector) +
    "); if (!el) return false; el.focus(); el.value = ''; return true; })()");
  await cdp.send('Input.insertText', { text: text });
}

async function main() {
  const port = 9700 + Math.floor(Math.random() * 400);
  const profile = mkdtempSync(join(tmpdir(), 'fs-ui-cdp-'));
  const proc = spawn(chrome, ['--headless=new', '--remote-debugging-port=' + port, '--user-data-dir=' + profile,
    '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--window-size=1440,900', 'about:blank'],
    { stdio: 'ignore' });
  const cleanup = () => { try { proc.kill('SIGKILL'); } catch (e) {} try { rmSync(profile, { recursive: true, force: true }); } catch (e) {} };
  let out = { ok: false };
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
    await sleep(2200);

    // —— 打开一篇稿子 ——
    async function openPaper() {
      const n = await evaluate(cdp, "document.querySelectorAll('.editable-para').length");
      if (n) return;
      const btn = await evaluate(cdp, "(() => { const els = Array.from(document.querySelectorAll('button'));" +
        " const hit = els.find((e) => (e.textContent||'').trim() === '打开' && e.offsetParent !== null);" +
        " if (!hit) return null; const r = hit.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2}; })()");
      if (!btn) throw new Error('no 打开 button');
      await mouseClick(cdp, btn.x, btn.y);
      await sleep(2500);
    }
    await openPaper();
    const paras = await evaluate(cdp, "Array.from(document.querySelectorAll('.editable-para')).map((e) => e.dataset.blockId)");
    if (!paras.length) throw new Error('no editable paragraph');

    // —— ① 章节名 ——
    const before = await evaluate(cdp, "(() => ({ cover: (document.querySelector('#coverTitle')||{}).textContent," +
      " sub: (document.querySelector('#coverSub')||{}).textContent," +
      " toc: Array.from(document.querySelectorAll('#tocList .toc-item .cn, #tocList .toc-item .en')).map((e) => e.textContent)," +
      " navW: Math.round(document.querySelector('#navPanel').getBoundingClientRect().width)," +
      " stored: localStorage.getItem('factscribe.navw') }))()");
    await clickSel(cdp, '#tocList [data-rename]');
    await sleep(300);
    const modalOpen = await evaluate(cdp, "!document.querySelector('#modalRename').hidden");
    await fill(cdp, '#rnTitle', 'E2E 章节名');
    await clickSel(cdp, '#rnOk');
    await sleep(1500);
    const afterRename = await evaluate(cdp, "(() => ({ toc: Array.from(document.querySelectorAll('#tocList .toc-item .cn, #tocList .toc-item .en')).map((e) => e.textContent)," +
      " toast: (document.querySelector('#toast')||{}).textContent }))()");

    // —— ① 论文标题 ——
    await clickSel(cdp, '#btnEditTitle');
    await sleep(300);
    const titleModal = await evaluate(cdp, "!document.querySelector('#modalTitle').hidden");
    await fill(cdp, '#dtTitle', 'E2E 论文标题');
    await fill(cdp, '#dtSub', 'E2E 副标题');
    await clickSel(cdp, '#dtOk');
    await sleep(1500);
    const afterTitle = await evaluate(cdp, "(() => ({ cover: (document.querySelector('#coverTitle')||{}).textContent," +
      " sub: (document.querySelector('#coverSub')||{}).textContent }))()");

    // —— ② 拖分隔条 ——
    const split = await evaluate(cdp, "(() => { const el = document.querySelector('#navSplitter'); if (!el) return null;" +
      " const r = el.getBoundingClientRect(); return { x: r.x + r.width/2, y: 400, left: r.left, right: r.right }; })()");
    if (!split) throw new Error('no #navSplitter');
    const splitDiag = await evaluate(cdp, "(() => { const el = document.querySelector('#navSplitter');" +
      " const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);" +
      " const top = document.elementFromPoint(r.x + r.width/2, 400);" +
      " return { rect: {x:r.x,y:r.y,w:r.width,h:r.height}, display: cs.display, z: cs.zIndex," +
      " pos: cs.position, right: cs.right, pe: cs.pointerEvents," +
      " topEl: top ? (top.id || top.className || top.tagName) : null }; })()");
    await evaluate(cdp, "(() => { window.__spl = { down: 0, move: 0, up: 0 }; const el = document.querySelector('#navSplitter');" +
      " el.addEventListener('pointerdown', () => { window.__spl.down++; });" +
      " el.addEventListener('pointermove', () => { window.__spl.move++; });" +
      " el.addEventListener('pointerup', () => { window.__spl.up++; });" +
      " window.__splDragging = () => document.body.classList.contains('nav-dragging');" +
      " return true; })()");
    await mouseDrag(cdp, split.x, split.y, split.x - 160, split.y);
    const splEvents = await evaluate(cdp, "Object.assign({}, window.__spl, { dragging: window.__splDragging() })");
    await sleep(600);
    const afterDrag = await evaluate(cdp, "(() => ({ navW: Math.round(document.querySelector('#navPanel').getBoundingClientRect().width)," +
      " sideW: getComputedStyle(document.documentElement).getPropertyValue('--side-w').trim()," +
      " stored: localStorage.getItem('factscribe.navw')," +
      " bodyRight: Math.round(document.querySelector('#leftCol').getBoundingClientRect().right) }))()");

    // 刷新：宽度还在吗（刷新后要重新打开这篇稿子——页面不记「上次开哪篇」）
    await cdp.send('Page.reload', { ignoreCache: true });
    await sleep(2600);
    await openPaper();
    const afterReload = await evaluate(cdp, "(() => ({ navW: Math.round(document.querySelector('#navPanel').getBoundingClientRect().width)," +
      " stored: localStorage.getItem('factscribe.navw') }))()");

    // —— ③ 插入事实 ——
    const before3 = await evaluate(cdp, "(() => { const el = document.querySelector('[data-block-id=\"" + paras[0] + "\"]');" +
      " return { chips: el ? el.querySelectorAll('.prot-chip').length : -1, text: el ? el.textContent.slice(-60) : '' }; })()");
    // 悬停段落 → 段落工具条 → ⋯ 菜单 → 插入事实
    const prect = await evaluate(cdp, "(() => { const el = document.querySelector('[data-block-id=\"" + paras[0] + "\"]');" +
      " if (!el) return null; const r = el.getBoundingClientRect(); return { x: r.x + 40, y: r.y + 12 }; })()");
    if (!prect) throw new Error('no para rect');
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: prect.x, y: prect.y });
    await sleep(400);
    await clickSel(cdp, '#ptMore');
    await sleep(400);
    const menuOpen = await evaluate(cdp, "!document.querySelector('#paraMenu').hidden");
    await clickSel(cdp, '#miFact');
    await sleep(1200);
    const listRows = await evaluate(cdp, "Array.from(document.querySelectorAll('#fiList .fi-row')).map((e) => e.dataset.fact)");
    const factSel = '#fiList [data-fact="' + FACT_ID + '"]';
    const hasFact = await evaluate(cdp, "!!document.querySelector(" + JSON.stringify(factSel) + ")");
    if (!hasFact) throw new Error('no fact row ' + FACT_ID);
    await clickSel(cdp, factSel);
    await sleep(1800);
    const after3 = await evaluate(cdp, "(() => { const el = document.querySelector('[data-block-id=\"" + paras[0] + "\"]');" +
      " return { chips: el ? el.querySelectorAll('.prot-chip').length : -1, text: el ? el.textContent.slice(-60) : ''," +
      " modalHidden: document.querySelector('#modalFactIns').hidden," +
      " toast: (document.querySelector('#toast')||{}).textContent }; })()");

    // —— ② 上下限：拖到最左/最右都不能把正文或右栏拖没 ——
    const clamp = {};
    {
      const sp = await evaluate(cdp, "(() => { const el = document.querySelector('#navSplitter'); const r = el.getBoundingClientRect(); return { x: r.x + r.width/2 }; })()");
      await mouseDrag(cdp, sp.x, 400, 40, 400);
      await sleep(400);
      clamp.wide = await evaluate(cdp, "Math.round(document.querySelector('#navPanel').getBoundingClientRect().width)");
      const sp2 = await evaluate(cdp, "(() => { const el = document.querySelector('#navSplitter'); const r = el.getBoundingClientRect(); return { x: r.x + r.width/2 }; })()");
      await mouseDrag(cdp, sp2.x, 400, 1400, 400);
      await sleep(400);
      clamp.narrow = await evaluate(cdp, "Math.round(document.querySelector('#navPanel').getBoundingClientRect().width)");
      clamp.bodyLeft = await evaluate(cdp, "Math.round(document.querySelector('#leftCol').getBoundingClientRect().width)");
    }

    out = {
      ok: true,
      rename: { modalOpen: modalOpen, before: before.toc, after: afterRename.toc, toast: afterRename.toast },
      title: { modalOpen: titleModal, before: before.cover + ' / ' + before.sub, after: afterTitle.cover + ' / ' + afterTitle.sub },
      splitter: { before: before.navW, diag: splitDiag, events: splEvents, afterDrag: afterDrag, afterReload: afterReload, clamp: clamp },
      fact: { before: before3, rows: listRows, menuOpen: menuOpen, after: after3 },
    };
    console.log(JSON.stringify(out));
    cleanup();
    process.exit(0);
  } catch (err) {
    out.error = String((err && err.message) || err);
    console.log(JSON.stringify(out));
    cleanup();
    process.exit(1);
  }
}

main();
