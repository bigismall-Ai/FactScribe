# -*- coding: utf-8 -*-
"""核验槽（check slot）：注册表＋[checks] 解析＋发现汇总＋退出码折算。

SPEC-CHECKS-draft（docs/design/SPEC-CHECKS-draft.md）§2.2：core 新增且仅新增
一个机构＝核验槽。槽只做四件事——①点名 ②收发现 ③折算退出码 ④出报告；
一切领域判据都在核验包里，core 不为任何具体领域保留判据代码。
paper（论文三闸，判据在 audit.py）是第一个注册进槽的核验包；legal（M2）是第二个。

宪法纪律（本模块是宪法面，改动＝修约）：

- **退出码值永不变**：折算只认 SPEC-V3.0 §2.5 唯一权威表的值↔语义配对
  （全闭集 0/1/2/3/4/5/6/7/8/9，见 constants.py）；包只报 findings，
  不产生退出码。
- **无 `[checks]` 节＝槽不启用**：audit 行为与槽引入前逐字节一致
  （§5.2 兼容承诺；实现模式照 `[budget]`/`[evidence]` 先例：节不出现＝
  判据不跑、行为与之前完全一致）。节存在但省 `packages` 同无节；
  显式点名 `packages` 才走槽。
- **确定性**：同一输入字节 ⇒ 同一 findings 字节；槽不读系统钟、不联网、
  不写盘（零 LLM，沿用 SPEC.md §5 硬性要求）。

包契约（§3.1 注册卡五样的代码面）：`domain_id`（全局唯一小写）、
冻结码表（在 docs/design/SPEC-V3.0.md §8 总表）、config 节名
`[checks.<domain_id>]`（键集由卡声明）、材料依赖声明（卡上写明，
材料缺失必须 fail-closed）、`verify() → findings`（纯函数）。
M1 的包结果协议 v1：`verify(cfg, facts, sections, resolve=False) →
(red, yellow, hints, summary, unresolved)`——与 `audit.run_audit` 的
返回形一致；M2 的 legal 挂槽时按同一协议收敛（判据与码表零改动）。

注册形态（裁定⑧「核验包入仓注册形态」）：core 自带域的卡在本模块
`register_builtins()`；外来域包走 `integrations/<pkg>/` 入仓注册、
调 `register_package()` 挂卡（先例：minifactscribe、factscribe-legal）。

冻结锁（裁定⑨「每域一把冻结锁」）：`evidence_lock_path()`——内建 paper
域沿用既有 `audit/evidence.lock`（既有冻结件字节不破坏，canonical 形态
一个字节不改）；其他域用 `audit/evidence-<domain>.lock`（§6 第 2 条）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import Config, ConfigError, _config_warn

# --------------------------------------------------------------------------
# 退出码全闭集（裁定②：全闭集入宪表述；值↔语义配对以 SPEC-V3.0 §2.5
# 为唯一权威表，永不变化）。constants.py 只列了本仓当前折算会用到的值；
# 这里把闭集整表列出供槽与核验包对照——新增退出码＝修约（major）。
# --------------------------------------------------------------------------

EXIT_CODE_CLOSED_SET = {
    0: "PASS／UNVERIFIED（不阻断）",
    1: "RED(FACT)：源层违例",
    2: "RED(CONFIG)：配置、用法、工具缺失",
    3: "ADVISORY：仅黄",
    4: "RED(INTERNAL)：异常、两份实现漂移",
    5: "RED(COVERAGE|INTEGRITY)：覆盖缺口、PDF/stamp 信任链失败",
    6: "RED(PROOF)：--require-proof 未达标",
    7: "RED(STALE|REPLAY)：报告/PDF 过期、nonce 重放",
    8: "UNVERIFIED（阻断）：--gate/--ci 下 level < L2、必需工具缺失",
    9: "RED(ATTACK_OPEN)：ATTACKS.md 有 blocking/open 条目",
}

# --------------------------------------------------------------------------
# 退出码折算（槽第 3 件事）。逻辑自 audit.py 原样迁入（audit 模块以旧名
# `_aggregate_exit` 再导出，调用方零改动）；折算规则一字不改，值永不变化。
# --------------------------------------------------------------------------


def aggregate_exit(red, yellow, strict: bool = False,
                   integrity_first: bool = False) -> int:
    """红黄发现 → 退出码。包不产生退出码，折算只在这里发生。"""
    if red:
        codes = {i.exit_code for i in red}
        if integrity_first and 5 in codes:
            return 5
        for code in (8, 1, 5, 7):
            if code in codes:
                return code
        return 1
    if yellow:
        return 1 if strict else 3
    return 0


# --------------------------------------------------------------------------
# 发现的域标（信封 §3.2 的 domain 键）：只在槽路径（显式 [checks] 点名）出现，
# 缺省路径不带域标——金样例逐字节锁的前提。
# --------------------------------------------------------------------------


class DomainIssue:
    """包一层既有 Issue、加域标的发现：as_dict 时前置 `domain` 键。

    只增键不改名不删键（§8.1 判定表：非 BREAKING）；旧消费者按
    「新增键忽略」口径不受影响。其余属性透传给被包的 Issue，
    折算（exit_code）与人读渲染（code/location/…）零感知。
    """

    def __init__(self, domain: str, issue):
        self.domain = domain
        self.issue = issue

    @property
    def exit_code(self) -> int:
        return self.issue.exit_code

    def as_dict(self) -> dict:
        d = {"domain": self.domain}
        d.update(self.issue.as_dict())
        return d

    def __getattr__(self, name):
        # 常规属性找不到才走这里；issue 自身缺失时别递归。
        if name == "issue":
            raise AttributeError(name)
        return getattr(self.__dict__["issue"], name)


# --------------------------------------------------------------------------
# 核验包注册卡与注册表（槽第 1 件事：点名的前提）
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckPackage:
    """核验包注册卡（SPEC-CHECKS §3.1 一张卡写死五样的代码面）。

    verify 的 M1 协议（包结果协议 v1）：
        verify(cfg, facts, sections, resolve=False)
            -> (red, yellow, hints, summary, unresolved)
    summary 是该包的信封 summary（dict）；槽只在单包时原样采用并追加
    `by_domain`（多包 summary 的合并语义是 M2 的卡上契约，本批不定义）。
    """

    domain_id: str
    verify: Callable
    config_keys: frozenset = frozenset()   # [checks.<domain>] 认识的键集
    description: str = ""

    def __post_init__(self):
        bad = [ch for ch in self.domain_id if ch not in
               "abcdefghijklmnopqrstuvwxyz0123456789-"]
        if not self.domain_id or bad:
            raise ConfigError(
                "核验包 domain_id %r 不合法：必须是 [a-z0-9-] 的小写 id"
                "（全局唯一，即配置节名 [checks.<domain_id>] 与码表命名空间）"
                % self.domain_id)


# 注册表：domain_id → 卡。槽要求全局唯一；重复注册＝修约级错误。
_REGISTRY: dict[str, CheckPackage] = {}
_BUILTINS_DONE = False

# 缺省包（裁定③：[checks] 缺省只跑 paper）。
DEFAULT_DOMAIN = "paper"


def register_package(pkg: CheckPackage) -> None:
    """把一张核验包卡挂进槽。domain_id 全局唯一，重复注册即报错。"""
    if pkg.domain_id in _REGISTRY:
        raise ConfigError(
            "核验包 %r 重复注册——槽要求 domain_id 全局唯一" % pkg.domain_id)
    _REGISTRY[pkg.domain_id] = pkg


def get_package(domain_id: str) -> CheckPackage | None:
    return _REGISTRY.get(domain_id)


def registered_domains() -> list[str]:
    return sorted(_REGISTRY)


def register_builtins() -> None:
    """注册 core 自带核验包（paper）。幂等；惰性导入避免 checks↔audit 环。

    paper 的判据代码物理位置仍在 audit.py（M1 以最小搬动为准）：卡在这
    里，verify 指向 run_audit——G1 数字绑定／G2 源头锚定／G3 引用对账
    三闸（SPEC-V1 §4）连同 run_audit 内的源层判据，从本卡起是 paper 包
    的实现细节。风格 G5–G7 与 PDF 回检层维持 core 现状直跑（第二批，
    裁定⑤）。
    """
    global _BUILTINS_DONE
    if _BUILTINS_DONE:
        return
    register_package(CheckPackage(
        domain_id=DEFAULT_DOMAIN,
        verify=_paper_verify,
        config_keys=frozenset(),   # 本批 paper 节没有键；写了即告警
        description="论文三闸：G1 数字绑定／G2 源头锚定／G3 引用对账"
                    "（SPEC-V1 §4；判据在 audit.run_audit）",
    ))
    _BUILTINS_DONE = True


def _paper_verify(cfg: Config, facts, sections, resolve: bool = False):
    from .audit import run_audit
    return run_audit(cfg, facts, sections, resolve=resolve)


# --------------------------------------------------------------------------
# 点名（槽第 1 件事）＋域节键集校验
# --------------------------------------------------------------------------


def resolve_packages(cfg: Config) -> list[CheckPackage]:
    """按 `[checks]` 配置点名本次要跑的核验包。

    - 缺省（无 [checks]，或节存在但省 `packages`）⇒ 只跑 paper（裁定③）；
    - `packages` 点了未注册的 id ⇒ exit 2（CONFIG），点名该 id 与已注册域
      清单（§5.2）；
    - `[checks.<domain>]` 键集错误 ⇒ CONFIG_UNKNOWN_FIELD 告警（info），
      不改退出码；未注册域的节同样告警并忽略（§5.2）。
    """
    register_builtins()
    wanted = list(cfg.checks_packages) if cfg.checks_packages \
        else [DEFAULT_DOMAIN]
    packages: list[CheckPackage] = []
    for pid in wanted:
        pkg = _REGISTRY.get(pid)
        if pkg is None:
            raise ConfigError(
                "[checks].packages 点名的核验包 %r 未注册（已注册：%s）——"
                "先注册进槽才能点名（SPEC-CHECKS §5.2）"
                % (pid, "、".join(registered_domains()) or "无"))
        packages.append(pkg)
    for domain, table in sorted((cfg.checks_tables or {}).items()):
        pkg = _REGISTRY.get(domain)
        if pkg is None:
            _config_warn(
                cfg, "CONFIG_UNKNOWN_FIELD",
                "[checks.%s] 的域未注册——该节已忽略（已注册：%s）"
                % (domain, "、".join(registered_domains())),
                field=domain, location="factscribe.toml [checks.%s]" % domain)
            continue
        for key in sorted(table):
            if key in pkg.config_keys:
                continue
            _config_warn(
                cfg, "CONFIG_UNKNOWN_FIELD",
                "[checks.%s] 的键 %r 不在 %s 包的契约里——已忽略"
                "（也不参与任何判据）" % (domain, key, domain),
                field=str(key), location="factscribe.toml [checks.%s]" % domain)
    return packages


# --------------------------------------------------------------------------
# 收发现＋出报告（槽第 2/4 件事）：跑点名包、加域标、按域计数、收拢信封
# --------------------------------------------------------------------------


def run_packages(cfg: Config, facts, sections, resolve: bool = False):
    """跑 `[checks]` 点名的全部核验包，返回信封五元组。

    返回形与 `audit.run_audit` 一致：(red, yellow, hints, summary,
    unresolved)，调用方（cli.cmd_audit）零学习成本。差异只有两处、都
    只发生在槽路径：每条发现多 `domain` 键（DomainIssue.as_dict），
    summary 末尾多 `by_domain` 计数（§3.2 只增键）。
    """
    packages = resolve_packages(cfg)
    red, yellow, hints = [], [], []
    unresolved: list = []
    by_domain: dict[str, dict] = {}
    summary: dict | None = None
    for pkg in packages:
        p_red, p_yellow, p_hints, p_summary, p_unresolved = pkg.verify(
            cfg, facts, sections, resolve=resolve)
        red += [DomainIssue(pkg.domain_id, i) for i in p_red]
        yellow += [DomainIssue(pkg.domain_id, i) for i in p_yellow]
        hints += [DomainIssue(pkg.domain_id, i) for i in p_hints]
        unresolved += list(p_unresolved)
        by_domain[pkg.domain_id] = {"red": len(p_red), "yellow": len(p_yellow),
                                    "hints": len(p_hints)}
        if summary is None:
            summary = dict(p_summary)
        # 多包时其余包的 summary 合并语义是 M2 的卡上契约（M1 只有单包）。
    if summary is not None:
        summary["by_domain"] = by_domain
    return red, yellow, hints, summary or {}, unresolved


# --------------------------------------------------------------------------
# 每域一把冻结锁（裁定⑨）：锁件路径的唯一权威函数
# --------------------------------------------------------------------------


def evidence_lock_path(root: Path, domain: str = "") -> Path:
    """域级冻结锁件路径：paper 沿用既有锁，其他域各用各的锁。

    - paper（或空串＝内建缺省域）⇒ `audit/evidence.lock`——既有冻结件的
      canonical 形态与路径一个字节都不改（§6 第 2 条；既有锁就是 paper
      域的锁）；
    - 其他域 ⇒ `audit/evidence-<domain>.lock`（M2 legal 起用；canonical
      形态由该域的卡写死）。
    """
    if domain == DEFAULT_DOMAIN or not domain:
        return root / "audit" / "evidence.lock"
    return root / "audit" / ("evidence-%s.lock" % domain)
