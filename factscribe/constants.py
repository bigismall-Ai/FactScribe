# -*- coding: utf-8 -*-
"""版本号、退出码分层与严重级别常量。"""
from __future__ import annotations

VERSION = "1.3.0"
SCHEMA_VERSION = "1.0"

CONFIDENCE_OK = {"high", "med", "low"}
KINDS_OK = {"claim", "config"}

# 退出码分层（SPEC-V1 §5）
EXIT_OK = 0        # 绿：完整覆盖且无红无黄
EXIT_RED = 1       # 红：违例（编造/不自洽/账坏）
EXIT_CONFIG = 2    # 配置或用法错（工具没跑起来）
EXIT_YELLOW = 3    # 黄：跑完了但有「未核验/未绑定/未签名/冲突」，不判死但必须列
EXIT_INTERNAL = 4  # 工具内部错误（异常）
EXIT_INTEGRITY = 5 # 覆盖缺口 / PDF 与签名信任链失败（V3.0）
EXIT_STALE = 7     # 报告/PDF 过期、nonce 重放
EXIT_MISSING = 8   # 必需工具缺失（PDF 工具链）——不许静默放行

SEV_RED = "red"
SEV_YELLOW = "yellow"
SEV_INFO = "info"
