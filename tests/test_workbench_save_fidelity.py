# -*- coding: utf-8 -*-
"""保存这条路的「逐字保留」闸：正文里的字、数字、保护面，保存一次都不许变。

这一组用例守的是 2026-11-22 验收里记下的那条现象：在 \\fact{E5} 芯片旁放探针
`[HOSTBAK1]`，**第一次**保存落盘完整，**第二次**保存往返后尾数字 `1` 不见了
（落盘成 `[HOSTBAK]`）——保存改掉了用户没打过的内容。

根因是两层，缺一不可：

1. **客户端**：块指纹（＝「这份 DOM 是哪一版文件渲染出来的」）被**无条件**推进。
   DOM 明明还是旧版渲染的（用户还在这一块里打字，整块重绘会吞掉新字），指纹却
   已经报成新版——下一轮保存就带着**过期的保护面序号**混过指纹闸。
2. **服务端**：占位符序号在当前扫描里不存在时，旧口径是 `continue`——**静默丢掉**
   那枚保护面。正文里插一个字，紧邻 \\fact{} 的绑定数字令牌可能整段消失，后面所有
   保护面序号整体前移一位，于是序号整体错位：用户没打过的字被换成了别的内容
   （实测：正文里的 `0/3` 被换成 \\fact{E5}，凭空多出 `0/2`）。

两道闸各自都要在：客户端不推进指纹（第一道），服务端对不上就拒写（第二道，
不许静默丢）。这里逐条钉住。

跑法（仓根）：python3 -m pytest tests/test_workbench_save_fidelity.py -q
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe.config import ConfigError  # noqa: E402
from factscribe.workbench.projects import (bound_values_of,  # noqa: E402
                                            disk_sections, short_sha, token_of)
from factscribe.workbench.write import (TOKEN_COUNT_MISMATCH_CODE,  # noqa: E402
                                        TOKEN_MISMATCH_CODE,
                                        _guard_surface_kept, find_block,
                                        save_block, scan)

MINIMAL = ROOT / "examples" / "minimal"
STATIC = ROOT / "factscribe" / "workbench" / "static"

#: 这一段的正文：数字**紧贴** \\fact{}（绑定数字令牌因此成立），
#: 探针插在数字与芯片之间就会把这段令牌打散 → 保护面序号整体前移一位。
SECTION_TEXT = (
    "\\label{sec:intro}\n\n"
    "开臂解决 10\\fact{A1}，对比臂解决 8\\fact{A3}。\n"
)

PROBE = "[HOSTBAK1]"


def _fact_token(segments, fact_id):
    """\\fact{ID} 那枚保护面的占位符（与前端 data-token 同口径）。"""
    for seg in segments:
        if seg.kind == "prot" and seg.text.strip() == "\\fact{%s}" % fact_id:
            return token_of(seg.index)
    return ""


def _payload(raw, bound_values):
    """按服务端扫描结果拼一份「散文＋占位符」的提交文本（前端 collectPlain 同口径）。"""
    parts = []
    for seg in scan(raw, bound_values):
        parts.append(seg.text if seg.kind == "text" else token_of(seg.index))
    return "".join(parts)


class SaveFidelityTests(unittest.TestCase):
    """正文保存：逐字保留，且对不上就拒写。"""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-save-fidelity-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)
        self.rel = "sections/01-intro.tex"
        (self.disk / self.rel).write_text(SECTION_TEXT, encoding="utf-8")
        self.bound = bound_values_of(self.disk)
        self.block = find_block(self.disk, self.rel, self._block_id())
        self.file = self.disk / self.rel

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _block_id(self):
        for block in disk_sections(self.disk).get("blocks") or []:
            if str(block.get("file")) == self.rel and block.get("kind") == "para":
                return str(block.get("id"))
        raise AssertionError("样例盘里没有这一段的正文块")

    def _payload_with_probe(self):
        """客户端在「绑定数字令牌与 \\fact{} 芯片之间」插探针后的提交文本。"""
        payload = _payload(self.block.raw, self.bound)
        token = _fact_token(scan(self.block.raw, self.bound), "A1")
        self.assertTrue(token, "这一段里没有 \\fact{A1} 芯片")
        return payload.replace(token, PROBE + token, 1)

    # ---------------------------------------------------------- 正常路径

    def test_two_saves_keep_the_probe_and_the_file_is_byte_stable(self):
        """连续保存两次：探针的数字还在，落盘逐字稳定。"""
        first = save_block(self.disk, self.rel, self.block.block_id,
                           self._payload_with_probe(),
                           expect_sha=short_sha(self.block.raw))
        self.assertIn(PROBE, first["after"])
        self.assertIn("10" + PROBE, first["after"])
        after_first = self.file.read_bytes()

        # 客户端刷新了 DOM（拿到服务端的新文与新指纹）→ 第二轮保存
        second = save_block(self.disk, self.rel, self.block.block_id,
                            _payload(first["after"], self.bound),
                            expect_sha=short_sha(first["after"]))
        self.assertIn(PROBE, second["after"])
        self.assertEqual(self.file.read_bytes(), after_first,
                         "第二次保存必须逐字稳定")
        self.assertEqual(second["after"], first["after"])

    def test_saving_twice_keeps_the_bound_number_token(self):
        """绑定数字令牌不许在保存里凭空消失（它是 \\fact{} 的绑定面）。"""
        segments = scan(self.block.raw, self.bound)
        nums = [seg for seg in segments if seg.label == "num"]
        self.assertTrue(nums, "样例这一段里没有绑定数字令牌")
        save_block(self.disk, self.rel, self.block.block_id,
                   self._payload_with_probe(),
                   expect_sha=short_sha(self.block.raw))
        self.assertIn("10", self.file.read_text(encoding="utf-8"))

    # ---------------------------------------------------------- stale 路径

    def test_stale_dom_is_refused_and_the_file_is_untouched(self):
        """客户端那份 DOM 还是旧版渲染的（指纹被提前推进）→ 拒写，文件一个字节都不动。

        这是「保存会改内容」那条现象的正路：旧口径下服务端按旧序号重建，
        用户没打过的字被换掉（0/3 → \\fact{E5}，凭空多出 0/2）。
        """
        first = save_block(self.disk, self.rel, self.block.block_id,
                           self._payload_with_probe(),
                           expect_sha=short_sha(self.block.raw))
        after_first = self.file.read_bytes()
        # 客户端没重绘 DOM：它手里的仍是**旧**占位符序号，
        # 但指纹已经被它自己推进到了新版（这正是旧口径的 bug）。
        stale_payload = self._payload_with_probe()
        with self.assertRaises(ConfigError) as ctx:
            save_block(self.disk, self.rel, self.block.block_id,
                       stale_payload, expect_sha=short_sha(first["after"]))
        self.assertEqual(getattr(ctx.exception, "code", ""), TOKEN_MISMATCH_CODE)
        self.assertEqual(self.file.read_bytes(), after_first,
                         "拒写之后文件必须逐字节不变")

    def test_unknown_token_index_is_refused_not_silently_dropped(self):
        """占位符序号在当前扫描里不存在 → 拒写（旧口径是静默丢掉那枚保护面）。"""
        payload = _payload(self.block.raw, self.bound) + token_of(99)
        before = self.file.read_bytes()
        with self.assertRaises(ConfigError) as ctx:
            save_block(self.disk, self.rel, self.block.block_id, payload,
                       expect_sha=short_sha(self.block.raw))
        self.assertEqual(getattr(ctx.exception, "code", ""), TOKEN_MISMATCH_CODE)
        self.assertEqual(self.file.read_bytes(), before)

    # ---------------------------------------------------------- 结构闸

    def test_stale_token_count_is_refused(self):
        """客户端那份 DOM 是**旧结构**渲染的（保护面数量对不上）→ 拒写，文件不动。

        账本变了（新事实的 value 出现在正文里）→ 同一段原文多出绑定数字令牌
        → 保护面数量变了 → 客户端那份 DOM 的占位符序号整体错位：按旧序号
        重建，用户没打过的字会被改掉。
        """
        before = self.file.read_bytes()
        with self.assertRaises(ConfigError) as ctx:
            save_block(self.disk, self.rel, self.block.block_id,
                       self._payload_with_probe(),
                       expect_sha=short_sha(self.block.raw),
                       expect_tokens="1")
        self.assertEqual(getattr(ctx.exception, "code", ""),
                         TOKEN_COUNT_MISMATCH_CODE)
        self.assertEqual(self.file.read_bytes(), before,
                         "拒写之后文件必须逐字节不变")

    def test_matching_token_count_is_accepted(self):
        """数量对得上 → 放行（别把正常保存拦了）。"""
        segments = scan(self.block.raw, self.bound)
        count = len([seg for seg in segments if seg.kind == "prot"])
        result = save_block(self.disk, self.rel, self.block.block_id,
                            self._payload_with_probe(),
                            expect_sha=short_sha(self.block.raw),
                            expect_tokens=str(count))
        self.assertIn(PROBE, result["after"])

    # ---------------------------------------------------------- 保护面不许丢

    def test_lost_protection_surface_is_refused(self):
        """重建之后少了一枚命令类保护面 → 拒写（「保存不许改内容」的兜底）。"""
        before = scan(self.block.raw, self.bound)
        # 假装重建结果把 \\fact{A1} 弄丢了（只剩 \\fact{A3}）。
        lost = self.block.raw.replace("\\fact{A1}", "")
        with self.assertRaises(ConfigError) as ctx:
            _guard_surface_kept(before, lost, self.bound, TOKEN_MISMATCH_CODE)
        self.assertEqual(getattr(ctx.exception, "code", ""), TOKEN_MISMATCH_CODE)

    def test_kept_protection_surface_passes(self):
        """保护面齐全 → 放行（别把正常保存也拦了）。"""
        before = scan(self.block.raw, self.bound)
        _guard_surface_kept(before, self.block.raw, self.bound,
                             TOKEN_MISMATCH_CODE)


class FrontendShaDisciplineTests(unittest.TestCase):
    """前端口径：块指纹只在**内容真的换成服务端新文**时推进。

    指纹＝「这份 DOM 是哪一版文件渲染出来的」。推进它＝告诉服务端「我这份 DOM
    对得上当前文件」。DOM 还是旧版渲染的却推进指纹，下一轮保存就会带着过期的
    保护面序号混过指纹闸，服务端按旧序号重建 → 用户没打过的字被改掉。
    """

    def setUp(self):
        self.src = (STATIC / "app.js").read_text(encoding="utf-8")

    def _function(self, name):
        start = self.src.index("function %s(" % name)
        depth = 0
        for index in range(start, len(self.src)):
            if self.src[index] == "{":
                depth += 1
            elif self.src[index] == "}":
                depth -= 1
                if depth == 0:
                    return self.src[start:index + 1]
        raise AssertionError("找不到函数 %s 的完整定义" % name)

    def test_save_block_node_does_not_push_sha_unconditionally(self):
        body = self._function("saveBlockNode")
        self.assertNotIn("if (data.sha) state.blockSha[blockId] = data.sha;", body,
                         "保存应答的指纹不能无条件推进（旧口径：DOM 没重绘也推进）")

    def test_apply_block_html_owns_the_sha(self):
        body = self._function("applyBlockHtml")
        self.assertIn("if (sha) state.blockSha[blockId] = sha;", body,
                      "指纹随内容替换一起推进（内容换了，指纹才换）")

    def test_client_reports_the_token_count(self):
        """客户端要把「这份 DOM 是哪一版**结构**渲染出来的」一起报上去。"""
        body = self._function("saveBlockNode")
        self.assertIn("body.expect_tokens", body,
                      "保存请求必须带上保护面数量（结构闸）")
        self.assertIn("function countProtTokens(", self.src,
                      "保护面数量从渲染 html 的芯片数里数")

    def test_reload_blocks_only_pushes_sha_for_replaced_blocks(self):
        body = self._function("reloadBlocks")
        self.assertIn("applyBlockHtml(block.id, block.html, block.sha)", body,
                      "重绘过的块才带着新指纹一起推进")
        self.assertIn("live.dataset.stale = '1';", body,
                      "聚焦中的块不重绘 → 记 stale，指纹不推进")



class BoundNumberProseTests(unittest.TestCase):
    """正文里出现与绑定数字令牌**同样的数字**时，保存不许挪动那枚令牌。

    这是「保存会改内容」的另一个入口：绑定数字令牌是**派生**出来的保护面
    （紧邻 \fact{} 或与账本同值），它的字面（8）在正文里本来就可能出现。
    旧口径下服务端按**文字**认领「原样抄回的保护面」——正文里那个 8 被认成
    别处那枚令牌，于是令牌被搬到正文位置，芯片旁边的绑定数字整段消失
    （实测：正文 still gave 0/3\fact{E2} 变成 still gave \fact{E2}）。
    """

    SECTION_TEXT = (
        "\\label{sec:intro}\n\n"
        "开臂解决 8\\fact{A1}，对比臂还是 8 题，8\\fact{A3}。\n"
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fs-save-fidelity-"))
        self.disk = self.tmp / "paper"
        shutil.copytree(MINIMAL, self.disk)
        self.rel = "sections/01-intro.tex"
        (self.disk / self.rel).write_text(self.SECTION_TEXT, encoding="utf-8")
        self.bound = bound_values_of(self.disk)
        self.block = find_block(self.disk, self.rel, self._block_id())
        self.file = self.disk / self.rel

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _block_id(self):
        for block in disk_sections(self.disk).get("blocks") or []:
            if str(block.get("file")) == self.rel and block.get("kind") == "para":
                return str(block.get("id"))
        raise AssertionError("样例盘里没有这一段的正文块")

    def _payload_with_probe(self):
        """客户端在「绑定数字令牌与 \\fact{} 芯片之间」插探针后的提交文本。"""
        payload = _payload(self.block.raw, self.bound)
        token = _fact_token(scan(self.block.raw, self.bound), "A1")
        self.assertTrue(token, "这一段里没有 \\fact{A1} 芯片")
        return payload.replace(token, PROBE + token, 1)

    def test_prose_number_is_not_mistaken_for_a_bound_token(self):
        """正文里的同名数字不许被认成别处的绑定数字令牌（一次保存都不许挪）。"""
        before = self.file.read_bytes()
        result = save_block(self.disk, self.rel, self.block.block_id,
                            _payload(self.block.raw, self.bound),
                            expect_sha=short_sha(self.block.raw))
        self.assertIn("8\\fact{A3}", result["after"],
                      "绑定数字令牌必须还留在它的芯片旁边")
        self.assertEqual(self.file.read_bytes(), before,
                         "保存不许挪动任何字符")

    def test_two_saves_with_probe_are_byte_stable(self):
        """探针打散绑定数字令牌后，连续两次保存仍逐字稳定。"""
        first = save_block(self.disk, self.rel, self.block.block_id,
                           self._payload_with_probe(),
                           expect_sha=short_sha(self.block.raw))
        self.assertIn("8" + PROBE + "\\fact{A1}", first["after"])
        after_first = self.file.read_bytes()
        second = save_block(self.disk, self.rel, self.block.block_id,
                            _payload(first["after"], self.bound),
                            expect_sha=short_sha(first["after"]))
        self.assertIn("8\\fact{A3}", second["after"],
                      "第二遍保存不许把绑定数字令牌搬走")
        self.assertEqual(self.file.read_bytes(), after_first,
                         "第二次保存必须逐字稳定")


if __name__ == "__main__":
    unittest.main()
