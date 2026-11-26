# -*- coding: utf-8 -*-
"""七条线的**适配点**：每条线的闸结果 + 逐条收据。

七条线（与核验槽的五闸 + 两条判例线对齐）
------------------------------------------
    id        线            国家    件型    闸
    fr        法国法条       法国    法条    verify
    cn        中国法规       中国    法规    verify-cn
    case      中国案例       中国    案例    verify-case
    it        意大利法条     意大利  法条    verify-it
    es        西班牙法条     西班牙  法条    verify-es
    fr-case   法国判例       法国    判例    verify-fr-case
    it-case   意大利判例     意大利  判例    verify-it-case

本件只做**适配**：闸的判定语义一行不动（判定码、措辞、退出码全由各闸自己
说了算），本件只负责

  ① 把各闸的 findings 归一成接口层的统一形状；
  ② 告诉共用收据逻辑（factscribe_legal.receipts）每条线
     **材料在哪、命中面怎么定、怎么核验**。

各线的材料形态与适配点
----------------------
    线       官方材料                    span 取自    face           how
    -------  --------------------------  ----------  -------------  -------------
    fr       条文 XML（BLOC_TEXTUEL）    条文正文    body / —       归一后 contains
    cn       详情 JSON（**无正文**）      —（无正文）  —（缺省）      catalog
    case     官方案例正文 txt            正文        body / —       contains/numnorm
    it       AKN 条文切片 XML            切片正文    body / —       contains
    es       BOE 条文块切片 XML          切片正文    body / —       contains
    fr-case  判决 XML + 纯文本还原件     txt 全文    body/résumé    contains/numnorm
    it-case  判决档案切片 XML            切片正文    body / —       contains/numnorm

本件只读、零 LLM、零网络、不写盘。
"""
import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from . import receipts
from .case_verify import CASE_CARD_RE, verify_case
from .cn_verify import CARD_RE as CN_CARD_RE
from .cn_verify import verify_cn
from .es_verify import _plain_text as _es_plain_text
from .es_verify import verify_es
from .fr_case_verify import CARD_RE as FR_CASE_CARD_RE
from .fr_case_verify import verify_fr_case
from .it_case_verify import CARD_SUFFIX as ITCASE_CARD_SUFFIX
from .it_case_verify import _itcase_plain
from .it_case_verify import verify_it_case
from .it_verify import _plain_text as _it_plain_text
from .it_verify import verify_it
from .provisions import norm_text
from .verify import PROV_RE, load_facts, verify as verify_fr

__all__ = ["Line", "LINES", "LineContext", "LineResult", "line_by_id",
           "collect", "collect_one", "fr_official_text"]

# 各域证据卡的后缀（归属判据：靠文件名后缀，不靠卡内标记——与各闸同一套）
OTHER_DOMAIN_SUFFIXES = (".cn.card.txt", ".case.card.txt", ".it.card.txt",
                         ".es.card.txt", ".fr-case.card.txt", ".itcase.card.txt")


@dataclass(frozen=True)
class Line:
    """一条线的身份（域 / 件型 / 对应闸）。"""
    id: str
    label: str
    country: str
    kind: str
    gate: str


LINES = (
    Line("fr", "法国法条", "法国", "法条", "verify"),
    Line("cn", "中国法规", "中国", "法规", "verify-cn"),
    Line("case", "中国案例", "中国", "案例", "verify-case"),
    Line("it", "意大利法条", "意大利", "法条", "verify-it"),
    Line("es", "西班牙法条", "西班牙", "法条", "verify-es"),
    Line("fr-case", "法国判例", "法国", "判例", "verify-fr-case"),
    Line("it-case", "意大利宪法法院判例", "意大利", "判例", "verify-it-case"),
)

# 法国法条：法文数字词（法国闸的 contains_number 认法文数字词）
_FR_NUM_WORDS = set()


def _init_fr_words():
    from . import provisions
    for w in provisions._UNITS:
        _FR_NUM_WORDS.add(w)
    for w in provisions._TENS:
        _FR_NUM_WORDS.add(w)


_init_fr_words()


@dataclass
class LineContext:
    """跑一条线需要的全部材料（全是路径与参考日，零写盘）。"""
    project_dir: str = ""
    corpus_dir: str = ""        # 语料视图根（FR 索引 / it / es / cn 都在底下）
    date: str = ""              # 参考日 YYYY-MM-DD
    view: str = ""              # 现行视图 JSONL（可选）
    catalog: str = ""           # 中国全库目录（可选）
    itcase_dir: str = ""        # 意大利判例语料 run 目录（可选）


@dataclass
class LineResult:
    """一条线的产出：闸结果 + 收据 + 状态。"""
    line: Line
    status: str = "na"          # ran / skipped / na
    note: str = ""
    findings: list = field(default_factory=list)
    receipts: list = field(default_factory=list)
    red: int = 0
    yellow: int = 0

    def finding_dicts(self):
        """findings → 接口层统一形状（码名/红黄/位置/措辞照抄，不改写）。"""
        out = []
        for f in self.findings:
            item = {"code": f.code,
                    "severity": f.severity,
                    "location": f.location,
                    "message": f.message}
            detail = getattr(f, "detail", "") or ""
            if detail:
                item["detail"] = detail
            out.append(item)
        return out


def line_by_id(line_id):
    for ln in LINES:
        if ln.id == line_id:
            return ln
    return None


# ---------------------------------------------------------------------------
# 材料查找（各线共用的小工具）
# ---------------------------------------------------------------------------

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def _read_bytes(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def _card_fields(path):
    """证据卡头部字段（遇 '--- OFFICIAL TEXT ---' 停；不读内嵌正文段）。"""
    out = {}
    for line in _read_text(path).splitlines():
        if line.startswith("--- OFFICIAL TEXT ---"):
            break
        if ":" not in line or line.startswith("#") or line.startswith("---"):
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def _embedded_official_text(path):
    """证据卡内嵌的官方正文段（'--- OFFICIAL TEXT ---' 之后）。"""
    text = _read_text(path)
    marker = "--- OFFICIAL TEXT ---"
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].lstrip("\n")


def _section_index(base_dir, section, key):
    """扫 <base>/<section> 下所有 index.json → {条目键: (目录, 条目, 索引)}。"""
    out = {}
    if not base_dir or not os.path.isdir(base_dir):
        return out
    roots = []
    sub = os.path.join(base_dir, section)
    if os.path.isfile(os.path.join(sub, "index.json")):
        roots.append(sub)
    elif os.path.isdir(sub):
        for name in sorted(os.listdir(sub)):
            d = os.path.join(sub, name)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "index.json")):
                roots.append(d)
    for root in roots:
        idx = _read_json(os.path.join(root, "index.json")) or {}
        for k, meta in (idx.get(key) or {}).items():
            out.setdefault(k, (root, meta, idx))
    return out



def _index_articles(base_dir, key="articles"):
    """语料目录里的 index.json → {条目键: (目录, 条目, 索引)}。

    语料目录本身就是「run 目录」（index.json 在它根上——与各闸读语料的
    约定一致），所以直接读它，不按打包形态再翻一层。
    """
    out = {}
    if not base_dir:
        return out
    idx = _read_json(os.path.join(base_dir, "index.json")) or {}
    for k, meta in (idx.get(key) or {}).items():
        out[k] = (base_dir, meta, idx)
    return out

def _resolve_section_dir(corpus_dir, section, key):
    """找某份子语料（it / es / it-case）的目录。

    两种布局都认：
      1. <corpus>/<section>/index.json      —— 项目语料视图（核验槽的约定）
      2. <corpus>/index.json 里带 key 段     —— 这一份语料**就是**语料视图根
         （打包形态：it/<run>、es/<run>、it-case/<run> 各自是一个 run 目录）
    找不到 → 空串（调用方按「材料没拿到」处理）。
    """
    if not corpus_dir:
        return ""
    sub = os.path.join(corpus_dir, section)
    if os.path.isfile(os.path.join(sub, "index.json")):
        return sub
    idx = _read_json(os.path.join(corpus_dir, "index.json")) or {}
    if key in idx:
        return corpus_dir
    return ""

def fr_official_text(ctx, src):
    """法国法条的官方条文正文（公开出口；与 _fr_receipts 同一份取文逻辑）。"""
    return _fr_official_text(ctx, src)


def _face_of(value, body_text, full_text):
    """命中面：正文 → body；只在正文之外命中 → résumé；没命中 → 缺省标记。"""
    if not value:
        return receipts.MISSING
    if body_text and receipts.contains_norm(value, body_text):
        return "body"
    if full_text and receipts.contains_norm(value, full_text):
        return "résumé"
    return receipts.MISSING


def _is_other_domain(src):
    return str(src or "").endswith(OTHER_DOMAIN_SUFFIXES)


# ---------------------------------------------------------------------------
# 七条线：闸结果 + 收据
# ---------------------------------------------------------------------------

def _run_fr(ctx):
    line = LINES[0]
    if not ctx.corpus_dir:
        return LineResult(line, "skipped", "语料视图未声明（corpus 为空）")
    try:
        findings, _corpus = verify_fr(ctx.project_dir, ctx.corpus_dir, ctx.date,
                                     ctx.view or None)
    except FileNotFoundError as exc:
        return LineResult(line, "skipped", "FR 语料读不了：%s" % exc)
    return LineResult(line, "ran", "", findings, _fr_receipts(ctx))


def _fr_official_text(ctx, src):
    """法国法条：卡里钉的官方 XML（或事实直接指向的 XML）→ 条文正文。"""
    path = os.path.join(ctx.project_dir, src) if src else ""
    if not path:
        return ""
    if src.endswith(".card.txt"):
        fields = _card_fields(path)
        off = fields.get("OFFICIAL_XML") or ""
        if not off:
            return ""
        path = os.path.join(os.path.dirname(path), off)
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as fh:
            root = ET.fromstring(fh.read())
    except (OSError, ET.ParseError):
        return ""
    block = root.find("BLOC_TEXTUEL")
    if block is None:
        return ""
    return norm_text(block)


def _fr_how(value):
    """法国法条：数字（阿拉伯或法文数字词）走归一 ⇒ numnorm；其余逐字。"""
    raw = str(value if value is not None else "").strip()
    if not raw:
        return receipts.MISSING
    if receipts.classify_how(raw) == "numnorm":
        return "numnorm"
    if raw.lower().replace(" ", "-") in _FR_NUM_WORDS:
        return "numnorm"
    return "contains"


def _fr_receipts(ctx):
    out = []
    for fact in load_facts(ctx.project_dir):
        src = fact.get("source", "")
        if _is_other_domain(src) or not PROV_RE.match(src):
            continue
        text = _fr_official_text(ctx, src)
        value = fact.get("value")
        span = receipts.span_in_text(value, text) if text else receipts.MISSING
        face = _face_of(value, text, text) if text else receipts.MISSING
        out.append(receipts.build_receipt(fact.get("id"),
                                          fact.get("source_sha256"),
                                          span, face, _fr_how(value)))
    return out


def _run_cn(ctx):
    line = LINES[1]
    if not ctx.catalog:
        return LineResult(line, "skipped", "中国全库目录没拿到（catalog 为空）")
    try:
        findings = verify_cn(ctx.project_dir, ctx.catalog, ctx.date)
    except Exception as exc:  # noqa: BLE001 —— 材料坏了不许穿透成堆栈
        return LineResult(line, "skipped", "CN 材料读不了：%s" % exc)
    return LineResult(line, "ran", "", findings, _cn_receipts(ctx))


def _cn_receipts(ctx):
    """中国法规：官方详情 JSON **无正文** ⇒ span/face 缺省，how＝目录树对账。"""
    out = []
    for fact in load_facts(ctx.project_dir):
        src = fact.get("source", "")
        if not CN_CARD_RE.match(src):
            continue
        out.append(receipts.build_receipt(fact.get("id"),
                                          fact.get("source_sha256"),
                                          receipts.MISSING, receipts.MISSING,
                                          "catalog"))
    return out


def _run_case(ctx):
    line = LINES[2]
    try:
        findings = verify_case(ctx.project_dir)
    except Exception as exc:  # noqa: BLE001
        return LineResult(line, "skipped", "案例材料读不了：%s" % exc)
    return LineResult(line, "ran", "", findings, _case_receipts(ctx))


def _case_receipts(ctx):
    """中国案例：官方正文在项目内 runs/<run>/official/<slug>.txt。"""
    out = []
    for fact in load_facts(ctx.project_dir):
        src = fact.get("source", "")
        m = CASE_CARD_RE.match(src)
        if not m:
            continue
        run, slug = m.group("run"), m.group("slug")
        text = _read_text(os.path.join(ctx.project_dir, "runs", run,
                                       "official", "%s.txt" % slug))
        value = fact.get("value")
        span = receipts.span_in_text(value, text) if text else receipts.MISSING
        face = _face_of(value, text, text) if text else receipts.MISSING
        out.append(receipts.build_receipt(fact.get("id"),
                                          fact.get("source_sha256"),
                                          span, face,
                                          receipts.classify_how(value)))
    return out


def _run_it(ctx):
    line = LINES[3]
    it_dir = _resolve_section_dir(ctx.corpus_dir, "it", "articles")
    if not it_dir or not os.path.isdir(it_dir):
        return LineResult(line, "skipped", "意大利语料没拿到（it/ 目录不在）")
    try:
        findings, _index = verify_it(ctx.project_dir, it_dir, ctx.date)
    except FileNotFoundError as exc:
        return LineResult(line, "skipped", "意大利语料读不了：%s" % exc)
    except Exception as exc:  # noqa: BLE001
        return LineResult(line, "skipped", "意大利材料读不了：%s" % exc)
    return LineResult(line, "ran", "", findings, _it_receipts(ctx, it_dir))


def _it_receipts(ctx, it_dir):
    """意大利法条：条文切片 XML → 归一正文（与 verify-it 同一份取文逻辑）。"""
    articles = _index_articles(it_dir)
    out = []
    for fact in load_facts(ctx.project_dir):
        src = fact.get("source", "")
        if not src.endswith(".it.card.txt"):
            continue
        card = os.path.join(ctx.project_dir, src)
        fields = _card_fields(card)
        eid = fields.get("ARTICLE_EID") or ""
        text = ""
        hit = articles.get(eid)
        if hit:
            root, meta, _idx = hit
            art_file = meta.get("article_file") or ""
            if art_file:
                raw = _read_bytes(os.path.join(root, art_file))
                if raw:
                    text = _it_plain_text(raw.decode("utf-8", "replace"))
        if not text:
            text = _embedded_official_text(card)
        value = fact.get("value")
        span = receipts.span_in_text(value, text) if text else receipts.MISSING
        face = _face_of(value, text, text) if text else receipts.MISSING
        out.append(receipts.build_receipt(fact.get("id"),
                                          fact.get("source_sha256"),
                                          span, face, "contains"))
    return out


def _run_es(ctx):
    line = LINES[4]
    es_dir = _resolve_section_dir(ctx.corpus_dir, "es", "articles")
    if not es_dir or not os.path.isdir(es_dir):
        return LineResult(line, "skipped", "西班牙语料没拿到（es/ 目录不在）")
    try:
        findings, _index = verify_es(ctx.project_dir, es_dir, ctx.date)
    except FileNotFoundError as exc:
        return LineResult(line, "skipped", "西班牙语料读不了：%s" % exc)
    except Exception as exc:  # noqa: BLE001
        return LineResult(line, "skipped", "西班牙材料读不了：%s" % exc)
    return LineResult(line, "ran", "", findings, _es_receipts(ctx, es_dir))


def _es_receipts(ctx, es_dir):
    """西班牙法条：条文块切片 XML → 归一正文（与 verify-es 同一份取文逻辑）。"""
    articles = _index_articles(es_dir)
    out = []
    for fact in load_facts(ctx.project_dir):
        src = fact.get("source", "")
        if not src.endswith(".es.card.txt"):
            continue
        card = os.path.join(ctx.project_dir, src)
        fields = _card_fields(card)
        bid = fields.get("BLOCK_ID") or ""
        text = ""
        hit = articles.get(bid)
        if hit:
            root, meta, _idx = hit
            art_file = meta.get("article_file") or ""
            if art_file:
                raw = _read_bytes(os.path.join(root, art_file))
                if raw:
                    text = _es_plain_text(raw.decode("utf-8", "replace"))
        if not text:
            text = _embedded_official_text(card)
        value = fact.get("value")
        span = receipts.span_in_text(value, text) if text else receipts.MISSING
        face = _face_of(value, text, text) if text else receipts.MISSING
        out.append(receipts.build_receipt(fact.get("id"),
                                          fact.get("source_sha256"),
                                          span, face, "contains"))
    return out


def _run_fr_case(ctx):
    line = LINES[5]
    try:
        findings, _stats = verify_fr_case(ctx.project_dir)
    except Exception as exc:  # noqa: BLE001
        return LineResult(line, "skipped", "法国判例材料读不了：%s" % exc)
    return LineResult(line, "ran", "", findings, _fr_case_receipts(ctx))


def _fr_case_body(text):
    """法国判例还原件里的判决正文段（'[CONTENU]' 之后；其余是元数据与摘要）。"""
    if not text:
        return ""
    marker = "[CONTENU]"
    if marker not in text:
        return text
    return text.split(marker, 1)[1]


def _fr_case_receipts(ctx):
    """法国判例：官方纯文本还原件在项目内 runs/<run>/official/<case>.txt。"""
    out = []
    for fact in load_facts(ctx.project_dir):
        src = fact.get("source", "")
        m = FR_CASE_CARD_RE.match(src)
        if not m:
            continue
        run, case_id = m.group("run"), m.group("case_id")
        text = _read_text(os.path.join(ctx.project_dir, "runs", run,
                                       "official", "%s.txt" % case_id))
        body = _fr_case_body(text)
        value = fact.get("value")
        span = receipts.span_in_text(value, text) if text else receipts.MISSING
        face = _face_of(value, body, text) if text else receipts.MISSING
        out.append(receipts.build_receipt(fact.get("id"),
                                          fact.get("source_sha256"),
                                          span, face,
                                          receipts.classify_how(value)))
    return out


def _run_it_case(ctx):
    line = LINES[6]
    itcase_dir = ctx.itcase_dir or _resolve_section_dir(
        ctx.corpus_dir, "it-case", "judgments")
    if not itcase_dir:
        return LineResult(line, "skipped",
                          "意大利判例语料没拿到（it-case/ 目录不在）")
    try:
        findings, _index = verify_it_case(ctx.project_dir, itcase_dir)
    except FileNotFoundError as exc:
        return LineResult(line, "skipped", "意大利判例语料读不了：%s" % exc)
    except Exception as exc:  # noqa: BLE001
        return LineResult(line, "skipped", "意大利判例材料读不了：%s" % exc)
    return LineResult(line, "ran", "", findings, _it_case_receipts(ctx, itcase_dir))


def _it_case_receipts(ctx, itcase_dir):
    """意大利判例：判决切片在语料 run 目录，卡在项目里（ECLI 对上）。"""
    judgments = _index_articles(itcase_dir, key="judgments")
    out = []
    for fact in load_facts(ctx.project_dir):
        src = fact.get("source", "")
        if not src.endswith(ITCASE_CARD_SUFFIX):
            continue
        card = os.path.join(ctx.project_dir, src)
        fields = _card_fields(card)
        ecli = (fields.get("ECLI") or "").strip()
        text = ""
        for key, (root, meta, _idx) in judgments.items():
            if ecli and (meta.get("ecli") or "") != ecli and key != ecli:
                continue
            slice_file = meta.get("slice_file") or ""
            if slice_file:
                raw = _read_bytes(os.path.join(root, slice_file))
                if raw:
                    text = _itcase_plain(raw)
            break
        if not text:
            text = _embedded_official_text(card)
        value = fact.get("value")
        span = receipts.span_in_text(value, text) if text else receipts.MISSING
        face = _face_of(value, text, text) if text else receipts.MISSING
        out.append(receipts.build_receipt(fact.get("id"),
                                          fact.get("source_sha256"),
                                          span, face,
                                          receipts.classify_how(value)))
    return out


_RUNNERS = {
    "fr": _run_fr,
    "cn": _run_cn,
    "case": _run_case,
    "it": _run_it,
    "es": _run_es,
    "fr-case": _run_fr_case,
    "it-case": _run_it_case,
}


def collect_one(ctx, line):
    """跑一条线 → LineResult（材料缺失＝skipped，不是异常）。"""
    runner = _RUNNERS.get(line.id)
    if runner is None:
        return LineResult(line, "na", "未知线")
    result = runner(ctx)
    result.red = sum(1 for f in result.findings if f.severity == "red")
    result.yellow = sum(1 for f in result.findings if f.severity == "yellow")
    return result


def collect(ctx, line_ids=None):
    """跑若干条线 → [LineResult]（七条线按固定次序；缺材料的标 skipped，不跳过）。"""
    wanted = None
    if line_ids:
        wanted = set(line_ids)
    out = []
    for line in LINES:
        if wanted is not None and line.id not in wanted:
            continue
        out.append(collect_one(ctx, line))
    return out
