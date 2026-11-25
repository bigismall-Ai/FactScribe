// 正文行尾保真：把「浏览器归一掉的行尾」按原文件的风格找回来。
//
// 为什么需要这一层：
//
//   1. HTML 规范规定 textarea 的 API value 归一为 LF（实测：真 Chrome 158，
//      textarea.value = "A\r\nB" 读回来是 "A\nB"）——浏览器这一层拿不到 CRLF。
//   2. 引擎的读路径（factscribe/config.py 的 read_text）做通用换行翻译，
//      CRLF 在到达浏览器之前就已经变成 LF 了——接口层也拿不到原始行尾。
//
// 所以行尾的「真相」只在磁盘上的原文件里。这一模块只做两件事：
//
//   * 读出原文件用哪种行尾（crlf / lf / mixed）；
//   * 把编辑后的正文按那种风格重新写回。
//
// 只碰行尾，不碰内容：段落文字、全角字符、emoji、\fact{}/\cite{} 标记、
// 段内换行——一个字符都不动。

/** 换行只有两种：\r\n 与 \n。落单的 \r 当作正文里的普通字符，不当行尾。 */
export const CRLF = '\r\n';
export const LF = '\n';

/**
 * 把文本切成 [{content, ending}]：行尾单独摘出来，行内容原样保留。
 *
 * 刻意不用 String.prototype.split('\n')：那样会把 '\r' 留在行内容里，
 * 重建时 \r\n 就会变成 '\r' + 换行，行尾就拼错了。
 */
export function splitKeepEnds(text) {
  const source = String(text ?? '');
  const out = [];
  let index = 0;
  while (index <= source.length) {
    const nl = source.indexOf('\n', index);
    if (nl === -1) {
      if (index < source.length) out.push({ content: source.slice(index), ending: '' });
      break;
    }
    // '\r\n' 是一个行尾；落单的 '\r' 留在行内容里（当正文看）。
    const hasCr = nl > index && source[nl - 1] === '\r';
    const contentEnd = hasCr ? nl - 1 : nl;
    out.push({
      content: source.slice(index, contentEnd),
      ending: source.slice(contentEnd, nl + 1),
    });
    index = nl + 1;
  }
  return out;
}

/** 数一数文本里的行尾种类。 */
export function detectEol(text) {
  let crlf = 0;
  let lf = 0;
  for (const line of splitKeepEnds(text)) {
    if (line.ending === CRLF) crlf += 1;
    else if (line.ending === LF) lf += 1;
  }
  let style = 'none';
  if (crlf && lf) style = 'mixed';
  else if (crlf) style = 'crlf';
  else if (lf) style = 'lf';
  return { style, crlf, lf };
}

/**
 * 原文件的主导行尾：CRLF 多就用 CRLF，LF 多就用 LF。
 *
 * 计数相同时取 CRLF——与引擎侧 factscribe/textio.py::dominant_newline 同一口径。
 * 原文件一行都没有行尾时用 fallback（LF）。
 */
export function dominantEnding(text, fallback = LF) {
  const { crlf, lf } = detectEol(text);
  if (crlf === 0 && lf === 0) return fallback;
  return crlf >= lf ? CRLF : LF;
}

/**
 * 把正文里所有行尾换成 ending；行内容一个字不动。
 *
 * 「末行有没有行尾」这个结构也原样保留：原文本末尾没有换行，换完还是没有。
 */
export function applyEnding(text, ending) {
  if (!ending) return String(text ?? '');
  return splitKeepEnds(text)
    .map((line) => line.content + (line.ending ? ending : ''))
    .join('');
}

/**
 * 传给引擎的形态：一律 LF，不带 '\r'。
 *
 * 引擎的写路径是 Python 文本模式（newline=None）：Windows 上每个 '\n' 会被
 * 翻成 '\r\n'，已经存在的 '\r\n' 会被写成 '\r\r\n'（内容损坏）。
 * 所以 '\r' 绝不进引擎那一层；行尾由本模块在引擎写完后按原风格校正。
 */
export function toLfOnly(text) {
  return String(text ?? '').replace(/\r\n/g, '\n');
}

/** 只要行内容（不要行尾）：用来判断「内容有没有被别人改过」。 */
export function lineContents(text) {
  return splitKeepEnds(text).map((line) => line.content);
}

/** 行内容序列一致＝只差行尾；不一致＝有人改过正文，不能覆盖。 */
export function sameContent(a, b) {
  const left = lineContents(a);
  const right = lineContents(b);
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}
