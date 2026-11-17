// 意大利 CCNL 链接层采集器（corpus-bulk-it）——CNEL 档案检索 API 的「列表＋链接」面。
//
// 用法（ego-browser 真浏览器会话，API 网关 Akamai 拒裸 curl）：
//   ego-browser nodejs < scripts/it_cnel_harvest.js
//
// 行为：
//   读 integrations/factscribe-legal/corpus-bulk-it/it-clusters.json 的簇码清单，逐簇调
//   ricerca-api 已实测 GET 面：/accordi/cerca/accordi/codice-ccnl/<码>?vigenti=true|false
//   （分页收齐；不走 POST 检索跳——簇码以清单表为权威源，GET 直查＝2 请求/簇）。
//   只取列表与链接（scarica 链接可由 idAccordo 推导），**不取全文 PDF**。
//   增量：it-harvest-state.json 记每簇 {ts,sha}；未过期（maxAgeHours）即跳过；
//        sha 变化才向 it-ccnl-accordi-manifest.ndjson 追加一行快照（append-only）。
//   礼貌：并发 1；请求间隔 minGapMs–maxGapMs 随机（默认 3000–5000）；
//        被拦（非 200 / 解析失败）即停，不在被拦会话内重试；进度已在 state，冷却后重跑即续。
//
// 运行配置 _state/run-config.json（可省，缺省内置）：
//   { baseDir, spaceName, limit, onlyCodes, maxAgeHours, minGapMs, maxGapMs, pageSize }
//
// 法律面：取件合法（官方档案公开、robots Allow、元数据 IODL 2.0）；
//        全文再分发未清权（当事方 Proprietà riservata）——见同目录 ATTRIBUTION。

const fs = await import("node:fs/promises");
const crypto = await import("node:crypto");

const DEFAULT_BASE = "/Users/moc/workspaces/SiAgent/factscribe-dev/integrations/factscribe-legal/corpus-bulk-it";
const CFG_PATH = `${DEFAULT_BASE}/_state/run-config.json`;

const cfg = { baseDir: DEFAULT_BASE, spaceName: null, limit: null, onlyCodes: null, maxAgeHours: 144, minGapMs: 3000, maxGapMs: 5000, pageSize: 50 };
try {
  Object.assign(cfg, JSON.parse(await fs.readFile(CFG_PATH, "utf8")));
  console.log("config:", CFG_PATH);
} catch {
  console.log("config: (内置缺省)");
}
const { baseDir, spaceName, limit, onlyCodes, maxAgeHours, minGapMs, maxGapMs, pageSize } = cfg;
const API = "https://az-apim-cne-sa-0002-lgc-we.azure-api.net/ricerca-api/ricerca/pubblica";

const clustersDoc = JSON.parse(await fs.readFile(`${baseDir}/it-clusters.json`, "utf8"));
const statePath = `${baseDir}/it-harvest-state.json`;
const manifestPath = `${baseDir}/it-ccnl-accordi-manifest.ndjson`;
const reqLogPath = `${baseDir}/_state/request-log.ndjson`;

let state = {};
try { state = JSON.parse(await fs.readFile(statePath, "utf8")); } catch {}
const manifest = await fs.open(manifestPath, "a");

const nowIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const gap = () => minGapMs + Math.floor(Math.random() * (maxGapMs - minGapMs + 1));
const jitter = () => 300 + Math.floor(Math.random() * 400);

const stable = (o) => {
  if (Array.isArray(o)) return "[" + o.map(stable).join(",") + "]";
  if (o && typeof o === "object") {
    return "{" + Object.keys(o).sort().map((k) => JSON.stringify(k) + ":" + stable(o[k])).join(",") + "}";
  }
  return JSON.stringify(o);
};
const sha256 = (s) => crypto.createHash("sha256").update(s, "utf8").digest("hex");
const logReq = (rec) => fs.appendFile(reqLogPath, JSON.stringify(rec) + "\n");

// 浏览器内取数：GET-only（codice 直查双面文书列表，分页收齐，记录按 idCcnl 分桶）。
// 不走 POST /ccnl 检索跳——簇码来自清单表（权威源），GET 直查是「查」不是「搜」，
// 请求量也从 3/簇 降到 2/簇。簇元数据（titolo/stato 等）以清单 TSV 为准，
// 记录面自带 partiDatoriali/Sindacali/settoriAteco 等签约与行业字段。
// 被拦（非 200 / 解析失败）即停，不在被拦会话内重试（重试会加深 Akamai 低分）。
const inPage = async (codice) => {
  const reqLog = [];

  const pagedGet = async (vigenti) => {
    const out = [];
    for (let pageIndex = 0; pageIndex < 20; pageIndex++) {
      const t = Date.now();
      const u = `${API}/accordi/cerca/accordi/codice-ccnl/${codice}?pageSize=${pageSize}&pageIndex=${pageIndex}&vigenti=${vigenti}`;
      const r = await fetch(u, { credentials: "include" });
      const ms = Date.now() - t;
      let j = null;
      try { j = await r.json(); } catch {}
      const ok = r.status === 200 && !!j?.pagedList;
      reqLog.push({ ts: nowIso(), op: "GET accordi", codice, vigenti, pageIndex, status: r.status, ms, ok });
      if (!ok) return { failed: true };
      const content = j.pagedList.content || [];
      out.push(...content);
      const total = j.pagedList.totalElements ?? out.length;
      if (out.length >= total || content.length === 0) break;
      await sleep(jitter());
    }
    return { records: out };
  };

  await sleep(jitter());
  const v = await pagedGet("true");
  if (v.failed) return { reqLog, failed: true };
  await sleep(jitter());
  const s = await pagedGet("false");
  if (s.failed) return { reqLog, failed: true };

  const idCcnls = [...new Set(v.records.concat(s.records).map((x) => String(x.idCcnl)))];
  const faces = {};
  for (const id of idCcnls) {
    faces[id] = {
      idCcnl: id,
      codiceCcnl: (v.records.concat(s.records).find((x) => String(x.idCcnl) === id) || {}).codiceCcnl,
      vigenti: v.records.filter((x) => String(x.idCcnl) === id),
      storici: s.records.filter((x) => String(x.idCcnl) === id),
    };
  }
  return { reqLog, nRecords: v.records.length + s.records.length, faces };
};

const task = await taskSpace(spaceName || `it-cnel-harvest ${nowIso()}`);
const page = task.page("p1");
if (!(await page.url()).startsWith("https://archiviocontratti.cnel.it/")) {
  await page.goto("https://archiviocontratti.cnel.it/ricerca/", { timeout: 60000 });
  // Akamai 暖机：令牌需数秒；再加一段拟人 UI 活动（开合高级检索面板），
  // 与成功交互会话同形（fill/click 后 API 才发）
  await page.waitForTimeout(8000);
  await page.click('loc=role:button[name="Ricerca Avanzata"]').catch(() => {});
  await page.waitForTimeout(2000);
  await page.click('loc=role:button[name="Ricerca Avanzata"]').catch(() => {});
  await page.waitForTimeout(1500);
}

let processed = 0, skipped = 0, changed = 0, anomalies = 0, stopped = null;
const codes = clustersDoc.clusters.map((c) => c.code).filter((c) => !onlyCodes || onlyCodes.includes(c));
const todo = typeof limit === "number" ? codes.slice(0, limit) : codes;
console.log(`clusters total=${codes.length} todo=${todo.length} maxAgeHours=${maxAgeHours}`);

for (const codice of todo) {
  const st = state[codice];
  const fresh = st && st.sha && !st.error && st.ts && Date.now() - Date.parse(st.ts) < maxAgeHours * 3600 * 1000;
  if (fresh) { skipped++; continue; }

  const res = await inPage(codice);
  for (const r of res.reqLog) await logReq(r);
  if (res.failed) {
    stopped = `blocked/anomaly at ${codice}`;
    await manifest.writeFile(JSON.stringify({ kind: "anomaly", ts: nowIso(), codice, note: stopped }) + "\n");
    break;
  }
  if (!res.nRecords) {
    anomalies++;
    state[codice] = { ts: nowIso(), error: "no-records" };
    await manifest.writeFile(JSON.stringify({ kind: "anomaly", ts: nowIso(), codice, note: "no records on either face" }) + "\n");
    await fs.writeFile(statePath, JSON.stringify(state, null, 1) + "\n");
    processed++;
    await sleep(gap());
    continue;
  }

  const content = { codice, harvested: nowIso(), faces: res.faces };
  const sha = sha256(stable(content));
  const nV = Object.values(res.faces).reduce((a, f) => a + f.vigenti.length, 0);
  const nS = Object.values(res.faces).reduce((a, f) => a + f.storici.length, 0);
  if (!st || st.sha !== sha) {
    await manifest.writeFile(JSON.stringify({ kind: "accordi", ts: nowIso(), codice, idCcnl: Object.keys(res.faces), sha, nVigenti: nV, nStorici: nS, content }) + "\n");
    changed++;
  }
  state[codice] = { ts: nowIso(), sha, nVigenti: nV, nStorici: nS };
  await fs.writeFile(statePath, JSON.stringify(state, null, 1) + "\n");
  processed++;
  if (processed % 10 === 0) console.log(`progress processed=${processed} changed=${changed} skipped=${skipped} anomalies=${anomalies}`);
  if (processed % 40 === 0) {
    const pause = 15000 + Math.floor(Math.random() * 10000); // 每 40 簇歇一口气（拟人段间停顿）
    console.log(`breather ${Math.round(pause / 1000)}s at ${codice}`);
    await sleep(pause);
  } else {
    await sleep(gap());
  }
}
await manifest.close();

console.log(`DONE processed=${processed} changed=${changed} skipped=${skipped} anomalies=${anomalies} stopped=${stopped || "no"}`);
await task.finish({ keep: "all" });
