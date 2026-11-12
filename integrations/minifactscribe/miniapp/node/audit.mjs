// 事实闸 · 审计引擎
// 语义移植自 FactScribe（MIT, github.com/bigismall-Ai/FactScribe）的
// facts.py / texscan.py / audit.py：
//   · 数字归一化：千分位、LaTeX 千分位空格、量级后缀、单位噪声、百分号、分数
//   · 值域：字面值 ∪ 精确分数商 ∪ 百分号裸值（无隐式四舍五入）
//   · 内联绑定 \fact{ID} / [[fact:ID]]：硬约束，行内数字必须在绑定事实值域内
//   · 引用族 fail-closed：任何 *cite* 命令都算引用，未知命令判红
//   · 账本自检：id 唯一、来源哈希现算、派生算式、同值冲突
//   · 处方层：只给可执行改法，不进判据、不产生分数

import { createHash } from 'node:crypto';

export const EXIT = { OK: 0, RED: 1, CONFIG: 2, YELLOW: 3 };

// 来源材料哈希：对材料正文现算，审计时与账本钉住值比对。
// 上游是 sha256_file(disk) —— 现算文件，而不是信账本里抄的哈希。
function sha256Text(text) {
  return createHash('sha256').update(String(text ?? ''), 'utf8').digest('hex');
}

// ---------------------------------------------------------------- 数字归一化

// 单位只表示量纲，不参与换算；量级后缀才换算（5MB 是单位，5M 是量级）。
const UNIT_ALT =
  'tokens|token|toks|tok|mins|min|ms|secs|sec|hrs|hr|' +
  'GiB|MiB|KiB|TiB|GB|MB|KB|TB|x|×|s|h';
const MAGNITUDE = { k: 1000n, K: 1000n, M: 1000000n, B: 1000000000n };

const NUM_RE = new RegExp(
  '(\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?|\\d+(?:\\.\\d+)?(?:[eE][+-]?\\d+)?)' +
    '(' + UNIT_ALT + '|[kKMB])?' +
    '(\\s*(?:%|percent\\b|pct\\b))?' +
    '(?![\\w])',
  'g',
);

function gcd(a, b) {
  a = a < 0n ? -a : a;
  b = b < 0n ? -b : b;
  while (b) {
    const t = a % b;
    a = b;
    b = t;
  }
  return a;
}

function reduce(n, d) {
  if (d === 0n) return null;
  if (d < 0n) {
    n = -n;
    d = -d;
  }
  const g = gcd(n, d) || 1n;
  return { n: n / g, d: d / g };
}

/** 十进制字符串 → 精确有理数（BigInt），避免浮点误差。 */
export function decToFrac(raw) {
  const t = String(raw).replace(/,/g, '');
  const m = /^(\d+)(?:\.(\d+))?$/.exec(t);
  if (!m) return null;
  const intPart = m[1];
  const fracPart = m[2] || '';
  const den = 10n ** BigInt(fracPart.length);
  const num = BigInt(intPart) * den + BigInt(fracPart || '0');
  return { n: num, d: den };
}

export function fracKey(f) {
  const r = reduce(f.n, f.d);
  return r ? `${r.n}/${r.d}` : null;
}

/** 把规范键还原成人读的形式：能整除 10 的还原成小数。 */
export function formatKey(key) {
  if (!key) return '—';
  const [n, d] = key.split('/').map((x) => BigInt(x));
  if (d === 1n) return n.toString();
  // 分母只含 2 与 5 时可写成有限小数
  let rest = d;
  let twos = 0;
  let fives = 0;
  while (rest % 2n === 0n) {
    rest /= 2n;
    twos += 1;
  }
  while (rest % 5n === 0n) {
    rest /= 5n;
    fives += 1;
  }
  if (rest !== 1n) return `${n}/${d}`;
  const k = Math.max(twos, fives);
  const den = 10n ** BigInt(k);
  const scaled = n * (den / d);
  const s = scaled.toString().padStart(k + 1, '0');
  const ip = s.slice(0, s.length - k) || '0';
  const fp = s.slice(s.length - k).replace(/0+$/, '');
  return fp ? `${ip}.${fp}` : ip;
}

/** 一个数字 token 的规范键（后缀量级会换算，单位不换算，百分号除以 100）。 */
export function numberKey(raw, suffix, percent) {
  const base = decToFrac(raw);
  if (!base) return String(raw);
  let f = base;
  if (suffix) {
    const mag = MAGNITUDE[suffix];
    if (mag) f = { n: f.n * mag, d: f.d };
  }
  if (percent) f = { n: f.n, d: f.d * 100n };
  return fracKey(f);
}

/** 抽出一段文本里的字面数字 token（不做分数展开）。 */
export function literalTokens(text) {
  const out = [];
  const s = String(text ?? '');
  NUM_RE.lastIndex = 0;
  let m;
  while ((m = NUM_RE.exec(s)) !== null) {
    const start = m.index;
    const prev = start > 0 ? s[start - 1] : '';
    // Python 用 (?<![\w.]) 排除 ctex2017 / v2.0 / H2O 这类，JS 无后行断言时手动判定。
    if (prev && /[\w.]/.test(prev)) continue;
    out.push({
      raw: m[1],
      suffix: m[2] || '',
      percent: Boolean(m[3]),
      token: m[0],
      index: start,
    });
  }
  return out;
}

/** 一段文本里的分数 a/b（不与小数点混用）。 */
export function fractionTokens(text) {
  const out = [];
  const s = String(text ?? '');
  const re = /(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)/g;
  let m;
  while ((m = re.exec(s)) !== null) {
    const before = m.index > 0 ? s[m.index - 1] : '';
    const after = s[m.index + m[0].length] ?? '';
    if (before && /[\d.]/.test(before)) continue;
    if (after && /[\d.]/.test(after)) continue;
    const a = decToFrac(m[1]);
    const b = decToFrac(m[2]);
    if (!a || !b || b.n === 0n) continue;
    out.push({ num: a, den: b, index: m.index });
  }
  return out;
}

/** 一个 fact.value 能接受的全部规范数字（值域）。 */
export function factValueKeys(value) {
  const keys = new Set();
  for (const t of literalTokens(value)) {
    keys.add(numberKey(t.raw, t.suffix, t.percent));
    if (t.percent) keys.add(numberKey(t.raw, t.suffix, false));
  }
  for (const f of fractionTokens(value)) {
    const q = reduce(f.num.n * f.den.d, f.num.d * f.den.n);
    if (q) keys.add(`${q.n}/${q.d}`);
  }
  keys.delete('null');
  return keys;
}

/** value 的「声明数」：算式对账时用的代表值（百分号不参与，量级会换算）。 */
export function declaredNumber(value) {
  const toks = literalTokens(value);
  if (!toks.length) return null;
  const t = toks[0];
  let f = decToFrac(t.raw);
  if (!f) return null;
  if (t.suffix && MAGNITUDE[t.suffix]) f = { n: f.n * MAGNITUDE[t.suffix], d: f.d };
  const fr = fractionTokens(value);
  if (fr.length && value.trim().match(/^\s*[\d.]+\s*\/\s*[\d.]+\s*$/)) {
    const q = reduce(fr[0].num.n * fr[0].den.d, fr[0].num.d * fr[0].den.n);
    if (q) return Number(q.n) / Number(q.d);
  }
  return Number(f.n) / Number(f.d);
}

// ---------------------------------------------------------------- 正文扫描

const CITE_IGNORE = new Set([
  'citestyle', 'citetext', 'bibcite', 'citeindextrue', 'citeindexfalse',
]);
const CITE_KNOWN = new Set([
  'cite', 'citep', 'citet', 'citealp', 'citealt', 'citeauthor', 'citeyear',
  'citenum', 'cites', 'nocite', 'upcite', 'parencite', 'textcite', 'autocite',
  'footcite', 'fullcite', 'smartcite', 'supercite', 'notecite', 'citeurl',
  'citefield', 'citetitle', 'citedate', 'citejournal', 'citelist',
]);
const CITE_RE = /\\([A-Za-z]*[Cc]ite[A-Za-z]*)\*?((?:\s*\[[^\]]*\])*)\s*\{([^}]*)\}/g;
const WIKI_FACT_RE = /\[\[\s*fact\s*:\s*([^\]]+?)\s*\]\]/g;
const FACT_CMD_RE = /\\fact\s*\{([^{}]*)\}/g;

// 结构命令：参数里的数字不是正文断言
const STRUCT_ARGS = {
  ref: 1, eqref: 1, pageref: 1, autoref: 1, cref: 1, Cref: 1, nameref: 1, vref: 1,
  label: 1, includegraphics: 1, url: 1, href: 2, input: 1, include: 1,
  subfile: 1, inputminted: 1, bibliography: 1, addbibresource: 1, bibitem: 1,
};
const MACRO_DEFS = new Set([
  'newcommand', 'renewcommand', 'providecommand', 'DeclareRobustCommand',
  'NewDocumentCommand', 'DeclareDocumentCommand', 'def',
]);

const CROSSREF_BEFORE =
  /(表|图|式|附表|附录|表格|Figure|Figures|Fig|TABLE|Table|Equation|Eq|Section|Sec|Chapter|§)\s*$/i;
const CROSSREF_ORDINAL = /第\s*$/;
const CROSSREF_AFTER = /^\s*(节|章|页|条|款)/;

function blankRange(chars, start, end) {
  for (let i = Math.max(0, start); i < Math.min(end, chars.length); i += 1) {
    if (chars[i] !== '\n') chars[i] = ' ';
  }
}

/** 抹掉整块环境与 \verb（保留换行，行号不漂）。 */
function maskEnvironments(text) {
  const chars = text.split('');
  const envRe = new RegExp(
    '\\\\begin\\{(verbatim\\*?|Verbatim|lstlisting|minted|comment\\*?|pkignore|thebibliography)\\}[\\s\\S]*?\\\\end\\{\\1\\}',
    'g',
  );
  let m;
  while ((m = envRe.exec(text)) !== null) blankRange(chars, m.index, m.index + m[0].length);
  const s = chars.join('');
  const verbRe = /\\verb\*?([^A-Za-z\s])/g;
  while ((m = verbRe.exec(s)) !== null) {
    const delim = m[1];
    let end = s.indexOf(delim, m.index + m[0].length);
    if (end < 0) end = s.indexOf('\n', m.index + m[0].length);
    if (end < 0) end = s.length;
    else end += 1;
    blankRange(chars, m.index, end);
  }
  return chars.join('');
}

/** 一行内的 LaTeX 转义与结构命令处理，返回「可抽数字的文本」。 */
function prepareLine(line) {
  let out = '';
  let i = 0;
  while (i < line.length) {
    const c = line[i];
    if (c === '\\') {
      const next = line[i + 1] ?? '';
      if (next === '%') {
        out += '% ';
        i += 2;
        continue;
      }
      if (next === ',' || next === ';' || next === ':' || next === '!' || next === '~') {
        i += 2; // LaTeX 千分位空格：直接删除，数字会合并
        continue;
      }
      if (next === ' ' || next === '\t') {
        i += 2;
        continue;
      }
      const nameMatch = /^\\([A-Za-z]+[0-9]*)/.exec(line.slice(i));
      if (nameMatch) {
        const name = nameMatch[1];
        let j = i + nameMatch[0].length;
        // 可选参数
        while (true) {
          const k = skipWs(line, j);
          if (line[k] === '[') j = balanced(line, k, '[', ']');
          else break;
        }
        if (name === 'fact') {
          const k = skipWs(line, j);
          if (line[k] === '{') {
            const end = balanced(line, k, '{', '}');
            out += ' '.repeat(end - i);
            j = end;
            const k2 = skipWs(line, j);
            if (line[k2] === '{') {
              // \fact{ID}{value}：value 里的数字要留在扫描流里
              const end2 = balanced(line, k2, '{', '}');
              out += line.slice(j, end2);
              j = end2;
            }
            i = j;
            continue;
          }
        }
        if (name === 'cite' || name.toLowerCase().includes('cite')) {
          const k = skipWs(line, j);
          if (line[k] === '{') {
            const end = balanced(line, k, '{', '}');
            out += ' '.repeat(end - i);
            i = end;
            continue;
          }
        }
        if (MACRO_DEFS.has(name)) {
          let j2 = j;
          while (true) {
            const k = skipWs(line, j2);
            if (line[k] === '{') j2 = balanced(line, k, '{', '}');
            else if (line[k] === '[') j2 = balanced(line, k, '[', ']');
            else break;
          }
          out += ' '.repeat(j2 - i);
          i = j2;
          continue;
        }
        const argCount = STRUCT_ARGS[name] || 0;
        if (argCount) {
          let j2 = j;
          for (let n = 0; n < argCount; n += 1) {
            const k = skipWs(line, j2);
            if (line[k] === '{') j2 = balanced(line, j2, '{', '}');
            else break;
          }
          out += ' '.repeat(j2 - i);
          i = j2;
          continue;
        }
        // 普通命令：只抹命令名（吃掉 \foo2 里的数字）
        out += ' '.repeat(nameMatch[0].length);
        i += nameMatch[0].length;
        continue;
      }
      out += c;
      i += 1;
      continue;
    }
    if (c === '~') {
      i += 1; // LaTeX 不断行空格
      continue;
    }
    if (c === '^' || c === '_') {
      // 上下标是结构量：R^2 / x_{12} / a_1 里的数字不算命题
      let j = i + 1;
      while (j < line.length && (line[j] === ' ' || line[j] === '\t')) j += 1;
      if (line[j] === '{') {
        const end = balanced(line, j, '{', '}');
        out += line.slice(i, j).replace(/[^\s]/g, ' ');
        out += ' '.repeat(end - j);
        i = end;
        continue;
      }
      if (j < line.length && /[A-Za-z0-9]/.test(line[j])) {
        out += c;
        out += ' ';
        i = j + 1;
        continue;
      }
      out += c;
      i += 1;
      continue;
    }
    if (c === '%') {
      break; // 注释
    }
    out += c;
    i += 1;
  }
  return out;
}

function skipWs(s, i) {
  let j = i;
  while (j < s.length && (s[j] === ' ' || s[j] === '\t')) j += 1;
  return j;
}

function balanced(s, start, opener, closer) {
  let depth = 0;
  for (let i = start; i < s.length; i += 1) {
    const c = s[i];
    if (c === '\\') {
      i += 1;
      continue;
    }
    if (c === opener) depth += 1;
    else if (c === closer) {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
  }
  return s.length;
}

/** 抽引用：\cite 家族 + pandoc 风格 [@key]。 */
export function scanCitations(text) {
  const cites = [];
  const unknown = [];
  const s = String(text ?? '');
  CITE_RE.lastIndex = 0;
  let m;
  while ((m = CITE_RE.exec(s)) !== null) {
    const name = m[1];
    const lower = name.toLowerCase();
    if (CITE_IGNORE.has(lower)) continue;
    const isKnown = CITE_KNOWN.has(lower);
    const keys = m[3].split(',').map((k) => k.trim()).filter(Boolean);
    for (const key of keys) {
      if (key === '*') continue;
      cites.push({ key, cmd: name, known: isKnown, index: m.index });
    }
    if (!isKnown) unknown.push({ cmd: name, index: m.index });
  }
  const pandoc = /\[@([A-Za-z0-9_][A-Za-z0-9_:.+\-/]*)\]/g;
  while ((m = pandoc.exec(s)) !== null) {
    cites.push({ key: m[1], cmd: 'pandoc', known: true, index: m.index });
  }
  return { cites, unknown };
}

/** 抽事实标记：\fact{ID} / \fact{ID}{value} / [[fact:ID]]。 */
export function scanMarkers(text) {
  const out = [];
  const s = String(text ?? '');
  FACT_CMD_RE.lastIndex = 0;
  let m;
  while ((m = FACT_CMD_RE.exec(s)) !== null) {
    const ids = m[1].split(',').map((x) => x.trim()).filter(Boolean);
    out.push({ ids, index: m.index, form: 'cmd' });
  }
  WIKI_FACT_RE.lastIndex = 0;
  while ((m = WIKI_FACT_RE.exec(s)) !== null) {
    const ids = m[1].split(',').map((x) => x.trim()).filter(Boolean);
    out.push({ ids, index: m.index, form: 'wiki' });
  }
  return out;
}

function isCrossRef(before, after) {
  const b = before.replace(/\s+$/, '');
  if (CROSSREF_ORDINAL.test(b)) return true;
  const m = /([\u4e00-\u9fffA-Za-z]+)\s*$/.exec(b);
  if (m) {
    const word = m[1];
    if (CROSSREF_BEFORE.test(word)) {
      const head = b.slice(0, b.length - word.length);
      // 「的形式 3」这种不是交叉引用
      if (!/[\u4e00-\u9fff]$/.test(head)) return true;
    }
  }
  if (CROSSREF_AFTER.test(after)) return true;
  return false;
}

/** 扫描整篇正文，返回逐行的绑定、数字与引用。 */
export function scanManuscript(text) {
  const raw = String(text ?? '');
  const masked = maskEnvironments(raw);
  const rawLines = raw.split('\n');
  const lines = [];
  let offset = 0;
  const lineOffsets = [];
  for (const l of rawLines) {
    lineOffsets.push(offset);
    offset += l.length + 1;
  }
  rawLines.forEach((line, idx) => {
    const prepared = prepareLine(line);
    const { cites, unknown } = scanCitations(line);
    const markers = scanMarkers(line);
    const bound = [];
    for (const mk of markers) for (const id of mk.ids) bound.push(id);
    const numbers = [];
    for (const t of literalTokens(prepared)) {
      const before = prepared.slice(Math.max(0, t.index - 24), t.index);
      const after = prepared.slice(t.index + t.token.length, t.index + t.token.length + 12);
      const key = numberKey(t.raw, t.suffix, t.percent);
      const crossref = isCrossRef(before, after);
      numbers.push({
        token: t.token.trim(),
        key,
        display: formatKey(key),
        percent: t.percent,
        suffix: t.suffix,
        col: t.index + 1,
        crossref,
        text: line.trim().slice(0, 220),
      });
    }
    lines.push({
      line: idx + 1,
      text: line,
      prepared,
      bound,
      numbers,
      cites,
      unknown,
    });
  });
  return { lines, raw };
}

// ---------------------------------------------------------------- bib 解析

export function parseBib(text) {
  const s = String(text ?? '');
  const entries = [];
  const re = /@(\w+)\s*\{\s*([^,\s}]+)\s*,/g;
  let m;
  while ((m = re.exec(s)) !== null) {
    const type = m[1].toLowerCase();
    const key = m[2].trim();
    const bodyStart = m.index + m[0].length;
    let depth = 1;
    let i = bodyStart;
    while (i < s.length && depth > 0) {
      if (s[i] === '{') depth += 1;
      else if (s[i] === '}') depth -= 1;
      i += 1;
    }
    const body = s.slice(bodyStart, i - 1);
    const fields = {};
    const fre = /(\w+)\s*=\s*(?:\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}|"([^"]*)"|'([^']*)')/g;
    let f;
    while ((f = fre.exec(body)) !== null) {
      fields[f[1].toLowerCase()] = (f[2] ?? f[3] ?? f[4] ?? '').trim();
    }
    entries.push({ type, key, fields });
  }
  return entries;
}

export function stableIdOf(entry) {
  const f = entry.fields || {};
  if (f.doi) return { kind: 'doi', value: f.doi.trim().replace(/^https?:\/\/(dx\.)?doi\.org\//i, '') };
  const arxivIn = (text) => {
    const m = /arxiv[:/\s]*(\d{4}\.\d{4,5})(v\d+)?/i.exec(String(text ?? ''));
    return m ? m[1] : null;
  };
  for (const key of ['arxiv', 'eprint', 'journal', 'note', 'primaryclass']) {
    const id = arxivIn(f[key]);
    if (id) return { kind: 'arxiv', value: id };
  }
  // BibTeX 常见写法：archivePrefix = {arXiv} + eprint = {2310.06770}
  if (f.eprint && /arxiv/i.test(String(f.archiveprefix ?? ''))) {
    const m = /(\d{4}\.\d{4,5})(v\d+)?/.exec(f.eprint);
    if (m) return { kind: 'arxiv', value: m[1] };
  }
  if (f.url) return { kind: 'url', value: f.url.trim() };
  return null;
}

// ---------------------------------------------------------------- 算式求值

/** 只允许四则运算、括号、数字与 fact.id.num / fact.id.den（不用 eval）。 */
export function evalExpr(expr, factsById) {
  const src = String(expr ?? '');
  let pos = 0;
  const peek = () => src[pos];
  const eat = (ch) => {
    if (src[pos] === ch) {
      pos += 1;
      return true;
    }
    return false;
  };
  const skip = () => {
    while (pos < src.length && /\s/.test(src[pos])) pos += 1;
  };
  function parseExpr() {
    let v = parseTerm();
    for (;;) {
      skip();
      if (eat('+')) v += parseTerm();
      else if (eat('-')) v -= parseTerm();
      else return v;
    }
  }
  function parseTerm() {
    let v = parseFactor();
    for (;;) {
      skip();
      if (eat('*')) v *= parseFactor();
      else if (eat('/')) {
        const d = parseFactor();
        if (d === 0) throw new Error('算式除零');
        v /= d;
      } else return v;
    }
  }
  function parseFactor() {
    skip();
    if (eat('-')) return -parseFactor();
    if (eat('+')) return parseFactor();
    if (eat('(')) {
      const v = parseExpr();
      skip();
      if (!eat(')')) throw new Error('算式括号不闭合');
      return v;
    }
    const num = /^\d+(\.\d+)?/.exec(src.slice(pos));
    if (num) {
      pos += num[0].length;
      return Number(num[0]);
    }
    const id = /^[A-Za-z_][A-Za-z0-9_]*(\.(num|den))?/.exec(src.slice(pos));
    if (id) {
      pos += id[0].length;
      const raw = id[0];
      const attr = raw.includes('.') ? raw.split('.')[1] : '';
      const fid = raw.split('.')[0].toLowerCase();
      const fact = factsById[fid];
      if (!fact) throw new Error(`算式引用了不存在的事实 ${fid}`);
      const parts = numericParts(fact.value);
      if (attr === 'num') return parts.num;
      if (attr === 'den') return parts.den;
      if (parts.den === 0) throw new Error(`父事实 ${fid} 分母为 0`);
      return parts.num / parts.den;
    }
    throw new Error(`算式里有解析不了的内容：${src.slice(pos, pos + 12)}`);
  }
  const v = parseExpr();
  skip();
  if (pos < src.length) throw new Error('算式尾部有多余内容');
  return v;
}

function numericParts(value) {
  const s = String(value ?? '').trim();
  const fr = fractionTokens(s);
  if (fr.length && s.match(/^\s*[\d.]+\s*\/\s*[\d.]+\s*$/)) {
    return { num: Number(fr[0].num.n) / Number(fr[0].num.d), den: Number(fr[0].den.n) / Number(fr[0].den.d) };
  }
  const toks = literalTokens(s);
  if (!toks.length) throw new Error(`value 不是数值：${value}`);
  const f = decToFrac(toks[0].raw);
  return { num: Number(f.n) / Number(f.d), den: 1 };
}

// ---------------------------------------------------------------- 处方层

export const PRESCRIPTIONS = {
  UNMATCHED_NUMBER: {
    title: '把这个数字钉回事实账',
    steps: [
      '找到它真正的原始材料（跑批报告、导出表、日志），把那一段贴进「来源材料」。',
      '在事实账新增一条：id / 主张 / 值 / 来源 / sha256 / 定位。',
      '回到正文那行，用 \\fact{ID} 把这一行绑定到这条事实。',
      '如果它其实是结构编号（表 1、图 1、第 3 节），改写成交叉引用，不要当数据。',
    ],
    note: '账外数字＝红线：正文里出现了一个没有任何账能支撑的数。',
  },
  BOUND_MISMATCH: {
    title: '数字与绑定对不上，二选一',
    steps: [
      '核对正文数字与该事实的 value：哪个写错了就改哪个。',
      '如果数字是对的、绑定错了，把 \\fact{ID} 改成真正支撑它的那条账。',
      '如果这条事实的值域确实该含这个数，就在事实账里把 value 写全（可写区间或分数）。',
    ],
    note: '内联绑定是硬约束：绑了就等于宣称这条数由这条账负责。',
  },
  UNBOUND_NUMBER: {
    title: '回得到账，但没钉住',
    steps: [
      '在这行加上 \\fact{ID}，指向真正支撑它的那条事实。',
      '黄牌不是失败，是欠账：不钉住就永远只能算「没核验」。',
    ],
    note: '同一批事实账里存在别的数，不代表这个数就归那笔账。',
  },
  MISSING_CITE: {
    title: 'bib 里没有这个 key',
    steps: [
      '补上这条文献的 bib 条目（必须带 doi 或 arXiv 或 url 之一）。',
      '如果这条引用其实是编造的，删掉它——不要为了让它变绿而造一条。',
    ],
    note: '指向不存在文献的引用，一律判红。',
  },
  BIB_NO_STABLE_ID: {
    title: '这条引用没有稳定标识',
    steps: [
      '补 doi、arxiv 或 url。稳定标识是这条引用能被任何人复核的最低要求。',
      '找不到标识的，多半这条文献本身就不该出现在这里。',
    ],
    note: '没有稳定标识的条目=不可复核。',
  },
  UNKNOWN_CITE_COMMAND: {
    title: '未知的引用命令',
    steps: [
      '改成标准引用命令（\\cite / \\citep / \\citet …）。',
      '如果它是排版命令（citestyle 之类），改个名字，工具只认得已知引用族。',
    ],
    note: '引用族 fail-closed：不认识的 *cite* 命令不许静默放行。',
  },
  DUPLICATE_BIB_KEY: {
    title: 'bib 里 key 重复',
    steps: ['同一个 key 只保留一条；合并字段，或改其中一个 key 并同步改正文引用。'],
    note: '重复 key 会让「引用是否存在」这个问题有两个答案。',
  },
  UNUSED_BIB: {
    title: '这条文献没被引用',
    steps: ['在正文引用它，或者从 bib 里删掉。', '确实要保留的（如预印本与正式版并存），在白名单里登记。'],
    note: '黄牌：留着不判死，但要知道它在那儿。',
  },
  UNUSED_FACT: {
    title: '账上有，文里没用',
    steps: ['在正文相应位置用 \\fact{ID} 绑定它。', '如果这条事实已经不成立了，标记为被新事实取代，别直接删。'],
    note: '事实账只追加：改数＝新增一条并写 supersedes。',
  },
  DUPLICATE_VALUE: {
    title: '两条事实的值相同',
    steps: ['确认是不是同一个量被写了两遍。', '确实是同一个量，就在其中一条上签「同值认可」。'],
    note: '同值可能是笔误，也可能是有意重述——需要人判断。',
  },
  MISSING_SOURCE: {
    title: '来源文件不存在',
    steps: [
      '核对这条事实的 source 指向：路径写错了就改正。',
      '材料还没贴进来，就把对应的原始产物贴进「来源材料」。',
    ],
    note: '与「没填 source 字段」是两回事：这里字段填了，但指向的来源在项目里找不到。',
  },
  MISSING_SOURCE_FIELD: {
    title: '事实缺来源字段',
    steps: ['在事实账里填 source，并把对应的原始材料贴进「来源材料」。'],
    note: '没有来源字段的事实，账有据这一条就无从谈起。',
  },
  MISSING_SOURCE_SHA256: {
    title: '事实没有记录来源哈希',
    steps: ['把来源材料贴进来，工具会现算 sha256 并填上。'],
    note: '哈希是「据未改」的凭据。',
  },
  SOURCE_SHA256_MISMATCH: {
    title: '来源材料被改过了',
    steps: [
      '确认改动是否有意：有意的就把它当成新版本，另存一份来源并新增一条事实。',
      '无意的就恢复原材料——事实账只追加，不要就地改数字。',
    ],
    note: '红线：账本记的哈希与材料现算的不一致，说明据被换过。',
  },
  DUPLICATE_ID: {
    title: '事实 id 重复',
    steps: ['id 按大小写不敏感判重，改其中一个，并同步更新正文的 \\fact{ID}。'],
    note: 'id 重复会让绑定指向不确定的事实。',
  },
  EXPR_MISMATCH: {
    title: '推算值和算式对不上',
    steps: ['重算这条派生事实的 expr，改 value 或改 expr，使两者一致。'],
    note: '派生事实的价值就在于能被重算。',
  },
  DERIVED_CYCLE: {
    title: '推算链成环',
    steps: ['打断环：其中一条事实改用别的父事实，或去掉 derived_from。'],
    note: '成环的推算链无法求值。',
  },
  NUMBER_AS_CROSSREF: {
    title: '这是结构编号，不是数据',
    steps: ['改用交叉引用（\\ref / \\label）指向编号对象，别手写编号。'],
    note: '手写编号不能替代稳定标识。',
  },
  LOW_BINDING_RATE: {
    title: '内联绑定率偏低',
    steps: ['给剩下的数字逐个加 \\fact{ID} 绑定。', '黄牌：还靠「回得到账」撑着，不算已核验。'],
    note: '绑定率低于 50% 时，绿牌的可信度要打折看。',
  },
  CITE_FAKE: {
    title: '这条引用在线核验查无此文',
    steps: [
      '确认 DOI 是否打错、是否是预印本（预印本常有独立 DOI）。',
      '确认无误但仍查不到：这条引用很可能不存在，删掉或换成真实文献。',
    ],
    note: '本地账目过了不代表文献存在——这一条只能联网查。',
  },
  CITE_SUSPECT: {
    title: '文献存在，但元数据对不上',
    steps: ['核对标题、作者、年份是否被写错。', '确认是同一篇的预印本与正式版，可在 bib 里注明。'],
    note: '标题相似度低不等于造假，但值得人看一眼。',
  },
  CITE_UNVERIFIED: {
    title: '这条引用本轮没核验成',
    steps: ['检查网络，或稍后重试。', '黄牌：本轮引用存在性等于没验。'],
    note: '没核验成不等于核验失败，别当成编造。',
  },
  RESOLVE_DEGRADED: {
    title: '联网核验大面积失败',
    steps: ['检查网络连通与 API 限流。', '本轮的引用存在性结论请按「未验」看待。'],
    note: '',
  },
  PROTECT_NUMBER: {
    title: '改写动了数字',
    steps: ['把数字改回原值；如果新数字更对，就新增一条事实并改写绑定，而不是就地改。'],
    note: '改写保护面：事实标记、数字、引用、公式、表格、交叉引用，六类不许变。',
  },
  PROTECT_CITE: {
    title: '改写动了引用',
    steps: ['把引用改回去，或补上新增文献的 bib 条目（带稳定标识）。'],
    note: '',
  },
  PROTECT_FACT: {
    title: '改写动了事实标记',
    steps: ['把 \\fact{ID} 绑定改回去；确实要换绑定，就把新绑定也写进账本。'],
    note: '',
  },
  PROTECT_FORMULA: {
    title: '改写动了公式',
    steps: ['把公式改回去，或在账本里登记新公式后再改。'],
    note: '',
  },
  PROTECT_TABLE: {
    title: '改写动了表格',
    steps: ['把表格改回去；表格里的每个数都要有账可回。'],
    note: '',
  },
  PROTECT_XREF: {
    title: '改写动了交叉引用',
    steps: ['把 \\ref / \\label 改回去。'],
    note: '',
  },
};

// ---------------------------------------------------------------- 主审计

function issue(severity, code, message, extra = {}) {
  return { severity, code, message, ...extra };
}

export function auditProject(project) {
  const issues = [];
  const p = project || {};
  const facts = Array.isArray(p.facts) ? p.facts : [];
  const sources = Array.isArray(p.sources) ? p.sources : [];
  const manuscript = String(p.manuscript ?? '');

  if (!manuscript.trim()) {
    issues.push(issue('red', 'CONFIG', '正文是空的——工具没跑起来，不静默放行。'));
    return finish(issues, null, [], null);
  }
  if (!facts.length) {
    issues.push(issue('red', 'CONFIG', '事实账是空的——没有账就没有「回账」可言。'));
    return finish(issues, null, [], null);
  }

  // ---- 账本自检 ----
  const seenIds = new Map();
  const factsById = {};
  for (const f of facts) {
    const key = String(f.id ?? '').trim().toLowerCase();
    if (!key) {
      issues.push(issue('red', 'BAD_ID_FORMAT', '有事实没有 id。', { location: '事实账' }));
      continue;
    }
    if (seenIds.has(key)) {
      issues.push(issue('red', 'DUPLICATE_ID', `事实 id ${f.id} 重复（id 按大小写不敏感判重）。`, { location: '事实账' }));
      continue;
    }
    seenIds.set(key, f);
    factsById[key] = f;
    f._key = key;
    f._valueKeys = factValueKeys(f.value ?? '');
  }

  const sourceById = new Map();
  for (const s of sources) sourceById.set(String(s.id), s);

  // 现算每个来源的哈希。src.sha256 只是上次记录的缓存值，
  // 「据未改」必须以材料正文现算为准，否则改了正文也不会翻牌。
  const sourceDigest = new Map();
  for (const s of sources) {
    const live = sha256Text(s.text ?? '');
    sourceDigest.set(String(s.id), live);
    s._liveSha256 = live;
  }

  for (const f of facts) {
    // 与 Python 侧对齐（批 139）：缺 source 字段报 MISSING_SOURCE_FIELD；
    // 字段填了但指向的来源在投影里找不到，才报 MISSING_SOURCE（来源文件不存在）。
    const sourceRef = String(f.source ?? '').trim();
    if (!sourceRef) {
      issues.push(issue('red', 'MISSING_SOURCE_FIELD', `事实 ${f.id} 缺 source 字段。`, { location: `事实账:${f.id}` }));
      continue;
    }
    const src = sourceById.get(sourceRef);
    if (!src) {
      issues.push(issue('red', 'MISSING_SOURCE', `事实 ${f.id} 的 source 指向的来源 ${sourceRef} 不存在。`, { location: `事实账:${f.id}` }));
      continue;
    }
    if (!f.sourceSha256) {
      issues.push(issue('red', 'MISSING_SOURCE_SHA256', `事实 ${f.id} 没有记录来源哈希。`, { location: `事实账:${f.id}` }));
      continue;
    }
    const live = sourceDigest.get(String(src.id));
    if (live && f.sourceSha256 !== live) {
      issues.push(issue('red', 'SOURCE_SHA256_MISMATCH', `事实 ${f.id} 的来源材料已被改动（账本哈希 ${String(f.sourceSha256).slice(0, 12)}… vs 现算 ${String(live).slice(0, 12)}…）。`, { location: `来源:${sourceRef}` }));
    }
  }

  // 同值冲突（除非人签认可）
  const byValue = new Map();
  for (const f of facts) {
    const keys = f._valueKeys;
    if (!keys || !keys.size) continue;
    const sig = [...keys].sort().join('|');
    if (!byValue.has(sig)) byValue.set(sig, []);
    byValue.get(sig).push(f);
  }
  for (const group of byValue.values()) {
    if (group.length < 2) continue;
    const signed = group.filter((f) => f.dupOk);
    if (signed.length === group.length) continue;
    issues.push(issue('yellow', 'DUPLICATE_VALUE', `事实 ${group.map((f) => f.id).join('、')} 的值相同（可能是笔误，也可能是有意重述）。`, { location: '事实账' }));
  }

  // 派生事实：expr 求值与 value 对账 + 环检测
  const derivedCycles = findCycles(facts);
  for (const cyc of derivedCycles) {
    issues.push(issue('red', 'DERIVED_CYCLE', `推算链成环：${cyc.join(' → ')}。`, { location: '事实账' }));
  }
  for (const f of facts) {
    if (!f.expr) continue;
    if (derivedCycles.length) continue;
    try {
      const v = evalExpr(f.expr, factsById);
      const declared = declaredNumber(f.value);
      if (declared !== null && Math.abs(v - declared) > 1e-9 * Math.max(1, Math.abs(declared))) {
        issues.push(issue('red', 'EXPR_MISMATCH', `事实 ${f.id} 的推算值 ${round(v)} 与记录的 value（${f.value}）不一致。`, { location: `事实账:${f.id}` }));
      }
    } catch (err) {
      issues.push(issue('red', 'EXPR_INVALID', `事实 ${f.id} 的算式无法求值：${err.message}`, { location: `事实账:${f.id}` }));
    }
  }

  // ---- 正文扫描 ----
  const scan = scanManuscript(manuscript);
  const usedFactIds = new Set();
  const numberToFacts = new Map();
  for (const f of facts) {
    for (const k of f._valueKeys || []) {
      if (!numberToFacts.has(k)) numberToFacts.set(k, []);
      numberToFacts.get(k).push(f.id);
    }
  }

  let bound = 0;
  let unboundYellow = 0;
  let unmatched = 0;
  const ledgerRows = [];

  for (const line of scan.lines) {
    const lineFacts = line.bound.map((id) => factsById[id.toLowerCase()]).filter(Boolean);
    for (const id of line.bound) {
      if (!factsById[id.toLowerCase()]) {
        issues.push(issue('red', 'UNKNOWN_FACT_MARKER', `正文引用了不存在的事实 ${id}。`, { location: `正文:${line.line}` }));
      }
    }
    for (const id of lineFacts) usedFactIds.add(id.id);

    for (const num of line.numbers) {
      if (num.crossref) {
        issues.push(issue('yellow', 'NUMBER_AS_CROSSREF', `数字 ${num.token} 是手写的结构编号，不是数据。`, { location: `正文:${line.line}`, token: num.token, context: num.text }));
        continue;
      }
      if (lineFacts.length) {
        const ok = lineFacts.some((f) => (f._valueKeys || new Set()).has(num.key));
        if (ok) {
          bound += 1;
          ledgerRows.push({ line: line.line, token: num.token, key: num.key, display: num.display, fact: lineFacts.map((f) => f.id).join(','), bound: true });
          continue;
        }
        unmatched += 1;
        issues.push(issue('red', 'BOUND_MISMATCH', `该行绑定了 ${lineFacts.map((f) => f.id).join('、')}，但数字 ${num.token}（${num.display}）不在它们的值域里。`, { location: `正文:${line.line}`, token: num.token, context: num.text }));
        ledgerRows.push({ line: line.line, token: num.token, key: num.key, display: num.display, fact: lineFacts.map((f) => f.id).join(','), bound: false });
        continue;
      }
      const hit = numberToFacts.get(num.key);
      if (hit && hit.length) {
        unboundYellow += 1;
        issues.push(issue('yellow', 'UNBOUND_NUMBER', `数字 ${num.token} 回得到账（${hit.join('、')}），但正文没内联绑定——只算黄，不算已核验。`, { location: `正文:${line.line}`, token: num.token, context: num.text }));
        ledgerRows.push({ line: line.line, token: num.token, key: num.key, display: num.display, fact: hit.join(','), bound: false });
      } else {
        unmatched += 1;
        issues.push(issue('red', 'UNMATCHED_NUMBER', `数字 ${num.token}（${num.display}）回不到任何事实的 value。`, { location: `正文:${line.line}`, token: num.token, context: num.text }));
        ledgerRows.push({ line: line.line, token: num.token, key: num.key, display: num.display, fact: '', bound: false });
      }
    }
  }

  for (const f of facts) {
    if (!usedFactIds.has(f.id)) {
      issues.push(issue('yellow', 'UNUSED_FACT', `账上有、文里没用：事实 ${f.id}（${f.claim || ''}）。`, { location: `事实账:${f.id}` }));
    }
  }

  const denom = bound + unboundYellow + unmatched;
  if (denom >= 4 && bound / denom < 0.5) {
    issues.push(issue('yellow', 'LOW_BINDING_RATE', `内联绑定率 ${bound}/${denom} 低于 50%——大部分数字只是「回得到账」，还没回到对的那条账。`, { location: '正文' }));
  }

  // ---- 引用检查 ----
  const bibEntries = parseBib(p.bib ?? '');
  const bibByKey = new Map();
  for (const e of bibEntries) {
    if (bibByKey.has(e.key)) {
      issues.push(issue('red', 'DUPLICATE_BIB_KEY', `bib 里 key ${e.key} 定义了不止一次。`, { location: `refs.bib:${e.key}` }));
      continue;
    }
    bibByKey.set(e.key, e);
  }
  const usedKeys = new Map();
  for (const line of scan.lines) {
    for (const c of line.cites) {
      usedKeys.set(c.key, (usedKeys.get(c.key) || 0) + 1);
      if (!bibByKey.has(c.key)) {
        issues.push(issue('red', 'MISSING_CITE', `引用了 bib 里不存在的 key ${c.key}。`, { location: `正文:${line.line}`, token: c.key, context: line.text.trim().slice(0, 220) }));
      }
    }
    for (const u of line.unknown) {
      issues.push(issue('red', 'UNKNOWN_CITE_COMMAND', `未知的引用命令 \\${u.cmd}——引用族 fail-closed，不许静默放行。`, { location: `正文:${line.line}`, context: line.text.trim().slice(0, 220) }));
    }
  }
  for (const e of bibEntries) {
    if (!usedKeys.has(e.key)) {
      issues.push(issue('yellow', 'UNUSED_BIB', `bib 条目 ${e.key} 没有被正文引用。`, { location: `refs.bib:${e.key}` }));
      continue;
    }
    const sid = stableIdOf(e);
    if (!sid) {
      issues.push(issue('red', 'BIB_NO_STABLE_ID', `bib 条目 ${e.key} 既没有 arxiv 也没有 doi（不可复核）。`, { location: `refs.bib:${e.key}` }));
    }
  }

  const matrix = buildMatrix(facts, ledgerRows, usedKeys, bibEntries);
  return finish(issues, { scan, factsById, ledgerRows, usedKeys, bibEntries }, matrix, {
    bound,
    unboundYellow,
    unmatched,
    denom,
  });
}

function round(v) {
  if (!Number.isFinite(v)) return String(v);
  return Math.abs(v - Math.round(v)) < 1e-9 ? String(Math.round(v)) : String(Number(v.toFixed(6)));
}

function numericPartsSafe(value) {
  try {
    return numericParts(value);
  } catch {
    return { num: 0, den: 1 };
  }
}

function findCycles(facts) {
  const graph = new Map();
  for (const f of facts) {
    const deps = (f.derivedFrom && f.derivedFrom.length ? f.derivedFrom : []).map((d) => String(d).trim().toLowerCase());
    graph.set(String(f.id).toLowerCase(), deps);
  }
  const color = new Map();
  const stack = [];
  const out = [];
  const dfs = (u) => {
    color.set(u, 1);
    stack.push(u);
    for (const v of graph.get(u) || []) {
      if (!graph.has(v)) continue;
      if (color.get(v) === 0) dfs(v);
      else if (color.get(v) === 1) {
        const idx = stack.indexOf(v);
        if (idx >= 0) out.push([...stack.slice(idx), v]);
      }
    }
    stack.pop();
    color.set(u, 2);
  };
  for (const k of graph.keys()) if ((color.get(k) || 0) === 0) dfs(k);
  return out;
}

function buildMatrix(facts, ledgerRows, usedKeys, bibEntries) {
  const rows = facts.map((f) => {
    const hits = ledgerRows.filter((r) => r.fact.split(',').includes(f.id));
    const boundHits = hits.filter((h) => h.bound);
    return {
      id: f.id,
      claim: f.claim || '',
      value: f.value || '',
      source: f.source || '',
      locator: f.locator || '',
      sha256: f.sourceSha256 || '',
      confidence: f.confidence || '',
      derived: Boolean(f.expr),
      inText: hits.length > 0,
      boundLines: [...new Set(boundHits.map((h) => h.line))].sort((a, b) => a - b),
      usedIn: boundHits.length ? '已内联绑定' : hits.length ? '只命中值域（未绑定）' : '未被引用',
    };
  });
  const citeRows = bibEntries.map((e) => ({
    key: e.key,
    title: e.fields.title || '',
    year: e.fields.year || '',
    stableId: stableIdOf(e),
    cited: usedKeys.get(e.key) || 0,
  }));
  return { facts: rows, citations: citeRows };
}

function finish(issues, ctx, matrix, stats) {
  const red = issues.filter((i) => i.severity === 'red');
  const yellow = issues.filter((i) => i.severity === 'yellow');
  let verdict = 'green';
  let exitCode = EXIT.OK;
  if (red.length) {
    verdict = 'red';
    exitCode = EXIT.RED;
  } else if (yellow.length) {
    verdict = 'yellow';
    exitCode = EXIT.YELLOW;
  }
  const prescriptions = {};
  for (const i of issues) {
    if (!prescriptions[i.code]) {
      const p = PRESCRIPTIONS[i.code];
      prescriptions[i.code] = p ? { title: p.title, steps: p.steps, note: p.note } : null;
    }
  }
  const foldedRed = foldIssues(red);
  const foldedYellow = foldIssues(yellow);
  return {
    verdict,
    exitCode,
    issues,
    red,
    yellow,
    // 呈现用：同一来源的失配折叠成一条。判定数组 red/yellow 原样保留。
    redShown: foldedRed,
    yellowShown: foldedYellow,
    redCount: red.length,
    yellowCount: yellow.length,
    matrix,
    stats,
    prescriptions,
    lines: ctx && ctx.scan ? ctx.scan.lines : [],
  };
}

// ---------------------------------------------------------------- 改写保护面

const PROTECT_CLASSES = [
  { key: 'facts', label: '事实标记', code: 'PROTECT_FACT' },
  { key: 'numbers', label: '数字', code: 'PROTECT_NUMBER' },
  { key: 'cites', label: '引用', code: 'PROTECT_CITE' },
  { key: 'formulas', label: '公式', code: 'PROTECT_FORMULA' },
  { key: 'tables', label: '表格', code: 'PROTECT_TABLE' },
  { key: 'xrefs', label: '交叉引用', code: 'PROTECT_XREF' },
];

function multiset(items) {
  const m = new Map();
  for (const it of items) m.set(it, (m.get(it) || 0) + 1);
  return m;
}

function diffMultiset(a, b) {
  const ma = multiset(a);
  const mb = multiset(b);
  const out = [];
  for (const [k, n] of ma) {
    const d = n - (mb.get(k) || 0);
    if (d > 0) out.push({ item: k, count: d });
  }
  for (const [k, n] of mb) {
    const d = n - (ma.get(k) || 0);
    if (d < 0) out.push({ item: k, count: -d });
  }
  return out;
}

function protectExtract(text) {
  const s = String(text ?? '');
  const scan = scanManuscript(s);
  const facts = [];
  const numbers = [];
  const cites = [];
  const xrefs = [];
  const formulas = [];
  const tables = [];
  for (const line of scan.lines) {
    for (const mk of scanMarkers(line.text)) for (const id of mk.ids) facts.push(id);
    for (const n of line.numbers) {
      if (n.crossref) continue;
      numbers.push(n.key);
    }
    for (const c of line.cites) cites.push(c.key);
    const xr = /\\(?:ref|eqref|autoref|cref|Cref|nameref|label)\s*\{([^}]*)\}/g;
    let m;
    while ((m = xr.exec(line.text)) !== null) xrefs.push(m[1]);
    const fm = /\$\$[\s\S]*?\$\$|\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$[^$\n]+\$/g;
    while ((m = fm.exec(line.text)) !== null) formulas.push(m[0].replace(/\s+/g, ' ').trim());
    if (/^\s*\|/.test(line.text)) tables.push(line.text.replace(/\s+/g, ' ').trim());
  }
  return { facts, numbers, cites, xrefs, formulas, tables };
}

export function protectDiff(before, after) {
  const b = protectExtract(before);
  const a = protectExtract(after);
  const issues = [];
  for (const cls of PROTECT_CLASSES) {
    const diff = diffMultiset(b[cls.key], a[cls.key]);
    for (const d of diff) {
      const raw = cls.key === 'numbers' ? formatKey(d.item) : String(d.item).replace(/\s+/g, ' ').trim();
      const shown = raw.length > 60 ? raw.slice(0, 60) + '…' : raw;
      issues.push(issue('red', cls.code, `${cls.label}变了：${d.count > 0 ? '少了' : '多了'} ${shown}。`, { location: cls.label, token: d.item }));
    }
  }
  const verdict = issues.length ? 'red' : 'green';
  return {
    verdict,
    exitCode: issues.length ? EXIT.RED : EXIT.OK,
    issues,
    before: b,
    after: a,
  };
}

export { PROTECT_CLASSES };

/**
 * 把联网核验结果并进判据：本地账目过了不代表文献真的存在。
 * 只有被正文引用的条目才升级为红/黄——没被引用的条目不参与判死。
 */
/**
 * 呈现层折叠：同一来源材料被改动时，会按 fact 逐条报失配（与上游一致）。
 * 但一份材料对应几十条事实时，报告会被几十条几乎相同的红牌淹没。
 * 这里只在展示层合并：同一来源合并成一条，列出受影响的 fact id。
 * 判定层（red/yellow 数组、退出码）不变。
 */
export function foldIssues(issues) {
  const out = [];
  const bySource = new Map();
  for (const i of issues || []) {
    if (i.code !== 'SOURCE_SHA256_MISMATCH') {
      out.push(i);
      continue;
    }
    const key = String(i.location || '');
    if (!bySource.has(key)) bySource.set(key, []);
    bySource.get(key).push(i);
  }
  for (const [loc, group] of bySource) {
    if (group.length === 1) {
      out.push(group[0]);
      continue;
    }
    const ids = group
      .map((g) => String(g.message || '').match(/^事实\s+(\S+?)\s/)?.[1])
      .filter(Boolean);
    out.push({
      ...group[0],
      message:
        '来源材料「' + loc.replace(/^来源:/, '') + '」已被改动，影响 ' + group.length + ' 条事实（' +
        ids.join('、') + '）。账本钉的哈希是 ' + String(group[0].message).match(/账本哈希\s*(\S+?…)/)?.[1] + '，材料现算是 ' +
        String(group[0].message).match(/现算\s*(\S+?…)/)?.[1] + '。',
      folded: group.length,
    });
  }
  return out;
}

export function mergeVerifyIssues(audit, verify) {
  const issues = [...(audit.issues || [])];
  const cited = new Map((audit.matrix?.citations || []).map((c) => [c.key, c.cited]));
  for (const r of (verify && verify.results) || []) {
    const used = (cited.get(r.key) || 0) > 0;
    if (r.status === 'not_found' && used) {
      issues.push(issue('red', 'CITE_FAKE', `引用 ${r.key} 的稳定标识（${r.kind}:${r.id}）在线查无此文。`, { location: 'refs.bib:' + r.key, token: r.key }));
    } else if (r.status === 'suspect' && used) {
      issues.push(issue('yellow', 'CITE_SUSPECT', `引用 ${r.key} 的元数据与来源对不上：${r.detail}`, { location: 'refs.bib:' + r.key, token: r.key }));
    } else if (r.status === 'unverified' && used) {
      issues.push(issue('yellow', 'CITE_UNVERIFIED', `引用 ${r.key} 本轮没核验成：${r.detail}`, { location: 'refs.bib:' + r.key, token: r.key }));
    }
  }
  if (verify && verify.total && verify.failures / verify.total > 0.5) {
    issues.push(issue('yellow', 'RESOLVE_DEGRADED', `联网核验 ${verify.failures}/${verify.total} 条都没成功（限流/无网？）——引用存在性本轮等于没验。`, { location: '引用核验' }));
  }
  const red = issues.filter((i) => i.severity === 'red');
  const yellow = issues.filter((i) => i.severity === 'yellow');
  const verdict = red.length ? 'red' : yellow.length ? 'yellow' : 'green';
  const exitCode = red.length ? EXIT.RED : yellow.length ? EXIT.YELLOW : EXIT.OK;
  const prescriptions = { ...(audit.prescriptions || {}) };
  for (const i of issues) {
    if (!prescriptions[i.code]) {
      const p = PRESCRIPTIONS[i.code];
      prescriptions[i.code] = p ? { title: p.title, steps: p.steps, note: p.note } : null;
    }
  }
  const foldedRed = foldIssues(red);
  const foldedYellow = foldIssues(yellow);
  return {
    ...audit,
    issues,
    red,
    yellow,
    // 折叠视图必须跟着新的 issues 重算——不能沿用基础审计的旧值，
    // 否则核验加入的红牌在页面上不显示。
    redShown: foldedRed,
    yellowShown: foldedYellow,
    redCount: red.length,
    yellowCount: yellow.length,
    verdict,
    exitCode,
    prescriptions,
  };
}