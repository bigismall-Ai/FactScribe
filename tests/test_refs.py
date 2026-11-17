# -*- coding: utf-8 -*-
"""CARD-G1：文献登记面（`factscribe refs dedupe / register / search`）。

正负例成对：

* **dedupe**：bib 跨条目同 DOI / 同 arXiv id → 黄（exit 3）逐条点名；
  干净 bib → exit 0；缺唯一键的条目只列清单不判红。
* **register**：登记表缺必填字段 → 红（exit 1）逐项点名；planned_key 撞
  既有 bib key → 红；落点节不存在 → 红；逐条齐且不撞 → exit 0。
* **search**：候选元数据落盘带 sha256；候选与既有 bib/todo 同 DOI 标「重复」
  且不给采纳号；网络失败（超时／无网／HTTP 错）显式报错，不静默放行、
  不拿假数据顶上。

网络面**不打真网**：全部用本地假响应（patch `urllib.request.urlopen`）。
「只发查询词」的口径由 `test_search_request_carries_only_query` 把住。
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from factscribe import cli, refs                     # noqa: E402
from factscribe.config import ConfigError            # noqa: E402
from factscribe.constants import (EXIT_CONFIG, EXIT_OK,  # noqa: E402
                                  EXIT_RED, EXIT_YELLOW)

CONFIG_TOML = """schema = "factscribe-project/3.0"

[project]
name = "Refs Fixture"
root_tex = "main.tex"
facts = "facts"
bib = "refs.bib"
level = "l1"
"""

MAIN_TEX = """\\documentclass{article}
\\begin{document}
\\input{sections/01-intro.tex}
\\end{document}
"""

SECTION_TEX = """\\section{Introduction}
\\label{sec:intro}
Some text without numbers.
"""

RELATED_TEX = """\\section{Related Work}
\\label{sec:related}
Some related work text.
"""

BIB_CLEAN = """@article{smith2020,
  title     = {A Study of Things},
  author    = {Smith, John and Doe, Jane},
  year      = {2020},
  doi       = {10.1000/xyz123}
}

@misc{chen2021,
  title        = {Another Study},
  author       = {Chen, Li},
  year         = {2021},
  eprint       = {2101.00001},
  archivePrefix = {arXiv}
}

@misc{software_repo,
  title = {A Software Repository},
  url   = {https://github.com/example/repo},
  year  = {2024}
}
"""

# 两条不同 key 挂同一 DOI（变异注入用）。
BIB_DUP_DOI = BIB_CLEAN.replace(
    "eprint       = {2101.00001}", "doi          = {10.1000/xyz123}")

TODO_FULL = """[[ref]]
slug = "paklina_2026"
title = "LLM-assisted writing and citation advantage"
authors = ["Sofia Paklina", "Petr Parshakov"]
year = "2026"
venue_or_id = "doi:10.1007/s11192-026-05805-9"
planned_key = "paklina2026"
section = "02_related.tex"
"""

TODO_MISSING = """[[ref]]
slug = "half_entry"
title = "Only a title here"
"""

CROSSREF_FIXTURE = json.dumps({
    "status": "ok",
    "message": {
        "items": [
            {
                "DOI": "10.1000/xyz123",
                "title": ["A Study of Things"],
                "author": [{"given": "John", "family": "Smith"},
                           {"given": "Jane", "family": "Doe"}],
                "issued": {"date-parts": [[2020, 5, 1]]},
                "container-title": ["Journal of Things"],
            },
            {
                "DOI": "10.5555/paklina2026",
                "title": ["LLM-assisted writing and citation advantage"],
                "author": [{"given": "Sofia", "family": "Paklina"}],
                "issued": {"date-parts": [[2026]]},
                "container-title": ["Scientometrics"],
            },
            {
                "DOI": "10.5555/third2025",
                "title": ["A Third Work"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "issued": {"date-parts": [[2025]]},
                "container-title": [],
            },
        ]
    },
}).encode("utf-8")

ARXIV_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2406.07016v2</id>
    <title>Delving into LLM-assisted writing</title>
    <published>2024-06-10T12:00:00Z</published>
    <author><name>Dmitry Kobak</name></author>
    <author><name>Rita Gonzalez-Marquez</name></author>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2604.05018v1</id>
    <title>PaperOrchestra</title>
    <published>2026-04-05T12:00:00Z</published>
    <arxiv:doi>10.5555/orchestra2026</arxiv:doi>
    <author><name>Yihao Luo</name></author>
  </entry>
</feed>
"""


class FakeResponse:
    """假的 urlopen 响应（够 refs.py 的 `with ... as resp` 用）。"""

    def __init__(self, payload: bytes, status: int = 200):
        self.payload = payload
        self.status = status

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(payload: bytes, status: int = 200):
    """造一个 patch `urllib.request.urlopen` 的替身，并把请求记下来。"""
    seen: list = []

    def _open(req, timeout=None):
        seen.append({"url": req.full_url, "headers": dict(req.headers),
                     "timeout": timeout})
        return FakeResponse(payload, status)

    return _open, seen


def make_project(root: Path, *, bib: str = BIB_CLEAN,
                 todo: str | None = None) -> Path:
    """造一个最小项目（够 refs 三个子命令读，不求能编译）。"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "factscribe.toml").write_text(CONFIG_TOML, encoding="utf-8")
    (root / "main.tex").write_text(MAIN_TEX, encoding="utf-8")
    (root / "refs.bib").write_text(bib, encoding="utf-8")
    (root / "facts").mkdir(exist_ok=True)
    (root / "sections").mkdir(exist_ok=True)
    (root / "sections" / "01-intro.tex").write_text(SECTION_TEX, encoding="utf-8")
    (root / "sections" / "02_related.tex").write_text(RELATED_TEX, encoding="utf-8")
    if todo is not None:
        (root / "refs").mkdir(exist_ok=True)
        (root / "refs" / "todo.toml").write_text(todo, encoding="utf-8")
    return root


def run_cli(*argv) -> tuple:
    """进程内跑 factscribe CLI：返回 (退出码, stdout, stderr)。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class RefsFixture(unittest.TestCase):
    """基类：每个用例一个临时项目。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def project(self, **kw) -> Path:
        return make_project(self.tmp / "paper", **kw)


# ==========================================================================
# dedupe
# ==========================================================================

class TestDedupe(RefsFixture):
    """跨条目同唯一键 → 黄（exit 3）逐条点名；干净 → exit 0。"""

    def test_clean_bib_has_no_dup_exit_ok(self):
        """正例：三条互不重复的条目 → 零重复、exit 0。"""
        project = self.project()
        result = refs.dedupe(project)
        self.assertEqual(result.dup_count, 0)
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.total, 3)
        self.assertEqual(result.keyed, 2)      # 第三条只有 url，缺唯一键
        self.assertEqual(len(result.unkeyed), 1)
        self.assertEqual(result.unkeyed[0]["key"], "software_repo")

    def test_same_doi_two_keys_is_dup_yellow(self):
        """负例：两条不同 key 挂同一 DOI → 黄，逐条点名。"""
        project = self.project(bib=BIB_DUP_DOI)
        result = refs.dedupe(project)
        self.assertEqual(result.exit_code, EXIT_YELLOW)
        self.assertEqual(result.dup_count, 1)
        group = result.groups[0]
        self.assertEqual(group.code, "REF_DUP_ID")
        self.assertEqual(group.id_kind, "doi")
        self.assertEqual(group.id_value, "10.1000/xyz123")
        self.assertEqual(sorted(group.keys), ["chen2021", "smith2020"])
        self.assertEqual(group.pairs, [["smith2020", "chen2021"]])
        for detail in group.detail:
            self.assertEqual(detail["file"], "refs.bib")
            self.assertGreater(detail["line"], 0)

    def test_same_arxiv_id_is_dup(self):
        """负例：同 arXiv id 两条也是重复。"""
        bib = BIB_CLEAN.replace("10.1000/xyz123", "10.1000/other456")
        bib = bib.replace("eprint       = {2101.00001}", "eprint       = {2406.07016}")
        bib = bib + """
@misc{dupe_arxiv,
  title  = {Yet Another Study},
  year   = {2021},
  eprint = {2406.07016}
}
"""
        project = self.project(bib=bib)
        result = refs.dedupe(project)
        self.assertEqual(result.exit_code, EXIT_YELLOW)
        self.assertEqual(result.dup_count, 1)
        self.assertEqual(result.groups[0].id_kind, "arxiv")
        self.assertEqual(sorted(result.groups[0].keys),
                         ["chen2021", "dupe_arxiv"])

    def test_doi_prefix_variants_are_same_key(self):
        """归一化：`https://doi.org/` 与 `doi:` 前缀、大小写差异不判漏。"""
        bib = BIB_CLEAN.replace("doi       = {10.1000/xyz123}",
                                "doi       = {https://doi.org/10.1000/XYZ123}")
        bib = bib.replace("eprint       = {2101.00001}",
                          "doi          = {doi:10.1000/xyz123}")
        project = self.project(bib=bib)
        result = refs.dedupe(project)
        self.assertEqual(result.exit_code, EXIT_YELLOW)
        self.assertEqual(result.dup_count, 1)
        self.assertEqual(result.groups[0].id_value, "10.1000/xyz123")

    def test_arxiv_version_variants_are_same_paper(self):
        """负例：同 id 不同版本号是同一篇文献的两条假名 → 判重。"""
        bib = BIB_CLEAN + """
@misc{chen2021_v2,
  title  = {Another Study, second version},
  year   = {2021},
  eprint = {2101.00001v3}
}
"""
        project = self.project(bib=bib)
        result = refs.dedupe(project)
        self.assertEqual(result.exit_code, EXIT_YELLOW)
        self.assertEqual(result.dup_count, 1)
        self.assertEqual(result.groups[0].id_kind, "arxiv")
        self.assertEqual(result.groups[0].id_value, "2101.00001")
        self.assertEqual(sorted(result.groups[0].keys),
                         ["chen2021", "chen2021_v2"])

    def test_missing_unique_key_is_listed_not_red(self):
        """缺唯一键的条目只列清单，不判红（不改退出码）。"""
        project = self.project()
        result = refs.dedupe(project)
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual([u["key"] for u in result.unkeyed], ["software_repo"])

    def test_crossref_inherited_id_is_not_dup(self):
        """正例：父子条目靠 crossref 继承同一 DOI 是 BibTeX 正常用法。"""
        bib = BIB_CLEAN + """
@inproceedings{child_entry,
  title    = {A Chapter of A Study of Things},
  crossref = {smith2020},
  year     = {2021}
}
"""
        project = self.project(bib=bib)
        result = refs.dedupe(project)
        self.assertEqual(result.dup_count, 0)
        self.assertEqual(result.exit_code, EXIT_OK)

    def test_dedupe_cli_json_payload(self):
        """CLI --json：冲突 key 对与文件行号在 payload 里。"""
        project = self.project(bib=BIB_DUP_DOI)
        code, out, _err = run_cli("refs", "dedupe", str(project), "--json")
        self.assertEqual(code, EXIT_YELLOW)
        payload = json.loads(out)
        self.assertEqual(payload["command"], "refs-dedupe")
        self.assertEqual(payload["exit"], EXIT_YELLOW)
        self.assertEqual(payload["severity"], "yellow")
        finding = payload["findings"][0]
        self.assertEqual(finding["code"], "REF_DUP_ID")
        self.assertEqual(sorted(finding["keys"]), ["chen2021", "smith2020"])
        self.assertEqual(finding["pairs"], [["smith2020", "chen2021"]])
        self.assertEqual(finding["entries"][0]["file"], "refs.bib")

    def test_dedupe_cli_exit_ok_on_clean(self):
        """CLI 干净 bib → exit 0。"""
        project = self.project()
        code, out, _err = run_cli("refs", "dedupe", str(project))
        self.assertEqual(code, EXIT_OK)
        self.assertIn("零重复", out)

    def test_dedupe_missing_project_is_config_error(self):
        """结构错 → exit 2（不静默放行）。"""
        code, _out, err = run_cli("refs", "dedupe", str(self.tmp / "nope"))
        self.assertEqual(code, EXIT_CONFIG)
        self.assertTrue(err.strip())


# ==========================================================================
# register
# ==========================================================================

class TestRegister(RefsFixture):
    """待补登记表逐项核对。"""

    def test_full_entry_exit_ok(self):
        """正例：七字段齐、key 不撞、落点节在 → exit 0。"""
        project = self.project(todo=TODO_FULL)
        result = refs.register(project)
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.complete, 1)
        self.assertEqual(result.entries[0].missing, [])
        self.assertEqual(result.entries[0].problems, [])

    def test_missing_fields_named_one_by_one(self):
        """负例：缺字段逐项点名（不只报「不齐」）。"""
        project = self.project(todo=TODO_MISSING)
        result = refs.register(project)
        self.assertEqual(result.exit_code, EXIT_RED)
        entry = result.entries[0]
        self.assertEqual(entry.missing, ["authors", "year", "venue_or_id",
                                         "planned_key", "section"])
        codes = [f["code"] for f in entry.findings()]
        self.assertIn("REF_TODO_MISSING_FIELD", codes)
        message = entry.findings()[0]["message"]
        for field in entry.missing:
            self.assertIn(field, message)

    def test_planned_key_collision_is_red(self):
        """负例：planned_key 撞既有 bib key → 红。"""
        todo = TODO_FULL.replace('planned_key = "paklina2026"',
                                 'planned_key = "smith2020"')
        project = self.project(todo=todo)
        result = refs.register(project)
        self.assertEqual(result.exit_code, EXIT_RED)
        codes = [p["code"] for p in result.entries[0].problems]
        self.assertIn("REF_TODO_KEY_COLLISION", codes)

    def test_missing_section_is_red(self):
        """负例：落点节不存在 → 红。"""
        todo = TODO_FULL.replace('section = "02_related.tex"',
                                 'section = "99_nowhere.tex"')
        project = self.project(todo=todo)
        result = refs.register(project)
        self.assertEqual(result.exit_code, EXIT_RED)
        codes = [p["code"] for p in result.entries[0].problems]
        self.assertIn("REF_TODO_SECTION_MISSING", codes)

    def test_section_may_be_given_as_stem(self):
        """正例：落点节写文件名干（`02_related`）也算找到。"""
        todo = TODO_FULL.replace('section = "02_related.tex"',
                                 'section = "02_related"')
        project = self.project(todo=todo)
        result = refs.register(project)
        self.assertEqual(result.exit_code, EXIT_OK)

    def test_section_not_in_closure_but_on_disk_is_found(self):
        """正例：还没接进 main.tex 的节，项目里有这个文件就算数。"""
        project = self.project(todo=TODO_FULL)
        result = refs.register(project)
        self.assertEqual(result.exit_code, EXIT_OK)

    def test_no_table_is_config_error(self):
        """没有登记表 → exit 2（可选文件不配不跑，但不静默放行）。"""
        project = self.project()
        code, _out, err = run_cli("refs", "register", str(project))
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("refs/todo.toml", err)

    def test_broken_table_is_config_error(self):
        """登记表坏 → exit 2。"""
        project = self.project(todo="[[ref]\nslug = broken\n")
        code, _out, err = run_cli("refs", "register", str(project))
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("refs/todo.toml", err)

    def test_register_cli_json_names_missing_fields(self):
        """CLI --json：缺字段逐项在 findings 里点名。"""
        project = self.project(todo=TODO_MISSING)
        code, out, _err = run_cli("refs", "register", str(project), "--json")
        self.assertEqual(code, EXIT_RED)
        payload = json.loads(out)
        self.assertEqual(payload["command"], "refs-register")
        self.assertEqual(payload["severity"], "red")
        finding = payload["findings"][0]
        self.assertEqual(finding["code"], "REF_TODO_MISSING_FIELD")
        self.assertEqual(finding["missing_fields"],
                         ["authors", "year", "venue_or_id", "planned_key",
                          "section"])

    def test_authors_accepts_plain_string(self):
        """正例：作者写成字符串也认（表里两种写法都收）。"""
        todo = TODO_FULL.replace(
            'authors = ["Sofia Paklina", "Petr Parshakov"]',
            'authors = "Sofia Paklina; Petr Parshakov"')
        project = self.project(todo=todo)
        result = refs.register(project)
        self.assertEqual(result.exit_code, EXIT_OK)


# ==========================================================================
# search（网络面：本地假响应，不打真网）
# ==========================================================================

class TestSearch(RefsFixture):
    """联网检索候选：落盘带 sha、查重标「重复」、失败显式报错。"""

    def test_candidates_parsed_and_saved_with_sha(self):
        """正例：候选元数据落盘，原始响应带 sha256（出处可查）。"""
        project = self.project()
        opener, seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("llm writing", project, source="crossref")
        self.assertEqual(result.exit_code, EXIT_OK)
        self.assertEqual(len(result.candidates), 3)
        first = result.candidates[0]
        self.assertEqual(first.title, "A Study of Things")
        self.assertEqual(first.authors, ["John Smith", "Jane Doe"])
        self.assertEqual(first.year, "2020")
        self.assertEqual(first.doi, "10.1000/xyz123")
        self.assertEqual(first.venue, "Journal of Things")
        # 原始响应落盘 + sha256 对得上
        self.assertTrue(result.raw_path.is_file())
        self.assertEqual(hashlib.sha256(result.raw_path.read_bytes()).hexdigest(),
                         result.raw_sha256)
        # 信封：出处（请求 URL）＋ 候选清单
        envelope = json.loads(result.envelope_path.read_text(encoding="utf-8"))
        self.assertEqual(envelope["raw_sha256"], result.raw_sha256)
        self.assertIn("query.bibliographic", envelope["request_url"])
        self.assertEqual(len(envelope["candidates"]), 3)
        self.assertEqual(len(seen), 1)

    def test_request_carries_only_query(self):
        """口径：只发查询词与标识——不发正文、不发本地路径。"""
        project = self.project()
        opener, seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            refs.search("llm writing", project, source="crossref")
        url = seen[0]["url"]
        self.assertIn("llm+writing", url)
        self.assertNotIn(str(project), url)
        self.assertNotIn("xyz123", url)          # bib 里的 DOI 不外发
        self.assertNotIn("A Study of Things", url)  # bib 题录不外发
        self.assertNotIn("refs.bib", url)
        self.assertIn("factscribe", seen[0]["headers"].get("User-agent", "")
                      .lower())

    def test_rows_capped_at_five(self):
        """礼貌面：单次查询条数上限 ≤5。"""
        project = self.project()
        opener, seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            refs.search("llm writing", project, source="crossref", rows=99)
        self.assertIn("rows=5", seen[0]["url"])

    def test_timeout_10s(self):
        """礼貌面：超时 10 秒。"""
        project = self.project()
        opener, seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            refs.search("llm writing", project, source="crossref")
        self.assertEqual(seen[0]["timeout"], 10.0)

    def test_candidate_dup_with_bib_gets_no_number(self):
        """查重面：候选与现有 bib 同 DOI → 标「重复」，不给采纳号。"""
        project = self.project()      # bib 里已有 doi 10.1000/xyz123
        opener, _seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("llm writing", project, source="crossref")
        dup = [c for c in result.candidates if c.duplicate]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].doi, "10.1000/xyz123")
        self.assertEqual(dup[0].number, 0)          # 不给采纳号
        self.assertIn("bib:smith2020", dup[0].duplicates)
        # 剩下的候选照给号，号从 1 起、连续
        numbers = [c.number for c in result.adoptable]
        self.assertEqual(numbers, [1, 2])

    def test_candidate_dup_with_todo_gets_no_number(self):
        """查重面：候选与登记表同 DOI 也算重复。"""
        # bib 里不含候选的 DOI —— 撞的是登记表那一条。
        bib = BIB_CLEAN.replace("doi       = {10.1000/xyz123}",
                                "doi       = {10.1000/other456}")
        todo = TODO_FULL.replace("doi:10.1007/s11192-026-05805-9",
                                 "doi:10.5555/paklina2026")
        project = self.project(bib=bib, todo=todo)
        opener, _seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("llm writing", project, source="crossref")
        dup = [c for c in result.candidates if c.duplicate]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].doi, "10.5555/paklina2026")
        self.assertEqual(dup[0].number, 0)          # 不给采纳号
        self.assertIn("todo:paklina_2026", dup[0].duplicates)

    def test_partial_date_parts_yields_empty_year_not_none(self):
        """正例：Crossref 的 date-parts 带空位 → 年份留空，不出「None」。"""
        payload = json.dumps({
            "message": {"items": [{
                "DOI": "10.5555/partial2026",
                "title": ["Partially Dated Work"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "issued": {"date-parts": [[2026, None, None]]},
                "container-title": [],
            }]}
        }).encode("utf-8")
        project = self.project()
        opener, _seen = fake_urlopen(payload)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("partial", project, source="crossref")
        self.assertEqual(result.candidates[0].year, "2026")
        payload = json.dumps({
            "message": {"items": [{
                "DOI": "10.5555/nodate2026",
                "title": ["Undated Work"],
                "author": [{"given": "Ada", "family": "Lovelace"}],
                "issued": {"date-parts": [[None]]},
                "container-title": [],
            }]}
        }).encode("utf-8")
        opener, _seen = fake_urlopen(payload)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("nodate", project, source="crossref")
        self.assertEqual(result.candidates[0].year, "")

    def test_arxiv_fixture_parsed(self):
        """正例：arXiv Atom 响应解析（id 去版本号、作者、DOI）。"""
        project = self.project()
        opener, _seen = fake_urlopen(ARXIV_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("llm writing", project, source="arxiv")
        self.assertEqual(len(result.candidates), 2)
        first = result.candidates[0]
        self.assertEqual(first.arxiv_id, "2406.07016")   # 版本号已去
        self.assertEqual(first.year, "2024")
        self.assertEqual(first.authors,
                         ["Dmitry Kobak", "Rita Gonzalez-Marquez"])
        second = result.candidates[1]
        self.assertEqual(second.arxiv_id, "2604.05018")
        self.assertEqual(second.doi, "10.5555/orchestra2026")
        self.assertTrue(result.raw_path.name.endswith(".raw.xml"))

    def test_pick_writes_complete_entry_to_table(self):
        """检索链路：--pick 把候选写进登记表（七字段齐，仍非正式 bib）。"""
        project = self.project()
        opener, _seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("llm writing", project, source="crossref")
        # 第一条候选与 bib 同 DOI → 重复、无采纳号；采纳号 1 是 Paklina 那条。
        self.assertEqual(result.duplicated[0].doi, "10.1000/xyz123")
        pick = refs.pick_candidate(result, 1, planned_key="paklina2026",
                                   section="02_related.tex")
        self.assertEqual(pick["slug"], "paklina_2026")
        self.assertEqual(pick["venue_or_id"], "doi:10.5555/paklina2026")
        table = project / "refs" / "todo.toml"
        self.assertTrue(table.is_file())
        text = table.read_text(encoding="utf-8")
        for field in ("slug", "title", "authors", "year", "venue_or_id",
                      "planned_key", "section"):
            self.assertIn(field, text)
        self.assertIn("paklina2026", text)
        # 入表后逐条齐 → register exit 0
        self.assertEqual(refs.register(project).exit_code, EXIT_OK)
        # 机器不代签：正式 refs.bib 一个字没动
        self.assertEqual((project / "refs.bib").read_text(encoding="utf-8"),
                         BIB_CLEAN)

    def test_pick_duplicate_candidate_is_refused(self):
        """查重面：重复候选没有采纳号，挑不动。"""
        project = self.project()
        opener, _seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            result = refs.search("llm writing", project, source="crossref")
        with self.assertRaises(ConfigError) as ctx:
            refs.pick_candidate(result, 99)
        self.assertEqual(ctx.exception.code, "REF_PICK_INVALID")

    def test_network_timeout_explicit_error(self):
        """网络失败：超时 → 显式报错（exit 2），不静默放行。"""
        project = self.project()

        def _boom(req, timeout=None):
            raise TimeoutError("timed out")

        with mock.patch.object(urllib.request, "urlopen", _boom):
            code, _out, err = run_cli("refs", "search", "llm writing",
                                      "--project", str(project))
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("超时", err)
        self.assertIn("不取假数据", err)

    def test_network_unreachable_explicit_error(self):
        """网络失败：无网 → 显式报错（exit 2）。"""
        project = self.project()

        def _boom(req, timeout=None):
            raise urllib.error.URLError("Name or service not known")

        with mock.patch.object(urllib.request, "urlopen", _boom):
            code, _out, err = run_cli("refs", "search", "llm writing",
                                      "--project", str(project))
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("无网", err)

    def test_network_http_error_explicit_error(self):
        """网络失败：HTTP 错 → 显式报错（exit 2），消息里带状态码。"""
        project = self.project()

        def _boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 503, "Service Unavailable",
                                         None, None)

        with mock.patch.object(urllib.request, "urlopen", _boom):
            code, _out, err = run_cli("refs", "search", "llm writing",
                                      "--project", str(project))
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("HTTP 503", err)

    def test_bad_payload_explicit_error(self):
        """响应解析不了 → 显式报错，不拿半截数据顶上。"""
        project = self.project()
        opener, _seen = fake_urlopen(b"<html>not json</html>")
        with mock.patch.object(urllib.request, "urlopen", opener):
            code, _out, err = run_cli("refs", "search", "llm writing",
                                      "--project", str(project))
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("JSON", err)

    def test_search_json_payload(self):
        """CLI --json：候选清单与出处都在 payload 里。"""
        project = self.project()
        opener, _seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            code, out, _err = run_cli("refs", "search", "llm writing",
                                      "--project", str(project), "--json")
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["command"], "refs-search")
        self.assertEqual(payload["summary"]["candidates"], 3)
        self.assertEqual(payload["summary"]["duplicated"], 1)
        self.assertEqual(len(payload["candidates"]), 3)
        self.assertTrue(payload["summary"]["raw_sha256"])


# ==========================================================================
# 离线身份不变（默认零网络）
# ==========================================================================

class TestOfflineIdentity(RefsFixture):
    """除 `refs search` 外，refs 命令族一律零网络。"""

    def test_dedupe_and_register_never_touch_network(self):
        project = self.project(todo=TODO_FULL)

        def _boom(*args, **kwargs):
            raise AssertionError("离线命令不许联网")

        with mock.patch.object(urllib.request, "urlopen", _boom):
            self.assertEqual(refs.dedupe(project).exit_code, EXIT_OK)
            self.assertEqual(refs.register(project).exit_code, EXIT_OK)

    def test_register_pick_from_latest_writes_entry(self):
        """register --pick：从最近一次检索的候选里挑一条写进登记表。"""
        project = self.project()
        opener, _seen = fake_urlopen(CROSSREF_FIXTURE)
        with mock.patch.object(urllib.request, "urlopen", opener):
            refs.search("llm writing", project, source="crossref")
        code, out, _err = run_cli("refs", "register", str(project),
                                  "--pick", "1", "--key", "paklina2026",
                                  "--section", "02_related.tex", "--json")
        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["picked"]["planned_key"], "paklina2026")
        self.assertEqual(payload["picked"]["slug"], "paklina_2026")
        self.assertEqual(payload["summary"]["complete"], 1)

    def test_register_pick_without_candidates_is_config_error(self):
        """没有候选文件 → exit 2（不是静默成功）。"""
        project = self.project(todo=TODO_FULL)
        code, _out, err = run_cli("refs", "register", str(project), "--pick", "1")
        self.assertEqual(code, EXIT_CONFIG)
        self.assertIn("refs/candidates", err)


# ==========================================================================
# 端到端（子进程）
# ==========================================================================

class TestEndToEnd(RefsFixture):
    """真子进程跑一遍（确认 argparse 挂载与退出码）。"""

    def run_cli(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        return subprocess.run(
            [sys.executable, "-m", "factscribe", *args],
            cwd=str(ROOT), env=env, capture_output=True, text=True)

    def test_dedupe_exit_codes(self):
        project = self.project()
        clean = self.run_cli("refs", "dedupe", str(project))
        self.assertEqual(clean.returncode, EXIT_OK)
        dup = self.run_cli("refs", "dedupe", str(self.project(bib=BIB_DUP_DOI)))
        self.assertEqual(dup.returncode, EXIT_YELLOW)
        self.assertIn("REF_DUP_ID", dup.stdout)
        self.assertIn("smith2020", dup.stdout)
        self.assertIn("chen2021", dup.stdout)

    def test_register_exit_codes(self):
        project = self.project(todo=TODO_FULL)
        ok = self.run_cli("refs", "register", str(project))
        self.assertEqual(ok.returncode, EXIT_OK)
        bad = self.run_cli("refs", "register", str(self.project(todo=TODO_MISSING)))
        self.assertEqual(bad.returncode, EXIT_RED)
        self.assertIn("缺字段", bad.stdout)

    def test_help_lists_three_actions(self):
        out = self.run_cli("refs", "--help")
        self.assertEqual(out.returncode, 0)
        for action in ("dedupe", "register", "search"):
            self.assertIn(action, out.stdout)


if __name__ == "__main__":
    unittest.main()
