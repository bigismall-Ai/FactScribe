"""中国判例**线索层**：文书查（wenshucha.com）MCP 服务客户端。

定位（本批设计红线一，先读这段再读代码）
------------------------------------------
文书查是**第三方聚合库**（自报 1.6 亿条记录、案号字段覆盖 97.8%、约 91% 记录
正文非空），**不是人民法院案例库**，也不是裁判文书网本身。所以本模块的一切
输出只能当「线索与初步核对」：

  * **禁止**写成官方证明——报告首行固定输出 `LEAD_LINE` 线索层标注；
  * 溯源只认「案号＋法院＋裁判日期」三元组，最终核对要拿三元组上
    中国裁判文书网（或人民法院案例库）对官方件；
  * 与 `verify-case`（官方维度）的分工：verify-case 核「**官方入库案例正文**
    被动没动」（哈希链），本层供「**找案子＋案号存在性**」（第三方库检索），
    两层互不替代。

不进核验槽（红线二）：本模块只服务三个独立 CLI 子命令
`cn-lead-search` / `cn-lead-verify` / `cn-lead-get`，不注册 `[checks]`，
不动 checks_adapter 与 SPEC-CHECKS。

礼貌与配额（红线三）
--------------------
* 客户端内置**随机间隔 ≥ 2 秒**、串行（进程内锁），绝不并发；
* 每条 CLI 子命令 = **恰好一次**服务调用（search 一发一页，翻页＝再跑一次
  命令换 `--page`，硬顶第 3 页），无任何自动循环重试；
* 每次输出透出服务回报的 `_quota` 余额行；数据口径 `_coverage` 原样透出；
* 公开测试 Key（`wsc_demo_public`）是**共享评估额度**，禁批量——生产用请按
  `_coverage.more_quota` 指引申请专属 Key，走 `[cn_lead] key` 或环境变量注入。

纯标准库（红线四）：urllib 直调 JSON-RPC（quickstart 已证 curl 直调合法，
无需 MCP SDK）；超时/网络错一律 fail-closed 抛 `CnLeadError`，CLI 退出码 2。

服务实测形状（2026-11-17 真端点探得，写死在这里的不是猜测）
------------------------------------------------------------
* `tools/call` 免握手直调合法；返回 JSON-RPC 信封，业务负载在
  `result.content[0].text` 里，是一段**内嵌 JSON 字符串**；
* 参数错误走 `result.isError=true` + 中文提示，**不计费**；
* `search_judgments`（q＋pageSize）内嵌 JSON：`results[]`（caseNo/court/
  date/province/title/cause/score/excerpt/has_body…）＋ `total` ＋
  `_coverage` ＋ `_quota`；
* `verify_case_number`（**参数名是 `caseNo`**，不是 caseNumber）内嵌 JSON：
  `verdict`（实测 "exists"）＋ caseNo/court/date/province ＋
  `records_with_this_case_number` ＋ `trace.note`（三元组溯源提示）；
* `get_judgment`（caseNo）实测 `include_body=false` 形状：`found` ＋ `struct`
  ＋ `matches[]` ＋ `body_chars/body_available/body_truncated`；`include_body=
  true` 时正文键名未实测（省正文配额），解析按 `body`/`content`/`text` 多键
  防御适配——README 有记录，上线前建议一次人工探测校准。

退出码（CLI 面）：0＝服务有答（verify 仅当 verdict=="exists"）；
1＝verify 未确认存在（查无此号/判不出）；2＝配置错/网络错/参数错（fail-closed）。
"""
import json
import os
import random
import threading
import time
import urllib.error
import urllib.request

# 复用本包自带的 TOML 读取层（3.10 兜底与 3.11+ tomllib 双轨，见 _toml.py）
from ._toml import load_toml

__all__ = [
    "LEAD_LINE", "DEFAULT_ENDPOINT", "DEFAULT_PUBLIC_KEY",
    "MAX_PAGE_SIZE", "MAX_PAGE", "MIN_INTERVAL_S",
    "CnLeadError", "CnLeadNetworkError", "CnLeadParamError",
    "WenshuChaClient", "load_cn_lead_config",
    "render_search", "render_verify", "render_get",
]

# ---- 首行标注（红线一：每个子命令输出第一行必须是这一句，逐字固定） ----
LEAD_LINE = ("线索层（第三方：文书查）——非官方核验，"
             "溯源凭案号＋法院＋日期三元组上裁判文书网核对")

DEFAULT_ENDPOINT = "https://mcp.wenshucha.com/mcp"
# 公开测试 Key：共享评估额度（README 载明「生产用须申请专属 Key」）。
# 这是本模块唯一允许出现在代码里的 Key 字面量——专属 Key 只从
# factscribe.toml [cn_lead] 或环境变量读（验收门 g）。
DEFAULT_PUBLIC_KEY = "wsc_demo_public"

MAX_PAGE_SIZE = 5        # search 每页硬顶（红线三：小步评估）
MAX_PAGE = 3             # 翻页硬顶：第 3 页以后请换更窄的检索词
MIN_INTERVAL_S = 2.0     # 两次真实调用之间的最小间隔（随机加长，不取整）
TIMEOUT_S = 30.0

ENV_ENDPOINT = "FACTSCRIBE_CN_LEAD_ENDPOINT"
ENV_KEY = "FACTSCRIBE_CN_LEAD_KEY"

# get_judgment 正文键名的防御适配序（include_body=true 形状未实测，见模块头）
_BODY_KEYS = ("body", "content", "text", "judgment_body", "full_text")


class CnLeadError(Exception):
    """线索层失败基类：配置错/网络错/信封坏——CLI 一律退出码 2（fail-closed）。"""


class CnLeadNetworkError(CnLeadError):
    """连不上/超时/HTTP 非 200/响应读不全——不重试，fail-closed。"""


class CnLeadParamError(CnLeadError):
    """服务回 isError=true（参数错误不计费）——按用法错处理，退出码 2。"""


class WenshuChaClient:
    """文书查 MCP 服务的最小 JSON-RPC 客户端（urllib 直调，免握手）。

    * 串行：进程内锁包住「等待＋调用」全程，多线程共享本实例也不会并发打服务；
    * 礼貌：非首次调用前随机睡 `MIN_INTERVAL_S` ~ `MIN_INTERVAL_S+1.5` 秒；
      `sleep_fn`/`rand_fn` 可注入（离线测试用，免真睡）；
    * fail-closed：一次调用只试一遍，网络/信封任何一层坏都抛错，不静默吞。
    """

    def __init__(self, endpoint=DEFAULT_ENDPOINT, api_key=None,
                 timeout=TIMEOUT_S, sleep_fn=time.sleep,
                 rand_fn=random.uniform):
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.api_key = api_key if api_key else DEFAULT_PUBLIC_KEY
        self.timeout = timeout
        self._sleep = sleep_fn
        self._rand = rand_fn
        self._lock = threading.Lock()
        self._calls = 0          # 本实例已发的真实调用数（含失败的）
        self._id = 0             # JSON-RPC id 计数

    # ---- 传输 ----

    def _polite_wait(self):
        if self._calls >= 1:
            self._sleep(self._rand(MIN_INTERVAL_S, MIN_INTERVAL_S + 1.5))

    def _post(self, method, params, req_id):
        payload = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method,
                              "params": params}).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "x-api-key": self.api_key,
            })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            raise CnLeadNetworkError(
                f"文书查服务回 HTTP {exc.code}（端点 {self.endpoint}）"
                "——fail-closed，不重试") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise CnLeadNetworkError(
                f"连不上文书查服务（端点 {self.endpoint}）：{exc}"
                "——fail-closed，不重试；请查网络或 [cn_lead].endpoint") from exc
        return raw

    @staticmethod
    def _unwrap_payload(raw):
        """信封 → JSON-RPC result。兼容纯 JSON 与 MCP SSE（data: 行）两种皮。"""
        text = raw.decode("utf-8", "replace").strip()
        if text.startswith("{"):
            try:
                envelope = json.loads(text)
            except json.JSONDecodeError as exc:
                raise CnLeadNetworkError(f"响应不是合法 JSON 信封：{exc}") from exc
        else:
            # Streamable HTTP 允许服务端回 SSE——取最后一条 data: 行
            data_lines = [ln[5:].strip() for ln in text.splitlines()
                          if ln.startswith("data:")]
            if not data_lines:
                raise CnLeadNetworkError(
                    "响应既不是 JSON 也不是 SSE data 行——信封不认识，fail-closed")
            try:
                envelope = json.loads(data_lines[-1])
            except json.JSONDecodeError as exc:
                raise CnLeadNetworkError(f"SSE data 行不是合法 JSON：{exc}") from exc
        if not isinstance(envelope, dict) or "result" not in envelope:
            err = envelope.get("error") if isinstance(envelope, dict) else None
            raise CnLeadNetworkError(
                "JSON-RPC 信封里没有 result（协议层错）："
                f"{json.dumps(err, ensure_ascii=False) if err else text[:200]}")
        return envelope["result"]

    def call_tool(self, name, arguments):
        """tools/call 一发。返回内嵌 JSON（dict）；参数错误抛 CnLeadParamError。"""
        with self._lock:
            self._polite_wait()
            self._calls += 1
            self._id += 1
            raw = self._post("tools/call",
                             {"name": name, "arguments": arguments}, self._id)
        result = self._unwrap_payload(raw)
        if result.get("isError"):
            parts = result.get("content") or []
            text = parts[0].get("text", "") if parts else ""
            raise CnLeadParamError(
                f"文书查拒了这次调用（参数错误不计费）：{text.strip()}")
        parts = result.get("content") or []
        if not parts or not isinstance(parts[0], dict) or \
                not isinstance(parts[0].get("text"), str):
            raise CnLeadNetworkError(
                "result.content[0].text 缺失——信封形状变了，fail-closed")
        try:
            inner = json.loads(parts[0]["text"])
        except json.JSONDecodeError as exc:
            raise CnLeadNetworkError(
                f"content[0].text 里的内嵌 JSON 解析失败：{exc}") from exc
        if not isinstance(inner, dict):
            raise CnLeadNetworkError("内嵌 JSON 不是对象——形状变了，fail-closed")
        return inner

    # ---- 三个业务面（参数名照服务实测：verify 用 caseNo！）----

    def search(self, q, page_size=MAX_PAGE_SIZE, page=1):
        """search_judgments：精确词检索（BM25 非语义）。一发一页，翻页再调。"""
        q = (q or "").strip()
        if not q:
            raise CnLeadParamError("检索词 q 不能为空（参数错误不计费的坑，先替你踩掉）")
        ps = max(1, min(int(page_size), MAX_PAGE_SIZE))
        pg = max(1, min(int(page), MAX_PAGE))
        return self.call_tool("search_judgments",
                              {"q": q, "pageSize": ps, "page": pg})

    def verify_case_no(self, case_no):
        """verify_case_number：案号存在性核验。注意参数名是 caseNo。"""
        case_no = (case_no or "").strip()
        if not case_no:
            raise CnLeadParamError("案号 caseNo 不能为空（参数错误不计费的坑，先替你踩掉）")
        return self.call_tool("verify_case_number", {"caseNo": case_no})

    def get_judgment(self, case_no, include_body=True, max_chars=None):
        """get_judgment：取单件元信息/正文。max_chars 分段读正文时用。"""
        case_no = (case_no or "").strip()
        if not case_no:
            raise CnLeadParamError("案号 caseNo 不能为空（参数错误不计费的坑，先替你踩掉）")
        args = {"caseNo": case_no, "include_body": bool(include_body)}
        if max_chars is not None:
            args["max_chars"] = max(1, int(max_chars))
        return self.call_tool("get_judgment", args)

    @staticmethod
    def extract_body(inner):
        """从 get_judgment 内嵌 JSON 里取正文（多键防御适配，找不到返回 None）。"""
        for key in _BODY_KEYS:
            val = inner.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return None


# ---- 配置：[cn_lead] 可选节（照 [budget]/[evidence] 可选节先例） ----

def load_cn_lead_config(config_path=None):
    """定位端点与 Key。优先级：环境变量 > factscribe.toml [cn_lead] > 缺省。

    * `config_path` 显式给路径；不给则看当前目录有没有 factscribe.toml；
      还没有就用缺省（公共端点＋公共测试 Key）——节可选，缺了不报错；
    * 节里只认 `endpoint`、`key` 两个字符串键；其余键忽略（向前兼容）；
    * 专属 Key 永不从命令行参数进（会留在 shell 历史里），只走配置/环境。

    返回 (endpoint, api_key)，两者都可能为 None＝用缺省。
    """
    table = {}
    path = config_path
    if not path and os.path.isfile("factscribe.toml"):
        path = "factscribe.toml"
    if path:
        if not os.path.isfile(path):
            raise CnLeadError(f"配置文件不存在：{path}")
        data = load_toml(path)
        raw = data.get("cn_lead")
        if raw is not None and not isinstance(raw, dict):
            raise CnLeadError(f"{path} 的 [cn_lead] 必须是表（endpoint / key 两键），"
                              f"现在是 {type(raw).__name__}")
        table = raw or {}
    endpoint = table.get("endpoint") or os.environ.get(ENV_ENDPOINT) or None
    key = table.get("key") or os.environ.get(ENV_KEY) or None
    if endpoint is not None and not str(endpoint).strip():
        endpoint = None
    if key is not None and not str(key).strip():
        key = None
    return endpoint, key


# ---- 渲染（首行标注逐字固定；_coverage/_quota 原样透出） ----

_VERDICT_TEXT = {
    "exists": "库内存在（线索）",
    "not_found": "库内查无（线索）",
}


def _quota_line(quota):
    if not isinstance(quota, dict):
        return "配额：服务未回 _quota（口径不明，勿连续调用）"
    label = quota.get("label") or quota.get("plan") or "?"
    parts = [f"配额（{label}）",
             "检索 已用 {}/{} 余 {}".format(quota.get("used", "?"),
                                            quota.get("limit", "?"),
                                            quota.get("remaining", "?"))]
    if quota.get("body_limit") is not None:
        parts.append("正文 已用 {}/{} 余 {}".format(quota.get("body_used", "?"),
                                                   quota.get("body_limit"),
                                                   quota.get("body_remaining", "?")))
    if quota.get("ip_daily") is not None:
        parts.append("本机今日 {}/{}".format(quota.get("ip_used_today", "?"),
                                             quota.get("ip_daily")))
    return " ｜ ".join(parts)


def _coverage_lines(coverage, keep=3):
    """数据口径：原样透出 caveats（全量），另带 corpus/search_type 一行。"""
    lines = []
    if isinstance(coverage, dict):
        head = coverage.get("corpus") or ""
        stype = coverage.get("search_type") or ""
        if head or stype:
            lines.append(f"数据口径：{head}{'；' if head and stype else ''}{stype}")
        caveats = coverage.get("caveats") or []
        for cav in caveats:
            lines.append(f"口径注意：{cav}")
        src = coverage.get("source") or ""
        if src:
            lines.append(f"来源：{src}")
    return lines


def render_search(inner, q):
    """search 结果 → 报告文本（首行=LEAD_LINE）。"""
    lines = [LEAD_LINE, ""]
    total = inner.get("total")
    exact = "精确" if inner.get("total_is_exact") else "估计"
    mode = inner.get("match_mode") or "?"
    page = inner.get("page", 1)
    ps = inner.get("pageSize", "?")
    lines.append(f"检索词：{q}（匹配 {mode}）")
    lines.append(f"命中：{total}（{exact}数）——本页第 {page} 页 × {ps} 条"
                 f"（页顶 {MAX_PAGE}，更多请换更窄检索词）")
    results = inner.get("results") or []
    if not results:
        lines.append("")
        lines.append("本页 0 条——注意：查不到≠不存在（口径见下），"
                     "换词/换年份区间再试，或直接拿案号走 cn-lead-verify。")
    for i, r in enumerate(results, 1):
        lines.append("")
        lines.append("{}. {} ｜ {} ｜ {} ｜ {}".format(
            i, r.get("caseNo") or "（无案号）", r.get("court") or "?",
            r.get("date") or "?", r.get("province") or "（无省份标注）"))
        lines.append(f"   标题：{r.get('title') or '?'}")
        if r.get("cause"):
            lines.append(f"   案由：{r['cause']}   相关度分：{r.get('score', '?')}")
        if r.get("has_body") is False:
            lines.append("   正文：库内无正文（约 9% 记录如此——可能系调解结案等正常情形）")
        elif r.get("body_truncated"):
            lines.append("   正文：库内正文已确认不完整（body_truncated=true）")
        excerpt = (r.get("excerpt") or "").strip()
        if excerpt:
            lines.append(f"   摘录：{excerpt[:160]}{'…' if len(excerpt) > 160 else ''}")
    lines.append("")
    lines.extend(_coverage_lines(inner.get("_coverage")))
    lines.append(_quota_line(inner.get("_quota")))
    lines.append(LEAD_LINE)
    return "\n".join(lines)


def render_verify(inner):
    """verify_case_number 结果 → 报告文本（首行=LEAD_LINE）。"""
    lines = [LEAD_LINE, ""]
    verdict = str(inner.get("verdict") or "").strip()
    case_no = inner.get("caseNo") or "?"
    mapped = _VERDICT_TEXT.get(verdict, f"服务判定：{verdict or '?'}（不认识的判定词，按未确认处理）")
    lines.append(f"案号：{case_no} ｜ 判定：{mapped}")
    fields = []
    if inner.get("court"):
        fields.append(f"法院 {inner['court']}")
    if inner.get("date"):
        fields.append(f"裁判日期 {inner['date']}")
    if inner.get("province"):
        fields.append(f"省份 {inner['province']}")
    if fields:
        lines.append("三元组：" + " ｜ ".join(fields))
    if inner.get("title"):
        lines.append(f"标题：{inner['title']}")
    rec = inner.get("records_with_this_case_number")
    if rec is not None:
        lines.append(f"库内同号记录：{rec} 条（记录数≠案件数，同号多记录常见于保全/执行系列）")
    trace = inner.get("trace") or {}
    note = trace.get("note") if isinstance(trace, dict) else None
    if note:
        lines.append(f"溯源：{note}")
    lines.append("")
    lines.extend(_coverage_lines(inner.get("_coverage")))
    lines.append(_quota_line(inner.get("_quota")))
    lines.append("提醒：这是第三方聚合库的「存在性线索」，不是官方证明；"
                 "确认 existence 后请拿三元组上裁判文书网/人民法院案例库对官方件。")
    lines.append(LEAD_LINE)
    return "\n".join(lines)


def render_get(inner):
    """get_judgment 结果 → 报告文本（首行=LEAD_LINE）。"""
    lines = [LEAD_LINE, ""]
    found = inner.get("found")
    if found is False:
        lines.append("案号：{} ｜ 判定：库内查无（线索）——查不到≠不存在，"
                     "请先 cn-lead-verify 或换案号写法（全半角括号、⦅2022⦆类）"
                     .format(inner.get("caseNo") or "?"))
    else:
        lines.append(f"案号：{inner.get('caseNo') or '?'} ｜ 判定：库内取到（线索）")
        matches = inner.get("matches") or []
        if matches:
            m0 = matches[0]
            lines.append("三元组：法院 {} ｜ 裁判日期 {} ｜ 省份 {}".format(
                m0.get("court") or "?", m0.get("date") or "?",
                m0.get("province") or "（无省份标注）"))
            if m0.get("title"):
                lines.append(f"标题：{m0['title']}")
            if m0.get("caseType") or m0.get("procedure"):
                lines.append("类型：{} {}".format(m0.get("caseType") or "",
                                                 m0.get("procedure") or ""))
        dup = inner.get("duplicate_records")
        if dup is not None:
            lines.append(f"库内同号记录：{dup} 条（记录数≠案件数）")
        chars = inner.get("body_chars")
        if chars is not None:
            avail = "可读" if inner.get("body_available") else "不可读"
            trunc = "，已确认结尾缺失" if inner.get("body_truncated") else ""
            lines.append(f"库内正文：{chars} 字（{avail}{trunc}）")
        body = WenshuChaClient.extract_body(inner)
        if body:
            lines.append("")
            lines.append("---- 正文（库内清洗件，非官方原件）----")
            lines.append(body.rstrip())
            lines.append("---- 正文完 ----")
        else:
            lines.append("（本次未取正文：include_body=false 或库内无正文）")
        struct = inner.get("struct") or {}
        if isinstance(struct, dict) and struct.get("referee_result"):
            lines.append("裁判要旨（自动解析，非权威字段）："
                         + str(struct["referee_result"]).strip()[:300])
    lines.append("")
    lines.extend(_coverage_lines(inner.get("_coverage")))
    lines.append(_quota_line(inner.get("_quota")))
    lines.append(LEAD_LINE)
    return "\n".join(lines)
