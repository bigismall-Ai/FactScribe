# -*- coding: utf-8 -*-
"""legal 域级冻结锁的**规范化形态**（canonical 四键闭集）。

为什么独立成件
----------------
canonical 四键（corpus／date／index_sha256／view）是 legal 域锁的**唯一形态**：
同输入逐字节一致。原先它住在 `checks_adapter.py` 里，而那个模块是本包
**唯一 import 上游 factscribe** 的模块（核验槽适配器）⇒ 只读接口层
（`api.py`，要能单独拷走单跑、不依赖宿主）用不上它。

所以把「形态」这一层搬进本件（纯标准库、零宿主依赖），
`checks_adapter.py` 改为 import 本件并原样再导出
（`checks_adapter.canonical_form` 等名字仍在，行为逐字节不变）。

纪律照旧：冻结可复核、解冻必须过只加流水账、锁在而现算不符＝红、
已解冻未重冻＝黄、没冻过＝不检查。本件只做**只读**解析（不写盘）。
"""
import hashlib
import os

from ._toml import load_toml

__all__ = [
    "LOCK_REL", "LOG_REL", "LOCK_KEYS", "canonical_form", "canonical_sha256",
    "index_sha256", "lock_path", "read_lock", "log_last_action",
]

LOCK_REL = "audit/evidence-legal.lock"
LOG_REL = "audit/evidence-legal-log.ndjson"

# 闭集四键（排序后拼进 canonical 正文）
LOCK_KEYS = ("corpus", "date", "index_sha256", "view")


def canonical_form(corpus, date, view, index_sha256) -> str:
    """legal 冻结工件的规范化正文（键为闭集、按键名排序；同输入同字节）。"""
    rows = {"corpus": str(corpus or "").strip(),
            "date": str(date or "").strip(),
            "index_sha256": str(index_sha256 or "").strip().lower(),
            "view": str(view or "").strip()}
    return "\n".join("%s\t%s" % (k, rows[k]) for k in sorted(rows))


def canonical_sha256(corpus, date, view, index_sha256) -> str:
    return hashlib.sha256(canonical_form(corpus, date, view,
                                         index_sha256).encode("utf-8")
                          ).hexdigest()


def index_sha256(corpus_dir) -> str:
    """语料视图 index.json 的字节哈希（空目录／缺文件 → 空串）。"""
    if not corpus_dir:
        return ""
    path = os.path.join(corpus_dir, "index.json")
    if not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def lock_path(project_dir) -> str:
    return os.path.join(str(project_dir), *LOCK_REL.split("/"))


def read_lock(project_dir) -> dict:
    """读锁件（只读）。返回四键＋canonical_sha256＋是否冻着。

    没冻过 → `{"frozen": False, ...四键全空}`；
    锁件坏了 → `{"frozen": True, "error": "..."}`（fail-closed 由调用方判）。
    """
    path = lock_path(project_dir)
    out = {"frozen": False, "canonical_sha256": "", "path": LOCK_REL,
           "corpus": "", "date": "", "index_sha256": "", "view": ""}
    if not os.path.exists(path):
        return out
    try:
        data = load_toml(path)
    except Exception as exc:  # noqa: BLE001 —— 坏锁件不当「没冻过」
        out["frozen"] = True
        out["error"] = "%s" % exc
        return out
    out["frozen"] = True
    out["canonical_sha256"] = str(data.get("canonical_sha256") or "").strip()
    for key in LOCK_KEYS:
        out[key] = str(data.get(key) or "").strip()
    return out


def log_last_action(project_dir) -> str:
    """流水账最后一条的 action：""＝没账／没 unfreeze；unreadable＝坏账。"""
    path = os.path.join(str(project_dir), *LOG_REL.split("/"))
    if not os.path.exists(path):
        return ""
    last = ""
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if not last:
            return ""
        import json
        return str(json.loads(last).get("action") or "")
    except Exception:  # noqa: BLE001
        return "unreadable"
