# -*- coding: utf-8 -*-
"""待批提案通道（第 ② 步）：**只建单、不写盘**。

法律闸**没有写路径**（第 ① 步的硬约束：接口层零落盘）。所以「待批提案」
在第 ② 步只做到**提议单**这一层：

* **建单**：把一条提议登记成单子（针对某条收据／某件语料／某条事实）；
* **指纹闸**：单子记下目标当时的指纹（before_sha）；采纳时现算指纹，
  对不上就**拒写**（目标已被别处改过 ⇒ 这张单作废）；
* **采纳**：**不写任何文件**，只在单上登记「采纳意图」，等第 ③ 步的真写路径。

存储：**进程内存**（模块级单例 ＋ 线程锁）。代价与好处都摆在这里：

* 代价：服务重启 ⇒ 在途提议单全失（这是「不写盘」的必然结果，不是缺陷）；
* 好处：项目目录、语料、锁件一个字节都不动（法律闸的写路径本来就不存在）。

命令行另起进程时读到的是**本进程**的存储（通常为空）——通道里会说明白，
不假装有单。

本件只碰提议单自身：不读项目、不写项目、不改任何判定语义、不改退出码。
"""
import threading

__all__ = ["PROPOSAL_KINDS", "STATUSES", "ProposalError", "adopt", "clear",
           "create", "get", "list_all"]

# 提议类型（工作台页面能建的三种目标）
PROPOSAL_KINDS = ("receipt_quote", "corpus_item", "fact_claim")

# 单子状态（闭集）
STATUSES = ("proposed", "adopted_pending", "rejected")

_LOCK = threading.Lock()
_STORE = []
_SEQ = [0]

_NO_WRITE_REASON = ("法律闸无写路径：采纳只登记意图（**未写盘**），"
                    "真写回等第 ③ 步。")


class ProposalError(Exception):
    """提议单的错误（带机器码；HTTP 层据此选状态码）。"""

    def __init__(self, message, code="PROPOSAL_INVALID"):
        super().__init__(message)
        self.code = code
        self.message = message


def clear():
    """清空存储（只给测试与「重来」用；它本身不是写路径，不碰任何文件）。"""
    with _LOCK:
        del _STORE[:]
        _SEQ[0] = 0


def list_all():
    """在途提议单（副本；按建单顺序）。"""
    with _LOCK:
        return [dict(p) for p in _STORE]


def get(pid):
    """按 id 取一张单（副本）；没有 → None。"""
    with _LOCK:
        for p in _STORE:
            if p["id"] == str(pid):
                return dict(p)
    return None


def _next_id():
    with _LOCK:
        _SEQ[0] += 1
        return "P-%04d" % _SEQ[0]


def create(kind, target, payload=None, before_sha="", fingerprint=None):
    """建一张提议单（**不写盘**）。

    fingerprint：调用方现算的目标指纹
    {"source": 指纹来源说明, "current": 现算指纹值}。

    * 客户端没给 before_sha ⇒ 取现算指纹当基准；
    * 客户端给了 before_sha ⇒ 必须与现算一致，否则**拒建**
      （目标已被改过 ⇒ 这张单从一开始就不该存在）。
    """
    kind = str(kind or "")
    if kind not in PROPOSAL_KINDS:
        raise ProposalError("未知的提议类型：%s（可选：%s）"
                            % (kind, "、".join(PROPOSAL_KINDS)))
    fingerprint = fingerprint or {}
    current = str(fingerprint.get("current") or "")
    stated = str(before_sha or "")
    if stated and current and stated != current:
        raise ProposalError(
            "指纹不符：单上的 before_sha=%s，目标现算指纹=%s——目标已被改过，不建单。"
            % (stated, current), code="PROPOSAL_STALE")
    record = {
        "id": _next_id(),
        "kind": kind,
        "target": dict(target or {}),
        "before_sha": stated or current,
        "after_sha": "",
        "payload": dict(payload or {}),
        "status": "proposed",
        "decision": {
            "action": "none",
            "write_path": False,
            "reason": _NO_WRITE_REASON,
        },
        "fingerprint": {
            "source": str(fingerprint.get("source") or ""),
            "current": current,
            "matches": (current == stated) if (current and stated) else None,
        },
    }
    with _LOCK:
        _STORE.append(record)
    return dict(record)


def adopt(pid, fingerprint=None):
    """采纳一张单：**过指纹闸**才过，不过就拒写。

    * 闸怎么算：现算目标指纹，与单上的 before_sha 比；
    * 对不上 ⇒ 状态转 rejected、记下原因、抛 PROPOSAL_STALE（HTTP 409）；
    * 对得上 ⇒ 状态转 adopted_pending，**只登记意图，不写任何文件**。
    """
    fingerprint = fingerprint or {}
    current = str(fingerprint.get("current") or "")
    pid = str(pid)
    with _LOCK:
        record = None
        for p in _STORE:
            if p["id"] == pid:
                record = p
                break
        if record is None:
            raise ProposalError("没有这张提议单：%s" % pid,
                                code="PROPOSAL_UNKNOWN")
        before = str(record.get("before_sha") or "")
        source = str(fingerprint.get("source") or "")
        if not current:
            record["status"] = "rejected"
            record["decision"] = {
                "action": "reject", "write_path": False,
                "reason": ("指纹核对不了：目标现在找不到（现算指纹为空）——拒写。"),
            }
            raise ProposalError(
                "指纹核对不了：目标现在找不到（现算指纹为空）——拒写。",
                code="PROPOSAL_STALE")
        if before != current:
            reason = ("指纹不符：单上 before_sha=%s，目标现算=%s"
                      "（%s）——目标已被别处改过，拒写。"
                      % (before or "—", current, source or "指纹来源未标注"))
            record["status"] = "rejected"
            record["decision"] = {
                "action": "reject", "write_path": False, "reason": reason,
            }
            record["fingerprint"] = {
                "source": source, "current": current, "matches": False,
            }
            raise ProposalError(reason, code="PROPOSAL_STALE")
        record["status"] = "adopted_pending"
        record["decision"] = {
            "action": "register_intent", "write_path": False,
            "reason": _NO_WRITE_REASON,
        }
        record["fingerprint"] = {
            "source": source, "current": current, "matches": True,
        }
        return dict(record)
