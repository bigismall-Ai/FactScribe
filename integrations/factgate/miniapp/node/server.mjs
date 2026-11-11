// 事实闸 · Node 服务
// 一个 Node 领域服务：所有写操作走这里，提交后再广播。
// 持久化落在 context.dataDir；浏览器只管呈现。

import { createHash } from 'node:crypto';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { dirname, extname, join, normalize } from 'node:path';
import { auditProject, mergeVerifyIssues, parseBib, protectDiff, stableIdOf } from './audit.mjs';
import { buildDemoProject } from './demo.mjs';

const CLIENT_DIR = 'miniapp/client';
const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
};

function sha256(text) {
  return createHash('sha256').update(String(text ?? ''), 'utf8').digest('hex');
}

export async function start(context) {
  const dataDir = context.dataDir;
  const projectFile = join(dataDir, 'project.json');
  const verifyFile = join(dataDir, 'verify.json');
  await mkdir(dataDir, { recursive: true });

  let project = null;
  let lastVerify = null;
  let verifyLoadInfo = 'not-loaded';
  try {
    project = JSON.parse(await readFile(projectFile, 'utf8'));
  } catch {
    project = buildDemoProject(sha256);
  }
  project = normalizeProject(project);

  // 核验结果落盘：否则重启/刷新后 CITE_FAKE 这类红牌会静默消失，
  // 用户会以为问题被修好了——那比多报一张牌危险得多。
  try {
    const saved = JSON.parse(await readFile(verifyFile, 'utf8'));
    const want = verifyBasis(project);
    if (saved && saved.verify && saved.basis === want) {
      lastVerify = saved.verify;
      verifyLoadInfo = 'restored:' + (saved.verify.results?.length ?? 0);
    } else {
      lastVerify = null;
      verifyLoadInfo = 'mismatch:saved=' + (saved?.basis?.slice(0, 12) || 'none') + ',want=' + want.slice(0, 12);
    }
  } catch (err) {
    lastVerify = null;
    verifyLoadInfo = 'readfailed:' + err.message;
  }

  // 核验结果的适用基线：正文与 bib 一致才算同一轮结论
  function verifyBasis(p) {
    return sha256(String(p.manuscript ?? '') + '\u0000' + String(p.bib ?? ''));
  }

  async function persist() {
    const tmp = projectFile + '.tmp';
    await writeFile(tmp, JSON.stringify(project, null, 2), 'utf8');
    await rename(tmp, projectFile);
  }

  async function persistVerify() {
    const tmp = verifyFile + '.tmp';
    await writeFile(tmp, JSON.stringify({ basis: verifyBasis(project), verify: lastVerify }, null, 2), 'utf8');
    await rename(tmp, verifyFile);
  }

  async function readBody(req) {
    const chunks = [];
    let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 8 * 1024 * 1024) throw new Error('请求体过大');
      chunks.push(chunk);
    }
    if (!chunks.length) return {};
    return JSON.parse(Buffer.concat(chunks).toString('utf8'));
  }

  function sendJson(res, code, payload) {
    res.writeHead(code, { 'content-type': 'application/json; charset=utf-8' });
    res.end(JSON.stringify(payload));
  }

  function sendText(res, code, body, type) {
    res.writeHead(code, { 'content-type': type });
    res.end(body);
  }

  // ---------------------------------------------------------- 引用在线核验

  function normalizeTitle(text) {
    return String(text ?? '')
      .toLowerCase()
      .replace(/[^a-z0-9\u4e00-\u9fff]+/g, ' ')
      .trim();
  }

  function titleSimilarity(a, b) {
    const ta = new Set(normalizeTitle(a).split(' ').filter(Boolean));
    const tb = new Set(normalizeTitle(b).split(' ').filter(Boolean));
    if (!ta.size || !tb.size) return 0;
    let inter = 0;
    for (const x of ta) if (tb.has(x)) inter += 1;
    const union = ta.size + tb.size - inter;
    const jaccard = inter / (union || 1);
    const na = normalizeTitle(a);
    const nb = normalizeTitle(b);
    const contains = na && nb && (na.includes(nb) || nb.includes(na)) ? 1 : 0;
    return Math.max(jaccard, contains * 0.85);
  }

  async function checkCrossref(entry, sid) {
    const url = 'https://api.crossref.org/works/' + encodeURIComponent(sid.value);
    const res = await fetch(url, {
      headers: { 'user-agent': 'FactGate/1.0 (MiniMax Code Mini App; local verification)' },
      signal: AbortSignal.timeout(12000),
    });
    if (res.status === 404) return { status: 'not_found', detail: 'Crossref 没有这条 DOI。' };
    if (!res.ok) return { status: 'unverified', detail: 'Crossref 返回 ' + res.status + '。' };
    const data = await res.json();
    const m = data.message || {};
    const remoteTitle = Array.isArray(m.title) ? m.title[0] : m.title || '';
    const sim = titleSimilarity(entry.fields.title || '', remoteTitle || '');
    return {
      status: sim >= 0.6 ? 'verified' : 'suspect',
      detail: remoteTitle ? 'Crossref 标题：' + remoteTitle : 'Crossref 无标题字段。',
      remoteTitle,
      similarity: Number(sim.toFixed(3)),
    };
  }

  async function checkArxiv(entry, sid) {
    const url = 'https://export.arxiv.org/api/query?id_list=' + encodeURIComponent(sid.value) + '&max_results=1';
    const res = await fetch(url, {
      headers: { 'user-agent': 'FactGate/1.0 (MiniMax Code Mini App; local verification)' },
      signal: AbortSignal.timeout(12000),
    });
    if (!res.ok) return { status: 'unverified', detail: 'arXiv 返回 ' + res.status + '。' };
    const xml = await res.text();
    const titles = [...xml.matchAll(/<title>([\s\S]*?)<\/title>/g)].map((m) => m[1].trim());
    const remoteTitle = titles.length > 1 ? titles[1] : '';
    if (!remoteTitle) return { status: 'not_found', detail: 'arXiv 没有这条记录。' };
    const sim = titleSimilarity(entry.fields.title || '', remoteTitle);
    return {
      status: sim >= 0.6 ? 'verified' : 'suspect',
      detail: 'arXiv 标题：' + remoteTitle,
      remoteTitle,
      similarity: Number(sim.toFixed(3)),
    };
  }

  async function verifyCitations(current) {
    const entries = parseBib(current.bib ?? '');
    const results = [];
    let failures = 0;
    for (const entry of entries) {
      const sid = stableIdOf(entry);
      if (!sid) {
        results.push({ key: entry.key, status: 'no_id', detail: '没有稳定标识，本地判红，不做在线核验。' });
        continue;
      }
      let r;
      try {
        r = sid.kind === 'doi' ? await checkCrossref(entry, sid) : await checkArxiv(entry, sid);
      } catch (err) {
        r = { status: 'unverified', detail: '请求失败：' + (err.name === 'TimeoutError' ? '超时' : err.message) };
      }
      if (r.status === 'unverified') failures += 1;
      results.push({ key: entry.key, kind: sid.kind, id: sid.value, ...r });
    }
    return { results, failures, total: results.length };
  }

  // ---------------------------------------------------------- 导出

  function buildReport(current, audit, verify) {
    const out = [];
    const verdictText = { green: '绿', red: '红', yellow: '黄' }[audit.verdict];
    out.push('# 事实闸审计报告');
    out.push('');
    out.push('- 结论：**' + verdictText + '**（退出码 ' + audit.exitCode + '）');
    const redShownN = (audit.redShown || audit.red).length;
    const yellowShownN = (audit.yellowShown || audit.yellow).length;
    out.push(
      '- 红牌 ' + redShownN + (redShownN === audit.red.length ? ' 项' : ' 类（' + audit.red.length + ' 条）') +
        '，黄牌 ' + yellowShownN + (yellowShownN === audit.yellow.length ? ' 项' : ' 类（' + audit.yellow.length + ' 条）')
    );
    if (audit.stats) {
      const pct = audit.stats.denom ? Math.round((audit.stats.bound / audit.stats.denom) * 100) : 0;
      out.push('- 内联绑定：' + audit.stats.bound + '/' + audit.stats.denom + '（' + pct + '%）');
    }
    out.push('- 事实账：' + (current.facts || []).length + ' 条；来源材料：' + (current.sources || []).length + ' 份');
    out.push('');
    out.push('> 绿只说明三件事：账有据、据未改、文有绑。它不说明结论为真。');
    out.push('');
    for (const group of [['红牌', audit.redShown || audit.red], ['黄牌', audit.yellowShown || audit.yellow]]) {
      if (!group[1].length) continue;
      out.push('## ' + group[0] + '（' + group[1].length + '）');
      out.push('');
      for (const i of group[1]) {
        out.push('- **' + i.code + '** ' + i.message + (i.location ? '  _(' + i.location + ')_' : ''));
        const p = audit.prescriptions[i.code];
        if (p) {
          out.push('  - 处方：' + p.title);
          for (const s of p.steps) out.push('    - ' + s);
        }
      }
      out.push('');
    }
    if (verify && verify.results && verify.results.length) {
      out.push('## 引用在线核验');
      out.push('');
      for (const r of verify.results) {
        out.push('- ' + r.key + '：' + r.status + (r.detail ? ' — ' + r.detail : ''));
      }
      out.push('');
    }
    return out.join('\n');
  }

  function buildMatrix(audit) {
    const out = ['# 追溯矩阵', ''];
    out.push('| 事实 | 主张 | 值 | 来源 | 正文位置 | 状态 |');
    out.push('| --- | --- | --- | --- | --- | --- |');
    for (const row of audit.matrix.facts) {
      const at = row.boundLines.length ? row.boundLines.map((l) => 'L' + l).join(', ') : '—';
      out.push('| ' + row.id + ' | ' + row.claim + ' | ' + row.value + ' | ' + row.source + ' | ' + at + ' | ' + row.usedIn + ' |');
    }
    out.push('');
    out.push('| 引用 key | 标题 | 稳定标识 | 引用次数 |');
    out.push('| --- | --- | --- | --- |');
    for (const row of audit.matrix.citations) {
      const sid = row.stableId ? row.stableId.kind + ':' + row.stableId.value : '无';
      out.push('| ' + row.key + ' | ' + row.title + ' | ' + sid + ' | ' + row.cited + ' |');
    }
    out.push('');
    return out.join('\n');
  }

  function buildManifest(current, audit) {
    return JSON.stringify(
      {
        tool: 'factgate',
        project: current.name || 'untitled',
        generatedAt: new Date().toISOString(),
        verdict: audit.verdict,
        exitCode: audit.exitCode,
        files: [
          { path: 'manuscript', sha256: sha256(current.manuscript ?? ''), bytes: String(current.manuscript ?? '').length },
          { path: 'refs.bib', sha256: sha256(current.bib ?? ''), bytes: String(current.bib ?? '').length },
          ...(current.sources || []).map((s) => ({
            path: 'sources/' + s.id,
            sha256: s.sha256 || sha256(s.text ?? ''),
            bytes: String(s.text ?? '').length,
          })),
        ],
        facts: (current.facts || []).map((f) => ({
          id: f.id,
          claim: f.claim,
          value: f.value,
          source: f.source,
          sourceSha256: f.sourceSha256,
          locator: f.locator,
        })),
        note: '哈希只保证「事后没被改过」，不保证「记录的就是真实发生过的」。',
      },
      null,
      2,
    );
  }

  // ---------------------------------------------------------- 路由

  const server = createServer(async (request, response) => {
    const url = new URL(request.url ?? '/', 'http://miniapp.local');
    const path = url.pathname;
    try {
      if (request.method === 'GET' && (path === '/factgate' || path === '/factgate/')) {
        const html = await readFile(join(context.pluginRoot, CLIENT_DIR, 'index.html'));
        sendText(response, 200, html, CONTENT_TYPES['.html']);
        return;
      }
      if (request.method === 'GET' && path.startsWith('/factgate/')) {
        const rel = normalize(path.slice('/factgate/'.length)).replace(/^(\.\.(\/|\\))+/, '');
        if (rel.includes('..')) {
          sendText(response, 404, 'not_found');
          return;
        }
        const file = await readFile(join(context.pluginRoot, CLIENT_DIR, rel));
        sendText(response, 200, file, CONTENT_TYPES[extname(rel)] || 'application/octet-stream');
        return;
      }
      if (request.method === 'GET' && path === '/api/state') {
        sendJson(response, 200, { ok: true, project, verify: lastVerify, verifyBasis: verifyBasis(project), verifyLoad: verifyLoadInfo });
        return;
      }
      if (request.method === 'PUT' && path === '/api/project') {
        const body = await readBody(request);
        const before = verifyBasis(project);
        project = normalizeProject(body.project || {});
        // 正文或 bib 变了，上一轮的联网核验结论不再适用——作废，别拿旧结论判新内容
        if (verifyBasis(project) !== before) {
          lastVerify = null;
          await persistVerify();
        }
        await persist();
        sendJson(response, 200, { ok: true, project });
        return;
      }
      if (request.method === 'POST' && path === '/api/demo') {
        project = buildDemoProject(sha256);
        lastVerify = null;
        await persistVerify();
        await persist();
        sendJson(response, 200, { ok: true, project });
        return;
      }
      if (request.method === 'POST' && path === '/api/audit') {
        // 审计一律带上已核验结论，避免刷新后红牌静默消失
        const base = auditProject(project);
        const audit = lastVerify ? mergeVerifyIssues(base, lastVerify) : base;
        sendJson(response, 200, { ok: true, audit, verify: lastVerify });
        return;
      }
      if (request.method === 'POST' && path === '/api/verify') {
        const verify = await verifyCitations(project);
        lastVerify = verify;
        await persistVerify();
        sendJson(response, 200, { ok: true, verify, audit: mergeVerifyIssues(auditProject(project), verify) });
        return;
      }
      if (request.method === 'POST' && path === '/api/protect') {
        const body = await readBody(request);
        sendJson(response, 200, { ok: true, result: protectDiff(body.before ?? '', body.after ?? '') });
        return;
      }
      if (request.method === 'GET' && path === '/api/export/report.md') {
        const base_audit = auditProject(project);
        const audit = lastVerify ? mergeVerifyIssues(base_audit, lastVerify) : base_audit;
        sendText(response, 200, buildReport(project, audit, lastVerify), 'text/markdown; charset=utf-8');
        return;
      }
      if (request.method === 'GET' && path === '/api/export/matrix.md') {
        const audit = auditProject(project);
        sendText(response, 200, buildMatrix(audit), 'text/markdown; charset=utf-8');
        return;
      }
      if (request.method === 'GET' && path === '/api/export/manifest.json') {
        const audit = auditProject(project);
        sendText(response, 200, buildManifest(project, audit), 'application/json; charset=utf-8');
        return;
      }
      sendText(response, 404, 'not_found');
    } catch (err) {
      context.logger.warn('factgate.request.failed', { path, message: err.message });
      sendJson(response, 500, { ok: false, error: err.message });
    }
  });

  await new Promise((resolve, reject) => {
    const onError = (error) => reject(error);
    server.once('error', onError);
    server.listen(context.listen.port, context.listen.host, () => {
      server.off('error', onError);
      resolve();
    });
  });
  context.logger.info('factgate.runtime.listening');

  let disposal;
  const dispose = () => {
    if (disposal) return disposal;
    context.signal.removeEventListener('abort', onAbort);
    disposal = new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
    return disposal;
  };
  const onAbort = () => {
    void dispose().catch(() => undefined);
  };
  context.signal.addEventListener('abort', onAbort, { once: true });
  if (context.signal.aborted) await dispose();

  return { dispose };
}

function normalizeProject(project) {
  const p = project && typeof project === 'object' ? project : {};
  return {
    name: String(p.name ?? '未命名项目'),
    note: String(p.note ?? ''),
    manuscript: String(p.manuscript ?? ''),
    bib: String(p.bib ?? ''),
    sources: Array.isArray(p.sources)
      ? p.sources.map((s) => ({
          id: String(s.id ?? ''),
          name: String(s.name ?? s.id ?? ''),
          text: String(s.text ?? ''),
          sha256: String(s.sha256 ?? ''),
        }))
      : [],
    facts: Array.isArray(p.facts)
      ? p.facts.map((f) => ({
          id: String(f.id ?? ''),
          claim: String(f.claim ?? ''),
          value: String(f.value ?? ''),
          source: String(f.source ?? ''),
          sourceSha256: String(f.sourceSha256 ?? ''),
          locator: String(f.locator ?? ''),
          confidence: String(f.confidence ?? ''),
          derivedFrom: Array.isArray(f.derivedFrom) ? f.derivedFrom.map(String) : [],
          expr: String(f.expr ?? ''),
          dupOk: Boolean(f.dupOk),
          notes: String(f.notes ?? ''),
        }))
      : [],
    protect: {
      before: String((p.protect && p.protect.before) ?? ''),
      after: String((p.protect && p.protect.after) ?? ''),
    },
  };
}
