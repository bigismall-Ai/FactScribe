"""法国判例（INCA / DILA 开放数据）纯文本还原＋法式值归一。

为什么独立成件（不并进 fr_case_verify.py）
------------------------------------------
「怎么把官方 XML 还原成可比的文本」和「一致不一致算红还是黄」是两件事：

* 还原/归一是**纯函数**，而且必须被**两处**共用——抓取器
  （`tools/fetch_corpus.py`，落 official/*.txt 与证据卡）和核验闸
  （`fr_case_verify.py`，现算哈希、判值是否出自正文）。
  同一份 XML 必须永远还原出**同一份字节**，否则 official/*.txt 的
  sha256 对账自己就废了（卡上钉的哈希与闸里现算的哈希会对不上）。
* 判据层只该问「一致不一致」，不该内嵌第二份解析实现。

所以：**reader＝还原与归一**（本件），**verify＝判据**
（`factscribe_legal/fr_case_verify.py`，import 本件）。本件不 import
verify ⇒ 无环。

法国写法的三条坑（侦察批 2026-11-16 实测）
------------------------------------------
1. 金额：千分位是**点**（`300.000`＝30 万）或空格/NBSP（`3 500`）；小数是
   **逗号**（`1 234,56`）。中国 reader 的「去逗号」规则会把法式小数逗号当
   千分位吃掉 ⇒ 法式数字必须单独归一。
2. 案号三形态：TITRE `01-16.595`／NUMEROS_AFFAIRES `01-16595`（官方自己
   去了点）／正文 `pourvoi n° 98-10.525`（**可能是被引用的他案**——样本
   JURITEXT000007471838 本案是 01-16.595，正文里的 98-10.525 是另一件）。
   ⇒ 案号一致性只锚 **XML 元数据**（TITRE＋NUMEROS_AFFAIRES，去点归一），
   绝不拿「正文里出现过」当案号一致的证据。
3. 日期：元数据 DATE_DEC 是 ISO（2004-09-29），正文写法文月名
   （«29 septembre 2004»／«Du 30 Juillet 1900»，大小写混杂）
   ⇒ ISO↔法文月名双向归一。

许可：官方件来自 DILA 开放数据 INCA 档案（licence ouverte v2.0 / Etalab）。
"""
import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET

__all__ = [
    "to_plain", "parse_meta", "br_aware_text",
    "norm_fr_number", "fr_number_tokens", "fr_numbers_in",
    "fr_date_to_iso", "fr_dates_in", "fr_date_variants",
    "norm_case_no", "case_numbers_in_titre", "meta_case_numbers",
    "build_card", "card_text_fields", "sha256_bytes",
]

# ---------------------------------------------------------------------------
# 法文月名（去音标＋小写后查表；大小写混杂照收）
# ---------------------------------------------------------------------------
FR_MONTHS = (
    ("janvier", 1), ("fevrier", 2), ("mars", 3), ("avril", 4), ("mai", 5),
    ("juin", 6), ("juillet", 7), ("aout", 8), ("septembre", 9), ("octobre", 10),
    ("novembre", 11), ("decembre", 12),
)

# 各种空白（含 NBSP / 窄 NBSP / thin space）——法式千分位常用 NBSP
_SPACEY = "\u00a0\u202f\u2009\u2007\u2008\u2005"

_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_FR_DATE_RE = re.compile(r"\b(\d{1,2})\s+([A-Za-zÀ-ÖØ-öø-ÿ']+)\s+(\d{4})\b")
# 法式数字 token：数字，可跟「数字＋分隔符」重复（空格/点/逗号/NBSP）
_NUM_TOKEN_RE = re.compile(r"\d(?:[\d %s.,]*\d)?" % re.escape(_SPACEY))
# 案号形态：NN-NN.NNN（Cour de cassation 写法）；NN-NNNNN（官方去点写法）
_CASE_NO_DOT_RE = re.compile(r"\b(\d{2}-\d{2}\.\d{3})\b")

_META_SKIP_TAGS = ("META", "META_COMMUN", "META_SPEC", "META_JURI",
                   "META_JURI_JUDI", "TEXTE_JURI_JUDI")


def _fold(text):
    """去音标＋小写（法文月名查表用）。"""
    s = unicodedata.normalize("NFD", str(text or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.lower().strip()


_FR_MONTH_BY_KEY = {_fold(name): num for name, num in FR_MONTHS}


def _clean_spaces(text):
    for ch in _SPACEY:
        text = text.replace(ch, " ")
    return text


def _local(tag):
    return str(tag).split("}")[-1]


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# XML → 纯文本（确定性：同一份 XML 字节 ⇒ 永远同一份文本字节）
# ---------------------------------------------------------------------------
def br_aware_text(el):
    """元素文本，`<br/>` 与 `<p>` 作硬换行（侦察批 extract_plain.py 同款）。"""
    out = []
    if el.text:
        out.append(el.text)
    for child in el:
        if child.tag.endswith("br") or child.tag.endswith("p"):
            out.append("\n")
        else:
            out.append(br_aware_text(child))
        if child.tail:
            out.append(child.tail)
    return "".join(out)


def to_plain(xml_bytes):
    """官方判决 XML → 纯文本（逐行：META 区 `[TAG] 值`，正文 `[CONTENU]` 段）。

    形状照 DILA INCA 的 `TEXTE_JURI_JUDI`（LEGIFRANCE DTD）：
      META/META_COMMUN   ID/URL/NATURE/…
      META/META_SPEC/META_JURI        TITRE/DATE_DEC/JURIDICTION/NUMERO/SOLUTION
      META/META_SPEC/META_JURI_JUDI   NUMEROS_AFFAIRES/PUBLI_BULL/FORMATION/…
      TEXTE/BLOC_TEXTUEL/CONTENU      正文（`<br/>` 换行）
    """
    root = ET.fromstring(xml_bytes)
    lines = []
    for sec in root:
        tag = _local(sec.tag)
        if tag == "META":
            for el in sec.iter():
                t = _local(el.tag)
                txt = (el.text or "").strip()
                if txt and t not in _META_SKIP_TAGS:
                    lines.append("[%s] %s" % (t, txt))
        elif tag == "TEXTE":
            for el in sec.iter():
                t = _local(el.tag)
                if t == "CONTENU":
                    lines.append("[CONTENU]")
                    lines.append(br_aware_text(el).strip())
                elif t == "SOMMAIRE":
                    lines.append("[SOMMAIRE] " + br_aware_text(el).strip())
    return "\n".join(lines)


def parse_meta(xml_bytes):
    """判决 XML 的元数据（结构化字段优先于正文）。

    返回的键：id/nature/url/origine/ancien_id/titre/date_dec/juridiction/
    numero/solution/formation/numeros_affaires。
    """
    root = ET.fromstring(xml_bytes)
    meta_el = None
    for child in root:
        if _local(child.tag) == "META":
            meta_el = child
            break
    out = {
        "id": "", "nature": "", "url": "", "origine": "", "ancien_id": "",
        "titre": "", "date_dec": "", "juridiction": "", "numero": "",
        "solution": "", "formation": "", "numeros_affaires": [],
    }
    if meta_el is None:
        return out
    firsts = ("ID", "NATURE", "URL", "ORIGINE", "ANCIEN_ID", "TITRE",
              "DATE_DEC", "JURIDICTION", "NUMERO", "SOLUTION", "FORMATION")
    for el in meta_el.iter():
        t = _local(el.tag)
        txt = (el.text or "").strip()
        if t in firsts and txt and not out.get(t.lower()):
            out[t.lower()] = txt
        elif t == "NUMERO_AFFAIRE" and txt:
            out["numeros_affaires"].append(txt)
    return out


# ---------------------------------------------------------------------------
# 法式数字归一
# ---------------------------------------------------------------------------
def _strip_int_zeros(digits):
    d = digits.lstrip("0")
    return d or "0"


def norm_fr_number(value):
    """法式数字 → 规范数字串（空串＝不是数字）。

        '300.000'  → '300000'   （点是千分位）
        '3 500'    → '3500'     （空格/NBSP 是千分位）
        '1 234,56' → '1234.56'  （逗号是小数点）
        '1234,56'  → '1234.56'
        '1234.56'  → '1234.56'  （点后不是三位 ⇒ 当小数读）
    """
    s = unicodedata.normalize("NFC", str(value if value is not None else "")).strip()
    s = _clean_spaces(s).strip()
    s = s.strip(" \t\r\n.,")
    if not s:
        return ""
    if "," in s:
        head, _, tail = s.partition(",")
        head_d = re.sub(r"[ .]", "", head)
        if head_d.isdigit() and tail.isdigit():
            frac = tail.rstrip("0")
            int_part = _strip_int_zeros(head_d)
            return int_part if not frac else "%s.%s" % (int_part, frac)
        return ""
    if re.fullmatch(r"\d{1,3}(?:[ .]\d{3})+", s):
        return _strip_int_zeros(re.sub(r"[ .]", "", s))
    if re.fullmatch(r"\d+\.\d+", s):
        int_part, _, frac = s.partition(".")
        frac = frac.rstrip("0")
        int_part = _strip_int_zeros(int_part)
        return int_part if not frac else "%s.%s" % (int_part, frac)
    if s.isdigit():
        return _strip_int_zeros(s)
    return ""


def fr_number_tokens(text):
    """文本里所有法式数字 token 的规范形集合。"""
    out = set()
    for m in _NUM_TOKEN_RE.finditer(text or ""):
        canon = norm_fr_number(m.group(0))
        if canon:
            out.add(canon)
    return out


def fr_number_token_pairs(text):
    """文本里的 (原样 token, 规范形) 列表（物化时挑「带千分位＝像金额」的数用）。"""
    out = []
    for m in _NUM_TOKEN_RE.finditer(text or ""):
        raw = m.group(0)
        canon = norm_fr_number(raw)
        if canon:
            out.append((raw, canon))
    return out


def fr_numbers_in(text):
    """文本里出现的法式数字（规范形集合）——判据层「值是否出自官方正文」用。"""
    return fr_number_tokens(text)


# ---------------------------------------------------------------------------
# 法式日期归一（ISO ↔ 法文月名，双向）
# ---------------------------------------------------------------------------
def fr_date_to_iso(value):
    """'29 septembre 2004' → '2004-09-29'；'2004-09-29' → '2004-09-29'。

    空串＝不是日期。接受 `DD/MM/YYYY` 作第三形态。
    """
    s = _clean_spaces(unicodedata.normalize("NFC", str(value or ""))).strip()
    if not s:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return "%04d-%02d-%02d" % (int(y), int(mo), int(d))
    m = re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return "%04d-%02d-%02d" % (int(y), int(mo), int(d))
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-zÀ-ÖØ-öø-ÿ']+)\s+(\d{4})", s)
    if m:
        d, mon, y = m.groups()
        mo = _FR_MONTH_BY_KEY.get(_fold(mon))
        if mo:
            return "%04d-%02d-%02d" % (int(y), mo, int(d))
    return ""


def fr_date_variants(value):
    """日期值的全部可写形态（原始串＋ISO＋斜杠形）。"""
    out = {str(value or "")}
    iso = fr_date_to_iso(value)
    if iso:
        out.add(iso)
        y, mo, d = iso.split("-")
        out.add("%s/%s/%s" % (d, mo, y))
    return {x for x in out if x}


def fr_dates_in(text):
    """文本里的全部日期（归一成 ISO 集合）——ISO 形态与法文月名形态都收。"""
    out = set()
    for m in _ISO_DATE_RE.finditer(text or ""):
        out.add("%s-%s-%s" % m.groups())
    for m in _FR_DATE_RE.finditer(text or ""):
        d, mon, y = m.groups()
        mo = _FR_MONTH_BY_KEY.get(_fold(mon))
        if mo:
            out.add("%04d-%02d-%02d" % (int(y), mo, int(d)))
    return out


# ---------------------------------------------------------------------------
# 案号归一（去点去空白）
# ---------------------------------------------------------------------------
def norm_case_no(value):
    """'01-16.595' ↔ '01-16595' → '0116595'（去点比对用）。"""
    s = unicodedata.normalize("NFC", str(value or "")).strip()
    s = _clean_spaces(s)
    s = re.sub(r"\s+", "", s)
    s = s.replace(".", "")
    return s


def case_numbers_in_titre(titre):
    """TITRE 里的案号（`01-16.595` 形态）。"""
    return _CASE_NO_DOT_RE.findall(titre or "")


def meta_case_numbers(meta):
    """元数据锚定的案号集合（已归一）。

    来源：TITRE 里的 `NN-NN.NNN`、META_JURI/NUMERO、NUMEROS_AFFAIRES 的
    每个 NUMERO_AFFAIRE。**不含正文**——正文里出现的案号可能是他案。
    """
    out = set()
    for raw in case_numbers_in_titre((meta or {}).get("titre")):
        out.add(norm_case_no(raw))
    numero = (meta or {}).get("numero") or ""
    if numero:
        out.add(norm_case_no(numero))
    for raw in (meta or {}).get("numeros_affaires") or []:
        out.add(norm_case_no(raw))
    return {x for x in out if x}


# ---------------------------------------------------------------------------
# 证据卡（派生件；官方 XML 与纯文本还原件的哈希钉在这里）
# ---------------------------------------------------------------------------
def build_card(meta, plain_text, xml_bytes, txt_bytes,
               source_url="", source_path="", fetched_at="",
               licence="Licence ouverte v2.0 (DILA / Etalab)",
               attribution=("Source : DILA (Direction de l'Information "
                            "Légale et Administrative) — données ouvertes INCA")):
    """造一张法国判例证据卡（确定性；同一份官方件 ⇒ 同一张卡字节）。"""
    case_id = meta.get("id") or ""
    affs = meta.get("numeros_affaires") or []
    case_no = ""
    dots = case_numbers_in_titre(meta.get("titre"))
    if dots:
        case_no = dots[0]
    elif affs:
        case_no = affs[0]
    lines = [
        "# 法国判例证据卡（派生件；官方判决 XML 与纯文本还原件的哈希钉在这里）",
        "CASE_ID: %s" % case_id,
        "TITRE: %s" % meta.get("titre", ""),
        "DATE_DEC: %s" % meta.get("date_dec", ""),
        "JUDGE_DATE: %s" % meta.get("date_dec", ""),
        "JURIDICTION: %s" % meta.get("juridiction", ""),
        "CASE_NO: %s" % case_no,
        "NUMEROS_AFFAIRES: %s" % ", ".join(affs),
        "FORMATION: %s" % meta.get("formation", ""),
        "NATURE: %s" % meta.get("nature", ""),
        "SOLUTION: %s" % meta.get("solution", ""),
        "OFFICIAL_XML: official/%s.xml" % case_id,
        "OFFICIAL_TXT: official/%s.txt" % case_id,
        "OFFICIAL_XML_BYTES: %d" % len(xml_bytes),
        "OFFICIAL_XML_SHA256: %s" % sha256_bytes(xml_bytes),
        "OFFICIAL_TXT_BYTES: %d" % len(txt_bytes),
        "OFFICIAL_TXT_SHA256: %s" % sha256_bytes(txt_bytes),
        "TEXT_CHARS: %d" % len(plain_text),
        "SOURCE_URL: %s" % source_url,
        "SOURCE_PATH: %s" % source_path,
        "FETCHED_AT: %s" % fetched_at,
        "LICENCE: %s" % licence,
        "ATTRIBUTION: %s" % attribution,
        "--- OFFICIAL TEXT ---",
        plain_text.rstrip("\n"),
        "",
    ]
    return "\n".join(lines)


def card_text_fields(card_text):
    """证据卡的 `KEY: value` 字段（大写键，稳定可机读）。

    只读 `--- OFFICIAL TEXT ---` **之前**的字段段——内嵌正文里也有冒号，
    混进来会污染字段表。
    """
    out = {}
    for line in (card_text or "").splitlines():
        if line.startswith("--- OFFICIAL TEXT ---"):
            break
        if ":" not in line or line.startswith("#") or line.startswith("---"):
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip()
    return out
