"""事实账维护（写径）：同值事实的 ``dup_ok`` 标注。

定位（SPEC-CHECKS §9.7 的 M2 落地）：改账是**写径**不是核验——本模块会改写
``facts/*.toml``，所以它是与 ``fact add`` 同层的独立账务维护工具，不进
``verify()``，也不随 legal 核验包挂槽（核验包内只读）。原先它与只读的
同值检测同居 ``facts_ledger.py``，P-100 松尾账①把写径移出成独立维护模块：
``facts_ledger``＝只读检测，``ledger_maint``＝改账。

上游 FactScribe 的 R-04 规则：**同一个值挂在不同 claim 上**时会报
``DUPLICATE_VALUE``（黄），确属同一个数（例如：法国侧参考日与中国侧参考日
是同一天；某法公布日与施行日同为一天）要显式写 ``dup_ok = true`` 承认同值。

本模块扫一遍项目内所有 facts/*.toml，给"同值且 claim 不同"的事实自动补
``dup_ok = true``（**幂等**：已标的不动，重跑零字节变化）。
"""
from .facts_ledger import FACT_BLOCK, _fields, scan_dupes


def mark_dup_ok(project_dir):
    """给同值且 claim 不同的事实补 dup_ok = true（幂等）。返回被标注的 id 列表。"""
    dupes, allfacts = scan_dupes(project_dir)
    if not dupes:
        return []
    ids = {d[1] for d in dupes}
    by_file = {}
    for path, fid, _v in dupes:
        by_file.setdefault(path, set()).add(fid)
    changed = []
    for path, want in by_file.items():
        # newline=""：读按原样。默认文本模式会把 CRLF 读成 LF，
        # 后面写回时又整体翻译成 CRLF——账本的原字节就此被改掉。
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        newline = "\r\n" if "\r\n" in text else "\n"

        def fix(m):
            block = m.group(1)
            fl = _fields(block)
            if fl.get("id") in want and "dup_ok" not in block:
                block = block.rstrip("\r\n") + newline + "dup_ok = true" + newline
                changed.append(fl["id"])
            return "[[fact]]" + newline + block

        new = FACT_BLOCK.sub(fix, text)
        # newline=""：写按原样，账本里原有的一行字节都不动。
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
    return changed
